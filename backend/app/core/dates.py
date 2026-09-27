"""Parse the short dates and times people type in chat commands.

Dates: today, yesterday, tomorrow, "3 days ago", weekday names, 2026-09-12, 12/9,
"12", "12th", "12 sept", "sept 12", "12 sep 2025". Times: 9am, 9:30pm, 21:00, 9.30, noon.
Weekday names resolve to the most recent one for past dates and the next one for
future dates ("friday" in /remind means the coming Friday).
"""

import re
from datetime import date, time, timedelta
from typing import Literal

Direction = Literal["past", "future"]

WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


def _month(token: str) -> int | None:
    token = token.lower().rstrip(".")
    if len(token) >= 3:
        for i, name in enumerate(MONTHS):
            if token.startswith(name):
                return i + 1
    return None


def _safe(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_date(text: str, today: date, direction: Direction = "past") -> date | None:
    """Parse the whole of ``text`` as a date, or return None."""
    t = text.strip().lower().rstrip(".,")
    if not t:
        return None
    if t == "today":
        return today
    if t == "yesterday":
        return today - timedelta(days=1)
    if t == "tomorrow":
        return today + timedelta(days=1)

    m = re.fullmatch(r"(\d+)\s+days?\s+ago", t)
    if m:
        return today - timedelta(days=int(m.group(1)))
    m = re.fullmatch(r"in\s+(\d+)\s+days?", t)
    if m:
        return today + timedelta(days=int(m.group(1)))

    for i, name in enumerate(WEEKDAYS):
        if t.startswith(name) and t.isalpha():
            if direction == "past":
                return today - timedelta(days=(today.weekday() - i) % 7 or 7)
            return today + timedelta(days=(i - today.weekday()) % 7 or 7)

    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", t)
    if m:
        return _safe(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    # Day/month[/year], day first (as in Sri Lanka).
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?", t)
    if m:
        year = int(m.group(3)) if m.group(3) else today.year
        year = year + 2000 if year < 100 else year
        return _safe(year, int(m.group(2)), int(m.group(1)))

    # "12", "12th": that day of the current month.
    m = re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)?", t)
    if m:
        return _safe(today.year, today.month, int(m.group(1)))

    # "12 sept [2025]" or "sept 12[th] [2025]".
    m = re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)?\s+([a-z.]+)(?:\s+(\d{4}))?", t) or None
    if m and _month(m.group(2)):
        year = int(m.group(3)) if m.group(3) else today.year
        return _safe(year, _month(m.group(2)), int(m.group(1)))
    m = re.fullmatch(r"([a-z.]+)\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?", t)
    if m and _month(m.group(1)):
        year = int(m.group(3)) if m.group(3) else today.year
        return _safe(year, _month(m.group(1)), int(m.group(2)))
    return None


def parse_time(text: str) -> time | None:
    """Parse the whole of ``text`` as a time of day, or return None."""
    t = text.strip().lower().replace(" ", "")
    if t == "noon":
        return time(12, 0)
    if t == "midnight":
        return time(0, 0)
    m = re.fullmatch(r"(\d{1,2})(?:[:.](\d{2}))?(am|pm)?", t)
    if not m or (m.group(2) is None and m.group(3) is None):
        return None
    hour, minute = int(m.group(1)), int(m.group(2) or 0)
    if m.group(3):
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if m.group(3) == "pm" else 0)
    if hour > 23 or minute > 59:
        return None
    return time(hour, minute)


def take_date(words: list[str], today: date, direction: Direction = "past"):
    """Parse the longest date at the start of ``words``: (date, remaining words)."""
    for n in (3, 2, 1):
        if len(words) >= n:
            parsed = parse_date(" ".join(words[:n]), today, direction)
            if parsed:
                return parsed, words[n:]
    return None, words


def take_time(words: list[str]):
    """Find a time anywhere in ``words``: (time, remaining words)."""
    for i, word in enumerate(words):
        # Allow "9 am" as two words.
        if i + 1 < len(words) and words[i + 1].lower() in ("am", "pm"):
            parsed = parse_time(word + words[i + 1])
            if parsed:
                return parsed, words[:i] + words[i + 2 :]
        parsed = parse_time(word)
        if parsed:
            return parsed, words[:i] + words[i + 1 :]
    return None, words


def parse_month(text: str, today: date) -> tuple[int, int] | None:
    """'september', 'sep 2025', '2025-09', 'last', 'this' or '' -> (year, month)."""
    t = text.strip().lower()
    if t in ("", "this", "this month"):
        return today.year, today.month
    if t in ("last", "last month"):
        first = today.replace(day=1) - timedelta(days=1)
        return first.year, first.month
    m = re.fullmatch(r"(\d{4})-(\d{1,2})", t)
    if m and 1 <= int(m.group(2)) <= 12:
        return int(m.group(1)), int(m.group(2))
    parts = t.split()
    month = _month(parts[0]) if parts else None
    if month and len(parts) <= 2:
        if len(parts) == 2 and parts[1].isdigit():
            return int(parts[1]), month
        # A month name alone means the most recent one (this year, or last year if later).
        year = today.year if month <= today.month else today.year - 1
        return year, month
    return None
