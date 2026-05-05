"""Cheatsheet skill.

Pipeline:
  1. LLM (Sonnet) with create_diagram + submit_cheatsheet tools →
       structured JSON (sections with typed entries, optional embedded diagrams)
  2. reportlab → dense 3-column PDF (page 1 = front, page 2 = back)
     - font size auto-optimised to fit all content
  3. pdf2image → page PNGs for in-chat preview
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path

from anthropic import Anthropic
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

_client = Anthropic()

DATA_ROOT = Path("data")
SHEETS_DIR = DATA_ROOT / "cheatsheets"

# ── Column geometry (fixed, independent of font size) ─────────────────────────
_page_w, _page_h = letter
_H_MARGIN  = 0.32 * inch
_V_MARGIN  = 0.26 * inch
_HEADER_H  = 0.20 * inch
_COL_GAP   = 0.10 * inch
_COL_W     = (_page_w - 2 * _H_MARGIN - 2 * _COL_GAP) / 3
_COL_H     = _page_h - _V_MARGIN - (_V_MARGIN + _HEADER_H + 0.04 * inch)


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class Entry:
    type: str           # "term" | "formula" | "list" | "note" | "diagram"
    term: str = ""
    detail: str = ""
    content: str = ""   # formula text, note text, or diagram caption
    items: list[str] = field(default_factory=list)
    url: str = ""       # diagram: /static/diagrams/<id>.png


@dataclass
class Section:
    heading: str
    entries: list[Entry] = field(default_factory=list)


@dataclass
class CheatsheetData:
    course_name: str
    topics: list[str]
    exam_type: str
    content_focus: str
    front_sections: list[Section] = field(default_factory=list)
    back_sections:  list[Section] = field(default_factory=list)


# ── JSON / tool schemas ───────────────────────────────────────────────────────

_ENTRY_SCHEMA = {
    "type": "object",
    "properties": {
        "type":    {"type": "string", "enum": ["term", "formula", "list", "note", "diagram"]},
        "term":    {"type": "string"},
        "detail":  {"type": "string"},
        "content": {"type": "string"},
        "items":   {"type": "array", "items": {"type": "string"}},
        "url":     {"type": "string", "description": "URL returned by create_diagram (diagram entries only)"},
    },
    "required": ["type"],
}

_SECTION_SCHEMA = {
    "type": "object",
    "properties": {
        "heading": {"type": "string"},
        "entries": {"type": "array", "items": _ENTRY_SCHEMA},
    },
    "required": ["heading", "entries"],
}

_CHEATSHEET_SCHEMA = {
    "type": "object",
    "properties": {
        "front_sections": {"type": "array", "items": _SECTION_SCHEMA},
        "back_sections":  {"type": "array", "items": _SECTION_SCHEMA},
    },
    "required": ["front_sections", "back_sections"],
}

# Inline the create_diagram schema so we don't import from agent.tools at module load
_CREATE_DIAGRAM_TOOL = {
    "name": "create_diagram",
    "description": (
        "Create a diagram image (flowchart, table, or pathway) to embed in the cheatsheet. "
        "Use for complex pathways, multi-step processes, or comparison tables."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "diagram_type": {"type": "string", "enum": ["flowchart", "table", "pathway"]},
            "title": {"type": "string"},
            "nodes":   {"type": "array", "items": {"type": "string"}},
            "edges":   {"type": "array", "items": {"type": "object",
                        "properties": {"from": {"type": "integer"}, "to": {"type": "integer"}}}},
            "headers": {"type": "array", "items": {"type": "string"}},
            "rows":    {"type": "array", "items": {"type": "array", "items": {"type": "string"}}},
        },
        "required": ["diagram_type", "title"],
    },
}

_SUBMIT_CHEATSHEET_TOOL = {
    "name": "submit_cheatsheet",
    "description": "Submit the completed cheatsheet content.",
    "input_schema": _CHEATSHEET_SCHEMA,
}


# ── LLM generation with multi-turn diagram support ────────────────────────────

def _generate_cheatsheet_json(
    course_name: str,
    topics: list[str],
    exam_type: str,
    content_focus: str,
    context_texts: list[str],
) -> dict:
    topic_str = ", ".join(topics) if topics and topics != ["all"] else "all course material"
    ctx = "\n\n---\n\n".join(context_texts[:12])

    focus_map = {
        "terms_only":     "Key terms and concise definitions only.",
        "terms_formulas": "Key terms, definitions, important formulas, and core mechanisms.",
        "comprehensive":  "Everything: key terms, definitions, formulas, mechanisms, pathways, comparisons, exceptions, mnemonics.",
    }
    focus_instruction = focus_map.get(content_focus, "Everything relevant for exam preparation.")

    prompt = f"""You are generating a dense, exam-focused cheatsheet for {course_name} \
({exam_type.replace('_', ' ')}).

Topics: {topic_str}
Content focus: {focus_instruction}

COURSE CONTENT (sole source of truth — do not invent facts):
{ctx}

Output JSON with front_sections and back_sections via submit_cheatsheet.

Front page: foundational knowledge — key terms, core definitions, essential mechanisms.
Back page: synthesis content — complex pathways, comparisons, formulas, exceptions, mnemonics.

Entry type rules:
- "term":    {{"term": "word", "detail": "≤12-word definition"}}
- "formula": {{"content": "equation or symbolic expression"}}
- "list":    {{"items": ["step 1", "step 2", ...]}} — ordered steps, 3–5 items max
- "note":    {{"content": "≤10-word high-yield warning or insight"}} — use sparingly
- "diagram": ONLY use if you first called create_diagram and received a URL back.
             {{"url": "<url from create_diagram>", "content": "short caption"}}

Guidelines:
- 9–14 sections per side, 3–7 entries per section.
- Section headings: 1–4 words.
- Use create_diagram for complex multi-step pathways or comparison tables (max 2 diagrams total).
- No redundancy between front and back.

Call create_diagram if needed, then call submit_cheatsheet with the final content.
"""

    tools = [_CREATE_DIAGRAM_TOOL, _SUBMIT_CHEATSHEET_TOOL]
    messages: list[dict] = [{"role": "user", "content": prompt}]

    for _ in range(6):  # max rounds: up to 2 diagrams + 1 submit + buffer
        resp = _client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=8096,
            tools=tools,
            messages=messages,
        )

        tool_results: list[dict] = []
        cheatsheet_data: dict | None = None

        for block in resp.content:
            if block.type != "tool_use":
                continue

            if block.name == "create_diagram":
                from apps.api.agent.tools import create_diagram as _create_diagram
                url = _create_diagram(
                    diagram_type=block.input.get("diagram_type", "flowchart"),
                    title=block.input.get("title", "Diagram"),
                    nodes=block.input.get("nodes"),
                    edges=block.input.get("edges"),
                    headers=block.input.get("headers"),
                    rows=block.input.get("rows"),
                )
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": f"Diagram created. URL: {url}",
                })

            elif block.name == "submit_cheatsheet":
                cheatsheet_data = {
                    "front_sections": block.input.get("front_sections", []),
                    "back_sections":  block.input.get("back_sections",  []),
                }
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": "Cheatsheet submitted.",
                })

        if cheatsheet_data is not None:
            return cheatsheet_data

        if not tool_results:
            break

        messages.append({"role": "assistant", "content": resp.content})
        messages.append({"role": "user", "content": tool_results})

    return {"front_sections": [], "back_sections": []}


def _parse_cheatsheet(
    raw: dict,
    course_name: str,
    topics: list[str],
    exam_type: str,
    content_focus: str,
) -> CheatsheetData:
    def parse_entries(raw_entries: list[dict]) -> list[Entry]:
        return [
            Entry(
                type=e.get("type", "term"),
                term=e.get("term", ""),
                detail=e.get("detail", ""),
                content=e.get("content", ""),
                items=e.get("items", []),
                url=e.get("url", ""),
            )
            for e in raw_entries
        ]

    def parse_sections(raw_sections: list[dict]) -> list[Section]:
        return [
            Section(
                heading=s.get("heading", ""),
                entries=parse_entries(s.get("entries", [])),
            )
            for s in raw_sections
        ]

    return CheatsheetData(
        course_name=course_name,
        topics=topics,
        exam_type=exam_type,
        content_focus=content_focus,
        front_sections=parse_sections(raw.get("front_sections", [])),
        back_sections=parse_sections(raw.get("back_sections",  [])),
    )


# ── Styles (parameterised by font size) ───────────────────────────────────────

def _make_styles(base_size: float = 6.5) -> dict:
    base = getSampleStyleSheet()
    heading_size = base_size + 1.0
    leading      = base_size + 1.5
    h_leading    = heading_size + 2.0
    return {
        "heading_inner": ParagraphStyle(
            "heading_inner", parent=base["Normal"],
            fontSize=heading_size, fontName="Helvetica-Bold",
            textColor=colors.white, leading=h_leading,
        ),
        "term": ParagraphStyle(
            "term", parent=base["Normal"],
            fontSize=base_size, leading=leading, spaceAfter=1,
        ),
        "formula": ParagraphStyle(
            "formula", parent=base["Normal"],
            fontSize=base_size, fontName="Courier",
            leading=leading, spaceAfter=1, leftIndent=4,
        ),
        "list_item": ParagraphStyle(
            "list_item", parent=base["Normal"],
            fontSize=base_size, leading=leading - 0.5, spaceAfter=0, leftIndent=6,
        ),
        "note": ParagraphStyle(
            "note", parent=base["Normal"],
            fontSize=base_size, leading=leading, spaceAfter=1, leftIndent=3,
        ),
    }


# ── Flowable builders ─────────────────────────────────────────────────────────

def _section_header(heading: str, styles: dict) -> Table:
    """Full-width Berkeley-blue heading bar."""
    p = Paragraph(heading, styles["heading_inner"])
    t = Table([[p]], colWidths=[_COL_W - 4])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor("#003262")),
        ("TOPPADDING",    (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING",   (0, 0), (-1, -1), 3),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 3),
    ]))
    return t


def _diagram_image(url: str) -> Image | None:
    """Convert a /static/... URL to a reportlab Image, or None if file missing."""
    if not url.startswith("/static/"):
        return None
    rel = url[len("/static/"):]           # e.g. "diagrams/abc123.png"
    file_path = Path("data") / rel
    if not file_path.exists():
        return None
    max_w = _COL_W - 8
    return Image(str(file_path), width=max_w, height=max_w * 0.6, kind="proportional")


def _section_flowables_inner(section: Section, styles: dict) -> list:
    """Flat flowable list for one section — used for both measuring and building."""
    items: list = [_section_header(section.heading, styles)]
    for entry in section.entries:
        if entry.type == "term" and (entry.term or entry.detail):
            text = f"<b>{entry.term}:</b> {entry.detail}" if entry.detail else f"<b>{entry.term}</b>"
            items.append(Paragraph(text, styles["term"]))
        elif entry.type == "formula" and entry.content:
            items.append(Paragraph(entry.content, styles["formula"]))
        elif entry.type == "list" and entry.items:
            for li in entry.items:
                items.append(Paragraph(f"• {li}", styles["list_item"]))
        elif entry.type == "note" and entry.content:
            items.append(Paragraph(f"▶ {entry.content}", styles["note"]))
        elif entry.type == "diagram" and entry.url:
            img = _diagram_image(entry.url)
            if img:
                items.append(img)
            if entry.content:
                items.append(Paragraph(f"↑ {entry.content}", styles["note"]))
    items.append(Spacer(1, 3))
    return items


def _section_flowables(section: Section, styles: dict) -> list:
    return [KeepTogether(_section_flowables_inner(section, styles))]


# ── Font optimizer ─────────────────────────────────────────────────────────────

def _measure_height(sections: list[Section], styles: dict) -> float:
    """Estimate total flowable height without rendering (uses Paragraph.wrap)."""
    total = 0.0
    for section in sections:
        for f in _section_flowables_inner(section, styles):
            try:
                _, h = f.wrap(_COL_W, 9999)
                total += h
            except Exception:
                total += 10.0
    return total


def _optimal_font_size(
    front_sections: list[Section],
    back_sections: list[Section],
) -> float:
    """Binary-descend from 8.5 to 5.5pt until content fits 2 pages (3 columns each)."""
    available = 3 * _COL_H * 2  # 3 columns × 2 pages
    for base_size in (8.5, 8.0, 7.5, 7.0, 6.5, 6.0, 5.5):
        styles = _make_styles(base_size)
        total_h = (
            _measure_height(front_sections, styles)
            + _measure_height(back_sections, styles)
        )
        if total_h <= available:
            return base_size
    return 5.5


# ── PDF assembly ──────────────────────────────────────────────────────────────

def _build_pdf(output_path: Path, data: CheatsheetData, base_size: float) -> None:
    def make_frames() -> list[Frame]:
        return [
            Frame(
                _H_MARGIN + i * (_COL_W + _COL_GAP),
                _V_MARGIN,
                _COL_W,
                _COL_H,
                leftPadding=2, rightPadding=2, topPadding=0, bottomPadding=0,
                id=f"col{i}",
            )
            for i in range(3)
        ]

    def on_page(canvas, doc: BaseDocTemplate) -> None:
        canvas.saveState()
        side  = "FRONT" if doc.page == 1 else "BACK"
        bar_y = _page_h - _V_MARGIN - _HEADER_H
        canvas.setFillColor(colors.HexColor("#003262"))
        canvas.rect(_H_MARGIN, bar_y, _page_w - 2 * _H_MARGIN, _HEADER_H, fill=1, stroke=0)
        canvas.setFillColor(colors.HexColor("#FDB515"))
        canvas.setFont("Helvetica-Bold", 7.5)
        title = f"{data.course_name}  —  {data.exam_type.replace('_', ' ').title()} Cheatsheet  [{side}]"
        canvas.drawString(_H_MARGIN + 3, bar_y + 6, title)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica", 6)
        canvas.drawRightString(_page_w - _H_MARGIN - 3, bar_y + 6, ", ".join(data.topics[:5]))
        canvas.restoreState()

    doc = BaseDocTemplate(
        str(output_path),
        pagesize=letter,
        leftMargin=_H_MARGIN,
        rightMargin=_H_MARGIN,
        topMargin=_V_MARGIN + _HEADER_H + 0.04 * inch,
        bottomMargin=_V_MARGIN,
    )
    doc.addPageTemplates([PageTemplate(id="cheat", frames=make_frames(), onPage=on_page)])

    styles = _make_styles(base_size)
    story: list = []
    for section in data.front_sections:
        story.extend(_section_flowables(section, styles))
    story.append(PageBreak())
    for section in data.back_sections:
        story.extend(_section_flowables(section, styles))

    doc.build(story)


# ── PDF → preview images ──────────────────────────────────────────────────────

def _pdf_to_previews(pdf_path: Path, sheet_id: str) -> list[str]:
    try:
        from pdf2image import convert_from_path  # type: ignore
    except ImportError:
        return []
    preview_dir = SHEETS_DIR / f"{sheet_id}_preview"
    preview_dir.mkdir(parents=True, exist_ok=True)
    try:
        pages = convert_from_path(str(pdf_path), dpi=150, fmt="png")
    except Exception:
        return []
    urls = []
    for i, img in enumerate(pages):
        p = preview_dir / f"page_{i + 1:02d}.png"
        img.save(p, "PNG")
        urls.append(f"/static/cheatsheets/{sheet_id}_preview/page_{i + 1:02d}.png")
    return urls


# ── Public entry point ────────────────────────────────────────────────────────

def generate_cheatsheet(
    course_id: str,
    course_name: str,
    retrieved_chunks: list,
    topics: list[str],
    exam_type: str = "review",
    content_focus: str = "comprehensive",
    extra_context: list[str] | None = None,
) -> dict:
    """Generate a 3-column front/back cheatsheet PDF with auto-optimised font size.

    Returns {"pdf_url": str, "preview_urls": list[str]}
    """
    SHEETS_DIR.mkdir(parents=True, exist_ok=True)
    sheet_id = uuid.uuid4().hex[:10]
    pdf_path = SHEETS_DIR / f"{course_id}_{sheet_id}.pdf"

    context_texts = [c.text for c in retrieved_chunks] + (extra_context or [])
    raw = _generate_cheatsheet_json(
        course_name=course_name,
        topics=topics,
        exam_type=exam_type,
        content_focus=content_focus,
        context_texts=context_texts,
    )
    data = _parse_cheatsheet(raw, course_name, topics, exam_type, content_focus)

    base_size = _optimal_font_size(data.front_sections, data.back_sections)
    _build_pdf(pdf_path, data, base_size)
    preview_urls = _pdf_to_previews(pdf_path, sheet_id)

    return {
        "pdf_url":      f"/static/cheatsheets/{pdf_path.name}",
        "preview_urls": preview_urls,
    }
