"""core life logging tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-26 16:06:39.000964+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "journal_entries",
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("ai_summary", sa.Text(), nullable=True),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("mood_summary", sa.String(length=200), nullable=True),
        sa.Column("is_private", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "importance_score", sa.SmallInteger(), server_default=sa.text("2"), nullable=False
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
            "importance_score BETWEEN 0 AND 5",
            name=op.f("ck_journal_entries_importance_score_range"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_journal_entries")),
    )
    op.create_index(
        op.f("ix_journal_entries_entry_date"), "journal_entries", ["entry_date"], unique=False
    )
    op.create_table(
        "caffeine_logs",
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_approximate", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("drink_type", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("estimated_caffeine_mg", sa.Integer(), nullable=True),
        sa.Column(
            "quantity",
            sa.Numeric(precision=5, scale=2),
            server_default=sa.text("1"),
            nullable=False,
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
            "estimated_caffeine_mg >= 0", name=op.f("ck_caffeine_logs_caffeine_mg_non_negative")
        ),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_caffeine_logs_quantity_positive")),
        sa.ForeignKeyConstraint(
            ["journal_entry_id"],
            ["journal_entries.id"],
            name=op.f("fk_caffeine_logs_journal_entry_id_journal_entries"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_caffeine_logs")),
    )
    op.create_index(
        op.f("ix_caffeine_logs_consumed_at"), "caffeine_logs", ["consumed_at"], unique=False
    )
    op.create_index(
        op.f("ix_caffeine_logs_journal_entry_id"),
        "caffeine_logs",
        ["journal_entry_id"],
        unique=False,
    )
    op.create_table(
        "expenses",
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("merchant", sa.String(length=200), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("expense_date", sa.Date(), nullable=False),
        sa.Column("is_impulse", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("impulse_reason", sa.Text(), nullable=True),
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
        sa.CheckConstraint("amount >= 0", name=op.f("ck_expenses_amount_non_negative")),
        sa.ForeignKeyConstraint(
            ["journal_entry_id"],
            ["journal_entries.id"],
            name=op.f("fk_expenses_journal_entry_id_journal_entries"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_expenses")),
    )
    op.create_index(op.f("ix_expenses_category"), "expenses", ["category"], unique=False)
    op.create_index(op.f("ix_expenses_expense_date"), "expenses", ["expense_date"], unique=False)
    op.create_index(
        op.f("ix_expenses_journal_entry_id"), "expenses", ["journal_entry_id"], unique=False
    )
    op.create_table(
        "mood_logs",
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("score", sa.SmallInteger(), nullable=True),
        sa.Column("label", sa.String(length=30), nullable=True),
        sa.Column("energy_score", sa.SmallInteger(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
            "energy_score BETWEEN 1 AND 10", name=op.f("ck_mood_logs_energy_score_range")
        ),
        sa.CheckConstraint("score BETWEEN 1 AND 10", name=op.f("ck_mood_logs_score_range")),
        sa.ForeignKeyConstraint(
            ["journal_entry_id"],
            ["journal_entries.id"],
            name=op.f("fk_mood_logs_journal_entry_id_journal_entries"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mood_logs")),
    )
    op.create_index(op.f("ix_mood_logs_date"), "mood_logs", ["date"], unique=False)
    op.create_index(
        op.f("ix_mood_logs_journal_entry_id"), "mood_logs", ["journal_entry_id"], unique=False
    )
    op.create_table(
        "sleep_logs",
        sa.Column("sleep_date", sa.Date(), nullable=False),
        sa.Column("sleep_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("wake_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("is_approximate", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("quality_score", sa.SmallInteger(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
            "duration_minutes BETWEEN 0 AND 1440", name=op.f("ck_sleep_logs_duration_range")
        ),
        sa.CheckConstraint(
            "quality_score BETWEEN 1 AND 10", name=op.f("ck_sleep_logs_quality_score_range")
        ),
        sa.ForeignKeyConstraint(
            ["journal_entry_id"],
            ["journal_entries.id"],
            name=op.f("fk_sleep_logs_journal_entry_id_journal_entries"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sleep_logs")),
    )
    op.create_index(
        op.f("ix_sleep_logs_journal_entry_id"), "sleep_logs", ["journal_entry_id"], unique=False
    )
    op.create_index(op.f("ix_sleep_logs_sleep_date"), "sleep_logs", ["sleep_date"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_sleep_logs_sleep_date"), table_name="sleep_logs")
    op.drop_index(op.f("ix_sleep_logs_journal_entry_id"), table_name="sleep_logs")
    op.drop_table("sleep_logs")
    op.drop_index(op.f("ix_mood_logs_journal_entry_id"), table_name="mood_logs")
    op.drop_index(op.f("ix_mood_logs_date"), table_name="mood_logs")
    op.drop_table("mood_logs")
    op.drop_index(op.f("ix_expenses_journal_entry_id"), table_name="expenses")
    op.drop_index(op.f("ix_expenses_expense_date"), table_name="expenses")
    op.drop_index(op.f("ix_expenses_category"), table_name="expenses")
    op.drop_table("expenses")
    op.drop_index(op.f("ix_caffeine_logs_journal_entry_id"), table_name="caffeine_logs")
    op.drop_index(op.f("ix_caffeine_logs_consumed_at"), table_name="caffeine_logs")
    op.drop_table("caffeine_logs")
    op.drop_index(op.f("ix_journal_entries_entry_date"), table_name="journal_entries")
    op.drop_table("journal_entries")
