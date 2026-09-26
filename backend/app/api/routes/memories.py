import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession, ListQuery
from app.core.errors import NotFoundError
from app.schemas.memory import MemoryRead, MemorySearchResponse, MemoryType, MemoryUpdate
from app.services import memories as service

router = APIRouter(prefix="/memories", tags=["memories"])

# Private (vault) memories are not served here; the vault gets its own routes in Phase 9.


@router.get("", response_model=list[MemoryRead])
def list_memories(
    db: DbSession,
    params: ListQuery,
    min_importance: Annotated[int | None, Query(ge=0, le=5)] = None,
    memory_type: MemoryType | None = None,
):
    return service.list_memories(
        db, min_importance=min_importance, memory_type=memory_type, **params.model_dump()
    )


@router.get("/search", response_model=MemorySearchResponse)
def search(
    db: DbSession,
    q: Annotated[str, Query(min_length=1, max_length=500)],
    date_from: date | None = None,
    date_to: date | None = None,
    min_importance: Annotated[int | None, Query(ge=0, le=5)] = None,
    memory_type: MemoryType | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
):
    return service.search_memories(
        db,
        q,
        date_from=date_from,
        date_to=date_to,
        min_importance=min_importance,
        memory_type=memory_type,
        limit=limit,
    )


@router.post("/backfill")
def backfill(db: DbSession, limit: Annotated[int, Query(ge=1, le=1000)] = 200) -> dict[str, int]:
    """Embed memories that are missing embeddings (e.g. after Ollama was down)."""
    return {"embedded": service.backfill_embeddings(db, limit=limit)}


@router.get("/{memory_id}", response_model=MemoryRead)
def get_memory(db: DbSession, memory_id: uuid.UUID):
    memory = service.get_memory(db, memory_id)
    if memory.is_private:
        # Behave as if it does not exist outside the vault.
        raise NotFoundError("Memory")
    return memory


@router.patch("/{memory_id}", response_model=MemoryRead)
def update_memory(db: DbSession, memory_id: uuid.UUID, data: MemoryUpdate):
    return service.update_memory(db, memory_id, data)
