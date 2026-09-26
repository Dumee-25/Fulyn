import uuid
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import DomainError
from app.core.time import today_local
from app.models.sleep import SleepLog
from app.schemas.sleep import SleepLogCreate, SleepLogUpdate
from app.services import crud


class InvalidSleepTimesError(DomainError):
    def __init__(self) -> None:
        super().__init__("wake_time must be after sleep_time")


def duration_between(sleep_time: datetime, wake_time: datetime) -> int:
    minutes = int((wake_time - sleep_time).total_seconds() // 60)
    if minutes <= 0:
        raise InvalidSleepTimesError()
    return minutes


def create_sleep_log(db: Session, data: SleepLogCreate) -> SleepLog:
    crud.ensure_journal_entry(db, data.journal_entry_id)
    log = SleepLog(**data.model_dump(exclude={"sleep_date"}))
    if data.sleep_date:
        log.sleep_date = data.sleep_date
    elif data.wake_time:
        log.sleep_date = data.wake_time.astimezone(get_settings().tz).date()
    else:
        log.sleep_date = today_local()
    if log.duration_minutes is None and log.sleep_time and log.wake_time:
        log.duration_minutes = duration_between(log.sleep_time, log.wake_time)
    return crud.save(db, log)


def get_sleep_log(db: Session, log_id: uuid.UUID) -> SleepLog:
    return crud.get_or_raise(db, SleepLog, log_id)


def list_sleep_logs(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[SleepLog]:
    stmt = crud.date_range(select(SleepLog), SleepLog.sleep_date, date_from, date_to)
    stmt = stmt.order_by(SleepLog.sleep_date.desc(), SleepLog.created_at.desc())
    return crud.paginate(db, stmt, limit, offset)


def update_sleep_log(db: Session, log_id: uuid.UUID, data: SleepLogUpdate) -> SleepLog:
    log = get_sleep_log(db, log_id)
    changes = data.changes()
    sleep_time = changes.get("sleep_time", log.sleep_time)
    wake_time = changes.get("wake_time", log.wake_time)
    times_changed = "sleep_time" in changes or "wake_time" in changes
    if sleep_time and wake_time:
        if times_changed and "duration_minutes" not in changes:
            changes["duration_minutes"] = duration_between(sleep_time, wake_time)
        elif wake_time <= sleep_time:
            raise InvalidSleepTimesError()
    return crud.apply_changes(db, log, changes)


def delete_sleep_log(db: Session, log_id: uuid.UUID) -> None:
    crud.delete(db, get_sleep_log(db, log_id))
