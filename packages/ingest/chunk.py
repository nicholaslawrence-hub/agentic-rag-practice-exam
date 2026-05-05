"""Structure-aware chunker for slide and handout documents."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Union

import tiktoken

from packages.ingest.parsers.docx import HandoutChunk
from packages.ingest.parsers.pptx import SlideDoc

MAX_TOKENS = 600
OVERLAP_TOKENS = 100

_enc = tiktoken.get_encoding("cl100k_base")


def _token_len(text: str) -> int:
    return len(_enc.encode(text))


def _split_sentences(text: str) -> list[str]:
    return re.split(r"(?<=[.!?])\s+", text.strip())


@dataclass
class Chunk:
    chunk_id: str
    text: str
    doc_type: str       # "slide" | "handout"
    source: str
    title: str
    week: int | None
    topic: str | None
    slide_num: int | None = None
    slide_image_url: str | None = None   # relative API path to rendered PNG
    heading_path: str | None = None


def _split_long_text(text: str, max_tok: int = MAX_TOKENS) -> list[tuple[str, str]]:
    """Split long text into overlapping windows. Returns (idx_suffix, text) pairs."""
    if _token_len(text) <= max_tok:
        return [("", text)]

    sentences = _split_sentences(text)
    windows: list[tuple[str, str]] = []
    current: list[str] = []
    current_tok = 0
    idx = 0

    for sent in sentences:
        sent_tok = _token_len(sent)
        if current_tok + sent_tok > max_tok and current:
            windows.append((f"_{idx}", " ".join(current)))
            idx += 1
            overlap: list[str] = []
            overlap_tok = 0
            for s in reversed(current):
                if overlap_tok + _token_len(s) > OVERLAP_TOKENS:
                    break
                overlap.insert(0, s)
                overlap_tok += _token_len(s)
            current = overlap
            current_tok = overlap_tok
        current.append(sent)
        current_tok += sent_tok

    if current:
        windows.append((f"_{idx}", " ".join(current)))

    return windows


def chunk_slide(doc: SlideDoc) -> list[Chunk]:
    windows = _split_long_text(doc.text)
    return [
        Chunk(
            chunk_id=doc.chunk_id + suffix,
            text=text,
            doc_type="slide",
            source=doc.source,
            title=doc.title or f"Slide {doc.slide_num}",
            week=doc.week,
            topic=doc.topic,
            slide_num=doc.slide_num,
            slide_image_url=doc.slide_image_url,
        )
        for suffix, text in windows
    ]


def chunk_handout(doc: HandoutChunk) -> list[Chunk]:
    windows = _split_long_text(doc.text)
    return [
        Chunk(
            chunk_id=doc.chunk_id + suffix,
            text=text,
            doc_type="handout",
            source=doc.source,
            title=doc.heading_path or doc.source,
            week=doc.week,
            topic=doc.topic,
            heading_path=doc.heading_path,
        )
        for suffix, text in windows
    ]


def to_chunks(doc: Union[SlideDoc, HandoutChunk]) -> list[Chunk]:
    if isinstance(doc, SlideDoc):
        return chunk_slide(doc)
    if isinstance(doc, HandoutChunk):
        return chunk_handout(doc)
    raise TypeError(f"Unknown doc type: {type(doc)}")
