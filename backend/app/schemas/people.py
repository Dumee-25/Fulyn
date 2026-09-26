import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.schemas.common import ImportanceScore, NonBlankStr, PatchModel, ReadModel

RelationshipType = Literal[
    "friend", "crush", "mentor", "lecturer", "family", "colleague", "acquaintance", "other"
]
PersonName = Annotated[NonBlankStr, Field(max_length=100), AfterValidator(str.strip)]


# --- People ------------------------------------------------------------------------


class PersonCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: PersonName
    nickname: str | None = Field(default=None, max_length=100)
    relationship_type: RelationshipType | None = Field(
        default=None, description="Only if the user said it"
    )
    notes: str | None = None


class PersonUpdate(PatchModel):
    non_nullable = frozenset({"name"})

    name: PersonName | None = None
    nickname: str | None = Field(default=None, max_length=100)
    relationship_type: RelationshipType | None = None
    notes: str | None = None


class PersonRead(ReadModel):
    id: uuid.UUID
    name: str
    nickname: str | None
    relationship_type: str | None
    notes: str | None
    first_mentioned_at: date
    last_interaction_at: date | None
    created_at: datetime
    updated_at: datetime


class PersonSummary(PersonRead):
    interaction_count: int = 0


# --- Interactions ------------------------------------------------------------------


class InteractionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    person_id: uuid.UUID
    interaction_date: date | None = Field(default=None, description="Defaults to today")
    summary: NonBlankStr = Field(description="What happened, in plain words")
    raw_context: str | None = None
    location: str | None = Field(default=None, max_length=200)
    mood_before: str | None = Field(default=None, max_length=50)
    mood_after: str | None = Field(default=None, max_length=50)
    importance_score: ImportanceScore = 2
    journal_entry_id: uuid.UUID | None = None


class InteractionUpdate(PatchModel):
    non_nullable = frozenset({"person_id", "interaction_date", "summary", "importance_score"})

    person_id: uuid.UUID | None = None
    interaction_date: date | None = None
    summary: NonBlankStr | None = None
    location: str | None = Field(default=None, max_length=200)
    mood_before: str | None = Field(default=None, max_length=50)
    mood_after: str | None = Field(default=None, max_length=50)
    importance_score: ImportanceScore | None = None
    journal_entry_id: uuid.UUID | None = None


class InteractionRead(ReadModel):
    id: uuid.UUID
    person_id: uuid.UUID
    interaction_date: date
    summary: str
    raw_context: str | None
    location: str | None
    mood_before: str | None
    mood_after: str | None
    importance_score: int
    journal_entry_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class InteractionWithPerson(InteractionRead):
    person_name: str


# --- Music -------------------------------------------------------------------------


class MusicCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    song: Annotated[NonBlankStr, Field(max_length=200)]
    artist: str | None = Field(default=None, max_length=200)
    album: str | None = Field(default=None, max_length=200)
    memory_text: str | None = Field(default=None, description="What the song is tied to")
    emotion: str | None = Field(default=None, max_length=50)
    memory_date: date | None = Field(default=None, description="Defaults to today")
    person_id: uuid.UUID | None = None
    importance_score: ImportanceScore = 2
    journal_entry_id: uuid.UUID | None = None


class MusicUpdate(PatchModel):
    non_nullable = frozenset({"song", "memory_date", "importance_score"})

    song: Annotated[NonBlankStr, Field(max_length=200)] | None = None
    artist: str | None = Field(default=None, max_length=200)
    album: str | None = Field(default=None, max_length=200)
    memory_text: str | None = None
    emotion: str | None = Field(default=None, max_length=50)
    memory_date: date | None = None
    person_id: uuid.UUID | None = None
    importance_score: ImportanceScore | None = None
    journal_entry_id: uuid.UUID | None = None


class MusicRead(ReadModel):
    id: uuid.UUID
    song: str
    artist: str | None
    album: str | None
    memory_text: str | None
    emotion: str | None
    memory_date: date
    person_id: uuid.UUID | None
    importance_score: int
    journal_entry_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class MusicWithPerson(MusicRead):
    person_name: str | None = None


class SongCount(BaseModel):
    song: str
    artist: str | None
    count: int
