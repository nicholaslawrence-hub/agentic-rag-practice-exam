"""Parse DOCX handouts into heading-bounded chunks."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn


@dataclass
class HandoutChunk:
    source: str
    heading_path: str    # e.g. "Initiation > eIF4F complex"
    body: str
    week: int | None
    topic: str | None

    @property
    def text(self) -> str:
        if self.heading_path:
            return f"[{self.heading_path}]\n{self.body}"
        return self.body

    @property
    def chunk_id(self) -> str:
        h = hashlib.sha256(self.text.encode()).hexdigest()[:12]
        return f"handout::{Path(self.source).stem}::{h}"


def _heading_level(para) -> int | None:
    """Return heading level (1-9) if paragraph is a heading, else None."""
    style_name = para.style.name if para.style else ""
    if style_name.startswith("Heading "):
        try:
            return int(style_name.split(" ")[1])
        except (IndexError, ValueError):
            pass
    # Check outline level via XML
    pPr = para._p.find(qn("w:pPr"))
    if pPr is not None:
        outlineLvl = pPr.find(qn("w:outlineLvl"))
        if outlineLvl is not None:
            val = outlineLvl.get(qn("w:val"))
            if val is not None:
                return int(val) + 1
    return None


def parse_docx(
    path: Path,
    *,
    week: int | None = None,
    topic: str | None = None,
    min_chunk_chars: int = 100,
) -> list[HandoutChunk]:
    doc = Document(str(path))
    source = path.name

    # Stack tracks (level, heading_text) for building heading_path
    heading_stack: list[tuple[int, str]] = []
    current_body_lines: list[str] = []
    chunks: list[HandoutChunk] = []

    def flush(heading_path: str) -> None:
        body = "\n".join(current_body_lines).strip()
        if len(body) >= min_chunk_chars:
            chunks.append(HandoutChunk(
                source=source,
                heading_path=heading_path,
                body=body,
                week=week,
                topic=topic,
            ))

    def current_path() -> str:
        return " > ".join(h for _, h in heading_stack)

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        lvl = _heading_level(para)
        if lvl is not None:
            # Flush whatever was accumulating under the previous heading
            flush(current_path())
            current_body_lines.clear()
            # Pop headings of equal or deeper level
            while heading_stack and heading_stack[-1][0] >= lvl:
                heading_stack.pop()
            heading_stack.append((lvl, text))
        else:
            current_body_lines.append(text)

    # Flush final section
    flush(current_path())

    return chunks
