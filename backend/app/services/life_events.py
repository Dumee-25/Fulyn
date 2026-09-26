import uuid
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.time import today_local
from app.models.report import LifeEvent
from app.schemas.report import LifeEventCreate, LifeEventUpdate
from app.services import crud, memories
from app.vault.filters import not_private


def create_life_event(db: Session, data: LifeEventCreate) -> LifeEvent:
    crud.ensure_journal_entry(db, data.journal_entry_id)
    event = LifeEvent(**data.model_dump(exclude={"event_date"}))
    event.event_date = data.event_date or today_local()
    crud.save(db, event)
    memories.sync_event_memory(db, event)
    return event


def get_life_event(db: Session, event_id: uuid.UUID) -> LifeEvent:
    return crud.get_or_raise(db, LifeEvent, event_id)


def list_life_events(
    db: Session,
    *,
    query: str | None = None,
    event_type: str | None = None,
    min_importance: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[LifeEvent]:
    stmt = select(LifeEvent).where(not_private(LifeEvent))
    if query:
        like = f"%{query.strip()}%"
        stmt = stmt.where(or_(LifeEvent.title.ilike(like), LifeEvent.description.ilike(like)))
    if event_type:
        stmt = stmt.where(LifeEvent.event_type.ilike(event_type.strip()))
    if min_importance is not None:
        stmt = stmt.where(LifeEvent.importance_score >= min_importance)
    stmt = crud.date_range(stmt, LifeEvent.event_date, date_from, date_to)
    stmt = stmt.order_by(LifeEvent.event_date.desc(), LifeEvent.created_at.desc())
    return crud.paginate(db, stmt, limit, offset)


def update_life_event(db: Session, event_id: uuid.UUID, data: LifeEventUpdate) -> LifeEvent:
    event = crud.apply_changes(db, get_life_event(db, event_id), data.changes())
    memories.sync_event_memory(db, event)
    return event


def delete_life_event(db: Session, event_id: uuid.UUID) -> None:
    crud.delete(db, get_life_event(db, event_id))
    memories.delete_memories_for(db, "event", event_id)
