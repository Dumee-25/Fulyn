"""memories

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-26 16:45:13.134855+00:00

"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "memories",
        sa.Column("memory_type", sa.String(length=30), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("memory_date", sa.Date(), nullable=False),
        sa.Column(
            "importance_score", sa.SmallInteger(), server_default=sa.text("2"), nullable=False
        ),
        sa.Column("is_private", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=768), nullable=True),
        sa.Column("embedding_model", sa.String(length=100), nullable=True),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(
                "to_tsvector('english', coalesce(title, '') || ' ' || content)", persisted=True
            ),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "memory_type IN ('journal', 'event', 'person_interaction', 'decision', 'music', 'expense', 'other')",
            name=op.f("ck_memories_memory_type_known"),
        ),
        sa.CheckConstraint(
            "importance_score BETWEEN 0 AND 5", name=op.f("ck_memories_importance_score_range")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_memories")),
        sa.UniqueConstraint("memory_type", "source_id", name="uq_memories_source"),
    )
    op.create_index(
        "ix_memories_embedding_hnsw",
        "memories",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index(op.f("ix_memories_is_private"), "memories", ["is_private"], unique=False)
    op.create_index(op.f("ix_memories_memory_date"), "memories", ["memory_date"], unique=False)
    op.create_index(
        "ix_memories_search_vector",
        "memories",
        ["search_vector"],
        unique=False,
        postgresql_using="gin",
    )

    # Existing journal entries become memories; embeddings are filled in later by backfill.
    op.execute(
        """
        INSERT INTO memories (id, memory_type, source_id, title, content, memory_date,
                              importance_score, is_private)
        SELECT gen_random_uuid(), 'journal', id,
               left(coalesce(ai_summary, split_part(btrim(raw_text), E'\n', 1)), 200),
               raw_text, entry_date, importance_score, is_private
        FROM journal_entries
        """
    )


def downgrade() -> None:
    op.drop_index("ix_memories_search_vector", table_name="memories", postgresql_using="gin")
    op.drop_index(op.f("ix_memories_memory_date"), table_name="memories")
    op.drop_index(op.f("ix_memories_is_private"), table_name="memories")
    op.drop_index(
        "ix_memories_embedding_hnsw",
        table_name="memories",
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.drop_table("memories")
