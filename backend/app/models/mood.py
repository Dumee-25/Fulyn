import uuid
from datetime import date

from sqlalchemy import CheckConstraint, Date, ForeignKey, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class MoodLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Mood and energy are separate 1-10 scales. Not a diagnostic tool."""

    __tablename__ = "mood_logs"
    __table_args__ = (
        CheckConstraint("score BETWEEN 1 AND 10", name="score_range"),
        CheckConstraint("energy_score BETWEEN 1 AND 10", name="energy_score_range"),
    )

    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    score: Mapped[int | None] = mapped_column(SmallInteger)
    label: Mapped[str | None] = mapped_column(String(30))
    energy_score: Mapped[int | None] = mapped_column(SmallInteger)
    notes: Mapped[str | None] = mapped_column(Text)
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("journal_entries.id", ondelete="SET NULL"), index=True
    )
