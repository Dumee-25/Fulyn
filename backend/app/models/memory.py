import uuid
from datetime import date

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    false,
    text,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

# Fixed by the schema. Changing the embedding model to one with a different size needs a
# migration that alters this column and re-embeds (embeddings are nulled and backfilled).
EMBEDDING_DIMENSIONS = 768

MEMORY_TYPES = (
    "journal",
    "event",
    "person_interaction",
    "decision",
    "music",
    "expense",
    "other",
)


class Memory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The searchable memory layer.

    A memory points at a domain record (``memory_type`` + ``source_id``) and holds the
    text that is embedded and full-text indexed. Domain records stay authoritative.
    """

    __tablename__ = "memories"
    __table_args__ = (
        UniqueConstraint("memory_type", "source_id", name="uq_memories_source"),
        CheckConstraint("importance_score BETWEEN 0 AND 5", name="importance_score_range"),
        CheckConstraint(
            "memory_type IN (" + ", ".join(f"'{t}'" for t in MEMORY_TYPES) + ")",
            name="memory_type_known",
        ),
        Index(
            "ix_memories_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_memories_search_vector", "search_vector", postgresql_using="gin"),
    )

    memory_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_id: Mapped[uuid.UUID | None] = mapped_column()
    title: Mapped[str | None] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    memory_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    importance_score: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=2, server_default=text("2")
    )
    is_private: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false(), index=True
    )
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    # Model that produced ``embedding``; a different configured model triggers re-embedding.
    embedding_model: Mapped[str | None] = mapped_column(String(100))
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', coalesce(title, '') || ' ' || content)", persisted=True),
    )
