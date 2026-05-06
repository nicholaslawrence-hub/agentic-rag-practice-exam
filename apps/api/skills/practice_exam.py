"""Practice exam skill.

Pipeline:
  1. LLM (Sonnet) → structured JSON: list of question dicts with slide_refs
  2. reportlab    → assembles PDF from raw JSON + PNG slide images (no LLM formatting)
  3. pdf2image    → renders each PDF page to PNG for in-chat preview

The LLM never touches PDF formatting. It only produces question content and
references to real slides. reportlab owns all layout decisions.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from anthropic import Anthropic
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

_client = Anthropic()

DATA_ROOT = Path("data")
EXAMS_DIR = DATA_ROOT / "exams"

QuestionType = Literal["mcq", "short_answer", "multi_part"]


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class SlideRef:
    source: str       # e.g. "Lecture_11_Translation.pptx"
    slide_num: int


@dataclass
class Question:
    num: int
    type: QuestionType
    text: str
    options: list[str] = field(default_factory=list)   # MCQ only: ["eIF4A", "eIF4E", ...]
    correct: str = ""                                   # MCQ: "B", multi_part: ""
    parts: list[dict] = field(default_factory=list)    # multi_part: [{"label":"a","text":"...","answer":"..."}]
    model_answer: str = ""                             # short_answer
    explanation: str = ""
    slide_refs: list[SlideRef] = field(default_factory=list)


@dataclass
class ExamData:
    course_name: str
    topics: list[str]
    difficulty: str
    purpose: str
    questions: list[Question]


# ── LLM generation (structured JSON only) ────────────────────────────────────

_QUESTION_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "num":          {"type": "integer"},
                    "type":         {"type": "string", "enum": ["mcq", "short_answer", "multi_part"]},
                    "text":         {"type": "string"},
                    "options":      {"type": "array", "items": {"type": "string"}},
                    "correct":      {"type": "string"},
                    "parts": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "label":  {"type": "string"},
                                "text":   {"type": "string"},
                                "answer": {"type": "string"},
                            },
                        },
                    },
                    "model_answer": {"type": "string"},
                    "explanation":  {"type": "string"},
                    "slide_refs": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "source":    {"type": "string"},
                                "slide_num": {"type": "integer"},
                            },
                        },
                    },
                },
                "required": ["num", "type", "text"],
            },
        }
    },
    "required": ["questions"],
}


def _available_slides(course_id: str) -> list[dict]:
    """Return a list of available slide images so the LLM only references real files."""
    slide_root = DATA_ROOT / course_id / "slide_images"
    if not slide_root.exists():
        return []
    available = []
    for pptx_dir in sorted(slide_root.iterdir()):
        if not pptx_dir.is_dir():
            continue
        pngs = sorted(pptx_dir.glob("slide_*.png"))
        if pngs:
            available.append({
                "source": pptx_dir.name + ".pptx",
                "available_slides": [int(p.stem.split("_")[-1]) for p in pngs],
            })
    return available


def _generate_questions_json(
    course_name: str,
    course_id: str,
    topics: list[str],
    difficulty: str,
    num_questions: int,
    question_types: list[str],
    purpose: str,
    context_texts: list[str],
) -> list[dict]:
    """Ask Sonnet to produce question data as a validated JSON array."""
    available = _available_slides(course_id)
    available_str = json.dumps(available, indent=2) if available else "No slide images available."

    topic_str = ", ".join(topics) if topics and topics != ["all"] else "all course material"
    type_mix = ", ".join(question_types)
    ctx = "\n\n---\n\n".join(context_texts[:8])

    prompt = f"""You are generating a {difficulty}-level {purpose} practice exam for {course_name}.

Topics: {topic_str}
Question types to include: {type_mix}
Total questions: {num_questions}

COURSE CONTENT (use as the sole source of truth — do not invent facts):
{ctx}

AVAILABLE SLIDE IMAGES (you may reference these in slide_refs — only use real file/slide combinations):
{available_str}

Output ONLY a JSON object matching this schema. No prose, no markdown fences.
- For MCQ: provide exactly 4 options (strings without A/B/C/D prefix), set correct to "A"/"B"/"C"/"D"
- For short_answer: leave options/correct/parts empty; fill model_answer (2-4 sentences)
- For multi_part: provide 2-3 parts, each with label ("a"/"b"/"c"), text, and answer
- slide_refs: 0-2 refs per question, referencing real slides from AVAILABLE SLIDE IMAGES above
- explanation: 1-2 sentences connecting the answer to course content

Distribute question types proportionally across the {num_questions} questions.
"""

    tool = {
        "name": "submit_exam_questions",
        "description": "Submit the generated exam questions as structured JSON.",
        "input_schema": _QUESTION_SCHEMA,
    }

    resp = _client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        tools=[tool],
        tool_choice={"type": "tool", "name": "submit_exam_questions"},
        messages=[{"role": "user", "content": prompt}],
    )

    for block in resp.content:
        if block.type == "tool_use" and block.name == "submit_exam_questions":
            return block.input.get("questions", [])
    return []


def _parse_questions(raw: list[dict]) -> list[Question]:
    questions = []
    for q in raw:
        refs = [
            SlideRef(source=r["source"], slide_num=r["slide_num"])
            for r in q.get("slide_refs", [])
            if "source" in r and "slide_num" in r
        ]
        questions.append(Question(
            num=q.get("num", len(questions) + 1),
            type=q.get("type", "short_answer"),
            text=q.get("text", ""),
            options=q.get("options", []),
            correct=q.get("correct", ""),
            parts=q.get("parts", []),
            model_answer=q.get("model_answer", ""),
            explanation=q.get("explanation", ""),
            slide_refs=refs,
        ))
    return questions


# ── Slide image lookup ────────────────────────────────────────────────────────

def _slide_png(course_id: str, source: str, slide_num: int) -> Path | None:
    stem = Path(source).stem
    p = DATA_ROOT / course_id / "slide_images" / stem / f"slide_{slide_num:03d}.png"
    return p if p.exists() else None


# ── PDF assembly (reportlab, no LLM involvement) ──────────────────────────────

def _exam_font_size(num_questions: int) -> float:
    """Scale body font down for larger exams to reduce PDF bulk."""
    if num_questions <= 8:
        return 11.0
    if num_questions <= 12:
        return 10.0
    return 9.0


def _make_styles(base_size: float = 11.0) -> dict:
    base = getSampleStyleSheet()
    sm = max(base_size - 1.0, 8.0)
    xs = max(base_size - 2.5, 7.0)
    return {
        "h1":      ParagraphStyle("h1", parent=base["Heading1"], fontSize=base_size + 7, spaceAfter=4, textColor=colors.HexColor("#003262")),
        "h2":      ParagraphStyle("h2", parent=base["Heading2"], fontSize=base_size + 2, spaceAfter=2, textColor=colors.HexColor("#003262")),
        "subtitle": ParagraphStyle("subtitle", parent=base["Normal"], fontSize=sm, textColor=colors.HexColor("#555555"), spaceAfter=16),
        "q_num":   ParagraphStyle("q_num", parent=base["Normal"], fontSize=base_size + 1, fontName="Helvetica-Bold", spaceAfter=4),
        "body":    ParagraphStyle("body", parent=base["Normal"], fontSize=base_size, leading=base_size * 1.45, spaceAfter=6),
        "option":  ParagraphStyle("option", parent=base["Normal"], fontSize=base_size, leading=base_size * 1.27, leftIndent=18, spaceAfter=3),
        "answer":  ParagraphStyle("answer", parent=base["Normal"], fontSize=sm, textColor=colors.HexColor("#1a6e2e"), leading=sm * 1.4, spaceAfter=4),
        "caption": ParagraphStyle("caption", parent=base["Normal"], fontSize=xs, textColor=colors.HexColor("#666666"), spaceAfter=8),
        "divider": ParagraphStyle("divider", parent=base["Normal"], fontSize=6, spaceAfter=12),
    }


def _add_question(story: list, q: Question, course_id: str, styles: dict, show_answers: bool) -> None:
    label = {"mcq": "Multiple Choice", "short_answer": "Short Answer", "multi_part": "Multi-Part"}
    story.append(Paragraph(f"Question {q.num} &nbsp;<font size='9' color='#888888'>[{label.get(q.type, q.type)}]</font>", styles["q_num"]))
    story.append(Paragraph(q.text, styles["body"]))

    if q.type == "mcq":
        letters = ["A", "B", "C", "D"]
        for i, opt in enumerate(q.options[:4]):
            letter = letters[i]
            story.append(Paragraph(f"{letter}.&nbsp;&nbsp;{opt}", styles["option"]))
        if show_answers and q.correct:
            story.append(Paragraph(f"✓ Correct: {q.correct}. {q.explanation}", styles["answer"]))

    elif q.type == "short_answer":
        story.append(Spacer(1, 0.8 * inch))  # blank writing space
        if show_answers and q.model_answer:
            story.append(Paragraph(f"Model answer: {q.model_answer}", styles["answer"]))

    elif q.type == "multi_part":
        for part in q.parts:
            story.append(Paragraph(f"<b>({part.get('label', '?')})</b> {part.get('text', '')}", styles["body"]))
            story.append(Spacer(1, 0.5 * inch))
            if show_answers and part.get("answer"):
                story.append(Paragraph(f"Answer ({part['label']}): {part['answer']}", styles["answer"]))

    # Slide image reference
    for ref in q.slide_refs[:2]:
        png = _slide_png(course_id, ref.source, ref.slide_num)
        if png:
            img = Image(str(png), width=3.5 * inch, height=2.2 * inch, kind="proportional")
            story.append(img)
            story.append(Paragraph(
                f"↑ Ref: {ref.source} — Slide {ref.slide_num}",
                styles["caption"],
            ))

    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#dddddd"), spaceAfter=14))


def _build_pdf(output_path: Path, exam: ExamData, course_id: str, base_size: float = 11.0) -> None:
    import datetime

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        leftMargin=inch,
        rightMargin=inch,
        topMargin=inch,
        bottomMargin=0.85 * inch,
    )
    styles = _make_styles(base_size)
    story: list = []

    # ── Cover / header ────────────────────────────────────────────────────────
    story.append(Paragraph(exam.course_name, styles["h1"]))
    story.append(Paragraph("Practice Exam", styles["h2"]))
    story.append(Paragraph(
        f"Topics: {', '.join(exam.topics)} &nbsp;|&nbsp; "
        f"Difficulty: {exam.difficulty.title()} &nbsp;|&nbsp; "
        f"Purpose: {exam.purpose.replace('_', ' ').title()} &nbsp;|&nbsp; "
        f"Generated: {datetime.date.today().strftime('%B %d, %Y')}",
        styles["subtitle"],
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#003262"), spaceAfter=16))

    # ── Questions (no answers) ────────────────────────────────────────────────
    story.append(Paragraph("Questions", styles["h2"]))
    story.append(Spacer(1, 8))
    for q in exam.questions:
        _add_question(story, q, course_id, styles, show_answers=False)

    # ── Answer key (new page) ─────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(Paragraph("Answer Key", styles["h1"]))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#003262"), spaceAfter=16))
    for q in exam.questions:
        _add_question(story, q, course_id, styles, show_answers=True)

    doc.build(story)


# ── PDF → preview images ──────────────────────────────────────────────────────

def _pdf_to_previews(pdf_path: Path, exam_id: str) -> list[str]:
    """Convert PDF pages to PNGs for in-chat preview. Returns relative API URL paths."""
    try:
        from pdf2image import convert_from_path  # type: ignore
    except ImportError:
        return []

    preview_dir = EXAMS_DIR / f"{exam_id}_preview"
    preview_dir.mkdir(parents=True, exist_ok=True)

    try:
        pages = convert_from_path(str(pdf_path), dpi=120, fmt="png")
    except Exception:
        return []

    urls = []
    for i, img in enumerate(pages):
        img_path = preview_dir / f"page_{i + 1:02d}.png"
        img.save(img_path, "PNG")
        urls.append(f"/static/exams/{exam_id}_preview/page_{i + 1:02d}.png")
    return urls


# ── Public entry point ────────────────────────────────────────────────────────

def generate_practice_exam(
    course_id: str,
    course_name: str,
    context_texts: list[str],
    topics: list[str],
    difficulty: str = "medium",
    num_questions: int = 10,
    question_types: list[str] | None = None,
    purpose: str = "review",
) -> dict:
    """Generate a practice exam PDF.

    Returns {"pdf_url": str, "preview_urls": list[str]}
    """
    if question_types is None:
        question_types = ["mcq", "short_answer", "multi_part"]

    EXAMS_DIR.mkdir(parents=True, exist_ok=True)
    exam_id = uuid.uuid4().hex[:10]
    pdf_path = EXAMS_DIR / f"{course_id}_{exam_id}.pdf"

    raw_questions = _generate_questions_json(
        course_name=course_name,
        course_id=course_id,
        topics=topics,
        difficulty=difficulty,
        num_questions=num_questions,
        question_types=question_types,
        purpose=purpose,
        context_texts=context_texts,
    )

    exam = ExamData(
        course_name=course_name,
        topics=topics,
        difficulty=difficulty,
        purpose=purpose,
        questions=_parse_questions(raw_questions),
    )

    # Step 2 — reportlab assembles the PDF (no LLM involvement)
    _build_pdf(pdf_path, exam, course_id, _exam_font_size(num_questions))

    # Step 3 — pdf2image renders preview PNGs for the chat window
    preview_urls = _pdf_to_previews(pdf_path, exam_id)

    return {
        "pdf_url": f"/static/exams/{pdf_path.name}",
        "preview_urls": preview_urls,
    }
