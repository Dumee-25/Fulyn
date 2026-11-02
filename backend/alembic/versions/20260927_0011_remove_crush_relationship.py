"""remove the crush relationship type

Narrows the ``relationship_type`` check constraint on ``people``. Any existing person
marked ``crush`` is set back to unknown (NULL) first, since the type is no longer allowed.
Downgrade restores the wider constraint; it does not bring the old values back.

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-27 18:00:00.000000+00:00

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT = "ck_people_relationship_type_known"
NEW_TYPES = ("friend", "mentor", "lecturer", "family", "colleague", "acquaintance", "other")
OLD_TYPES = ("friend", "crush", "mentor", "lecturer", "family", "colleague", "acquaintance", "other")


def _check(types: Sequence[str]) -> str:
    return "relationship_type IN (" + ", ".join(f"'{t}'" for t in types) + ")"


def upgrade() -> None:
    op.execute("UPDATE people SET relationship_type = NULL WHERE relationship_type = 'crush'")
    op.drop_constraint(op.f(CONSTRAINT), "people", type_="check")
    op.create_check_constraint(op.f(CONSTRAINT), "people", _check(NEW_TYPES))


def downgrade() -> None:
    op.drop_constraint(op.f(CONSTRAINT), "people", type_="check")
    op.create_check_constraint(op.f(CONSTRAINT), "people", _check(OLD_TYPES))
