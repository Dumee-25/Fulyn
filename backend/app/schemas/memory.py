import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import Field, field_validator

from app.schemas.common import ImportanceScore, PatchModel, ReadModel

MemoryType = Literal[
    "journal", "event", "person_interaction", "decision", "music", "expense", "other"
]


class MemoryRead(ReadModel):
    id: uuid.UUID
    memory_type: str
    source_id: uuid.UUID | None
    title: str | None
    content: str
    # People, places, events, songs and decisions logged in the same moment.
    tags: list[str] = []
    memory_date: date
    importance_score: int
    is_private: bool
    created_at: datetime
    updated_at: datetime

    @field_validator("tags", mode="before")
    @classmethod
    def _split_tags(cls, value: object) -> object:
        if value is None:
            return []
        return value.splitlines() if isinstance(value, str) else value


class MemorySearchResult(MemoryRead):
    # Cosine similarity to the query; None when semantic search was not available.
    similarity: float | None = None
    # True when the memory's text contains words from the query (full-text match).
    keyword_match: bool = False


class MemorySearchResponse(ReadModel):
    query: str
    semantic: bool = Field(description="False when only full-text search could run")
    results: list[MemorySearchResult]


class MemoryUpdate(PatchModel):
    non_nullable = frozenset({"importance_score"})

    importance_score: ImportanceScore | None = None
    title: str | None = Field(default=None, max_length=200)
