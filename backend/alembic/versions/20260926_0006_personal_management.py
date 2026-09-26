"""personal management

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-26 17:10:22.068859+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reminders",
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recurrence_rule", sa.String(length=20), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("last_completed_at", sa.DateTime(timezone=True), nullable=True),
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
            "recurrence_rule IS NULL OR recurrence_rule IN ('daily', 'weekly', 'monthly', 'yearly')",
            name=op.f("ck_reminders_recurrence_rule_known"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'completed', 'cancelled')",
            name=op.f("ck_reminders_status_known"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reminders")),
    )
    op.create_index("ix_reminders_status_due_at", "reminders", ["status", "due_at"], unique=False)
    op.create_table(
        "subscriptions",
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("billing_cycle", sa.String(length=20), nullable=False),
        sa.Column("custom_interval_days", sa.Integer(), nullable=True),
        sa.Column("next_billing_date", sa.Date(), nullable=True),
        sa.Column("category", sa.String(length=50), server_default="Subscription", nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
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
            "billing_cycle <> 'custom' OR custom_interval_days > 0",
            name=op.f("ck_subscriptions_custom_cycle_has_interval"),
        ),
        sa.CheckConstraint(
            "billing_cycle IN ('weekly', 'monthly', 'quarterly', 'yearly', 'custom')",
            name=op.f("ck_subscriptions_billing_cycle_known"),
        ),
        sa.CheckConstraint("amount >= 0", name=op.f("ck_subscriptions_amount_non_negative")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subscriptions")),
    )
    op.create_index(op.f("ix_subscriptions_active"), "subscriptions", ["active"], unique=False)
    op.create_table(
        "decisions",
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("decision_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
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
            "status IN ('active', 'reconsidered', 'reversed', 'completed')",
            name=op.f("ck_decisions_status_known"),
        ),
        sa.CheckConstraint(
            "importance_score BETWEEN 0 AND 5", name=op.f("ck_decisions_importance_score_range")
        ),
        sa.ForeignKeyConstraint(
            ["journal_entry_id"],
            ["journal_entries.id"],
            name=op.f("fk_decisions_journal_entry_id_journal_entries"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_decisions")),
    )
    op.create_index(
        op.f("ix_decisions_decision_date"), "decisions", ["decision_date"], unique=False
    )
    op.create_index(
        op.f("ix_decisions_journal_entry_id"), "decisions", ["journal_entry_id"], unique=False
    )
    op.create_table(
        "waiting_items",
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("waiting_since", sa.Date(), nullable=False),
        sa.Column("expected_by", sa.Date(), nullable=True),
        sa.Column("related_person_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="waiting", nullable=False),
        sa.Column("resolved_at", sa.Date(), nullable=True),
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
            "status IN ('waiting', 'received', 'cancelled', 'expired')",
            name=op.f("ck_waiting_items_status_known"),
        ),
        sa.ForeignKeyConstraint(
            ["related_person_id"],
            ["people.id"],
            name=op.f("fk_waiting_items_related_person_id_people"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_waiting_items")),
    )
    op.create_index(
        op.f("ix_waiting_items_related_person_id"),
        "waiting_items",
        ["related_person_id"],
        unique=False,
    )
    op.create_index(op.f("ix_waiting_items_status"), "waiting_items", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_waiting_items_status"), table_name="waiting_items")
    op.drop_index(op.f("ix_waiting_items_related_person_id"), table_name="waiting_items")
    op.drop_table("waiting_items")
    op.drop_index(op.f("ix_decisions_journal_entry_id"), table_name="decisions")
    op.drop_index(op.f("ix_decisions_decision_date"), table_name="decisions")
    op.drop_table("decisions")
    op.drop_index(op.f("ix_subscriptions_active"), table_name="subscriptions")
    op.drop_table("subscriptions")
    op.drop_index("ix_reminders_status_due_at", table_name="reminders")
    op.drop_table("reminders")
