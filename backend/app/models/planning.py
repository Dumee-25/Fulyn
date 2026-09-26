"""Personal management: subscriptions, reminders, decisions and things being waited for."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


BILLING_CYCLES = ("weekly", "monthly", "quarterly", "yearly", "custom")
RECURRENCE_RULES = ("daily", "weekly", "monthly", "yearly")
REMINDER_STATUSES = ("pending", "completed", "cancelled")
DECISION_STATUSES = ("active", "reconsidered", "reversed", "completed")
WAITING_STATUSES = ("waiting", "received", "cancelled", "expired")


class Subscription(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="amount_non_negative"),
        CheckConstraint(_in("billing_cycle", BILLING_CYCLES), name="billing_cycle_known"),
        CheckConstraint(
            "billing_cycle <> 'custom' OR custom_interval_days > 0",
            name="custom_cycle_has_interval",
        ),
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    billing_cycle: Mapped[str] = mapped_column(String(20), nullable=False)
    # Only for billing_cycle = 'custom'.
    custom_interval_days: Mapped[int | None] = mapped_column(Integer)
    next_billing_date: Mapped[date | None] = mapped_column(Date)
    category: Mapped[str] = mapped_column(String(50), nullable=False, server_default="Subscription")
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true(), index=True
    )
    notes: Mapped[str | None] = mapped_column(Text)


class Reminder(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """In-app reminders. ``due_at`` + ``status`` is what a future notifier would poll."""

    __tablename__ = "reminders"
    __table_args__ = (
        CheckConstraint(_in("status", REMINDER_STATUSES), name="status_known"),
        CheckConstraint(
            f"recurrence_rule IS NULL OR {_in('recurrence_rule', RECURRENCE_RULES)}",
            name="recurrence_rule_known",
        ),
        Index("ix_reminders_status_due_at", "status", "due_at"),
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recurrence_rule: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    last_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Decision(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "decisions"
    __table_args__ = (
        CheckConstraint(_in("status", DECISION_STATUSES), name="status_known"),
        CheckConstraint("importance_score BETWEEN 0 AND 5", name="importance_score_range"),
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    reasoning: Mapped[str | None] = mapped_column(Text)
    decision_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active"
    )
    importance_score: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=2, server_default=text("2")
    )
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("journal_entries.id", ondelete="SET NULL"), index=True
    )


class WaitingItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "waiting_items"
    __table_args__ = (CheckConstraint(_in("status", WAITING_STATUSES), name="status_known"),)

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    waiting_since: Mapped[date] = mapped_column(Date, nullable=False)
    expected_by: Mapped[date | None] = mapped_column(Date)
    related_person_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("people.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="waiting", server_default="waiting", index=True
    )
    resolved_at: Mapped[date | None] = mapped_column(Date)
