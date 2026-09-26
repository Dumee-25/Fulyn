"""Dashboard data and cross-domain analytics.

All numbers are computed here, never by the model. Comparisons report group sizes and a
reminder that they show what coincided, not what caused what.
"""

from collections import Counter
from datetime import date, timedelta
from decimal import Decimal
from statistics import median
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.core.time import today_local
from app.models.memory import Memory
from app.models.mood import MoodLog
from app.models.people import MusicMemory
from app.models.planning import Decision
from app.reports import stats
from app.reports.privacy import not_private
from app.reports.series import METRICS, DaySeries
from app.services.planning import list_waiting, summarize_subscriptions

Metric = Literal["spending", "mood", "energy", "sleep_minutes", "caffeine_drinks"]
GroupBy = Literal[
    "went_out",
    "saw_person",
    "weekend",
    "impulse_purchase",
    "more_sleep",
    "more_caffeine",
    "better_mood",
    "more_spending",
]
Granularity = Literal["day", "week"]

MIN_GROUP = 3
MAX_RANGE_DAYS = 731
CAVEAT = "These are averages of what you logged. They show what coincided, not what caused what."
POSITIVE_EMOTIONS = {
    "happy",
    "joy",
    "joyful",
    "excited",
    "grateful",
    "calm",
    "peaceful",
    "hopeful",
    "love",
    "loved",
    "content",
    "proud",
    "nostalgic",
    "good",
    "great",
    "uplifted",
    "euphoric",
}
_MEDIAN_SPLITS = {
    "more_sleep": "sleep_minutes",
    "more_caffeine": "caffeine_drinks",
    "better_mood": "mood",
    "more_spending": "spending",
}


def _round(metric: str, value: float | None) -> Any:
    if value is None:
        return None
    if metric == "spending":
        return str(Decimal(str(value)).quantize(Decimal("0.01")))
    return round(value, 1)


# --- Dashboard ---------------------------------------------------------------------


def dashboard(db: Session, today: date | None = None, days: int = 30) -> dict[str, Any]:
    today = today or today_local()
    start = today - timedelta(days=days - 1)
    month_start = today.replace(day=1)
    series = DaySeries(db, min(start, month_start), today)
    window = [start + timedelta(days=i) for i in range(days)]

    month = stats.spending(db, month_start, today)
    people = stats.people(db, start, today)
    hours = Counter(series.caffeine_hours)

    return {
        "today": today.isoformat(),
        "spending": {
            "month_total": month["total"],
            "month_impulse": month["impulse_total"],
            "currency": month["currency"],
            "by_category": month["by_category"],
            "subscriptions": summarize_subscriptions(db).model_dump(mode="json"),
            "daily": [
                {"date": d.isoformat(), "total": _round("spending", series.value("spending", d))}
                for d in window
            ],
        },
        "mood": {
            "daily": [
                {
                    "date": d.isoformat(),
                    "mood": _round("mood", series.value("mood", d)),
                    "energy": _round("energy", series.value("energy", d)),
                }
                for d in window
            ],
            "average": _average(series, "mood", window),
            "energy_average": _average(series, "energy", window),
        },
        "sleep": {
            "daily": [
                {"date": d.isoformat(), "minutes": series.value("sleep_minutes", d)} for d in window
            ],
            "average_minutes": _average(series, "sleep_minutes", window),
        },
        "caffeine": {
            "daily": [
                {"date": d.isoformat(), "drinks": series.value("caffeine_drinks", d)}
                for d in window
            ],
            "by_hour": [{"hour": h, "drinks": hours.get(h, 0)} for h in range(24)],
        },
        "people": {
            "recent": list(reversed(people["interactions"]))[:8],
            "counts": people["by_person"],
        },
        "memories": {
            "important": stats.important_memories(db, start, today, min_importance=4),
            "core": [
                {"date": m.memory_date.isoformat(), "type": m.memory_type, "title": m.title}
                for m in db.scalars(
                    select(Memory)
                    .where(Memory.importance_score == 5, Memory.is_private.is_(False))
                    .order_by(Memory.memory_date.desc())
                    .limit(8)
                )
            ],
        },
        "decisions": [
            {"date": d.decision_date.isoformat(), "title": d.title, "status": d.status}
            for d in db.scalars(
                select(Decision)
                .where(not_private(Decision))
                .order_by(Decision.decision_date.desc(), Decision.created_at.desc())
                .limit(5)
            )
        ],
        "waiting": [
            w.model_dump(mode="json", include={"id", "title", "overdue", "waiting_since"})
            for w in list_waiting(db, limit=8)
        ],
    }


def _average(series: DaySeries, metric: str, days: list[date]) -> Any:
    values = [v for d in days if (v := series.value(metric, d)) is not None]
    return _round(metric, sum(values) / len(values)) if values else None


# --- Cross-domain comparisons ------------------------------------------------------


def _weeks(days: list[date]) -> list[list[date]]:
    weeks: dict[date, list[date]] = {}
    for d in days:
        weeks.setdefault(d - timedelta(days=d.weekday()), []).append(d)
    return list(weeks.values())


def _unit_value(series: DaySeries, metric: str, unit: list[date]) -> float | None:
    """Average of a metric over a day or week (days with data only)."""
    values = [v for d in unit if (v := series.value(metric, d)) is not None]
    return sum(values) / len(values) if values else None


def analyze(
    db: Session,
    *,
    metric: Metric,
    group_by: GroupBy,
    granularity: Granularity = "day",
    person_name: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    """Compare a metric between two groups of days (or weeks).

    Example: spending on days you went out vs days you didn't; mood in weeks with more
    sleep vs weeks with less. Median splits compare above-median units with the rest.
    """
    if metric not in METRICS:
        raise DomainError(f"unknown metric {metric}")
    end = date_to or today_local()
    start = date_from or end - timedelta(days=89)
    if start > end:
        raise DomainError("date_from is after date_to")
    if (end - start).days > MAX_RANGE_DAYS:
        raise DomainError("range too long; use at most two years")
    if group_by == "saw_person" and not person_name:
        raise DomainError("group_by saw_person needs person_name")
    if group_by == "weekend" and granularity == "week":
        raise DomainError("weekend grouping only works per day")

    series = DaySeries(db, start, end)
    # Only units where something was logged count.
    logged_days = [d for d in series.days if d in series.logged]
    units = [[d] for d in logged_days] if granularity == "day" else _weeks(logged_days)

    def membership(unit: list[date]) -> bool | None:
        if group_by == "went_out":
            return any(series.went_out(d) for d in unit)
        if group_by == "saw_person":
            needle = person_name.strip().lower()
            return any(
                any(
                    n == needle or n.startswith(needle + " ")
                    for n in series.people_by_day.get(d, ())
                )
                for d in unit
            )
        if group_by == "weekend":
            return unit[0].weekday() >= 5
        if group_by == "impulse_purchase":
            return any(d in series.impulse_days for d in unit)
        return None  # median splits are handled below

    split_metric = _MEDIAN_SPLITS.get(group_by)
    pairs: list[tuple[bool, float]] = []
    if split_metric:
        known = [(u, x) for u in units if (x := _unit_value(series, split_metric, u)) is not None]
        if not known:
            return _result(metric, group_by, granularity, start, end, [], None, person_name)
        cut = median(x for _, x in known)
        for unit, x in known:
            y = _unit_value(series, metric, unit)
            if y is not None:
                pairs.append((x > cut, y))
    else:
        for unit in units:
            y = _unit_value(series, metric, unit)
            if y is not None:
                pairs.append((bool(membership(unit)), y))
        cut = None
    return _result(metric, group_by, granularity, start, end, pairs, cut, person_name)


_LABELS = {
    "went_out": ("went out (saw someone or had an event)", "did not"),
    "saw_person": ("saw {person}", "did not see {person}"),
    "weekend": ("weekend", "weekday"),
    "impulse_purchase": ("with an impulse purchase", "without"),
    "more_sleep": ("more sleep (above median)", "less sleep"),
    "more_caffeine": ("more caffeine (above median)", "less caffeine"),
    "better_mood": ("better mood (above median)", "lower mood"),
    "more_spending": ("more spending (above median)", "less spending"),
}


def _result(metric, group_by, granularity, start, end, pairs, cut, person_name) -> dict:
    yes = [y for flag, y in pairs if flag]
    no = [y for flag, y in pairs if not flag]
    label_yes, label_no = (s.format(person=person_name) for s in _LABELS[group_by])
    unit = "days" if granularity == "day" else "weeks"
    groups = [
        {
            "group": label_yes,
            unit: len(yes),
            "average": _round(metric, sum(yes) / len(yes)) if yes else None,
        },
        {
            "group": label_no,
            unit: len(no),
            "average": _round(metric, sum(no) / len(no)) if no else None,
        },
    ]
    enough = len(yes) >= MIN_GROUP and len(no) >= MIN_GROUP
    result: dict[str, Any] = {
        "metric": metric,
        "granularity": granularity,
        "period": {"from": start.isoformat(), "to": end.isoformat()},
        "groups": groups,
        "enough_data": enough,
        "caveat": CAVEAT,
    }
    if cut is not None:
        result["median_split_at"] = round(cut, 1)
    if not enough:
        result["note"] = (
            f"Each group needs at least {MIN_GROUP} {unit} with data for a fair comparison; "
            "treat this as anecdotal."
        )
    return result


def songs_in_positive_memories(
    db: Session, *, date_from: date | None = None, date_to: date | None = None, limit: int = 10
) -> dict[str, Any]:
    """Songs from music memories that were positive: a positive emotion was recorded, or
    the mood logged that day was 7/10 or higher."""
    stmt = select(MusicMemory).where(not_private(MusicMemory))
    if date_from:
        stmt = stmt.where(MusicMemory.memory_date >= date_from)
    if date_to:
        stmt = stmt.where(MusicMemory.memory_date <= date_to)
    music = list(db.scalars(stmt))
    good_days = set(
        db.scalars(
            select(MoodLog.date)
            .where(not_private(MoodLog))
            .group_by(MoodLog.date)
            .having(func.avg(MoodLog.score) >= 7)
        )
    )
    positive = [
        m
        for m in music
        if (m.emotion and m.emotion.strip().lower() in POSITIVE_EMOTIONS)
        or m.memory_date in good_days
    ]
    counts = Counter((m.song, m.artist) for m in positive)
    return {
        "positive_music_memories": len(positive),
        "total_music_memories": len(music),
        "songs": [{"song": s, "artist": a, "count": n} for (s, a), n in counts.most_common(limit)],
        "definition": "positive = a positive emotion was recorded, or that day's mood was 7+/10",
    }
