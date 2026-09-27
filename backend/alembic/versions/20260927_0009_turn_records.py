"""turn records

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-27 01:18:07.832570+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "turn_records",
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("record_type", sa.String(length=40), nullable=False),
        sa.Column("record_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_turn_records_conversation_id_conversations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["chat_messages.id"],
            name=op.f("fk_turn_records_message_id_chat_messages"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_turn_records")),
    )
    op.create_index(
        op.f("ix_turn_records_conversation_id"), "turn_records", ["conversation_id"], unique=False
    )
    op.create_index(
        op.f("ix_turn_records_message_id"), "turn_records", ["message_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_turn_records_message_id"), table_name="turn_records")
    op.drop_index(op.f("ix_turn_records_conversation_id"), table_name="turn_records")
    op.drop_table("turn_records")
