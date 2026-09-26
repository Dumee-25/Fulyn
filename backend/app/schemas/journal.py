import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import ImportanceScore, NonBlankStr, PatchModel, ReadModel


class JournalEntryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Stored exactly as given; never trimmed or rewritten.
    raw_text: NonBlankStr
    ai_summary: str | None = None
    entry_date: date | None = Field(default=None, description="Defaults to today (local time)")
    mood_summary: str | None = Field(default=None, max_length=200)
    is_private: bool = False
    importance_score: ImportanceScore = 2


class JournalEntryUpdate(PatchModel):
    non_nullable = frozenset({"raw_text", "entry_date", "is_private", "importance_score"})

    raw_text: NonBlankStr | None = None
    ai_summary: str | None = None
    entry_date: date | None = None
    mood_summary: str | None = Field(default=None, max_length=200)
    is_private: bool | None = None
    importance_score: ImportanceScore | None = None


class JournalEntryRead(ReadModel):
    id: uuid.UUID
    raw_text: str
    ai_summary: str | None
    entry_date: date
    mood_summary: str | None
    is_private: bool
    importance_score: int
    created_at: datetime
    updated_at: datetime
