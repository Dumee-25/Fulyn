import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import today_local
from app.models.journal import JournalEntry
from app.schemas.journal import JournalEntryCreate, JournalEntryUpdate
from app.services import crud, memories


def create_journal_entry(db: Session, data: JournalEntryCreate) -> JournalEntry:
    entry = JournalEntry(**data.model_dump(exclude={"entry_date"}))
    entry.entry_date = data.entry_date or today_local()
    crud.save(db, entry)
    memories.sync_journal_memory(db, entry)
    return entry


def get_journal_entry(db: Session, entry_id: uuid.UUID) -> JournalEntry:
    return crud.get_or_raise(db, JournalEntry, entry_id)


def list_journal_entries(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    query: str | None = None,
    min_importance: int | None = None,
    private: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> list[JournalEntry]:
    """Public entries, or with private=True vault entries only (used by app.vault)."""
    stmt = select(JournalEntry).where(JournalEntry.is_private.is_(private))
    stmt = crud.date_range(stmt, JournalEntry.entry_date, date_from, date_to)
    if query:
        stmt = stmt.where(JournalEntry.raw_text.ilike(f"%{query}%"))
    if min_importance is not None:
        stmt = stmt.where(JournalEntry.importance_score >= min_importance)
    stmt = stmt.order_by(JournalEntry.entry_date.desc(), JournalEntry.created_at.desc())
    return crud.paginate(db, stmt, limit, offset)


def update_journal_entry(
    db: Session, entry_id: uuid.UUID, data: JournalEntryUpdate
) -> JournalEntry:
    changes = data.changes()
    entry = crud.apply_changes(db, get_journal_entry(db, entry_id), changes)
    if "importance_score" in changes:
        # Importance belongs to the moment: linked records follow the entry.
        memories.set_moment_importance(db, entry.id, entry.importance_score)
    else:
        memories.sync_journal_memory(db, entry)
    return entry


def delete_journal_entry(db: Session, entry_id: uuid.UUID) -> None:
    """Linked records keep existing; their journal_entry_id becomes NULL and each gets a
    memory of its own again."""
    linked = memories.moment_records(db, entry_id)
    crud.delete(db, get_journal_entry(db, entry_id))
    memories.delete_memories_for(db, "journal", entry_id)
    for record in linked:
        db.refresh(record)
        memories.sync_record_memory(db, record)
