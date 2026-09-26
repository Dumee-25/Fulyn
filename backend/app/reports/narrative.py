"""Optional prose for reports, written by the model strictly from computed facts.

The model receives only the report data (and, for monthly themes, public journal
excerpts). It is told not to add anything. If it is unavailable, reports are still
produced without prose.
"""

import json
import logging
from typing import Any

from app.agent.llm import LLMClient, LLMUnavailableError

logger = logging.getLogger(__name__)

RULES = """\
You write a short recap for the person whose data this is. Speak to them as "you".
Rules:
- Use only facts present in the data. Do not add events, people, places, feelings, \
reasons or numbers that are not there.
- Do not infer times of day, order of events or who was present unless the data states \
it (a coffee at 10:00 does not mean the day was spent in the morning).
- Never claim one thing caused another. You may say things "coincided".
- Do not judge spending or habits. No advice unless asked.
- Plain, warm, concise. No headings, no lists, no emoji.
"""


def _ask(llm: LLMClient, instruction: str, payload: dict[str, Any]) -> str | None:
    messages = [
        {"role": "system", "content": RULES},
        {"role": "user", "content": f"{instruction}\n\nDATA:\n{json.dumps(payload, default=str)}"},
    ]
    try:
        reply = llm.chat(messages, [])
    except LLMUnavailableError:
        logger.info("Narrative skipped: language model unavailable")
        return None
    return reply.content.strip() or None


def daily_narrative(llm: LLMClient | None, data: dict[str, Any]) -> str | None:
    if llm is None:
        return None
    return _ask(llm, "Write 1-2 sentences summarising this day.", data)


def weekly_narrative(llm: LLMClient | None, data: dict[str, Any]) -> str | None:
    if llm is None:
        return None
    return _ask(
        llm,
        "Write 2-3 sentences summarising this week, mentioning notable changes from the "
        "previous week when the data shows them.",
        data,
    )


def monthly_narrative(
    llm: LLMClient | None, data: dict[str, Any], excerpts: list[str]
) -> tuple[str | None, list[str]]:
    """Returns (month in one sentence, recurring themes)."""
    if llm is None:
        return None, []
    text = _ask(
        llm,
        "First line: the month in one sentence. Then, only if the journal excerpts clearly "
        "show them, up to 4 recurring themes, one per line, each starting with '- ' and "
        "naming what recurs (e.g. '- Late nights studying for exams'). Themes must be "
        "supported by at least two excerpts. If there are none, write nothing after the "
        "first line.",
        {**data, "journal_excerpts": excerpts},
    )
    if not text:
        return None, []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    sentence = lines[0].removeprefix("-").strip() if lines else None
    themes = [line[1:].strip() for line in lines[1:] if line.startswith("-")][:4]
    return sentence, themes
