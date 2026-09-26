"""The only HTTP routes that return private content."""

import datetime as dt
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.schemas.journal import JournalEntryRead
from app.schemas.memory import MemorySearchResponse
from app.vault import service as vault

router = APIRouter(prefix="/vault", tags=["vault"])


@router.get("")
def summary(db: DbSession) -> dict[str, Any]:
    return vault.summary(db)


@router.get("/entries", response_model=list[JournalEntryRead])
def list_entries(
    db: DbSession,
    q: Annotated[str | None, Query(max_length=200)] = None,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
):
    return vault.list_entries(db, query=q, date_from=date_from, date_to=date_to, limit=limit)


@router.get("/entries/{entry_id}")
def get_entry(db: DbSession, entry_id: uuid.UUID) -> dict[str, Any]:
    entry = vault.get_entry(db, entry_id)
    return {
        "entry": JournalEntryRead.model_validate(entry).model_dump(mode="json"),
        "linked": vault.linked_counts(db, entry_id),
    }


@router.get("/search", response_model=MemorySearchResponse)
def search(
    db: DbSession,
    q: Annotated[str, Query(min_length=1, max_length=500)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
):
    return vault.search(db, q, limit=limit)


@router.put("/entries/{entry_id}", response_model=JournalEntryRead)
def move_to_vault(db: DbSession, entry_id: uuid.UUID):
    """Make a journal entry, and everything logged with it, private."""
    return vault.set_entry_private(db, entry_id, True)


@router.delete("/entries/{entry_id}", response_model=JournalEntryRead)
def remove_from_vault(db: DbSession, entry_id: uuid.UUID):
    """Make a vault entry public again (the entry is kept)."""
    return vault.set_entry_private(db, entry_id, False)
