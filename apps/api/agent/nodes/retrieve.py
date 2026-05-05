"""Retrieve relevant chunks from Pinecone.

Only runs for generation intents (exam_config, cheatsheet_config).
No LLM reranking — returns top-FETCH_K results above the score threshold.
"""

from __future__ import annotations

import os

from openai import OpenAI
from pinecone import Pinecone

from apps.api.agent.state import RetrievedChunk

_oai = OpenAI()
_pc: Pinecone | None = None
_index = None

FETCH_K = 20
SCORE_THRESHOLD = 0.25

_GENERATION_INTENTS = {"exam_config", "cheatsheet_config"}


def _get_index():
    global _pc, _index
    if _index is None:
        _pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
        _index = _pc.Index(os.environ.get("PINECONE_INDEX", "mcb-tutor"))
    return _index


def _embed(text: str) -> list[float]:
    return _oai.embeddings.create(model="text-embedding-3-large", input=text).data[0].embedding


def retrieve_node(state: dict) -> dict:
    intent = state.get("intent", "unknown")
    if intent not in _GENERATION_INTENTS:
        return {"retrieved": []}

    messages = state.get("messages", [])
    course = state.get("course", "")
    last_user = next(
        (m for m in reversed(messages) if getattr(m, "type", None) == "human"), None
    )
    if not last_user or not course:
        return {"retrieved": []}

    embedding = _embed(last_user.content)
    results = _get_index().query(
        vector=embedding,
        top_k=FETCH_K,
        namespace=course,
        include_metadata=True,
    )

    chunks: list[RetrievedChunk] = []
    for match in results.matches:
        if match.score < SCORE_THRESHOLD:
            continue
        meta = match.metadata or {}
        chunks.append(RetrievedChunk(
            chunk_id=match.id,
            text=meta.get("text", ""),
            doc_type=meta.get("doc_type", ""),
            source=meta.get("source", ""),
            title=meta.get("title", ""),
            score=match.score,
            slide_num=meta.get("slide_num"),
            slide_image_url=meta.get("slide_image_url"),
            heading_path=meta.get("heading_path"),
            week=meta.get("week"),
            topic=meta.get("topic"),
        ))
    return {"retrieved": chunks}
