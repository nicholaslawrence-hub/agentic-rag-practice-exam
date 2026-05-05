"""Upsert embedded chunks into Pinecone (namespace per course)."""

from __future__ import annotations

import os
from typing import Any

from pinecone import Pinecone, ServerlessSpec

from packages.ingest.chunk import Chunk

INDEX_NAME = os.environ.get("PINECONE_INDEX", "mcb-tutor")
DIMENSION = 3072
METRIC = "cosine"
UPSERT_BATCH = 100


def _get_or_create_index(pc: Pinecone) -> Any:
    existing = [i.name for i in pc.list_indexes()]
    if INDEX_NAME not in existing:
        pc.create_index(
            name=INDEX_NAME,
            dimension=DIMENSION,
            metric=METRIC,
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
    return pc.Index(INDEX_NAME)


def _chunk_to_vector(chunk: Chunk, embedding: list[float], course: str) -> dict:
    metadata: dict[str, Any] = {
        "course": course,
        "doc_type": chunk.doc_type,
        "source": chunk.source,
        "title": chunk.title,
        "text": chunk.text[:1000],
    }
    if chunk.week is not None:
        metadata["week"] = chunk.week
    if chunk.topic:
        metadata["topic"] = chunk.topic
    if chunk.slide_num is not None:
        metadata["slide_num"] = chunk.slide_num
    if chunk.slide_image_url:
        metadata["slide_image_url"] = chunk.slide_image_url
    if chunk.heading_path:
        metadata["heading_path"] = chunk.heading_path
    return {"id": chunk.chunk_id, "values": embedding, "metadata": metadata}


def upsert_chunks(
    chunks: list[Chunk],
    embeddings: list[list[float]],
    course: str,
    pinecone_api_key: str | None = None,
) -> int:
    pc = Pinecone(api_key=pinecone_api_key or os.environ["PINECONE_API_KEY"])
    index = _get_or_create_index(pc)

    vectors = [_chunk_to_vector(c, e, course) for c, e in zip(chunks, embeddings)]
    upserted = 0
    for i in range(0, len(vectors), UPSERT_BATCH):
        batch = vectors[i : i + UPSERT_BATCH]
        index.upsert(vectors=batch, namespace=course)
        upserted += len(batch)
    return upserted
