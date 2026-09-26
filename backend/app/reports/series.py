"""Per-day metric series, the building block for dashboards and cross-domain analytics.

Conventions (documented because they change the answers):
- A day is "logged" if anything was recorded on it (journal entry, expense, mood, sleep,
  caffeine, interaction, event, music or decision).
- Spending and caffeine are 0 on logged days without any, and unknown on unlogged days.
- Mood, energy and sleep are only known on days they were recorded.
- A day's sleep is the night before it (sleep_date is the wake-up date).
- Private (vault) records are excluded.
"""

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.caffeine import CaffeineLog
from app.models.expense import Expense
from app.models.journal import JournalEntry
from app.models.mood import MoodLog
from app.models.people import MusicMemory, Person, PersonInteraction
from app.models.planning import Decision
from app.models.report import LifeEvent
from app.models.sleep import SleepLog
from app.reports.privacy import not_private

METRICS = ("spending", "mood", "energy", "sleep_minutes", "caffeine_drinks")


class DaySeries:
    """All per-day facts for a date range, computed with a handful of queries."""

    def __init__(self, db: Session, start: date, end: date) -> None:
        self.start, self.end = start, end
        self.days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
        settings = get_settings()
        tz = settings.tz
        self.logged: set[date] = set()
        self.spending: dict[date, Decimal] = defaultdict(lambda: Decimal("0.00"))
        self.impulse_days: set[date] = set()
        self.mood: dict[date, list[int]] = defaultdict(list)
        self.energy: dict[date, list[int]] = defaultdict(list)
        self.sleep: dict[date, int] = {}
        self.caffeine: dict[date, float] = defaultdict(float)
        self.caffeine_hours: list[int] = []
        self.people_by_day: dict[date, set[str]] = defaultdict(set)
        self.event_days: set[date] = set()

        for d in db.scalars(
            select(JournalEntry.entry_date).where(
                JournalEntry.entry_date.between(start, end), JournalEntry.is_private.is_(False)
            )
        ):
            self.logged.add(d)

        for x in db.scalars(
            select(Expense).where(
                Expense.currency == settings.default_currency,
                Expense.expense_date.between(start, end),
                not_private(Expense),
            )
        ):
            self.spending[x.expense_date] += x.amount
            self.logged.add(x.expense_date)
            if x.is_impulse:
                self.impulse_days.add(x.expense_date)

        for m in db.scalars(
            select(MoodLog).where(MoodLog.date.between(start, end), not_private(MoodLog))
        ):
            self.logged.add(m.date)
            if m.score is not None:
                self.mood[m.date].append(m.score)
            if m.energy_score is not None:
                self.energy[m.date].append(m.energy_score)

        for s in db.scalars(
            select(SleepLog).where(SleepLog.sleep_date.between(start, end), not_private(SleepLog))
        ):
            self.logged.add(s.sleep_date)
            if s.duration_minutes is not None:
                self.sleep[s.sleep_date] = s.duration_minutes

        low = datetime.combine(start, time.min, tzinfo=tz)
        high = datetime.combine(end + timedelta(days=1), time.min, tzinfo=tz)
        for c in db.scalars(
            select(CaffeineLog).where(
                CaffeineLog.consumed_at >= low,
                CaffeineLog.consumed_at < high,
                not_private(CaffeineLog),
            )
        ):
            local = c.consumed_at.astimezone(tz)
            self.caffeine[local.date()] += float(c.quantity)
            self.caffeine_hours.append(local.hour)
            self.logged.add(local.date())

        for i, name in db.execute(
            select(PersonInteraction, Person.name)
            .join(Person, Person.id == PersonInteraction.person_id)
            .where(
                PersonInteraction.interaction_date.between(start, end),
                not_private(PersonInteraction),
            )
        ).all():
            self.people_by_day[i.interaction_date].add(name.lower())
            self.logged.add(i.interaction_date)

        for d in db.scalars(
            select(LifeEvent.event_date).where(
                LifeEvent.event_date.between(start, end), not_private(LifeEvent)
            )
        ):
            self.event_days.add(d)
            self.logged.add(d)

        for model, column in (
            (MusicMemory, MusicMemory.memory_date),
            (Decision, Decision.decision_date),
        ):
            for d in db.scalars(
                select(column).where(column.between(start, end), not_private(model))
            ):
                self.logged.add(d)

    def value(self, metric: str, day: date) -> float | None:
        """The metric on a day, or None if unknown."""
        if metric == "spending":
            return float(self.spending[day]) if day in self.logged else None
        if metric == "caffeine_drinks":
            return self.caffeine[day] if day in self.logged else None
        if metric == "mood":
            values = self.mood.get(day)
            return sum(values) / len(values) if values else None
        if metric == "energy":
            values = self.energy.get(day)
            return sum(values) / len(values) if values else None
        if metric == "sleep_minutes":
            minutes = self.sleep.get(day)
            return float(minutes) if minutes is not None else None
        raise ValueError(f"unknown metric {metric!r}")

    def went_out(self, day: date) -> bool:
        return bool(self.people_by_day.get(day)) or day in self.event_days
