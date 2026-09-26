"""People, interactions and music memories.

Interactions and music are mirrored into the memory layer so they show up in memory
search. People are matched by name or nickname; when a name is ambiguous the caller
gets an error listing the candidates instead of a guess.
"""

import uuid
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.core.time import today_local
from app.models.people import MusicMemory, Person, PersonInteraction
from app.schemas.people import (
    InteractionCreate,
    InteractionRead,
    InteractionUpdate,
    InteractionWithPerson,
    MusicCreate,
    MusicUpdate,
    MusicWithPerson,
    PersonCreate,
    PersonSummary,
    PersonUpdate,
    SongCount,
)
from app.services import crud, memories
from app.vault.filters import not_private


class AmbiguousPersonError(DomainError):
    def __init__(self, name: str, candidates: list[Person]) -> None:
        listed = "; ".join(
            f"{p.name} (id {p.id}"
            + (f", {p.relationship_type}" if p.relationship_type else "")
            + (f", last seen {p.last_interaction_at}" if p.last_interaction_at else "")
            + ")"
            for p in candidates
        )
        super().__init__(f"more than one person matches '{name}': {listed}. Ask which one.")


# --- People ------------------------------------------------------------------------


def find_people(db: Session, name: str) -> list[Person]:
    """Exact name or nickname, or name starting with the word ("Sarah" -> "Sarah Perera").

    Case-insensitive. Exact matches win over first-name matches.
    """
    needle = name.strip().lower()
    if not needle:
        return []
    exact = list(
        db.scalars(
            select(Person).where(
                or_(func.lower(Person.name) == needle, func.lower(Person.nickname) == needle)
            )
        )
    )
    if exact:
        return exact
    return list(
        db.scalars(
            select(Person)
            .where(func.lower(Person.name).startswith(needle + " "))
            .order_by(Person.name)
        )
    )


def resolve_person(db: Session, name: str, *, create: bool) -> tuple[Person | None, bool]:
    """Return (person, created). Raises AmbiguousPersonError for several matches."""
    matches = find_people(db, name)
    if len(matches) == 1:
        return matches[0], False
    if len(matches) > 1:
        raise AmbiguousPersonError(name, matches)
    if not create:
        return None, False
    return create_person(db, PersonCreate(name=name)), True


def create_person(db: Session, data: PersonCreate) -> Person:
    person = Person(**data.model_dump(), first_mentioned_at=today_local())
    return crud.save(db, person)


def get_person(db: Session, person_id: uuid.UUID) -> Person:
    return crud.get_or_raise(db, Person, person_id)


def list_people(
    db: Session, *, query: str | None = None, limit: int = 200, offset: int = 0
) -> list[PersonSummary]:
    """Alphabetical, with interaction counts. No ranking of people."""
    counts = (
        select(PersonInteraction.person_id, func.count().label("n"))
        .where(not_private(PersonInteraction))
        .group_by(PersonInteraction.person_id)
        .subquery()
    )
    stmt = select(Person, func.coalesce(counts.c.n, 0)).outerjoin(
        counts, counts.c.person_id == Person.id
    )
    if query:
        like = f"%{query.strip()}%"
        stmt = stmt.where(or_(Person.name.ilike(like), Person.nickname.ilike(like)))
    stmt = stmt.order_by(func.lower(Person.name)).limit(limit).offset(offset)
    return [
        PersonSummary.model_validate(person).model_copy(update={"interaction_count": n})
        for person, n in db.execute(stmt).all()
    ]


def update_person(db: Session, person_id: uuid.UUID, data: PersonUpdate) -> Person:
    person = crud.apply_changes(db, get_person(db, person_id), data.changes())
    # Names appear in interaction and music memories; refresh them.
    if "name" in data.model_fields_set:
        for interaction in _interactions_of(db, person.id):
            memories.sync_interaction_memory(db, interaction)
        for music in db.scalars(select(MusicMemory).where(MusicMemory.person_id == person.id)):
            memories.sync_music_memory(db, music)
    return person


def delete_person(db: Session, person_id: uuid.UUID) -> None:
    """Deletes the person's interactions too. Music memories are kept, unlinked."""
    person = get_person(db, person_id)
    for interaction in _interactions_of(db, person.id):
        memories.delete_memories_for(db, "person_interaction", interaction.id)
    music = list(db.scalars(select(MusicMemory).where(MusicMemory.person_id == person.id)))
    crud.delete(db, person)
    for item in music:
        db.refresh(item)
        memories.sync_music_memory(db, item)


def _interactions_of(db: Session, person_id: uuid.UUID) -> list[PersonInteraction]:
    return list(
        db.scalars(select(PersonInteraction).where(PersonInteraction.person_id == person_id))
    )


def _refresh_person_dates(db: Session, person_id: uuid.UUID) -> None:
    person = db.get(Person, person_id)
    if person is None:
        return
    first, last = db.execute(
        select(
            func.min(PersonInteraction.interaction_date),
            func.max(PersonInteraction.interaction_date),
        ).where(PersonInteraction.person_id == person_id)
    ).one()
    person.last_interaction_at = last
    if first is not None and first < person.first_mentioned_at:
        person.first_mentioned_at = first
    db.commit()


# --- Interactions ------------------------------------------------------------------


def with_person(db: Session, interaction: PersonInteraction) -> InteractionWithPerson:
    person = db.get(Person, interaction.person_id)
    return _interaction_view(interaction, person.name if person else "")


def _interaction_view(interaction: PersonInteraction, person_name: str) -> InteractionWithPerson:
    base = InteractionRead.model_validate(interaction).model_dump()
    return InteractionWithPerson(**base, person_name=person_name)


def create_interaction(db: Session, data: InteractionCreate) -> PersonInteraction:
    get_person(db, data.person_id)
    crud.ensure_journal_entry(db, data.journal_entry_id)
    interaction = PersonInteraction(**data.model_dump(exclude={"interaction_date"}))
    interaction.interaction_date = data.interaction_date or today_local()
    crud.save(db, interaction)
    _refresh_person_dates(db, interaction.person_id)
    memories.sync_interaction_memory(db, interaction)
    return interaction


def get_interaction(db: Session, interaction_id: uuid.UUID) -> PersonInteraction:
    return crud.get_or_raise(db, PersonInteraction, interaction_id)


def list_interactions(
    db: Session,
    *,
    person_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[InteractionWithPerson]:
    stmt = (
        select(PersonInteraction, Person.name)
        .join(Person, Person.id == PersonInteraction.person_id)
        .where(not_private(PersonInteraction))
    )
    if person_id is not None:
        stmt = stmt.where(PersonInteraction.person_id == person_id)
    stmt = crud.date_range(stmt, PersonInteraction.interaction_date, date_from, date_to)
    stmt = stmt.order_by(
        PersonInteraction.interaction_date.desc(), PersonInteraction.created_at.desc()
    )
    rows = db.execute(stmt.limit(max(1, min(limit, crud.MAX_LIMIT))).offset(offset)).all()
    return [_interaction_view(i, name) for i, name in rows]


def update_interaction(
    db: Session, interaction_id: uuid.UUID, data: InteractionUpdate
) -> PersonInteraction:
    interaction = get_interaction(db, interaction_id)
    old_person = interaction.person_id
    changes = data.changes()
    if "person_id" in changes:
        get_person(db, changes["person_id"])
    interaction = crud.apply_changes(db, interaction, changes)
    for person_id in {old_person, interaction.person_id}:
        _refresh_person_dates(db, person_id)
    memories.sync_interaction_memory(db, interaction)
    return interaction


def delete_interaction(db: Session, interaction_id: uuid.UUID) -> None:
    interaction = get_interaction(db, interaction_id)
    person_id = interaction.person_id
    crud.delete(db, interaction)
    memories.delete_memories_for(db, "person_interaction", interaction_id)
    _refresh_person_dates(db, person_id)


# --- Music -------------------------------------------------------------------------


def music_with_person(db: Session, music: MusicMemory) -> MusicWithPerson:
    person = db.get(Person, music.person_id) if music.person_id else None
    return MusicWithPerson.model_validate(music).model_copy(
        update={"person_name": person.name if person else None}
    )


def create_music(db: Session, data: MusicCreate) -> MusicMemory:
    if data.person_id is not None:
        get_person(db, data.person_id)
    crud.ensure_journal_entry(db, data.journal_entry_id)
    music = MusicMemory(**data.model_dump(exclude={"memory_date"}))
    music.memory_date = data.memory_date or today_local()
    crud.save(db, music)
    memories.sync_music_memory(db, music)
    return music


def get_music(db: Session, music_id: uuid.UUID) -> MusicMemory:
    return crud.get_or_raise(db, MusicMemory, music_id)


def list_music(
    db: Session,
    *,
    query: str | None = None,
    artist: str | None = None,
    person_id: uuid.UUID | None = None,
    emotion: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[MusicWithPerson]:
    stmt = (
        select(MusicMemory, Person.name)
        .outerjoin(Person, Person.id == MusicMemory.person_id)
        .where(not_private(MusicMemory))
    )
    if query:
        like = f"%{query.strip()}%"
        stmt = stmt.where(
            or_(
                MusicMemory.song.ilike(like),
                MusicMemory.artist.ilike(like),
                MusicMemory.album.ilike(like),
                MusicMemory.memory_text.ilike(like),
            )
        )
    if artist:
        stmt = stmt.where(MusicMemory.artist.ilike(f"%{artist.strip()}%"))
    if person_id is not None:
        stmt = stmt.where(MusicMemory.person_id == person_id)
    if emotion:
        stmt = stmt.where(func.lower(MusicMemory.emotion) == emotion.strip().lower())
    stmt = crud.date_range(stmt, MusicMemory.memory_date, date_from, date_to)
    stmt = stmt.order_by(MusicMemory.memory_date.desc(), MusicMemory.created_at.desc())
    rows = db.execute(stmt.limit(max(1, min(limit, crud.MAX_LIMIT))).offset(offset)).all()
    return [
        MusicWithPerson.model_validate(m).model_copy(update={"person_name": name})
        for m, name in rows
    ]


def top_songs(
    db: Session, *, date_from: date | None = None, date_to: date | None = None, limit: int = 10
) -> list[SongCount]:
    """Most-mentioned songs in a range, for "what songs defined September?"."""
    stmt = (
        select(MusicMemory.song, MusicMemory.artist, func.count().label("n"))
        .where(not_private(MusicMemory))
        .group_by(MusicMemory.song, MusicMemory.artist)
    )
    stmt = crud.date_range(stmt, MusicMemory.memory_date, date_from, date_to)
    stmt = stmt.order_by(func.count().desc(), MusicMemory.song).limit(limit)
    return [SongCount(song=s, artist=a, count=n) for s, a, n in db.execute(stmt).all()]


def update_music(db: Session, music_id: uuid.UUID, data: MusicUpdate) -> MusicMemory:
    changes = data.changes()
    if changes.get("person_id") is not None:
        get_person(db, changes["person_id"])
    music = crud.apply_changes(db, get_music(db, music_id), changes)
    memories.sync_music_memory(db, music)
    return music


def delete_music(db: Session, music_id: uuid.UUID) -> None:
    crud.delete(db, get_music(db, music_id))
    memories.delete_memories_for(db, "music", music_id)
