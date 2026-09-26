import uuid

from fastapi import APIRouter, status

from app.api.deps import DbSession, ListQuery
from app.schemas.caffeine import CaffeineLogCreate, CaffeineLogRead, CaffeineLogUpdate
from app.services import caffeine as service

router = APIRouter(prefix="/caffeine", tags=["caffeine"])


@router.get("", response_model=list[CaffeineLogRead])
def list_caffeine(db: DbSession, params: ListQuery):
    return service.list_caffeine_logs(db, **params.model_dump())


@router.post("", response_model=CaffeineLogRead, status_code=status.HTTP_201_CREATED)
def create_caffeine(db: DbSession, data: CaffeineLogCreate):
    return service.create_caffeine_log(db, data)


@router.get("/{log_id}", response_model=CaffeineLogRead)
def get_caffeine(db: DbSession, log_id: uuid.UUID):
    return service.get_caffeine_log(db, log_id)


@router.patch("/{log_id}", response_model=CaffeineLogRead)
def update_caffeine(db: DbSession, log_id: uuid.UUID, data: CaffeineLogUpdate):
    return service.update_caffeine_log(db, log_id, data)


@router.delete("/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_caffeine(db: DbSession, log_id: uuid.UUID) -> None:
    service.delete_caffeine_log(db, log_id)
