import uuid

from fastapi import APIRouter, status

from app.api.deps import DbSession, ListQuery
from app.schemas.mood import MoodLogCreate, MoodLogRead, MoodLogUpdate
from app.services import moods as service

router = APIRouter(prefix="/moods", tags=["moods"])


@router.get("", response_model=list[MoodLogRead])
def list_moods(db: DbSession, params: ListQuery):
    return service.list_mood_logs(db, **params.model_dump())


@router.post("", response_model=MoodLogRead, status_code=status.HTTP_201_CREATED)
def create_mood(db: DbSession, data: MoodLogCreate):
    return service.create_mood_log(db, data)


@router.get("/{mood_id}", response_model=MoodLogRead)
def get_mood(db: DbSession, mood_id: uuid.UUID):
    return service.get_mood_log(db, mood_id)


@router.patch("/{mood_id}", response_model=MoodLogRead)
def update_mood(db: DbSession, mood_id: uuid.UUID, data: MoodLogUpdate):
    return service.update_mood_log(db, mood_id, data)


@router.delete("/{mood_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_mood(db: DbSession, mood_id: uuid.UUID) -> None:
    service.delete_mood_log(db, mood_id)
