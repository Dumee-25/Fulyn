import uuid
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.time import now_local
from app.models.caffeine import CaffeineLog
from app.schemas.caffeine import CaffeineLogCreate, CaffeineLogUpdate
from app.services import crud
from app.vault.filters import not_private


def create_caffeine_log(db: Session, data: CaffeineLogCreate) -> CaffeineLog:
    crud.ensure_journal_entry(db, data.journal_entry_id)
    log = CaffeineLog(**data.model_dump(exclude={"consumed_at", "is_approximate"}))
    if data.consumed_at is None:
        # Time not given: record "now" but flag it as an estimate.
        log.consumed_at = now_local()
        log.is_approximate = True
    else:
        log.consumed_at = data.consumed_at
        log.is_approximate = data.is_approximate
    return crud.save(db, log)


def get_caffeine_log(db: Session, log_id: uuid.UUID) -> CaffeineLog:
    return crud.get_or_raise(db, CaffeineLog, log_id)


def _local_midnight(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=get_settings().tz)


def list_caffeine_logs(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[CaffeineLog]:
    """Dates are local calendar days."""
    stmt = select(CaffeineLog).where(not_private(CaffeineLog))
    if date_from is not None:
        stmt = stmt.where(CaffeineLog.consumed_at >= _local_midnight(date_from))
    if date_to is not None:
        stmt = stmt.where(CaffeineLog.consumed_at < _local_midnight(date_to + timedelta(days=1)))
    stmt = stmt.order_by(CaffeineLog.consumed_at.desc())
    return crud.paginate(db, stmt, limit, offset)


def update_caffeine_log(db: Session, log_id: uuid.UUID, data: CaffeineLogUpdate) -> CaffeineLog:
    return crud.apply_changes(db, get_caffeine_log(db, log_id), data.changes())


def delete_caffeine_log(db: Session, log_id: uuid.UUID) -> None:
    crud.delete(db, get_caffeine_log(db, log_id))
