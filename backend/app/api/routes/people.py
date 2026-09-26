import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DbSession, ListQuery
from app.schemas.people import (
    InteractionCreate,
    InteractionUpdate,
    InteractionWithPerson,
    MusicCreate,
    MusicUpdate,
    MusicWithPerson,
    PersonCreate,
    PersonRead,
    PersonSummary,
    PersonUpdate,
    SongCount,
)
from app.services import people as service

people_router = APIRouter(prefix="/people", tags=["people"])
interactions_router = APIRouter(prefix="/interactions", tags=["interactions"])
music_router = APIRouter(prefix="/music", tags=["music"])


# --- People ------------------------------------------------------------------------


@people_router.get("", response_model=list[PersonSummary])
def list_people(
    db: DbSession,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return service.list_people(db, query=q, limit=limit, offset=offset)


@people_router.post("", response_model=PersonRead, status_code=status.HTTP_201_CREATED)
def create_person(db: DbSession, data: PersonCreate):
    return service.create_person(db, data)


@people_router.get("/{person_id}", response_model=PersonRead)
def get_person(db: DbSession, person_id: uuid.UUID):
    return service.get_person(db, person_id)


@people_router.patch("/{person_id}", response_model=PersonRead)
def update_person(db: DbSession, person_id: uuid.UUID, data: PersonUpdate):
    return service.update_person(db, person_id, data)


@people_router.delete("/{person_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_person(db: DbSession, person_id: uuid.UUID) -> None:
    service.delete_person(db, person_id)


# --- Interactions ------------------------------------------------------------------


@interactions_router.get("", response_model=list[InteractionWithPerson])
def list_interactions(db: DbSession, params: ListQuery, person_id: uuid.UUID | None = None):
    return service.list_interactions(db, person_id=person_id, **params.model_dump())


@interactions_router.post(
    "", response_model=InteractionWithPerson, status_code=status.HTTP_201_CREATED
)
def create_interaction(db: DbSession, data: InteractionCreate):
    return service.with_person(db, service.create_interaction(db, data))


@interactions_router.get("/{interaction_id}", response_model=InteractionWithPerson)
def get_interaction(db: DbSession, interaction_id: uuid.UUID):
    return service.with_person(db, service.get_interaction(db, interaction_id))


@interactions_router.patch("/{interaction_id}", response_model=InteractionWithPerson)
def update_interaction(db: DbSession, interaction_id: uuid.UUID, data: InteractionUpdate):
    return service.with_person(db, service.update_interaction(db, interaction_id, data))


@interactions_router.delete("/{interaction_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_interaction(db: DbSession, interaction_id: uuid.UUID) -> None:
    service.delete_interaction(db, interaction_id)


# --- Music -------------------------------------------------------------------------


@music_router.get("", response_model=list[MusicWithPerson])
def list_music(
    db: DbSession,
    params: ListQuery,
    q: Annotated[
        str | None, Query(max_length=200, description="Song, artist, album or text")
    ] = None,
    artist: Annotated[str | None, Query(max_length=200)] = None,
    person_id: uuid.UUID | None = None,
    emotion: Annotated[str | None, Query(max_length=50)] = None,
):
    return service.list_music(
        db, query=q, artist=artist, person_id=person_id, emotion=emotion, **params.model_dump()
    )


@music_router.get("/top", response_model=list[SongCount])
def top_songs(
    db: DbSession,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
):
    return service.top_songs(db, date_from=date_from, date_to=date_to, limit=limit)


@music_router.post("", response_model=MusicWithPerson, status_code=status.HTTP_201_CREATED)
def create_music(db: DbSession, data: MusicCreate):
    return service.music_with_person(db, service.create_music(db, data))


@music_router.get("/{music_id}", response_model=MusicWithPerson)
def get_music(db: DbSession, music_id: uuid.UUID):
    return service.music_with_person(db, service.get_music(db, music_id))


@music_router.patch("/{music_id}", response_model=MusicWithPerson)
def update_music(db: DbSession, music_id: uuid.UUID, data: MusicUpdate):
    return service.music_with_person(db, service.update_music(db, music_id, data))


@music_router.delete("/{music_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_music(db: DbSession, music_id: uuid.UUID) -> None:
    service.delete_music(db, music_id)
