"""The life timeline: notable records from every domain, in date order.

What counts as notable:
- life events, decisions, person interactions and music memories at or above
  ``min_importance``;
- journal entries only at "notable" (3) or above, since every chat log creates one;
- expenses only at or above MAJOR_PURCHASE_AMOUNT (home currency).
Private (vault) records never appear.
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.expense import Expense
from app.models.journal import JournalEntry
from app.models.people import MusicMemory, Person, PersonInteraction
from app.models.planning import Decision
from app.models.report import LifeEvent
from app.reports.privacy import not_private
from app.reports.render import format_money
from app.schemas.report import TimelineItem

JOURNAL_MIN_IMPORTANCE = 3
DETAIL_MAX = 280


def _clip(text: str | None) -> str | None:
    if not text:
        return None
    text = " ".join(text.split())
    return text if len(text) <= DETAIL_MAX else text[: DETAIL_MAX - 1] + "…"


def _in_range(stmt, column, date_from: date | None, date_to: date | None):
    if date_from is not None:
        stmt = stmt.where(column >= date_from)
    if date_to is not None:
        stmt = stmt.where(column <= date_to)
    return stmt


def get_timeline(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    min_importance: int = 2,
    limit: int = 200,
) -> list[TimelineItem]:
    items: list[TimelineItem] = []

    stmt = select(LifeEvent).where(
        LifeEvent.importance_score >= min_importance, not_private(LifeEvent)
    )
    for e in db.scalars(_in_range(stmt, LifeEvent.event_date, date_from, date_to)):
        items.append(
            TimelineItem(
                kind="event",
                id=e.id,
                date=e.event_date,
                title=e.title,
                detail=_clip(e.description),
                importance_score=e.importance_score,
            )
        )

    stmt = select(Decision).where(
        Decision.importance_score >= min_importance, not_private(Decision)
    )
    for d in db.scalars(_in_range(stmt, Decision.decision_date, date_from, date_to)):
        items.append(
            TimelineItem(
                kind="decision",
                id=d.id,
                date=d.decision_date,
                title=d.title,
                detail=_clip(d.reasoning or d.decision),
                importance_score=d.importance_score,
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
            TimelineItem(
                kind="interaction",
                id=i.id,
                date=i.interaction_date,
                title=f"With {name}",
                detail=_clip(i.summary),
                importance_score=i.importance_score,
            )
        )

    stmt = select(MusicMemory).where(
        MusicMemory.importance_score >= min_importance, not_private(MusicMemory)
    )
    for m in db.scalars(_in_range(stmt, MusicMemory.memory_date, date_from, date_to)):
        title = m.song + (f" by {m.artist}" if m.artist else "")
        items.append(
            TimelineItem(
                kind="music",
                id=m.id,
                date=m.memory_date,
                title=title,
                detail=_clip(m.memory_text),
                importance_score=m.importance_score,
            )
        )

    stmt = select(JournalEntry).where(
        JournalEntry.is_private.is_(False),
        JournalEntry.importance_score >= max(min_importance, JOURNAL_MIN_IMPORTANCE),
    )
    for j in db.scalars(_in_range(stmt, JournalEntry.entry_date, date_from, date_to)):
        items.append(
            TimelineItem(
                kind="journal",
                id=j.id,
                date=j.entry_date,
                title=j.ai_summary or _clip(j.raw_text.splitlines()[0]) or "Journal",
                detail=_clip(j.raw_text),
                importance_score=j.importance_score,
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
        items.append(
            TimelineItem(
                kind="purchase",
                id=x.id,
                date=x.expense_date,
                title=f"{label}: {format_money(x.amount, x.currency)}",
                detail=_clip(x.description if x.merchant else None),
                # Purchases have no importance of their own; treat as notable.
                importance_score=3,
            )
        )

    items.sort(key=lambda item: (item.date, item.importance_score), reverse=True)
    return items[:limit]
