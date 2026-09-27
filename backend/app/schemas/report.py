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


class TimelineMoment(BaseModel):
    """One logged moment: a chat message's journal entry and the records made from it,
    or a single record added on its own."""

    journal_entry_id: uuid.UUID | None = None
    # What the moment contains, most telling first (event, decision, interaction, …).
    kinds: list[TimelineKind]
    line: str
    # The user's original words (the journal entry), else the record's own detail.
    text: str | None = None
    importance_score: int


class TimelineTag(BaseModel):
    kind: Literal["person", "place", "amount"]
    label: str


class TimelineDay(BaseModel):
    date: date
    headline: str
    headline_kind: TimelineKind
    importance_score: int
    summary: str | None = None
    # "recap" when the summary is the stored daily recap's narrative.
    summary_source: Literal["recap", "records"] = "records"
    tags: list[TimelineTag]
    moments: list[TimelineMoment]


# --- Reports -----------------------------------------------------------------------


class ReportRead(BaseModel):
    kind: Literal["daily", "weekly", "monthly"]
    period_start: date
    period_end: date
    content: str
    data: dict[str, Any]
    generated_at: datetime
