"""Structured data for recaps and reports, computed from stored records only.

Everything returned is JSON-ready (decimals as strings, dates ISO). Private (vault)
records are excluded. Nothing here calls the language model.
"""

from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from statistics import median
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.time import today_local
from app.models.caffeine import CaffeineLog
from app.models.expense import Expense
from app.models.journal import JournalEntry
from app.models.memory import Memory
from app.models.mood import MoodLog
from app.models.people import MusicMemory, Person, PersonInteraction
from app.models.planning import Decision, WaitingItem
from app.models.report import LifeEvent
from app.models.sleep import SleepLog
from app.reports.privacy import not_private
from app.services.planning import summarize_subscriptions

ZERO = Decimal("0.00")
# Minimum difference in average sleep before a caffeine/sleep coincidence is reported.
COINCIDENCE_MIN_MINUTES = 30
COINCIDENCE_MIN_PAIRS = 3


def _money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01")))


def _avg(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


def _days(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def _local_bounds(start: date, end: date) -> tuple[datetime, datetime]:
    tz = get_settings().tz
    return (
        datetime.combine(start, time.min, tzinfo=tz),
        datetime.combine(end + timedelta(days=1), time.min, tzinfo=tz),
    )


# --- Sections ----------------------------------------------------------------------


def spending(db: Session, start: date, end: date) -> dict[str, Any]:
    currency = get_settings().default_currency
    rows = db.execute(
        select(Expense.category, Expense.amount, Expense.is_impulse, Expense.expense_date).where(
            Expense.currency == currency,
            Expense.expense_date.between(start, end),
            not_private(Expense),
        )
    ).all()
    total = sum((r.amount for r in rows), ZERO)
    impulse = sum((r.amount for r in rows if r.is_impulse), ZERO)
    by_category: dict[str, Decimal] = defaultdict(lambda: ZERO)
    by_day: dict[date, Decimal] = defaultdict(lambda: ZERO)
    for r in rows:
        by_category[r.category] += r.amount
        by_day[r.expense_date] += r.amount
    return {
        "currency": currency,
        "total": _money(total),
        "impulse_total": _money(impulse),
        "count": len(rows),
        "by_category": [
            {"category": c, "total": _money(t)}
            for c, t in sorted(by_category.items(), key=lambda kv: kv[1], reverse=True)
        ],
        "by_day": {d.isoformat(): _money(t) for d, t in sorted(by_day.items())},
    }


def mood(db: Session, start: date, end: date) -> dict[str, Any]:
    logs = list(
        db.scalars(
            select(MoodLog)
            .where(MoodLog.date.between(start, end), not_private(MoodLog))
            .order_by(MoodLog.date, MoodLog.created_at)
        )
    )
    scores = [m.score for m in logs if m.score is not None]
    energy = [m.energy_score for m in logs if m.energy_score is not None]
    per_day: dict[date, list[int]] = defaultdict(list)
    for m in logs:
        if m.score is not None:
            per_day[m.date].append(m.score)
    return {
        "count": len(logs),
        "average_score": _avg(scores),
        "average_energy": _avg(energy),
        "labels": dict(Counter(m.label for m in logs if m.label).most_common()),
        "by_day": {d.isoformat(): _avg(v) for d, v in sorted(per_day.items())},
    }


def sleep(db: Session, start: date, end: date) -> dict[str, Any]:
    logs = list(
        db.scalars(
            select(SleepLog)
            .where(SleepLog.sleep_date.between(start, end), not_private(SleepLog))
            .order_by(SleepLog.sleep_date)
        )
    )
    durations = {
        log.sleep_date: log.duration_minutes for log in logs if log.duration_minutes is not None
    }
    return {
        "nights": len(durations),
        "average_minutes": round(sum(durations.values()) / len(durations)) if durations else None,
        "shortest_minutes": min(durations.values(), default=None),
        "longest_minutes": max(durations.values(), default=None),
        "any_approximate": any(log.is_approximate for log in logs),
        "by_day": {d.isoformat(): m for d, m in sorted(durations.items())},
    }


def caffeine(db: Session, start: date, end: date) -> dict[str, Any]:
    low, high = _local_bounds(start, end)
    tz = get_settings().tz
    logs = list(
        db.scalars(
            select(CaffeineLog)
            .where(
                CaffeineLog.consumed_at >= low,
                CaffeineLog.consumed_at < high,
                not_private(CaffeineLog),
            )
            .order_by(CaffeineLog.consumed_at)
        )
    )
    per_day: dict[date, float] = defaultdict(float)
    latest: dict[date, str] = {}
    for log in logs:
        local = log.consumed_at.astimezone(tz)
        per_day[local.date()] += float(log.quantity)
        latest[local.date()] = local.strftime("%H:%M")
    days = len(_days(start, end))
    total = sum(per_day.values())
    return {
        "drinks": round(total, 2),
        "per_day_average": round(total / days, 2) if days else None,
        "drinks_by_type": dict(Counter(log.drink_type.lower() for log in logs).most_common()),
        "by_day": {d.isoformat(): round(n, 2) for d, n in sorted(per_day.items())},
        "latest_time_by_day": {d.isoformat(): t for d, t in sorted(latest.items())},
        "items": [
            {
                "drink": log.drink_type,
                "time": log.consumed_at.astimezone(tz).strftime("%H:%M"),
                "approximate": log.is_approximate,
            }
            for log in logs
        ]
        if days == 1
        else [],
    }


def people(db: Session, start: date, end: date) -> dict[str, Any]:
    rows = db.execute(
        select(PersonInteraction, Person.name)
        .join(Person, Person.id == PersonInteraction.person_id)
        .where(
            PersonInteraction.interaction_date.between(start, end),
            not_private(PersonInteraction),
        )
        .order_by(PersonInteraction.interaction_date, PersonInteraction.created_at)
    ).all()
    counts = Counter(name for _, name in rows)
    return {
        "interaction_count": len(rows),
        # Alphabetical on purpose: people are never ranked.
        "by_person": [{"name": n, "count": counts[n]} for n in sorted(counts, key=str.lower)],
        "interactions": [
            {
                "date": i.interaction_date.isoformat(),
                "person": name,
                "summary": i.summary,
                "location": i.location,
                "importance": i.importance_score,
            }
            for i, name in rows
        ],
    }


def music(db: Session, start: date, end: date) -> dict[str, Any]:
    items = list(
        db.scalars(
            select(MusicMemory)
            .where(MusicMemory.memory_date.between(start, end), not_private(MusicMemory))
            .order_by(MusicMemory.memory_date)
        )
    )
    counts = Counter((m.song, m.artist) for m in items)
    return {
        "count": len(items),
        "most_mentioned": [
            {"song": s, "artist": a, "count": n} for (s, a), n in counts.most_common(5)
        ],
        "items": [
            {
                "date": m.memory_date.isoformat(),
                "song": m.song,
                "artist": m.artist,
                "emotion": m.emotion,
                "memory": m.memory_text,
            }
            for m in items
        ],
    }


def decisions(db: Session, start: date, end: date) -> list[dict[str, Any]]:
    return [
        {
            "date": d.decision_date.isoformat(),
            "title": d.title,
            "decision": d.decision,
            "reasoning": d.reasoning,
            "status": d.status,
        }
        for d in db.scalars(
            select(Decision)
            .where(Decision.decision_date.between(start, end), not_private(Decision))
            .order_by(Decision.decision_date)
        )
    ]


def events(db: Session, start: date, end: date) -> list[dict[str, Any]]:
    return [
        {
            "date": e.event_date.isoformat(),
            "title": e.title,
            "description": e.description,
            "importance": e.importance_score,
        }
        for e in db.scalars(
            select(LifeEvent)
            .where(LifeEvent.event_date.between(start, end), not_private(LifeEvent))
            .order_by(LifeEvent.event_date)
        )
    ]


def important_memories(db: Session, start: date, end: date, min_importance: int = 4) -> list:
    return [
        {
            "date": m.memory_date.isoformat(),
            "type": m.memory_type,
            "title": m.title,
            "importance": m.importance_score,
        }
        for m in db.scalars(
            select(Memory)
            .where(
                Memory.memory_date.between(start, end),
                Memory.importance_score >= min_importance,
                Memory.is_private.is_(False),
            )
            .order_by(Memory.importance_score.desc(), Memory.memory_date)
            .limit(10)
        )
    ]


def waiting(db: Session, start: date, end: date) -> dict[str, Any]:
    today = today_local()
    open_items = list(
        db.scalars(
            select(WaitingItem)
            .where(WaitingItem.status == "waiting")
            .order_by(WaitingItem.waiting_since)
        )
    )
    resolved = list(
        db.scalars(
            select(WaitingItem).where(
                WaitingItem.status == "received", WaitingItem.resolved_at.between(start, end)
            )
        )
    )
    return {
        "open": [
            {
                "title": w.title,
                "since": w.waiting_since.isoformat(),
                "overdue": w.expected_by is not None and w.expected_by < today,
            }
            for w in open_items
        ],
        "received": [w.title for w in resolved],
    }


def journal_count(db: Session, start: date, end: date) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(JournalEntry)
            .where(JournalEntry.entry_date.between(start, end), JournalEntry.is_private.is_(False))
        )
        or 0
    )


def journal_excerpts(db: Session, start: date, end: date, limit: int = 40) -> list[str]:
    """Public journal text for the narrative's theme detection (not stored in reports)."""
    entries = db.scalars(
        select(JournalEntry)
        .where(JournalEntry.entry_date.between(start, end), JournalEntry.is_private.is_(False))
        .order_by(JournalEntry.importance_score.desc(), JournalEntry.entry_date)
        .limit(limit)
    )
    return [f"{e.entry_date.isoformat()}: {e.raw_text[:300]}" for e in entries]


def caffeine_sleep_coincidence(
    caffeine_by_day: dict[str, float], sleep_by_day: dict[str, int]
) -> dict[str, Any] | None:
    """Compare sleep after higher- vs lower-caffeine days. Describes, never explains.

    A day's caffeine is paired with the sleep logged on the following date (the night after).
    """
    pairs = []
    for day, drinks in caffeine_by_day.items():
        next_day = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
        if next_day in sleep_by_day:
            pairs.append((drinks, sleep_by_day[next_day]))
    if len(pairs) < COINCIDENCE_MIN_PAIRS:
        return None
    cut = median(d for d, _ in pairs)
    high = [s for d, s in pairs if d > cut]
    low = [s for d, s in pairs if d <= cut]
    if not high or not low:
        return None
    diff = round(sum(low) / len(low) - sum(high) / len(high))
    if abs(diff) < COINCIDENCE_MIN_MINUTES:
        return None
    return {"pairs": len(pairs), "sleep_difference_minutes": diff}


# --- Periods -----------------------------------------------------------------------


def period(db: Session, start: date, end: date) -> dict[str, Any]:
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "journal_entries": journal_count(db, start, end),
        "spending": spending(db, start, end),
        "mood": mood(db, start, end),
        "sleep": sleep(db, start, end),
        "caffeine": caffeine(db, start, end),
        "people": people(db, start, end),
        "music": music(db, start, end),
        "decisions": decisions(db, start, end),
        "events": events(db, start, end),
        "important_memories": important_memories(db, start, end),
        "waiting": waiting(db, start, end),
    }


def is_empty(data: dict[str, Any]) -> bool:
    return not any(
        [
            data["journal_entries"],
            data["spending"]["count"],
            data["mood"]["count"],
            data["sleep"]["nights"],
            data["caffeine"]["drinks"],
            data["people"]["interaction_count"],
            data["music"]["count"],
            data["decisions"],
            data["events"],
        ]
    )


def daily(db: Session, day: date) -> dict[str, Any]:
    return period(db, day, day)


def weekly(db: Session, week_start: date) -> dict[str, Any]:
    end = week_start + timedelta(days=6)
    data = period(db, week_start, end)
    previous = period(db, week_start - timedelta(days=7), week_start - timedelta(days=1))
    data["previous_week"] = {
        "spending_total": previous["spending"]["total"],
        "mood_average": previous["mood"]["average_score"],
        "sleep_average_minutes": previous["sleep"]["average_minutes"],
        "caffeine_drinks": previous["caffeine"]["drinks"],
    }
    # Sleep on the Monday after the week closes the last night's pair.
    sleep_after = sleep(db, week_start + timedelta(days=1), end + timedelta(days=1))
    data["caffeine_sleep"] = caffeine_sleep_coincidence(
        data["caffeine"]["by_day"], sleep_after["by_day"]
    )
    return data


def monthly(db: Session, year: int, month: int) -> dict[str, Any]:
    start = date(year, month, 1)
    end = (date(year + month // 12, month % 12 + 1, 1)) - timedelta(days=1)
    data = period(db, start, end)
    data["subscriptions"] = summarize_subscriptions(db).model_dump(mode="json")
    weeks: dict[str, list[float]] = defaultdict(list)
    for day, score in data["mood"]["by_day"].items():
        if score is not None:
            monday = date.fromisoformat(day) - timedelta(days=date.fromisoformat(day).weekday())
            weeks[monday.isoformat()].append(score)
    data["mood"]["by_week"] = {w: _avg(v) for w, v in sorted(weeks.items())}
    data["important_memories"] = important_memories(db, start, end, min_importance=3)
    return data
