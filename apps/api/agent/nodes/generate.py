"""Generate practice exam or cheatsheet PDF.

Retrieval is handled by Pinecone Assistant — no manual embedding or reranking.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

import yaml
from anthropic import Anthropic
from pinecone import Pinecone

from apps.api.agent.nodes.route import CHEAT_Q_MARKER, EXAM_Q_MARKER
from apps.api.agent.state import Attachment

_client = Anthropic()

_COURSES_YAML = Path("packages/ingest/courses.yaml")
_courses_cache: dict | None = None


def _course_name(course_id: str) -> str:
    global _courses_cache
    if _courses_cache is None:
        try:
            _courses_cache = yaml.safe_load(_COURSES_YAML.read_text()).get("courses", {})
        except Exception:
            _courses_cache = {}
    return _courses_cache.get(course_id, {}).get("name", course_id)


@lru_cache(maxsize=1)
def _get_assistant():
    pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
    name = os.environ.get("PINECONE_ASSISTANT_NAME", "mcb-tutor")
    return pc.assistant.Assistant(assistant_name=name)


def _retrieve_context(topics: list[str], weeks: list[int] | None = None) -> list[str]:
    """Ask Pinecone Assistant for relevant course content and extract citation passages."""
    topic_str = ", ".join(topics) if topics and topics != ["all"] else "all major topics"
    query = f"Provide detailed notes on: {topic_str}"
    if weeks:
        query += f" (weeks {', '.join(str(w) for w in weeks)})"

    resp = _get_assistant().chat(messages=[{"role": "user", "content": query}])

    passages: list[str] = []
    for citation in (resp.citations or []):
        for ref in citation.references:
            if getattr(ref, "content", None):
                passages.append(ref.content)

    # Fall back to the assistant's synthesised answer if no raw citations
    if not passages and resp.message and resp.message.content:
        passages.append(resp.message.content)

    return passages


# -- Questionnaires -----------------------------------------------------------

_EXAM_QUESTIONNAIRE = (
    "I'll create a personalized practice exam for you. Answer these questions:\n\n"
    "**1. Topics to cover**\n"
    "- a) Everything covered so far\n"
    "- b) Specific topics - list them (e.g. *translation initiation, enzyme kinetics*)\n"
    "- c) A specific week range (e.g. *weeks 5-8*)\n\n"
    "**2. Difficulty**\n"
    "- a) Easy - recall and definitions\n"
    "- b) Medium - application and analysis\n"
    "- c) Hard - synthesis and multi-step reasoning\n\n"
    "**3. Number of questions**\n"
    "- a) 5 (quick check)\n"
    "- b) 10 (standard)\n"
    "- c) 15 (comprehensive)\n\n"
    "**4. Question format**\n"
    "- a) Multiple choice only\n"
    "- b) Short answer only\n"
    "- c) Mixed - MCQ + short answer + multi-part\n\n"
    "**5. Purpose**\n"
    "- a) Upcoming midterm or final\n"
    "- b) Weekly review\n"
    "- c) Problem set practice\n\n"
    "Reply with your choices, e.g. *b - glycolysis and TCA, b, b, c, a*\n\n"
) + EXAM_Q_MARKER

_CHEAT_QUESTIONNAIRE = (
    "I'll build you a dense 3-column cheatsheet PDF (front + back). Quick questions:\n\n"
    "**1. Topics to cover**\n"
    "- a) Everything covered so far\n"
    "- b) Specific topics - list them (e.g. *translation, mRNA processing*)\n"
    "- c) A specific week range (e.g. *weeks 1-5*)\n\n"
    "**2. Exam scope**\n"
    "- a) Midterm 1\n"
    "- b) Midterm 2\n"
    "- c) Final exam\n"
    "- d) General review\n\n"
    "**3. Content to include**\n"
    "- a) Key terms + definitions only (cleaner, more readable)\n"
    "- b) Terms + formulas + mechanisms\n"
    "- c) Everything - maximum density\n\n"
    "Reply with your choices, e.g. *b - translation and splicing, a, c*\n\n"
) + CHEAT_Q_MARKER


# -- Config parsers -----------------------------------------------------------

_PARSE_EXAM_SYSTEM = (
    "Parse the student's exam preferences. Return ONLY valid JSON:\n"
    '{"topics":[...],"weeks":[],"difficulty":"easy|medium|hard",'
    '"num_questions":5|10|15,"question_types":[...],"purpose":"midterm|review|problem_set"}\n'
    "Use sensible defaults if a field is not specified."
)

_PARSE_CHEAT_SYSTEM = (
    "Parse the student's cheatsheet preferences. Return ONLY valid JSON:\n"
    '{"topics":[...],"weeks":[],"exam_type":"midterm_1|midterm_2|final|review",'
    '"content_focus":"terms_only|terms_formulas|comprehensive"}\n'
    "Use sensible defaults if a field is not specified."
)


def _parse_config(student_reply: str, system: str, default: dict) -> dict:
    resp = _client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        system=system,
        messages=[{"role": "user", "content": student_reply}],
    )
    try:
        return json.loads(resp.content[0].text.strip())
    except Exception:
        return default


# -- Tool definitions ---------------------------------------------------------

_EXAM_TOOL = {
    "name": "generate_practice_exam",
    "description": "Build a practice exam PDF.",
    "input_schema": {
        "type": "object",
        "properties": {
            "topics":         {"type": "array", "items": {"type": "string"}},
            "difficulty":     {"type": "string", "enum": ["easy", "medium", "hard"]},
            "num_questions":  {"type": "integer"},
            "question_types": {"type": "array", "items": {"type": "string"}},
            "purpose":        {"type": "string"},
        },
        "required": ["topics", "difficulty", "num_questions", "question_types"],
    },
}

_CHEAT_TOOL = {
    "name": "generate_cheatsheet",
    "description": "Build a cheatsheet PDF.",
    "input_schema": {
        "type": "object",
        "properties": {
            "topics":        {"type": "array", "items": {"type": "string"}},
            "exam_type":     {"type": "string"},
            "content_focus": {"type": "string"},
        },
        "required": ["topics", "exam_type", "content_focus"],
    },
}


# -- Tool dispatcher ----------------------------------------------------------

def _dispatch_tool(name: str, tool_input: dict, state: dict, context_texts: list[str]) -> str:
    course_id = state.get("course", "")
    user_doc_texts: list[str] = state.get("user_doc_texts", [])
    all_context = context_texts + user_doc_texts

    if name == "generate_practice_exam":
        from apps.api.skills.practice_exam import generate_practice_exam

        result = generate_practice_exam(
            course_id=course_id,
            course_name=_course_name(course_id),
            context_texts=all_context,
            topics=tool_input.get("topics", ["all"]),
            difficulty=tool_input.get("difficulty", "medium"),
            num_questions=tool_input.get("num_questions", 10),
            question_types=tool_input.get("question_types", ["mcq", "short_answer", "multi_part"]),
            purpose=tool_input.get("purpose", "review"),
        )
        label = "Download Practice Exam"

    elif name == "generate_cheatsheet":
        from apps.api.skills.cheatsheet import generate_cheatsheet

        result = generate_cheatsheet(
            course_id=course_id,
            course_name=_course_name(course_id),
            context_texts=all_context,
            topics=tool_input.get("topics", ["all"]),
            exam_type=tool_input.get("exam_type", "review"),
            content_focus=tool_input.get("content_focus", "comprehensive"),
        )
        label = "Download Cheatsheet"

    else:
        return json.dumps({"error": f"Unknown tool: {name}"})

    state.setdefault("_pending_attachments", []).append(
        Attachment(
            filename=result["pdf_url"].split("/")[-1],
            url=result["pdf_url"],
            preview_urls=result.get("preview_urls", []),
            label=label,
        )
    )
    return json.dumps({"pdf_url": result["pdf_url"], "status": "generated"})


def _run_generation(tool: dict, config_summary: str, done_system: str, state: dict, context_texts: list[str]) -> dict:
    """Force a tool call, run the skill, return a friendly completion message."""
    seed = [{"role": "user", "content": f"{config_summary} Call {tool['name']} now."}]

    resp = _client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=256,
        system=f"You are a tool dispatcher. Call {tool['name']} immediately with the provided parameters.",
        tools=[tool],
        messages=seed,
    )

    tool_results = []
    for block in resp.content:
        if block.type == "tool_use":
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": _dispatch_tool(block.name, block.input, state, context_texts),
            })

    final = _client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=128,
        system=done_system,
        tools=[tool],
        messages=seed + [
            {"role": "assistant", "content": resp.content},
            {"role": "user", "content": tool_results},
        ],
    )
    draft = next(
        (b.text for b in final.content if hasattr(b, "text")),
        "Your file is ready - see the download button below.",
    )
    return {"draft": draft, "citations": [], "attachments": state.pop("_pending_attachments", [])}


# -- Main node ----------------------------------------------------------------

_UNKNOWN_MSG = (
    "I can help you create a **practice exam** or a **cheatsheet** from your course materials. "
    'Just say something like *"make me a practice exam"* or *"generate a cheatsheet"*.'
)

_EXAM_DONE_SYSTEM = (
    "The practice exam PDF has been generated. "
    "Write 1-2 friendly sentences telling the student it's ready and briefly what it covers. "
    "Do not list questions."
)
_CHEAT_DONE_SYSTEM = (
    "The cheatsheet PDF has been generated. "
    "Write 1-2 friendly sentences telling the student their cheatsheet is ready and what it covers."
)


def generate_node(state: dict) -> dict:
    messages = state.get("messages", [])
    intent: str = state.get("intent", "unknown")
    last_user = next(
        (m.content for m in reversed(messages) if getattr(m, "type", None) == "human"), ""
    )

    if intent == "practice_exam":
        return {"draft": _EXAM_QUESTIONNAIRE, "citations": [], "attachments": []}

    if intent == "exam_config":
        cfg = _parse_config(last_user, _PARSE_EXAM_SYSTEM, {
            "topics": ["all"], "weeks": [], "difficulty": "medium",
            "num_questions": 10, "question_types": ["mcq", "short_answer", "multi_part"],
            "purpose": "review",
        })
        context_texts = _retrieve_context(cfg["topics"], cfg.get("weeks") or None)
        summary = (
            f"Generate a practice exam: topics={cfg['topics']}, "
            f"difficulty={cfg['difficulty']}, num_questions={cfg['num_questions']}, "
            f"question_types={cfg['question_types']}, purpose={cfg.get('purpose', 'review')}."
        )
        return _run_generation(_EXAM_TOOL, summary, _EXAM_DONE_SYSTEM, state, context_texts)

    if intent == "cheatsheet":
        return {"draft": _CHEAT_QUESTIONNAIRE, "citations": [], "attachments": []}

    if intent == "cheatsheet_config":
        cfg = _parse_config(last_user, _PARSE_CHEAT_SYSTEM, {
            "topics": ["all"], "weeks": [], "exam_type": "review",
            "content_focus": "comprehensive",
        })
        context_texts = _retrieve_context(cfg["topics"], cfg.get("weeks") or None)
        summary = (
            f"Generate a cheatsheet: topics={cfg['topics']}, "
            f"exam_type={cfg.get('exam_type', 'review')}, "
            f"content_focus={cfg.get('content_focus', 'comprehensive')}."
        )
        return _run_generation(_CHEAT_TOOL, summary, _CHEAT_DONE_SYSTEM, state, context_texts)

    return {"draft": _UNKNOWN_MSG, "citations": [], "attachments": []}
