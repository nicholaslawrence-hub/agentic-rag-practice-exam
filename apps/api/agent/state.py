"""Shared state for the MCB Tutor pipeline — dataclasses + LangGraph TypedDict."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypedDict


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    doc_type: str       # "slide" | "handout"
    source: str
    title: str
    score: float
    slide_num: int | None = None
    slide_image_url: str | None = None
    heading_path: str | None = None
    week: int | None = None
    topic: str | None = None


@dataclass
class Citation:
    source: str
    title: str
    doc_type: str
    slide_num: int | None
    slide_image_url: str | None
    heading_path: str | None


@dataclass
class Attachment:
    filename: str
    url: str            # relative API path, e.g. /static/exams/<id>.pdf
    mime_type: str = "application/pdf"
    label: str = "Download"
    preview_urls: list[str] = field(default_factory=list)


class AgentState(TypedDict, total=False):
    """LangGraph state — each field returned by a node replaces the prior value."""
    messages: list
    course: str
    user_id: str
    user_doc_texts: list[str]
    intent: str
    retrieved: list          # list[RetrievedChunk]
    draft: str
    citations: list
    attachments: list
    _pending_attachments: list
