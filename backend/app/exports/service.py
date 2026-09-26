"""Data export: everything you logged, in open formats.

- ``build_zip(private=False)``: journal/ as Markdown, one CSV per record type, memories.json
  and conversations.json. Vault content is never included.
- ``build_zip(private=True)``: the separate vault export, only private content.
- ``full_json``: all non-secret application data in one JSON document.

Embeddings and full-text vectors are derived data and are left out.
"""

import csv
import io
import json
import zipfile
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.time import now_local
from app.core.version import __version__
from app.models import (
    CaffeineLog,
    ChatMessage,
    Conversation,
    DailyRecap,
    Decision,
    Expense,
    JournalEntry,
    LifeEvent,
    Memory,
    MonthlyReport,
    MoodLog,
    MusicMemory,
    Person,
    PersonInteraction,
    Reminder,
    SleepLog,
    Subscription,
    WaitingItem,
    WeeklyRecap,
)
from app.vault.filters import not_private

SKIP_COLUMNS = {"embedding", "search_vector"}

# File name -> model. Models with journal_entry_id follow their journal entry's privacy.
CSV_FILES: dict[str, Any] = {
    "expenses.csv": Expense,
    "moods.csv": MoodLog,
    "sleep.csv": SleepLog,
    "caffeine.csv": CaffeineLog,
    "people.csv": Person,
    "interactions.csv": PersonInteraction,
    "music_memories.csv": MusicMemory,
    "subscriptions.csv": Subscription,
    "reminders.csv": Reminder,
    "decisions.csv": Decision,
    "waiting_items.csv": WaitingItem,
    "life_events.csv": LifeEvent,
}
# People, subscriptions, reminders and waiting items have no journal link: never private.
NO_PRIVACY = {Person, Subscription, Reminder, WaitingItem}


def _columns(model: Any) -> list[str]:
    """id first, timestamps last, the rest in declaration order."""
    names = [c.key for c in inspect(model).columns if c.key not in SKIP_COLUMNS]
    last = [n for n in ("created_at", "updated_at") if n in names]
    middle = [n for n in names if n != "id" and n not in last]
    return (["id"] if "id" in names else []) + middle + last


def _value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(get_settings().tz).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if value is None:
        return ""
    return value if isinstance(value, bool | int | float) else str(value)


def _json_value(value: Any) -> Any:
    return None if value is None else _value(value)


def _rows(db: Session, model: Any, private: bool) -> list[Any]:
    stmt = select(model)
    if model is JournalEntry:
        stmt = stmt.where(JournalEntry.is_private.is_(private)).order_by(
            JournalEntry.entry_date, JournalEntry.created_at
        )
    elif model is Memory:
        stmt = stmt.where(Memory.is_private.is_(private)).order_by(Memory.memory_date)
    elif model in NO_PRIVACY:
        if private:
            return []
    else:
        privacy = not_private(model)
        stmt = stmt.where(~privacy if private else privacy)
    if "created_at" in _columns(model) and model not in (JournalEntry, Memory):
        stmt = stmt.order_by(model.created_at)
    return list(db.scalars(stmt))


def _csv(model: Any, rows: list[Any]) -> str:
    buffer = io.StringIO()
    columns = _columns(model)
    writer = csv.writer(buffer)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([_value(getattr(row, c)) for c in columns])
    return buffer.getvalue()


def _records(model: Any, rows: list[Any]) -> list[dict[str, Any]]:
    columns = _columns(model)
    return [{c: _json_value(getattr(row, c)) for c in columns} for row in rows]


def journal_markdown(db: Session, entries: list[JournalEntry]) -> dict[str, str]:
    """One Markdown file per day, e.g. journal/2026-09-26.md."""
    moods: dict[Any, str] = {}
    for mood in db.scalars(
        select(MoodLog).where(MoodLog.journal_entry_id.in_([e.id for e in entries]))
    ):
        moods[mood.journal_entry_id] = (mood.label or f"{mood.score}/10").capitalize()
    by_day: dict[date, list[JournalEntry]] = defaultdict(list)
    for entry in entries:
        by_day[entry.entry_date].append(entry)
    files = {}
    for day, day_entries in sorted(by_day.items()):
        parts = []
        for entry in day_entries:
            meta = []
            mood = entry.mood_summary or moods.get(entry.id)
            if mood:
                meta.append(f"Mood: {mood}")
            meta.append(f"Importance: {entry.importance_score}")
            if entry.ai_summary:
                meta.append(f"Summary: {entry.ai_summary}")
            parts.append(f"{entry.raw_text.strip()}\n\n" + "\n".join(meta))
        heading = f"# {day.strftime('%B')} {day.day}, {day.year}"
        files[f"journal/{day.isoformat()}.md"] = heading + "\n\n" + "\n\n---\n\n".join(parts) + "\n"
    return files


def _conversations(db: Session) -> list[dict[str, Any]]:
    out = []
    for conversation in db.scalars(select(Conversation).order_by(Conversation.created_at)):
        messages = db.scalars(
            select(ChatMessage)
            .where(
                ChatMessage.conversation_id == conversation.id,
                ChatMessage.is_private.is_(False),
                ChatMessage.role.in_(["user", "assistant"]),
                ChatMessage.content != "",
            )
            .order_by(ChatMessage.created_at)
        )
        out.append(
            {
                "id": str(conversation.id),
                "title": conversation.title,
                "created_at": _json_value(conversation.created_at),
                "messages": [
                    {"role": m.role, "content": m.content, "at": _json_value(m.created_at)}
                    for m in messages
                ],
            }
        )
    return out


def _manifest(private: bool) -> str:
    kind = "VAULT (private content only)" if private else "Fulyn export (vault not included)"
    return (
        f"{kind}\n"
        f"Created {now_local().isoformat(timespec='seconds')} by Fulyn {__version__}.\n"
        f"Times are in {get_settings().default_timezone}; amounts are exact decimals.\n"
        "journal/ holds one Markdown file per day; other records are CSV; memories.json\n"
        "is the searchable memory index (without embeddings).\n"
    )


def build_zip(db: Session, *, private: bool = False) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("README.txt", _manifest(private))
        entries = _rows(db, JournalEntry, private)
        for name, text in journal_markdown(db, entries).items():
            archive.writestr(name, text)
        for name, model in CSV_FILES.items():
            if private and model in NO_PRIVACY:
                continue
            archive.writestr(name, _csv(model, _rows(db, model, private)))
        archive.writestr(
            "memories.json",
            json.dumps(_records(Memory, _rows(db, Memory, private)), indent=2, ensure_ascii=False),
        )
        if not private:
            archive.writestr(
                "conversations.json",
                json.dumps(_conversations(db), indent=2, ensure_ascii=False),
            )
    return buffer.getvalue()


def expenses_csv(db: Session) -> str:
    return _csv(Expense, _rows(db, Expense, private=False))


def full_json(db: Session) -> dict[str, Any]:
    """All non-secret, non-vault data. Settings are included without secrets."""
    settings = get_settings()
    data: dict[str, Any] = {
        "exported_at": now_local().isoformat(timespec="seconds"),
        "app_version": __version__,
        "settings": {
            "timezone": settings.default_timezone,
            "currency": settings.default_currency,
            "expense_categories": settings.expense_categories,
        },
        "journal_entries": _records(JournalEntry, _rows(db, JournalEntry, False)),
        "memories": _records(Memory, _rows(db, Memory, False)),
        "conversations": _conversations(db),
    }
    for name, model in CSV_FILES.items():
        data[name.removesuffix(".csv")] = _records(model, _rows(db, model, False))
    for key, model in (
        ("daily_recaps", DailyRecap),
        ("weekly_recaps", WeeklyRecap),
        ("monthly_reports", MonthlyReport),
    ):
        data[key] = _records(model, list(db.scalars(select(model))))
    return data
