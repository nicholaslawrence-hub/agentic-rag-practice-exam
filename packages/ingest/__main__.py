"""CLI entry point: python -m ingest <command>

Commands:
  sync --course <id>   Ingest / refresh one course
  sync --all           Ingest / refresh all courses
  list                 Show registered courses
  stats --course <id>  Show vector counts for a course namespace
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import typer
import yaml
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from packages.ingest.chunk import to_chunks
from packages.ingest.embed import embed_texts
from packages.ingest.parsers.docx import parse_docx
from packages.ingest.parsers.pptx import parse_pptx, render_pptx_to_images
from packages.ingest.upsert import upsert_chunks

load_dotenv(".env", override=False)
load_dotenv("config.env", override=False)

app = typer.Typer(pretty_exceptions_show_locals=False)
console = Console()

COURSES_YAML = Path("packages/ingest/courses.yaml")


def load_courses() -> dict:
    return yaml.safe_load(COURSES_YAML.read_text())["courses"]


def _guess_week(filename: str) -> int | None:
    m = re.search(r"(?:week|lecture|lec|wk)[_\- ]?(\d+)", filename, re.IGNORECASE)
    return int(m.group(1)) if m else None


def _ingest_course(course_id: str, config: dict) -> None:
    topic_map: dict[int, str] = {int(k): v for k, v in config.get("topic_map", {}).items()}
    sources = config.get("sources", {})
    all_docs = []

    # ── PPTX slides ──────────────────────────────────────────────────────────
    for slide_dir in sources.get("slides", []):
        p = Path(slide_dir)
        if not p.exists():
            console.print(f"  [yellow]⚠ slides dir not found: {p}[/yellow]")
            continue
        for pptx_file in sorted(p.glob("*.pptx")):
            week = _guess_week(pptx_file.name)
            topic = topic_map.get(week) if week else None

            # Try to render slide images (requires LibreOffice + pdf2image)
            console.print(f"  [dim]rendering images for {pptx_file.name}…[/dim]")
            slide_images = render_pptx_to_images(pptx_file, course_id)
            if slide_images:
                console.print(f"  [dim]  → {len(slide_images)} slide images[/dim]")
            else:
                console.print(
                    "  [dim]  → image rendering skipped (install LibreOffice + pdf2image)[/dim]"
                )

            docs = parse_pptx(pptx_file, week=week, topic=topic, slide_images=slide_images)
            all_docs.extend(docs)
            console.print(f"  [dim]parsed {pptx_file.name} → {len(docs)} slides[/dim]")

    # ── DOCX handouts ─────────────────────────────────────────────────────────
    for handout_dir in sources.get("handouts", []):
        p = Path(handout_dir)
        if not p.exists():
            console.print(f"  [yellow]⚠ handouts dir not found: {p}[/yellow]")
            continue
        for docx_file in sorted(p.glob("*.docx")):
            week = _guess_week(docx_file.name)
            topic = topic_map.get(week) if week else None
            docs = parse_docx(docx_file, week=week, topic=topic)
            all_docs.extend(docs)
            console.print(f"  [dim]parsed {docx_file.name} → {len(docs)} chunks[/dim]")

    if not all_docs:
        console.print(f"  [red]No documents found for {course_id}[/red]")
        return

    # Chunk
    all_chunks = []
    for doc in all_docs:
        all_chunks.extend(to_chunks(doc))
    console.print(f"  [cyan]{len(all_chunks)} chunks total[/cyan]")

    # Embed (cache avoids re-embedding unchanged slides)
    texts = [c.text for c in all_chunks]
    console.print("  [cyan]Embedding (cached chunks skipped)…[/cyan]")
    embeddings = embed_texts(texts)

    # Upsert to Pinecone
    console.print("  [cyan]Upserting to Pinecone…[/cyan]")
    n = upsert_chunks(all_chunks, embeddings, course=course_id)
    console.print(f"  [green]✓ Upserted {n} vectors into namespace '{course_id}'[/green]")


@app.command()
def sync(
    course: str = typer.Option(None, "--course", "-c", help="Course ID to sync"),
    all_courses: bool = typer.Option(False, "--all", "-a", help="Sync all courses"),
) -> None:
    """Ingest / refresh course materials into Pinecone."""
    courses = load_courses()

    if all_courses:
        targets = list(courses.keys())
    elif course:
        if course not in courses:
            console.print(f"[red]Unknown course '{course}'. Available: {list(courses)}[/red]")
            raise typer.Exit(1)
        targets = [course]
    else:
        console.print("[red]Provide --course <id> or --all[/red]")
        raise typer.Exit(1)

    for cid in targets:
        console.print(f"\n[bold blue]▶ {cid}: {courses[cid]['name']}[/bold blue]")
        _ingest_course(cid, courses[cid])


@app.command()
def list_courses() -> None:
    """List registered courses."""
    courses = load_courses()
    table = Table("ID", "Name", "Sources")
    for cid, cfg in courses.items():
        sources = cfg.get("sources", {})
        src_summary = ", ".join(f"{k}({len(v)})" for k, v in sources.items() if v)
        table.add_row(cid, cfg["name"], src_summary)
    console.print(table)


@app.command()
def stats(course: str = typer.Option(..., "--course", "-c")) -> None:
    """Show vector counts in Pinecone for a course namespace."""
    from pinecone import Pinecone

    pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
    index_name = os.environ.get("PINECONE_INDEX", "mcb-tutor")
    index = pc.Index(index_name)
    info = index.describe_index_stats()
    ns = info.namespaces.get(course, None)
    if ns:
        console.print(f"[green]{course}[/green]: {ns.vector_count} vectors")
    else:
        console.print(f"[yellow]{course}[/yellow]: namespace not found (0 vectors)")


if __name__ == "__main__":
    app()
