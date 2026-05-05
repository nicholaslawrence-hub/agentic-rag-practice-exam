"""Agentic reranker node.

Haiku sees the initially retrieved chunks + the student's request, then:
  - can call `search` (max 3 times) to find additional relevant material
  - must call `finalize_ranking` to submit an ordered list of chunk IDs

Only runs for exam_config and cheatsheet_config intents.
"""

from __future__ import annotations

import json

from anthropic import Anthropic

from apps.api.agent.state import RetrievedChunk
from apps.api.agent.tools import FINALIZE_TOOL_SCHEMA, SEARCH_TOOL_SCHEMA, search

_client = Anthropic()

MAX_ROUNDS = 4      # includes the finalize call
MAX_CHUNKS = 16

_GENERATION_INTENTS = {"exam_config", "cheatsheet_config"}

_SYSTEM = """You are a retrieval specialist curating the best source material for generating \
exam study content (practice exams and cheatsheets).

You have two tools:
- search: query the course vector store for additional chunks if important topics are missing
- finalize_ranking: submit your final ordered list of chunk IDs (most → least relevant)

Process:
1. Review the initial chunks and the student's request
2. Identify any important topics that are missing or under-represented
3. Use search up to 3 times to find missing material
4. Call finalize_ranking with up to 16 chunk IDs ordered by relevance

Be selective — quality over quantity. Prefer chunks that directly address the requested topics."""


def rerank_node(state: dict) -> dict:
    intent = state.get("intent", "unknown")
    if intent not in _GENERATION_INTENTS:
        return {}

    retrieved: list[RetrievedChunk] = state.get("retrieved", [])
    course = state.get("course", "")
    messages = state.get("messages", [])
    last_user = next(
        (m.content for m in reversed(messages) if getattr(m, "type", None) == "human"), ""
    )

    # Build an ID-indexed map so we can look up chunks by ID throughout the loop
    chunk_map: dict[str, RetrievedChunk] = {c.chunk_id: c for c in retrieved}

    # Summarise initial chunks for the LLM
    summaries = [
        f"[{i}] id={c.chunk_id} score={c.score:.2f} {c.doc_type} | {c.source} | {c.title}\n"
        f"    {c.text[:160].replace(chr(10), ' ')}…"
        for i, c in enumerate(retrieved)
    ]
    chunks_str = "\n\n".join(summaries) if summaries else "No chunks retrieved."

    user_content = (
        f"Student request: {last_user}\n\n"
        f"Initially retrieved chunks ({len(retrieved)}):\n{chunks_str}\n\n"
        f"Select and rank the best chunks for generating {intent.replace('_', ' ')} content. "
        "Search for more material if key topics are missing, then call finalize_ranking."
    )

    conversation: list[dict] = [{"role": "user", "content": user_content}]
    tools = [SEARCH_TOOL_SCHEMA, FINALIZE_TOOL_SCHEMA]
    final_chunks: list[RetrievedChunk] | None = None
    search_count = 0

    for _ in range(MAX_ROUNDS):
        resp = _client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=_SYSTEM,
            tools=tools,
            messages=conversation,
        )

        tool_results: list[dict] = []
        finalized = False

        for block in resp.content:
            if block.type != "tool_use":
                continue

            if block.name == "search" and search_count < 3:
                query = block.input.get("query", "")
                top_k = min(int(block.input.get("top_k", 8)), 12)
                new_chunks = search(query=query, course=course, top_k=top_k)
                search_count += 1
                for c in new_chunks:
                    chunk_map.setdefault(c.chunk_id, c)
                result_lines = [
                    f"id={c.chunk_id} score={c.score:.2f} | {c.title}\n  {c.text[:120]}…"
                    for c in new_chunks
                ]
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": "\n\n".join(result_lines) or "No results found.",
                })

            elif block.name == "finalize_ranking":
                chunk_ids: list[str] = block.input.get("chunk_ids", [])
                final_chunks = [
                    chunk_map[cid] for cid in chunk_ids[:MAX_CHUNKS] if cid in chunk_map
                ]
                # Pad with highest-scoring unseen chunks if finalize returned few results
                seen = {c.chunk_id for c in final_chunks}
                remaining = sorted(
                    (c for c in chunk_map.values() if c.chunk_id not in seen),
                    key=lambda c: c.score,
                    reverse=True,
                )
                final_chunks.extend(remaining[:MAX_CHUNKS - len(final_chunks)])
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": f"Ranking finalized with {len(final_chunks)} chunks.",
                })
                finalized = True

        conversation.append({"role": "assistant", "content": resp.content})
        if tool_results:
            conversation.append({"role": "user", "content": tool_results})

        if finalized or not tool_results:
            break

    # Fallback: sort initial chunks by score if reranker never finalized
    if final_chunks is None:
        final_chunks = sorted(retrieved, key=lambda c: c.score, reverse=True)[:MAX_CHUNKS]

    return {"retrieved": final_chunks}
