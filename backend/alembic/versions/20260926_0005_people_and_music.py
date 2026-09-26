"""people and music

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-26 16:55:41.670276+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "people",
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("nickname", sa.String(length=100), nullable=True),
        sa.Column("relationship_type", sa.String(length=20), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("first_mentioned_at", sa.Date(), nullable=False),
        sa.Column("last_interaction_at", sa.Date(), nullable=True),
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
            "relationship_type IN ('friend', 'crush', 'mentor', 'lecturer', 'family', 'colleague', 'acquaintance', 'other')",
            name=op.f("ck_people_relationship_type_known"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_people")),
    )
    op.create_index(
        op.f("ix_people_last_interaction_at"), "people", ["last_interaction_at"], unique=False
    )
    op.create_index(op.f("ix_people_name"), "people", ["name"], unique=False)
    op.create_table(
        "music_memories",
        sa.Column("song", sa.String(length=200), nullable=False),
        sa.Column("artist", sa.String(length=200), nullable=True),
        sa.Column("album", sa.String(length=200), nullable=True),
        sa.Column("memory_text", sa.Text(), nullable=True),
        sa.Column("emotion", sa.String(length=50), nullable=True),
        sa.Column("memory_date", sa.Date(), nullable=False),
        sa.Column("person_id", sa.Uuid(), nullable=True),
        sa.Column(
            "importance_score", sa.SmallInteger(), server_default=sa.text("2"), nullable=False
        ),
        sa.Column("journal_entry_id", sa.Uuid(), nullable=True),
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
            "importance_score BETWEEN 0 AND 5",
            name=op.f("ck_music_memories_importance_score_range"),
        ),
        sa.ForeignKeyConstraint(
            ["journal_entry_id"],
            ["journal_entries.id"],
            name=op.f("fk_music_memories_journal_entry_id_journal_entries"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["people.id"],
            name=op.f("fk_music_memories_person_id_people"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_music_memories")),
    )
    op.create_index(op.f("ix_music_memories_artist"), "music_memories", ["artist"], unique=False)
    op.create_index(
        op.f("ix_music_memories_journal_entry_id"),
        "music_memories",
        ["journal_entry_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_music_memories_memory_date"), "music_memories", ["memory_date"], unique=False
    )
    op.create_index(
        op.f("ix_music_memories_person_id"), "music_memories", ["person_id"], unique=False
    )
    op.create_index(op.f("ix_music_memories_song"), "music_memories", ["song"], unique=False)
    op.create_table(
        "person_interactions",
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.Column("interaction_date", sa.Date(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("raw_context", sa.Text(), nullable=True),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("mood_before", sa.String(length=50), nullable=True),
        sa.Column("mood_after", sa.String(length=50), nullable=True),
        sa.Column(
            "importance_score", sa.SmallInteger(), server_default=sa.text("2"), nullable=False
        ),
        sa.Column("journal_entry_id", sa.Uuid(), nullable=True),
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
            "importance_score BETWEEN 0 AND 5",
            name=op.f("ck_person_interactions_importance_score_range"),
        ),
        sa.ForeignKeyConstraint(
            ["journal_entry_id"],
            ["journal_entries.id"],
            name=op.f("fk_person_interactions_journal_entry_id_journal_entries"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["people.id"],
            name=op.f("fk_person_interactions_person_id_people"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_person_interactions")),
    )
    op.create_index(
        op.f("ix_person_interactions_interaction_date"),
        "person_interactions",
        ["interaction_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_interactions_journal_entry_id"),
        "person_interactions",
        ["journal_entry_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_interactions_person_id"), "person_interactions", ["person_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_person_interactions_person_id"), table_name="person_interactions")
    op.drop_index(op.f("ix_person_interactions_journal_entry_id"), table_name="person_interactions")
    op.drop_index(op.f("ix_person_interactions_interaction_date"), table_name="person_interactions")
    op.drop_table("person_interactions")
    op.drop_index(op.f("ix_music_memories_song"), table_name="music_memories")
    op.drop_index(op.f("ix_music_memories_person_id"), table_name="music_memories")
    op.drop_index(op.f("ix_music_memories_memory_date"), table_name="music_memories")
    op.drop_index(op.f("ix_music_memories_journal_entry_id"), table_name="music_memories")
    op.drop_index(op.f("ix_music_memories_artist"), table_name="music_memories")
    op.drop_table("music_memories")
    op.drop_index(op.f("ix_people_name"), table_name="people")
    op.drop_index(op.f("ix_people_last_interaction_at"), table_name="people")
    op.drop_table("people")
