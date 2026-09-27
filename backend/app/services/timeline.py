"""The life timeline: one card per day, built from that day's notable records.

What counts as notable:
- life events, decisions, person interactions and music memories at or above
  ``min_importance``;
- journal entries only at "notable" (3) or above, since every chat log creates one;
- expenses only at or above MAJOR_PURCHASE_AMOUNT (home currency).
Private (vault) records never appear.

Records logged by the same chat message share a journal entry and form one moment, so a
message that created a journal entry, an interaction and a life event shows once. Each day
gets a headline, its highest importance, a short summary and tags, all computed here
without a model; a stored daily recap's narrative replaces the summary when there is one.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.expense import Expense
from app.models.journal import JournalEntry
from app.models.people import MusicMemory, Person, PersonInteraction
from app.models.planning import Decision
from app.models.report import DailyRecap, LifeEvent
from app.reports.privacy import not_private
from app.reports.render import format_money
from app.schemas.report import TimelineDay, TimelineKind, TimelineMoment, TimelineTag
from app.services.reports import EMPTY

JOURNAL_MIN_IMPORTANCE = 3
DETAIL_MAX = 280
LINE_MAX = 120
# Which record names a day or a moment when importance ties.
KIND_ORDER: dict[TimelineKind, int] = {
    "event": 0,
    "decision": 1,
    "interaction": 2,
    "music": 3,
    "journal": 4,
    "purchase": 5,
}
SUMMARY_HIGHLIGHTS = 3


@dataclass
class _Item:
    kind: TimelineKind
    id: uuid.UUID
    date: date
    title: str
    detail: str | None
    importance_score: int
    journal_entry_id: uuid.UUID | None = None
    person: str | None = None
    place: str | None = None
    amount: str | None = None


def _clip(text: str | None, limit: int = DETAIL_MAX) -> str | None:
    if not text:
        return None
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _in_range(stmt, column, date_from: date | None, date_to: date | None):
    if date_from is not None:
        stmt = stmt.where(column >= date_from)
    if date_to is not None:
        stmt = stmt.where(column <= date_to)
    return stmt


def _and(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _unique(values: list[str | None]) -> list[str]:
    seen: set[str] = set()
    out = []
    for value in values:
        if value and value.lower() not in seen:
            seen.add(value.lower())
            out.append(value)
    return out


def _rank(item: _Item) -> tuple[int, int]:
    """Most important first; ties go to events, then decisions, interactions, music…"""
    return (-item.importance_score, KIND_ORDER[item.kind])


# --- Collecting notable records ------------------------------------------------------


def _collect(
    db: Session, date_from: date | None, date_to: date | None, min_importance: int
) -> list[_Item]:
    items: list[_Item] = []

    stmt = select(LifeEvent).where(
        LifeEvent.importance_score >= min_importance, not_private(LifeEvent)
    )
    for e in db.scalars(_in_range(stmt, LifeEvent.event_date, date_from, date_to)):
        items.append(
            _Item(
                "event",
                e.id,
                e.event_date,
                e.title,
                _clip(e.description),
                e.importance_score,
                e.journal_entry_id,
            )
        )

    stmt = select(Decision).where(
        Decision.importance_score >= min_importance, not_private(Decision)
    )
    for d in db.scalars(_in_range(stmt, Decision.decision_date, date_from, date_to)):
        items.append(
            _Item(
                "decision",
                d.id,
                d.decision_date,
                d.title,
                _clip(d.reasoning or d.decision),
                d.importance_score,
                d.journal_entry_id,
            )
        )

    stmt = (
        select(PersonInteraction, Person.name)
        .join(Person, Person.id == PersonInteraction.person_id)
        .where(
            PersonInteraction.importance_score >= min_importance,
            not_private(PersonInteraction),
        )
    )
    stmt = _in_range(stmt, PersonInteraction.interaction_date, date_from, date_to)
    for i, name in db.execute(stmt).all():
        items.append(
            _Item(
                "interaction",
                i.id,
                i.interaction_date,
                f"With {name}",
                _clip(i.summary),
                i.importance_score,
                i.journal_entry_id,
                person=name,
                place=i.location,
            )
        )

    stmt = (
        select(MusicMemory, Person.name)
        .outerjoin(Person, Person.id == MusicMemory.person_id)
        .where(MusicMemory.importance_score >= min_importance, not_private(MusicMemory))
    )
    stmt = _in_range(stmt, MusicMemory.memory_date, date_from, date_to)
    for m, name in db.execute(stmt).all():
        items.append(
            _Item(
                "music",
                m.id,
                m.memory_date,
                m.song + (f" by {m.artist}" if m.artist else ""),
                _clip(m.memory_text),
                m.importance_score,
                m.journal_entry_id,
                person=name,
            )
        )

    stmt = select(JournalEntry).where(
        JournalEntry.is_private.is_(False),
        JournalEntry.importance_score >= max(min_importance, JOURNAL_MIN_IMPORTANCE),
    )
    for j in db.scalars(_in_range(stmt, JournalEntry.entry_date, date_from, date_to)):
        items.append(
            _Item(
                "journal",
                j.id,
                j.entry_date,
                j.ai_summary or _clip(j.raw_text.splitlines()[0], LINE_MAX) or "Journal",
                _clip(j.raw_text),
                j.importance_score,
                j.id,
            )
        )

    settings = get_settings()
    stmt = select(Expense).where(
        Expense.currency == settings.default_currency,
        Expense.amount >= settings.major_purchase_amount,
        not_private(Expense),
    )
    for x in db.scalars(_in_range(stmt, Expense.expense_date, date_from, date_to)):
        label = x.merchant or x.description or x.category
        money = format_money(x.amount, x.currency)
        items.append(
            _Item(
                "purchase",
                x.id,
                x.expense_date,
                f"{label}: {money}",
                _clip(x.description if x.merchant else None),
                # Purchases have no importance of their own; treat as notable.
                3,
                x.journal_entry_id,
                amount=f"{money} ({label})",
            )
        )
    return items


# --- Moments and days ----------------------------------------------------------------


def _moment_line(items: list[_Item]) -> str:
    """The moment's best record, plus who it was with when that isn't already said."""
    best = min(items, key=_rank)
    people = _unique([i.person for i in items if i.kind == "interaction"])
    if best.kind == "interaction":
        places = _unique([i.place for i in items if i.kind == "interaction"])
        line = f"With {_and(people)}" + (f" at {_and(places)}" if places else "")
    elif people and best.kind != "purchase":
        line = f"{best.title}, with {_and(people)}"
    else:
        line = best.title
    return _clip(line, LINE_MAX) or best.title


def _moment(items: list[_Item], raw_text: dict[uuid.UUID, str]) -> TimelineMoment:
    items = sorted(items, key=_rank)
    entry_id = items[0].journal_entry_id
    text = raw_text.get(entry_id) if entry_id else None
    return TimelineMoment(
        journal_entry_id=entry_id,
        kinds=sorted({i.kind for i in items}, key=KIND_ORDER.__getitem__),
        line=_moment_line(items),
        text=text or items[0].detail,
        importance_score=max(i.importance_score for i in items),
    )


def _summary(items: list[_Item], headline: _Item) -> str | None:
    """A few plain sentences from the records: who with, where, what else, what it cost."""
    sentences = []
    people = _unique([i.person for i in items if i.kind == "interaction"])
    places = _unique([i.place for i in items if i.kind == "interaction"])
    if people:
        sentences.append(f"With {_and(people)}" + (f" at {_and(places)}" if places else "") + ".")
    highlights = _unique(
        [
            i.title if i.kind in ("event", "music") else f"Decided: {i.title}"
            for i in sorted(items, key=_rank)
            if i.kind in ("event", "decision", "music") and i is not headline
        ]
    )
    if highlights:
        more = len(highlights) - SUMMARY_HIGHLIGHTS
        text = "; ".join(highlights[:SUMMARY_HIGHLIGHTS]) + (f" (+{more} more)" if more > 0 else "")
        sentences.append(f"Also: {text}." if headline.kind == "event" else f"{text}.")
    amounts = _unique([i.amount for i in items if i.amount])
    if amounts:
        sentences.append(f"Spent {_and(amounts)}.")
    if not sentences:
        others = _unique(
            [i.title for i in sorted(items, key=_rank) if i.kind == "journal" and i is not headline]
        )
        if others:
            sentences.append("; ".join(others[:SUMMARY_HIGHLIGHTS]) + ".")
    return " ".join(sentences) or None


def _recap_narrative(recap: DailyRecap) -> str | None:
    """The model-written first paragraph of a stored daily recap, if it has one."""
    if "narrative" in recap.data:
        return recap.data["narrative"] or None
    # Recaps stored before the narrative was kept in data: "# Day\n\n<narrative>\n\n## …".
    blocks = [b.strip() for b in recap.content.split("\n\n") if b.strip()]
    if len(blocks) > 1 and blocks[0].startswith("# ") and not blocks[1].startswith("#"):
        return blocks[1] if blocks[1] != EMPTY else None
    return None


def _day(
    day: date,
    items: list[_Item],
    raw_text: dict[uuid.UUID, str],
    narrative: str | None,
) -> TimelineDay:
    groups: dict[tuple[str, uuid.UUID], list[_Item]] = defaultdict(list)
    for item in items:
        key = ("journal", item.journal_entry_id) if item.journal_entry_id else (item.kind, item.id)
        groups[key].append(item)
    moments = sorted(
        (_moment(group, raw_text) for group in groups.values()),
        key=lambda m: (-m.importance_score, KIND_ORDER[m.kinds[0]]),
    )
    headline = min(items, key=_rank)
    tags = [
        *(
            TimelineTag(kind="person", label=p)
            for p in _unique([i.person for i in sorted(items, key=_rank)])
        ),
        *(
            TimelineTag(kind="place", label=p)
            for p in _unique([i.place for i in sorted(items, key=_rank)])
        ),
        *(TimelineTag(kind="amount", label=a) for a in _unique([i.amount for i in items])),
    ]
    return TimelineDay(
        date=day,
        headline=headline.title,
        headline_kind=headline.kind,
        importance_score=max(i.importance_score for i in items),
        summary=narrative or _summary(items, headline),
        summary_source="recap" if narrative else "records",
        tags=tags,
        moments=moments,
    )


def get_timeline(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    min_importance: int = 2,
    limit: int = 200,
) -> list[TimelineDay]:
    """One item per day, newest first. ``limit`` counts days."""
    by_day: dict[date, list[_Item]] = defaultdict(list)
    for item in _collect(db, date_from, date_to, min_importance):
        by_day[item.date].append(item)
    days = sorted(by_day, reverse=True)[: max(1, limit)]
    if not days:
        return []

    entry_ids = {i.journal_entry_id for d in days for i in by_day[d] if i.journal_entry_id}
    raw_text = dict(
        db.execute(
            select(JournalEntry.id, JournalEntry.raw_text).where(
                JournalEntry.id.in_(entry_ids), JournalEntry.is_private.is_(False)
            )
        ).all()
    )
    narratives = {
        r.date: _recap_narrative(r)
        for r in db.scalars(select(DailyRecap).where(DailyRecap.date.in_(days)))
    }
    return [_day(d, by_day[d], raw_text, narratives.get(d)) for d in days]
