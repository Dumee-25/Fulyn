import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import today_local
from app.models.mood import MoodLog
from app.schemas.mood import MoodLogCreate, MoodLogUpdate
from app.services import crud


def create_mood_log(db: Session, data: MoodLogCreate) -> MoodLog:
    crud.ensure_journal_entry(db, data.journal_entry_id)
    mood = MoodLog(**data.model_dump(exclude={"date"}))
    mood.date = data.date or today_local()
    return crud.save(db, mood)


def get_mood_log(db: Session, mood_id: uuid.UUID) -> MoodLog:
    return crud.get_or_raise(db, MoodLog, mood_id)


def list_mood_logs(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[MoodLog]:
    stmt = crud.date_range(select(MoodLog), MoodLog.date, date_from, date_to)
    stmt = stmt.order_by(MoodLog.date.desc(), MoodLog.created_at.desc())
    return crud.paginate(db, stmt, limit, offset)


def update_mood_log(db: Session, mood_id: uuid.UUID, data: MoodLogUpdate) -> MoodLog:
    return crud.apply_changes(db, get_mood_log(db, mood_id), data.changes())


def delete_mood_log(db: Session, mood_id: uuid.UUID) -> None:
    crud.delete(db, get_mood_log(db, mood_id))
