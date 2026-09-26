import uuid
from datetime import date

from sqlalchemy import CheckConstraint, Date, ForeignKey, SmallInteger, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

RELATIONSHIP_TYPES = (
    "friend",
    "crush",
    "mentor",
    "lecturer",
    "family",
    "colleague",
    "acquaintance",
    "other",
)


class Person(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Someone in the user's life. Holds only what the user has said; no scoring.

    ``first_mentioned_at`` and ``last_interaction_at`` are calendar dates (interactions
    are logged per day), kept up to date from ``person_interactions``.
    """

    __tablename__ = "people"
    __table_args__ = (
        CheckConstraint(
            "relationship_type IN (" + ", ".join(f"'{t}'" for t in RELATIONSHIP_TYPES) + ")",
            name="relationship_type_known",
        ),
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    nickname: Mapped[str | None] = mapped_column(String(100))
    # Unknown until the user says; never guessed.
    relationship_type: Mapped[str | None] = mapped_column(String(20))
    notes: Mapped[str | None] = mapped_column(Text)
    first_mentioned_at: Mapped[date] = mapped_column(Date, nullable=False)
    last_interaction_at: Mapped[date | None] = mapped_column(Date, index=True)


class PersonInteraction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "person_interactions"
    __table_args__ = (
        CheckConstraint("importance_score BETWEEN 0 AND 5", name="importance_score_range"),
    )

    person_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("people.id", ondelete="CASCADE"), nullable=False, index=True
    )
    interaction_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    # The user's own words that described the interaction, stored verbatim.
    raw_context: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(200))
    # The user's own mood before/after, only if they said so.
    mood_before: Mapped[str | None] = mapped_column(String(50))
    mood_after: Mapped[str | None] = mapped_column(String(50))
    importance_score: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=2, server_default=text("2")
    )
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("journal_entries.id", ondelete="SET NULL"), index=True
    )


class MusicMemory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "music_memories"
    __table_args__ = (
        CheckConstraint("importance_score BETWEEN 0 AND 5", name="importance_score_range"),
    )

    song: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    artist: Mapped[str | None] = mapped_column(String(200), index=True)
    album: Mapped[str | None] = mapped_column(String(200))
    memory_text: Mapped[str | None] = mapped_column(Text)
    emotion: Mapped[str | None] = mapped_column(String(50))
    memory_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    person_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("people.id", ondelete="SET NULL"), index=True
    )
    importance_score: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=2, server_default=text("2")
    )
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("journal_entries.id", ondelete="SET NULL"), index=True
    )
