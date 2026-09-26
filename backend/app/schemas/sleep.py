import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import LocalDateTime, PatchModel, ReadModel, Score10

DurationMinutes = Annotated[int, Field(ge=0, le=1440)]


class SleepLogCreate(BaseModel):
    """All fields optional: "slept about 5 hours" is a valid log.

    When both times are given and the duration is not, the duration is computed.
    """

    model_config = ConfigDict(extra="forbid")

    sleep_date: date | None = Field(
        default=None, description="Date woken up on. Defaults to the wake date, else today"
    )
    sleep_time: LocalDateTime | None = None
    wake_time: LocalDateTime | None = None
    duration_minutes: DurationMinutes | None = None
    is_approximate: bool = False
    quality_score: Score10 | None = None
    notes: str | None = None
    journal_entry_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _check_times(self) -> "SleepLogCreate":
        if self.sleep_time and self.wake_time and self.wake_time <= self.sleep_time:
            raise ValueError("wake_time must be after sleep_time")
        return self


class SleepLogUpdate(PatchModel):
    non_nullable = frozenset({"sleep_date", "is_approximate"})

    sleep_date: date | None = None
    sleep_time: LocalDateTime | None = None
    wake_time: LocalDateTime | None = None
    duration_minutes: DurationMinutes | None = None
    is_approximate: bool | None = None
    quality_score: Score10 | None = None
    notes: str | None = None
    journal_entry_id: uuid.UUID | None = None


class SleepLogRead(ReadModel):
    id: uuid.UUID
    sleep_date: date
    sleep_time: datetime | None
    wake_time: datetime | None
    duration_minutes: int | None
    is_approximate: bool
    quality_score: int | None
    notes: str | None
    journal_entry_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
