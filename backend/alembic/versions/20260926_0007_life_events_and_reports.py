"""life events and reports

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-26 17:24:15.632642+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "daily_recaps",
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_daily_recaps")),
        sa.UniqueConstraint("date", name=op.f("uq_daily_recaps_date")),
    )
    op.create_table(
        "monthly_reports",
        sa.Column("year", sa.SmallInteger(), nullable=False),
        sa.Column("month", sa.SmallInteger(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("month BETWEEN 1 AND 12", name=op.f("ck_monthly_reports_month_range")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_monthly_reports")),
        sa.UniqueConstraint("year", "month", name="uq_monthly_reports_year_month"),
    )
    op.create_table(
        "weekly_recaps",
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_weekly_recaps")),
        sa.UniqueConstraint("week_start", name=op.f("uq_weekly_recaps_week_start")),
    )
    op.create_table(
        "life_events",
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=True),
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
            "importance_score BETWEEN 0 AND 5", name=op.f("ck_life_events_importance_score_range")
        ),
        sa.ForeignKeyConstraint(
            ["journal_entry_id"],
            ["journal_entries.id"],
            name=op.f("fk_life_events_journal_entry_id_journal_entries"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_life_events")),
    )
    op.create_index(op.f("ix_life_events_event_date"), "life_events", ["event_date"], unique=False)
    op.create_index(
        op.f("ix_life_events_journal_entry_id"), "life_events", ["journal_entry_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_life_events_journal_entry_id"), table_name="life_events")
    op.drop_index(op.f("ix_life_events_event_date"), table_name="life_events")
    op.drop_table("life_events")
    op.drop_table("weekly_recaps")
    op.drop_table("monthly_reports")
    op.drop_table("daily_recaps")
