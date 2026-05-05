"""Embed chunks using OpenAI text-embedding-3-large with SHA-256 disk cache."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from openai import OpenAI

CACHE_DIR = Path(".cache/embeddings")
MODEL = "text-embedding-3-large"
BATCH_SIZE = 96  # max texts per API call (OpenAI limit is 2048, but smaller batches are safer)


def _cache_path(text: str) -> Path:
    key = hashlib.sha256(text.encode()).hexdigest()
    return CACHE_DIR / f"{key}.json"


def _load_cache(text: str) -> list[float] | None:
    p = _cache_path(text)
    if p.exists():
        return json.loads(p.read_text())
    return None


def _save_cache(text: str, embedding: list[float]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(text).write_text(json.dumps(embedding))


def embed_texts(texts: list[str], client: OpenAI | None = None) -> list[list[float]]:
    """Embed a list of texts, using disk cache to avoid re-embedding unchanged content."""
    if client is None:
        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    results: list[list[float] | None] = [None] * len(texts)
    uncached_indices: list[int] = []
    uncached_texts: list[str] = []

    for i, text in enumerate(texts):
        cached = _load_cache(text)
        if cached is not None:
            results[i] = cached
        else:
            uncached_indices.append(i)
            uncached_texts.append(text)

    # Batch embed uncached texts
    for batch_start in range(0, len(uncached_texts), BATCH_SIZE):
        batch = uncached_texts[batch_start : batch_start + BATCH_SIZE]
        response = client.embeddings.create(model=MODEL, input=batch)
        for j, item in enumerate(response.data):
            idx = uncached_indices[batch_start + j]
            emb = item.embedding
            results[idx] = emb
            _save_cache(uncached_texts[batch_start + j], emb)

    return results  # type: ignore[return-value]
