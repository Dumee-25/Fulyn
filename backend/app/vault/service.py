"""Reading and managing vault content. The only code path that returns private data."""

import uuid
from datetime import date
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.errors import DomainError, NotFoundError
from app.models.caffeine import CaffeineLog
from app.models.conversation import ChatMessage
from app.models.expense import Expense
from app.models.journal import JournalEntry
from app.models.memory import Memory
from app.models.mood import MoodLog
from app.models.people import MusicMemory, PersonInteraction
from app.models.planning import Decision
from app.models.report import LifeEvent
from app.models.sleep import SleepLog
from app.schemas.journal import JournalEntryUpdate
from app.schemas.memory import MemorySearchResponse
from app.services import journal, memories

# Record types that become vault content through their journal entry.
LINKED = {
    "expenses": Expense,
    "moods": MoodLog,
    "sleep": SleepLog,
    "caffeine": CaffeineLog,
    "interactions": PersonInteraction,
    "music": MusicMemory,
    "decisions": Decision,
    "events": LifeEvent,
}
MEMORY_SOURCES = {
    "person_interaction": PersonInteraction,
    "music": MusicMemory,
    "decision": Decision,
    "event": LifeEvent,
}


class NotVaultableError(DomainError):
    def __init__(self) -> None:
        super().__init__("only records that belong to a journal entry can be moved to the vault")


def list_entries(
    db: Session,
    *,
    query: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[JournalEntry]:
    return journal.list_journal_entries(
        db,
        private=True,
        query=query,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )


def get_entry(db: Session, entry_id: uuid.UUID) -> JournalEntry:
    entry = journal.get_journal_entry(db, entry_id)
    if not entry.is_private:
        raise NotFoundError("Vault entry")
    return entry


def linked_counts(db: Session, entry_id: uuid.UUID) -> dict[str, int]:
    """How many records share the entry's privacy (for the UI)."""
    counts = {}
    for name, model in LINKED.items():
        n = db.scalar(
            select(func.count()).select_from(model).where(model.journal_entry_id == entry_id)
        )
        if n:
            counts[name] = n
    return counts


def search(db: Session, query: str, limit: int = 10) -> MemorySearchResponse:
    """Hybrid search over vault memories only."""
    return memories.search_memories(db, query, private=True, limit=limit)


def set_entry_private(db: Session, entry_id: uuid.UUID, private: bool) -> JournalEntry:
    """Move a journal entry (and everything linked to it) into or out of the vault."""
    entry = journal.update_journal_entry(db, entry_id, JournalEntryUpdate(is_private=private))
    mark_chat_turns(db, entry.raw_text, private)
    return entry


def journal_entry_for_memory(db: Session, memory_id: uuid.UUID) -> uuid.UUID:
    memory = memories.get_memory(db, memory_id)
    if memory.memory_type == "journal" and memory.source_id:
        return memory.source_id
    model = MEMORY_SOURCES.get(memory.memory_type)
    source = db.get(model, memory.source_id) if model and memory.source_id else None
    if source is None or source.journal_entry_id is None:
        raise NotVaultableError()
    return source.journal_entry_id


def mark_chat_turns(db: Session, raw_text: str, private: bool) -> int:
    """Mark the chat turn(s) where this text was said, so they stop being sent to the model.

    Journal text is the user's message verbatim, so the turn is found by exact match. A turn
    is the user message plus every message after it until the next user message.
    """
    starts = list(
        db.scalars(
            select(ChatMessage).where(ChatMessage.role == "user", ChatMessage.content == raw_text)
        )
    )
    changed = 0
    for start in starts:
        next_user = db.scalar(
            select(func.min(ChatMessage.created_at)).where(
                ChatMessage.conversation_id == start.conversation_id,
                ChatMessage.role == "user",
                ChatMessage.created_at > start.created_at,
            )
        )
        stmt = update(ChatMessage).where(
            ChatMessage.conversation_id == start.conversation_id,
            ChatMessage.created_at >= start.created_at,
        )
        if next_user is not None:
            stmt = stmt.where(ChatMessage.created_at < next_user)
        changed += db.execute(stmt.values(is_private=private)).rowcount
    db.commit()
    return changed


def summary(db: Session) -> dict[str, Any]:
    return {
        "entries": db.scalar(
            select(func.count()).select_from(JournalEntry).where(JournalEntry.is_private.is_(True))
        ),
        "memories": db.scalar(
            select(func.count()).select_from(Memory).where(Memory.is_private.is_(True))
        ),
    }
