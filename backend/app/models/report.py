"""Life events and stored recaps/reports."""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class LifeEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "life_events"
    __table_args__ = (
        CheckConstraint("importance_score BETWEEN 0 AND 5", name="importance_score_range"),
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    event_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    # Free text (outing, milestone, trip, exam, celebration…) so types can evolve.
    event_type: Mapped[str | None] = mapped_column(String(50))
    importance_score: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=2, server_default=text("2")
    )
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("journal_entries.id", ondelete="SET NULL"), index=True
    )


class _Report:
    """Shared columns: rendered markdown plus the structured data it was built from."""

    content: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DailyRecap(UUIDPrimaryKeyMixin, _Report, Base):
    __tablename__ = "daily_recaps"

    date: Mapped[date] = mapped_column(Date, nullable=False, unique=True)


class WeeklyRecap(UUIDPrimaryKeyMixin, _Report, Base):
    __tablename__ = "weekly_recaps"

    # Monday of the week.
    week_start: Mapped[date] = mapped_column(Date, nullable=False, unique=True)


class MonthlyReport(UUIDPrimaryKeyMixin, _Report, Base):
    __tablename__ = "monthly_reports"
    __table_args__ = (
        UniqueConstraint("year", "month", name="uq_monthly_reports_year_month"),
        CheckConstraint("month BETWEEN 1 AND 12", name="month_range"),
    )

    year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    month: Mapped[int] = mapped_column(SmallInteger, nullable=False)
