import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import ImportanceScore, NonBlankStr, PatchModel, ReadModel

# --- Life events -------------------------------------------------------------------


class LifeEventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: NonBlankStr = Field(max_length=200, description="e.g. 'Barista with Maya'")
    description: str | None = None
    event_date: date | None = Field(default=None, description="Defaults to today")
    event_type: str | None = Field(
        default=None, max_length=50, description="e.g. outing, milestone, trip, exam"
    )
    importance_score: ImportanceScore = 2
    journal_entry_id: uuid.UUID | None = None


class LifeEventUpdate(PatchModel):
    non_nullable = frozenset({"title", "event_date", "importance_score"})

    title: NonBlankStr | None = Field(default=None, max_length=200)
    description: str | None = None
    event_date: date | None = None
    event_type: str | None = Field(default=None, max_length=50)
    importance_score: ImportanceScore | None = None
    journal_entry_id: uuid.UUID | None = None


class LifeEventRead(ReadModel):
    id: uuid.UUID
    title: str
    description: str | None
    event_date: date
    event_type: str | None
    importance_score: int
    journal_entry_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


# --- Timeline ----------------------------------------------------------------------

TimelineKind = Literal["event", "decision", "interaction", "music", "journal", "purchase"]


class TimelineItem(BaseModel):
    kind: TimelineKind
    id: uuid.UUID
    date: date
    title: str
    detail: str | None = None
    importance_score: int


# --- Reports -----------------------------------------------------------------------


class ReportRead(BaseModel):
    kind: Literal["daily", "weekly", "monthly"]
    period_start: date
    period_end: date
    content: str
    data: dict[str, Any]
    generated_at: datetime
