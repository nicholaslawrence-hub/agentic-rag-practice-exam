"""Chat routes — SSE streaming, thread CRUD, quota enforcement."""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import asdict
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.agent.graph import run_agent
from apps.api.agent.state import Attachment, Citation
from apps.api.auth import get_current_user
from apps.api.db.models import Message, Thread, UsageDaily, User, UserDocument
from apps.api.db.session import get_db
from apps.api.settings import settings

router = APIRouter(prefix="/chat", tags=["chat"])


class SendMessageRequest(BaseModel):
    thread_id: str | None = None  # omit to start a new thread
    course: str
    content: str


class ThreadOut(BaseModel):
    id: str
    course: str
    title: str
    created_at: datetime
    updated_at: datetime


async def _check_quota(user: User, db: AsyncSession) -> None:
    today = date.today()
    result = await db.execute(
        select(UsageDaily).where(UsageDaily.user_id == user.id, UsageDaily.date == today)
    )
    usage = result.scalar_one_or_none()
    if usage and usage.messages >= user.daily_quota:
        raise HTTPException(status_code=429, detail="Daily message quota reached")


async def _bump_usage(user: User, db: AsyncSession) -> None:
    today = date.today()
    result = await db.execute(
        select(UsageDaily).where(UsageDaily.user_id == user.id, UsageDaily.date == today)
    )
    usage = result.scalar_one_or_none()
    if usage is None:
        usage = UsageDaily(user_id=user.id, date=today, messages=0)
        db.add(usage)
    usage.messages += 1
    await db.commit()


async def _get_or_create_thread(
    thread_id: str | None, course: str, user: User, db: AsyncSession
) -> Thread:
    if thread_id:
        result = await db.execute(
            select(Thread).where(Thread.id == thread_id, Thread.user_id == user.id)
        )
        thread = result.scalar_one_or_none()
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")
        return thread

    thread = Thread(id=uuid.uuid4(), user_id=user.id, course=course, title="New chat")
    db.add(thread)
    await db.commit()
    await db.refresh(thread)
    return thread


async def _load_history(thread: Thread, db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(Message).where(Message.thread_id == thread.id).order_by(Message.created_at)
    )
    messages = result.scalars().all()
    return [{"role": m.role, "content": m.content} for m in messages]


def _to_json_list(items: list) -> list[dict]:
    result = []
    for item in items:
        if hasattr(item, "__dict__"):
            result.append({k: v for k, v in item.__dict__.items() if not k.startswith("_")})
        elif isinstance(item, dict):
            result.append(item)
    return result


@router.post("/send")
async def send_message(
    body: SendMessageRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _check_quota(user, db)
    thread = await _get_or_create_thread(body.thread_id, body.course, user, db)
    history = await _load_history(thread, db)
    history.append({"role": "user", "content": body.content})

    # Save user message
    user_msg = Message(
        id=uuid.uuid4(),
        thread_id=thread.id,
        role="user",
        content=body.content,
    )
    db.add(user_msg)
    await db.commit()

    async def event_stream():
        # Load user-uploaded documents for this thread
        ud_result = await db.execute(
            select(UserDocument).where(UserDocument.thread_id == thread.id)
        )
        user_doc_texts = [d.extracted_text for d in ud_result.scalars().all()]

        # Run agent in thread pool to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: run_agent(
                messages=history,
                course=body.course,
                user_id=str(user.id),
                user_doc_texts=user_doc_texts,
            ),
        )

        draft: str = result["draft"]
        citations: list = result["citations"]
        attachments: list = result.get("attachments", [])
        intent: str = result["intent"]

        # Stream tokens word-by-word (replace with Anthropic streaming in production)
        words = draft.split(" ")
        for i, word in enumerate(words):
            yield {"event": "token", "data": json.dumps({"text": word + (" " if i < len(words) - 1 else "")})}
            await asyncio.sleep(0)

        citations_json = _to_json_list(citations)
        attachments_json = _to_json_list(attachments)
        yield {
            "event": "done",
            "data": json.dumps({
                "thread_id": str(thread.id),
                "intent": intent,
                "attachments": attachments_json,
                "citations": citations_json,
            }),
        }

        # Persist AI message
        ai_msg = Message(
            id=uuid.uuid4(),
            thread_id=thread.id,
            role="assistant",
            content=draft,
            intent=intent,
            citations_json=citations_json,
        )
        db.add(ai_msg)

        # Update thread title from first user message if still default
        if thread.title == "New chat" and body.content:
            thread.title = body.content[:60]

        await db.commit()
        await _bump_usage(user, db)

    return EventSourceResponse(event_stream())


@router.get("/threads")
async def list_threads(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ThreadOut]:
    result = await db.execute(
        select(Thread)
        .where(Thread.user_id == user.id)
        .order_by(Thread.updated_at.desc())
        .limit(50)
    )
    threads = result.scalars().all()
    return [
        ThreadOut(
            id=str(t.id),
            course=t.course,
            title=t.title,
            created_at=t.created_at,
            updated_at=t.updated_at,
        )
        for t in threads
    ]


@router.get("/threads/{thread_id}/messages")
async def get_messages(
    thread_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    result = await db.execute(
        select(Thread).where(Thread.id == thread_id, Thread.user_id == user.id)
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    result = await db.execute(
        select(Message).where(Message.thread_id == thread_id).order_by(Message.created_at)
    )
    msgs = result.scalars().all()
    return [
        {
            "id": str(m.id),
            "role": m.role,
            "content": m.content,
            "intent": m.intent,
            "citations": m.citations_json or [],
            "created_at": m.created_at.isoformat(),
        }
        for m in msgs
    ]


@router.delete("/threads/{thread_id}", status_code=204)
async def delete_thread(
    thread_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        select(Thread).where(Thread.id == thread_id, Thread.user_id == user.id)
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    await db.delete(thread)
    await db.commit()
