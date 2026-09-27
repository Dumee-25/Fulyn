"""Agent tools for people, interactions and music memories.

People are referred to by name; the backend matches existing people (name, nickname or
first name) and creates new ones. Ambiguous names come back as an error listing the
candidates, so the model asks instead of guessing. ``raw_context`` of an interaction is
always the user's message, never model text.
"""

import uuid
from datetime import date
from typing import Any

from pydantic import Field, model_validator

from app.models.journal import JournalEntry
from app.models.people import MusicMemory, Person, PersonInteraction
from app.schemas.common import ImportanceScore
from app.schemas.people import (
    InteractionCreate,
    InteractionUpdate,
    InteractionWithPerson,
    MusicCreate,
    MusicUpdate,
    MusicWithPerson,
    PersonCreate,
    PersonRead,
    PersonUpdate,
    RelationshipType,
)
from app.services import people
from app.tools.life_logging import (
    DateRangeArgs,
    ToolArgs,
    delete_tool,
    link_to_turn,
    update_tool,
)
from app.tools.registry import Tool, ToolContext

PERSON_FIELDS = {"id", "name", "nickname", "relationship_type", "last_interaction_at"}
JOURNAL_EXCERPT = 600


class PersonRef(ToolArgs):
    person_id: uuid.UUID | None = Field(default=None, description="If known from earlier")
    person_name: str | None = Field(
        default=None, max_length=100, description="Name as the user said it"
    )


def _person_payload(person: Any) -> dict[str, Any]:
    return PersonRead.model_validate(person).model_dump(include=PERSON_FIELDS)


def _resolve(ctx: ToolContext, ref: PersonRef, *, create: bool) -> tuple[Any, bool]:
    if ref.person_id is not None:
        return people.get_person(ctx.db, ref.person_id), False
    if ref.person_name:
        return people.resolve_person(ctx.db, ref.person_name, create=create)
    return None, False


# --- People ------------------------------------------------------------------------


class FindPersonArgs(ToolArgs):
    name: str = Field(max_length=100)


def find_person(ctx: ToolContext, args: FindPersonArgs) -> dict[str, Any]:
    found = people.list_people(ctx.db, query=args.name, limit=10)
    return {
        "count": len(found),
        "people": [{**_person_payload(p), "interaction_count": p.interaction_count} for p in found],
    }


def create_person(ctx: ToolContext, args: PersonCreate) -> dict[str, Any]:
    existing = people.find_people(ctx.db, args.name)
    if existing:
        return {
            "people": [_person_payload(p) for p in existing],
            "note": "a person with this name already exists; use their id, or ask the "
            "user if this is someone different",
        }
    person = people.create_person(ctx.db, args)
    ctx.created.append((Person, person.id))
    return {"person": _person_payload(person)}


# --- Interactions ------------------------------------------------------------------


class CreateInteractionArgs(PersonRef):
    interaction_date: date | None = Field(default=None, description="Defaults to today")
    summary: str = Field(
        min_length=1, description="What happened, from the user's words, e.g. 'Met after uni'"
    )
    location: str | None = Field(default=None, max_length=200)
    mood_before: str | None = Field(
        default=None, max_length=50, description="The user's own mood, only if stated"
    )
    mood_after: str | None = Field(default=None, max_length=50)
    importance_score: ImportanceScore = 2

    @model_validator(mode="after")
    def _needs_person(self) -> "CreateInteractionArgs":
        if self.person_id is None and not self.person_name:
            raise ValueError("give person_name or person_id")
        return self


def create_person_interaction(ctx: ToolContext, args: CreateInteractionArgs) -> dict[str, Any]:
    person, created = _resolve(ctx, args, create=True)
    if created:
        ctx.created.append((Person, person.id))
    data = InteractionCreate(
        person_id=person.id,
        raw_context=ctx.user_message,
        **args.model_dump(exclude={"person_id", "person_name"}),
    )
    link_to_turn(ctx, data)
    interaction = people.create_interaction(ctx.db, data)
    ctx.created.append((PersonInteraction, interaction.id))
    record = people.with_person(ctx.db, interaction).model_dump(
        exclude={"created_at", "updated_at", "raw_context"}
    )
    return {"record": record, "person": _person_payload(person), "person_created": created}


class GetInteractionsArgs(PersonRef, DateRangeArgs):
    pass


def get_person_interactions(ctx: ToolContext, args: GetInteractionsArgs) -> dict[str, Any]:
    person, _ = _resolve(ctx, args, create=False)
    if (args.person_id or args.person_name) and person is None:
        return {"count": 0, "interactions": [], "note": "no person with that name"}
    found = people.list_interactions(
        ctx.db,
        person_id=person.id if person else None,
        date_from=args.date_from,
        date_to=args.date_to,
        limit=args.limit,
    )
    results = []
    for item in found:
        data = item.model_dump(exclude={"created_at", "updated_at", "raw_context"})
        # What the user wrote that day, for "what did I write after talking to X".
        entry = ctx.db.get(JournalEntry, item.journal_entry_id) if item.journal_entry_id else None
        if entry is not None and not entry.is_private:
            data["journal_text"] = entry.raw_text[:JOURNAL_EXCERPT]
        results.append(data)
    payload: dict[str, Any] = {"count": len(results), "interactions": results}
    if person is not None:
        payload["person"] = _person_payload(person)
    return payload


# --- Music -------------------------------------------------------------------------


class CreateMusicArgs(PersonRef):
    song: str = Field(min_length=1, max_length=200)
    artist: str | None = Field(default=None, max_length=200)
    album: str | None = Field(default=None, max_length=200)
    memory_text: str | None = Field(default=None, description="What the song is tied to")
    emotion: str | None = Field(default=None, max_length=50)
    memory_date: date | None = Field(default=None, description="Defaults to today")
    importance_score: ImportanceScore = 2


def create_music_memory(ctx: ToolContext, args: CreateMusicArgs) -> dict[str, Any]:
    person, created = _resolve(ctx, args, create=True)
    if created:
        ctx.created.append((Person, person.id))
    data = MusicCreate(
        person_id=person.id if person else None,
        **args.model_dump(exclude={"person_id", "person_name"}),
    )
    link_to_turn(ctx, data)
    music = people.create_music(ctx.db, data)
    ctx.created.append((MusicMemory, music.id))
    record = people.music_with_person(ctx.db, music).model_dump(
        exclude={"created_at", "updated_at"}
    )
    return {"record": record, "person_created": created}


class SearchMusicArgs(PersonRef, DateRangeArgs):
    query: str | None = Field(default=None, description="Song, artist, album or memory text")
    artist: str | None = None
    emotion: str | None = None


def search_music_memories(ctx: ToolContext, args: SearchMusicArgs) -> dict[str, Any]:
    person, _ = _resolve(ctx, args, create=False)
    if (args.person_id or args.person_name) and person is None:
        return {"count": 0, "music": [], "note": "no person with that name"}
    found = people.list_music(
        ctx.db,
        query=args.query,
        artist=args.artist,
        person_id=person.id if person else None,
        emotion=args.emotion,
        date_from=args.date_from,
        date_to=args.date_to,
        limit=args.limit,
    )
    payload: dict[str, Any] = {
        "count": len(found),
        "music": [m.model_dump(exclude={"created_at", "updated_at"}) for m in found],
    }
    if args.date_from or args.date_to:
        payload["most_mentioned"] = [
            s.model_dump()
            for s in people.top_songs(ctx.db, date_from=args.date_from, date_to=args.date_to)
        ]
    return payload


def _person_update(ctx: ToolContext, args: Any) -> dict[str, Any]:
    changes = args.changes()
    person_id = changes.pop("person_id")
    person = people.update_person(ctx.db, person_id, PersonUpdate.model_validate(changes))
    return {"person": _person_payload(person)}


class UpdatePersonArgs(PersonUpdate):
    person_id: uuid.UUID
    relationship_type: RelationshipType | None = Field(
        default=None, description="Only if the user said it"
    )


def people_tools() -> list[Tool]:
    return [
        Tool(
            "find_person",
            "Look up people by name or nickname. Returns matches with their ids.",
            FindPersonArgs,
            find_person,
        ),
        Tool(
            "create_person",
            "Add a person. Only include a relationship or notes the user stated. Usually "
            "not needed: interaction and music tools create people automatically.",
            PersonCreate,
            create_person,
        ),
        Tool(
            "update_person",
            "Change a person's name, nickname, relationship or notes.",
            UpdatePersonArgs,
            _person_update,
        ),
        delete_tool(
            "delete_person",
            "Delete a person and their interactions. Only when the user explicitly asks.",
            "person_id",
            people.delete_person,
        ),
        Tool(
            "create_person_interaction",
            "Record time the user spent with someone (met, talked, called). One call per "
            "person. Give person_name as the user said it; the person is matched or "
            "created. Summarize only what the user said; never what the other person "
            "thought or felt.",
            CreateInteractionArgs,
            create_person_interaction,
        ),
        Tool(
            "get_person_interactions",
            "List interactions, optionally for one person and date range, newest first. "
            "Answers 'when did I last see X'. Includes what the user wrote that day.",
            GetInteractionsArgs,
            get_person_interactions,
        ),
        update_tool(
            "update_person_interaction",
            "Correct an interaction.",
            InteractionUpdate,
            "interaction_id",
            lambda db, rid, data: people.with_person(db, people.update_interaction(db, rid, data)),
            InteractionWithPerson,
        ),
        delete_tool(
            "delete_person_interaction",
            "Delete an interaction.",
            "interaction_id",
            people.delete_interaction,
        ),
        Tool(
            "create_music_memory",
            "Record a song the user connects with a moment, feeling or person.",
            CreateMusicArgs,
            create_music_memory,
        ),
        Tool(
            "search_music_memories",
            "Find music memories by song/artist text, person, emotion or date range. With "
            "a date range it also returns the most-mentioned songs ('what songs defined "
            "September?').",
            SearchMusicArgs,
            search_music_memories,
        ),
        update_tool(
            "update_music_memory",
            "Correct a music memory.",
            MusicUpdate,
            "music_memory_id",
            lambda db, rid, data: people.music_with_person(db, people.update_music(db, rid, data)),
            MusicWithPerson,
        ),
        delete_tool(
            "delete_music_memory",
            "Delete a music memory.",
            "music_memory_id",
            people.delete_music,
        ),
    ]
