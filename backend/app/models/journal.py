from datetime import date

from sqlalchemy import Boolean, CheckConstraint, Date, SmallInteger, String, Text, false, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class JournalEntry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The user's own words. ``raw_text`` is authoritative and never rewritten by the AI.

    The ``embedding`` column is added in Phase 4 once the embedding model is chosen.
    """

    __tablename__ = "journal_entries"
    __table_args__ = (
        CheckConstraint("importance_score BETWEEN 0 AND 5", name="importance_score_range"),
    )

    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    ai_summary: Mapped[str | None] = mapped_column(Text)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    mood_summary: Mapped[str | None] = mapped_column(String(200))
    is_private: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    importance_score: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=2, server_default=text("2")
    )
