"""What each chat message created, and the actions that apply to "the last message":
undo it, move it to another day, change its importance, or put it in the vault."""

import uuid
from collections.abc import Callable
from datetime import date, datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.models.caffeine import CaffeineLog
from app.models.expense import Expense
from app.models.journal import JournalEntry
from app.models.mood import MoodLog
from app.models.people import MusicMemory, Person, PersonInteraction
from app.models.planning import Decision, Reminder, Subscription, WaitingItem
from app.models.report import LifeEvent
from app.models.sleep import SleepLog
from app.models.turn import TurnRecord
from app.schemas.caffeine import CaffeineLogUpdate
from app.schemas.expense import ExpenseUpdate
from app.schemas.journal import JournalEntryUpdate
from app.schemas.mood import MoodLogUpdate
from app.schemas.people import InteractionUpdate, MusicUpdate
from app.schemas.planning import DecisionUpdate
from app.schemas.report import LifeEventUpdate
from app.schemas.sleep import SleepLogUpdate
from app.services import (
    caffeine,
    expenses,
    journal,
    life_events,
    moods,
    people,
    planning,
    sleep,
)
from app.vault.filters import not_private

MODELS: dict[str, type] = {
    m.__tablename__: m
    for m in (
        JournalEntry,
        Expense,
        MoodLog,
        SleepLog,
        CaffeineLog,
        PersonInteraction,
        MusicMemory,
        Decision,
        LifeEvent,
        Subscription,
        Reminder,
        WaitingItem,
        Person,
    )
}

# Singular names used in replies and as action labels ("deleted expense").
NOUNS = {
    "journal_entries": "journal_entry",
    "expenses": "expense",
    "mood_logs": "mood_log",
    "sleep_logs": "sleep_log",
    "caffeine_logs": "caffeine_log",
    "person_interactions": "person_interaction",
    "music_memories": "music_memory",
    "decisions": "decision",
    "life_events": "life_event",
    "subscriptions": "subscription",
    "reminders": "reminder",
    "waiting_items": "waiting_item",
    "people": "person",
}

DELETE: dict[type, Callable[[Session, uuid.UUID], None]] = {
    Expense: expenses.delete_expense,
    MoodLog: moods.delete_mood_log,
    SleepLog: sleep.delete_sleep_log,
    CaffeineLog: caffeine.delete_caffeine_log,
    PersonInteraction: people.delete_interaction,
    MusicMemory: people.delete_music,
    Decision: planning.delete_decision,
    LifeEvent: life_events.delete_life_event,
    Subscription: planning.delete_subscription,
    Reminder: planning.delete_reminder,
    WaitingItem: planning.delete_waiting,
    JournalEntry: journal.delete_journal_entry,
}
# Records that carry an importance score, and how to update it.
IMPORTANCE: dict[type, Callable[[Session, uuid.UUID, int], Any]] = {
    JournalEntry: lambda db, i, s: journal.update_journal_entry(
        db, i, JournalEntryUpdate(importance_score=s)
    ),
    PersonInteraction: lambda db, i, s: people.update_interaction(
        db, i, InteractionUpdate(importance_score=s)
    ),
    MusicMemory: lambda db, i, s: people.update_music(db, i, MusicUpdate(importance_score=s)),
    Decision: lambda db, i, s: planning.update_decision(db, i, DecisionUpdate(importance_score=s)),
    LifeEvent: lambda db, i, s: life_events.update_life_event(
        db, i, LifeEventUpdate(importance_score=s)
    ),
}


class NothingToActOnError(DomainError):
    def __init__(self) -> None:
        super().__init__("there is no earlier message in this conversation that logged anything")


def record_turn(
    db: Session,
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    created: list[tuple[type, uuid.UUID]],
) -> None:
    for model, record_id in created:
        db.add(
            TurnRecord(
                conversation_id=conversation_id,
                message_id=message_id,
                record_type=model.__tablename__,
                record_id=record_id,
            )
        )
    db.commit()


def last_turn(db: Session, conversation_id: uuid.UUID) -> tuple[uuid.UUID, list[Any]]:
    """The most recent message in the conversation that created records still present."""
    message_ids = db.scalars(
        select(TurnRecord.message_id)
        .where(TurnRecord.conversation_id == conversation_id)
        .group_by(TurnRecord.message_id)
        .order_by(func.max(TurnRecord.created_at).desc())
    ).all()
    for message_id in message_ids:
        records = []
        for row in db.scalars(select(TurnRecord).where(TurnRecord.message_id == message_id)):
            model = MODELS.get(row.record_type)
            record = db.get(model, row.record_id) if model else None
            if record is not None:
                records.append(record)
        if records:
            return message_id, records
    raise NothingToActOnError()


def describe(record: Any) -> str:
    return NOUNS.get(record.__tablename__, record.__tablename__).replace("_", " ")


def undo_last(db: Session, conversation_id: uuid.UUID) -> list[str]:
    """Delete everything the last logging message created. Returns what was deleted."""
    message_id, records = last_turn(db, conversation_id)
    deleted = []
    # Linked records first, then the journal entry, then people created for them.
    order = sorted(records, key=lambda r: (isinstance(r, JournalEntry), isinstance(r, Person)))
    for record in order:
        if isinstance(record, Person):
            still_used = db.scalar(
                select(func.count())
                .select_from(PersonInteraction)
                .where(PersonInteraction.person_id == record.id)
            ) or db.scalar(
                select(func.count())
                .select_from(MusicMemory)
                .where(MusicMemory.person_id == record.id)
            )
            if still_used:
                continue
            people.delete_person(db, record.id)
        else:
            DELETE[type(record)](db, record.id)
        deleted.append(describe(record))
    db.execute(delete(TurnRecord).where(TurnRecord.message_id == message_id))
    db.commit()
    return deleted


def _record_day(record: Any) -> date | None:
    for field in (
        "entry_date",
        "expense_date",
        "date",
        "sleep_date",
        "interaction_date",
        "memory_date",
        "decision_date",
        "event_date",
    ):
        value = getattr(record, field, None)
        if isinstance(value, date):
            return value
    consumed = getattr(record, "consumed_at", None)
    return consumed.date() if isinstance(consumed, datetime) else None


def move_last(db: Session, conversation_id: uuid.UUID, new_day: date) -> tuple[date, list[str]]:
    """Move the last message's records to another day, keeping times of day.

    Returns (the old day, what moved).
    """
    _, records = last_turn(db, conversation_id)
    anchor = next((r.entry_date for r in records if isinstance(r, JournalEntry)), None)
    if anchor is None:
        anchor = next((d for r in records if (d := _record_day(r)) is not None), None)
    if anchor is None:
        raise DomainError("the last message didn't log anything with a date")
    delta = new_day - anchor
    moved = []
    for r in records:
        if isinstance(r, JournalEntry):
            journal.update_journal_entry(
                db, r.id, JournalEntryUpdate(entry_date=r.entry_date + delta)
            )
        elif isinstance(r, Expense):
            expenses.update_expense(db, r.id, ExpenseUpdate(expense_date=r.expense_date + delta))
        elif isinstance(r, MoodLog):
            moods.update_mood_log(db, r.id, MoodLogUpdate(date=r.date + delta))
        elif isinstance(r, SleepLog):
            changes: dict[str, Any] = {"sleep_date": r.sleep_date + delta}
            if r.sleep_time:
                changes["sleep_time"] = r.sleep_time + delta
            if r.wake_time:
                changes["wake_time"] = r.wake_time + delta
            if r.duration_minutes is not None:
                changes["duration_minutes"] = r.duration_minutes
            sleep.update_sleep_log(db, r.id, SleepLogUpdate(**changes))
        elif isinstance(r, CaffeineLog):
            caffeine.update_caffeine_log(
                db, r.id, CaffeineLogUpdate(consumed_at=r.consumed_at + delta)
            )
        elif isinstance(r, PersonInteraction):
            people.update_interaction(
                db, r.id, InteractionUpdate(interaction_date=r.interaction_date + delta)
            )
        elif isinstance(r, MusicMemory):
            people.update_music(db, r.id, MusicUpdate(memory_date=r.memory_date + delta))
        elif isinstance(r, Decision):
            planning.update_decision(
                db, r.id, DecisionUpdate(decision_date=r.decision_date + delta)
            )
        elif isinstance(r, LifeEvent):
            life_events.update_life_event(
                db, r.id, LifeEventUpdate(event_date=r.event_date + delta)
            )
        else:
            continue  # people, subscriptions, reminders, waiting items have no "day it happened"
        moved.append(describe(r))
    return anchor, moved


def set_importance(db: Session, records: list[Any], score: int) -> list[str]:
    changed = []
    for record in records:
        update = IMPORTANCE.get(type(record))
        if update:
            update(db, record.id, score)
            changed.append(describe(record))
    return changed


def journal_entry_of(records: list[Any]) -> JournalEntry | None:
    return next((r for r in records if isinstance(r, JournalEntry)), None)


def last_expense(db: Session, conversation_id: uuid.UUID | None) -> Expense | None:
    """The expense from the last logging message, else the most recently added one."""
    if conversation_id is not None:
        try:
            _, records = last_turn(db, conversation_id)
            found = [r for r in records if isinstance(r, Expense)]
            if found:
                return found[-1]
        except NothingToActOnError:
            pass
    return db.scalar(
        select(Expense).where(not_private(Expense)).order_by(Expense.created_at.desc()).limit(1)
    )
