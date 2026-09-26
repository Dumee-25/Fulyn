import uuid

from fastapi import APIRouter, status

from app.api.deps import DbSession, ListQuery
from app.schemas.sleep import SleepLogCreate, SleepLogRead, SleepLogUpdate
from app.services import sleep as service

router = APIRouter(prefix="/sleep", tags=["sleep"])


@router.get("", response_model=list[SleepLogRead])
def list_sleep(db: DbSession, params: ListQuery):
    return service.list_sleep_logs(db, **params.model_dump())


@router.post("", response_model=SleepLogRead, status_code=status.HTTP_201_CREATED)
def create_sleep(db: DbSession, data: SleepLogCreate):
    return service.create_sleep_log(db, data)


@router.get("/{log_id}", response_model=SleepLogRead)
def get_sleep(db: DbSession, log_id: uuid.UUID):
    return service.get_sleep_log(db, log_id)


@router.patch("/{log_id}", response_model=SleepLogRead)
def update_sleep(db: DbSession, log_id: uuid.UUID, data: SleepLogUpdate):
    return service.update_sleep_log(db, log_id, data)


@router.delete("/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sleep(db: DbSession, log_id: uuid.UUID) -> None:
    service.delete_sleep_log(db, log_id)
