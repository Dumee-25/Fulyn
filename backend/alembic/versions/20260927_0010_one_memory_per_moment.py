"""one memory per moment

Records linked to a journal entry (interactions, events, music, decisions) no longer get a
memory of their own: the journal entry's memory stands for the whole moment, with the
linked people, places, event, song and decision titles in a new ``tags`` column that is
part of the full-text vector and the embedding.

Data steps:
1. Importance becomes per moment: the journal entry and its linked records all take the
   highest importance among them.
2. Memory rows of linked records are deleted.
3. Journal memories of affected entries get their tags and the moment's importance, and
   their embedding is cleared so the backfill re-embeds them with the tags.

The data steps are not reversed on downgrade (re-saving a record recreates its memory).

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-27 12:00:00.000000+00:00

"""

import logging
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")

OLD_VECTOR = "to_tsvector('english', coalesce(title, '') || ' ' || content)"
NEW_VECTOR = (
    "to_tsvector('english', coalesce(title, '') || ' ' || content || ' ' || coalesce(tags, ''))"
)
# memory_type -> table, in the order tags are built (see app.services.memories).
LINKED = {
    "person_interaction": "person_interactions",
    "event": "life_events",
    "music": "music_memories",
    "decision": "decisions",
}
TITLE_MAX = 200


def _replace_search_vector(expression: str) -> None:
    op.drop_index("ix_memories_search_vector", table_name="memories", postgresql_using="gin")
    op.drop_column("memories", "search_vector")
    op.add_column(
        "memories",
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(expression, persisted=True),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_memories_search_vector", "memories", ["search_vector"], postgresql_using="gin"
    )


def _moment_tags(conn: sa.Connection, entry_id: uuid.UUID) -> list[str]:
    """Same tags, in the same order, as app.services.memories.moment_tags."""
    tags: list[str | None] = []
    for row in conn.execute(
        sa.text(
            "SELECT p.name, i.location FROM person_interactions i "
            "LEFT JOIN people p ON p.id = i.person_id "
            "WHERE i.journal_entry_id = :id ORDER BY i.created_at, i.id"
        ),
        {"id": entry_id},
    ):
        tags += [row.name, row.location]
    tags += conn.scalars(
        sa.text(
            "SELECT title FROM life_events WHERE journal_entry_id = :id ORDER BY created_at, id"
        ),
        {"id": entry_id},
    ).all()
    for row in conn.execute(
        sa.text(
            "SELECT m.song, m.artist, p.name FROM music_memories m "
            "LEFT JOIN people p ON p.id = m.person_id "
            "WHERE m.journal_entry_id = :id ORDER BY m.created_at, m.id"
        ),
        {"id": entry_id},
    ):
        tags += [row.song + (f" by {row.artist}" if row.artist else ""), row.name]
    tags += conn.scalars(
        sa.text("SELECT title FROM decisions WHERE journal_entry_id = :id ORDER BY created_at, id"),
        {"id": entry_id},
    ).all()
    seen: set[str] = set()
    unique = []
    for tag in tags:
        tag = " ".join((tag or "").split())[:TITLE_MAX]
        if tag and tag.lower() not in seen:
            seen.add(tag.lower())
            unique.append(tag)
    return unique


def fold_moments(conn: sa.Connection) -> dict[str, int]:
    """The data steps. Returns counts of what changed (also logged)."""
    entry_ids = sorted(
        set(
            conn.scalars(
                sa.text(
                    " UNION ".join(
                        f"SELECT journal_entry_id FROM {table} WHERE journal_entry_id IS NOT NULL"
                        for table in LINKED.values()
                    )
                )
            ).all()
        )
    )
    counts = {"moments": len(entry_ids), "entries_raised": 0, "records_aligned": 0}

    # 1. Importance per moment: the highest among the entry and its records.
    linked_scores = " UNION ALL ".join(
        f"SELECT journal_entry_id, importance_score FROM {table}" for table in LINKED.values()
    )
    counts["entries_raised"] = conn.execute(
        sa.text(
            f"UPDATE journal_entries j SET importance_score = sub.top "
            f"FROM (SELECT journal_entry_id, max(importance_score) AS top FROM ({linked_scores}) u "
            f"WHERE journal_entry_id IS NOT NULL GROUP BY journal_entry_id) sub "
            f"WHERE j.id = sub.journal_entry_id AND j.importance_score < sub.top"
        )
    ).rowcount
    for table in LINKED.values():
        counts["records_aligned"] += conn.execute(
            sa.text(
                f"UPDATE {table} t SET importance_score = j.importance_score "
                f"FROM journal_entries j "
                f"WHERE t.journal_entry_id = j.id AND t.importance_score <> j.importance_score"
            )
        ).rowcount

    # 2. Linked records lose their own memory.
    deleted = 0
    for memory_type, table in LINKED.items():
        deleted += conn.execute(
            sa.text(
                f"DELETE FROM memories m USING {table} t "
                f"WHERE m.memory_type = :type AND m.source_id = t.id "
                f"AND t.journal_entry_id IS NOT NULL"
            ),
            {"type": memory_type},
        ).rowcount
    counts["memories_deleted"] = deleted

    # 3. Journal memories carry the moment: tags, importance, privacy; re-embed later.
    updated = 0
    for entry_id in entry_ids:
        tags = "\n".join(_moment_tags(conn, entry_id)) or None
        updated += conn.execute(
            sa.text(
                "UPDATE memories m SET tags = :tags, importance_score = j.importance_score, "
                "is_private = j.is_private, embedding = NULL, embedding_model = NULL, "
                "updated_at = now() "
                "FROM journal_entries j "
                "WHERE m.memory_type = 'journal' AND m.source_id = :id AND j.id = :id"
            ),
            {"tags": tags, "id": entry_id},
        ).rowcount
    counts["journal_memories_updated"] = updated

    logger.info("one memory per moment: %s", counts)
    return counts


def upgrade() -> None:
    op.add_column("memories", sa.Column("tags", sa.Text(), nullable=True))
    _replace_search_vector(NEW_VECTOR)
    fold_moments(op.get_bind())


def downgrade() -> None:
    _replace_search_vector(OLD_VECTOR)
    op.drop_column("memories", "tags")
