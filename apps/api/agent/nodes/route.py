"""Keyword router — no LLM call needed for a two-skill system.

Detects two questionnaire sentinels embedded in the previous AI message
so the student's reply bypasses routing and goes straight to generation.
Everything else is classified by simple regex.
"""

from __future__ import annotations

import re

EXAM_Q_MARKER  = "<!-- EXAM_Q -->"
CHEAT_Q_MARKER = "<!-- CHEAT_Q -->"

_EXAM_RE = re.compile(
    r"\b(practice[\s-]exam|practice[\s-]quiz|mock[\s-]exam|mock[\s-]quiz"
    r"|make\s+(me\s+)?(a\s+)?(quiz|exam|test)|generate\s+(a\s+)?(quiz|exam)"
    r"|create\s+(a\s+)?(quiz|exam)|quiz\s+me|test\s+me)\b",
    re.IGNORECASE,
)
_CHEAT_RE = re.compile(
    r"\b(cheat[\s-]?sheet|crib[\s-]sheet|reference[\s-]sheet|study[\s-]sheet"
    r"|make\s+(me\s+)?(a\s+)?cheat|one[\s-]?pager|formula[\s-]sheet)\b",
    re.IGNORECASE,
)


def _last_ai_content(messages: list) -> str:
    for m in reversed(messages):
        if getattr(m, "type", None) == "ai":
            return m.content
    return ""


def route_node(state: dict) -> dict:
    messages = state.get("messages", [])
    last_ai = _last_ai_content(messages)

    # Student just answered a setup questionnaire — skip classification
    if EXAM_Q_MARKER in last_ai:
        return {"intent": "exam_config"}
    if CHEAT_Q_MARKER in last_ai:
        return {"intent": "cheatsheet_config"}

    last_user = ""
    for m in reversed(messages):
        if getattr(m, "type", None) == "human":
            last_user = m.content
            break

    if _EXAM_RE.search(last_user):
        return {"intent": "practice_exam"}
    if _CHEAT_RE.search(last_user):
        return {"intent": "cheatsheet"}
    return {"intent": "unknown"}
