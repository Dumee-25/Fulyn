import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DbSession, ListQuery
from app.core.errors import NotFoundError
from app.schemas.journal import JournalEntryCreate, JournalEntryRead, JournalEntryUpdate
from app.services import journal as service

router = APIRouter(prefix="/journal", tags=["journal"])


@router.get("", response_model=list[JournalEntryRead])
def list_entries(
    db: DbSession,
    params: ListQuery,
    q: Annotated[str | None, Query(max_length=200, description="Text search")] = None,
    min_importance: Annotated[int | None, Query(ge=0, le=5)] = None,
):
    return service.list_journal_entries(
        db,
        query=q,
        min_importance=min_importance,
        **params.model_dump(),
    )


@router.post("", response_model=JournalEntryRead, status_code=status.HTTP_201_CREATED)
def create_entry(db: DbSession, data: JournalEntryCreate):
    return service.create_journal_entry(db, data)


@router.get("/{entry_id}", response_model=JournalEntryRead)
def get_entry(db: DbSession, entry_id: uuid.UUID):
    entry = service.get_journal_entry(db, entry_id)
    if entry.is_private:
        # Vault entries are only served by /api/vault.
        raise NotFoundError("JournalEntry")
    return entry


@router.patch("/{entry_id}", response_model=JournalEntryRead)
def update_entry(db: DbSession, entry_id: uuid.UUID, data: JournalEntryUpdate):
    return service.update_journal_entry(db, entry_id, data)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entry(db: DbSession, entry_id: uuid.UUID) -> None:
    service.delete_journal_entry(db, entry_id)
