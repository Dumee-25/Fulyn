import datetime as dt
import uuid
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import PatchModel, ReadModel, Score10

MoodLabel = Annotated[
    str,
    Field(max_length=30, description="e.g. great, good, calm, neutral, tired, mixed"),
    AfterValidator(lambda v: v.strip().lower()),
]


class MoodLogCreate(BaseModel):
    """Mood and energy are separate scales. This is a log, not a diagnosis."""

    model_config = ConfigDict(extra="forbid")

    date: dt.date | None = Field(default=None, description="Defaults to today (local time)")
    score: Score10 | None = None
    label: MoodLabel | None = None
    energy_score: Score10 | None = None
    notes: str | None = None
    journal_entry_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _has_signal(self) -> "MoodLogCreate":
        if self.score is None and self.label is None and self.energy_score is None:
            raise ValueError("provide at least one of score, label or energy_score")
        return self


class MoodLogUpdate(PatchModel):
    non_nullable = frozenset({"date"})

    date: dt.date | None = None
    score: Score10 | None = None
    label: MoodLabel | None = None
    energy_score: Score10 | None = None
    notes: str | None = None
    journal_entry_id: uuid.UUID | None = None


class MoodLogRead(ReadModel):
    id: uuid.UUID
    date: dt.date
    score: int | None
    label: str | None
    energy_score: int | None
    notes: str | None
    journal_entry_id: uuid.UUID | None
    created_at: dt.datetime
    updated_at: dt.datetime
