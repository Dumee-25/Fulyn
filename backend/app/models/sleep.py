import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    Text,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SleepLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Every field except ``sleep_date`` is optional: "slept about 5 hours" is valid.

    ``sleep_date`` is the date the user woke up on.
    """

    __tablename__ = "sleep_logs"
    __table_args__ = (
        CheckConstraint("duration_minutes BETWEEN 0 AND 1440", name="duration_range"),
        CheckConstraint("quality_score BETWEEN 1 AND 10", name="quality_score_range"),
    )

    sleep_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    sleep_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    wake_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    # True when times/duration are the user's estimate ("around 2", "maybe 4 hours").
    is_approximate: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    quality_score: Mapped[int | None] = mapped_column(SmallInteger)
    notes: Mapped[str | None] = mapped_column(Text)
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("journal_entries.id", ondelete="SET NULL"), index=True
    )
