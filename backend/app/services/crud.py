"""Small shared helpers for the per-domain services. Services own commits."""

import uuid
from datetime import date
from typing import Any

from sqlalchemy import Select
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.core.errors import InvalidReferenceError, NotFoundError
from app.db.base import Base
from app.models.journal import JournalEntry

MAX_LIMIT = 500


def get_or_raise[ModelT: Base](db: Session, model: type[ModelT], record_id: uuid.UUID) -> ModelT:
    record = db.get(model, record_id)
    if record is None:
        raise NotFoundError(model.__name__)
    return record


def ensure_journal_entry(db: Session, journal_entry_id: uuid.UUID | None) -> None:
    """Validate an optional journal_entry_id before it hits the FK constraint."""
    if journal_entry_id is not None and db.get(JournalEntry, journal_entry_id) is None:
        raise InvalidReferenceError("journal_entry_id")


def save[ModelT: Base](db: Session, record: ModelT) -> ModelT:
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def apply_changes[ModelT: Base](db: Session, record: ModelT, changes: dict[str, Any]) -> ModelT:
    if "journal_entry_id" in changes:
        ensure_journal_entry(db, changes["journal_entry_id"])
    for field, value in changes.items():
        setattr(record, field, value)
    return save(db, record)


def delete(db: Session, record: Base) -> None:
    db.delete(record)
    db.commit()


def date_range(
    stmt: Select[Any],
    column: InstrumentedAttribute[Any],
    date_from: date | None,
    date_to: date | None,
) -> Select[Any]:
    """Inclusive date range filter on a Date column."""
    if date_from is not None:
        stmt = stmt.where(column >= date_from)
    if date_to is not None:
        stmt = stmt.where(column <= date_to)
    return stmt


def paginate(db: Session, stmt: Select[Any], limit: int, offset: int) -> list[Any]:
    limit = max(1, min(limit, MAX_LIMIT))
    return list(db.scalars(stmt.limit(limit).offset(max(0, offset))))
