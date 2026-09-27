"""Subscriptions, reminders, decisions and waiting items."""

import uuid
from datetime import date, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import DomainError
from app.core.recurrence import monthly_cost, next_after, next_on_or_after
from app.core.time import now_local, today_local
from app.models.people import Person
from app.models.planning import Decision, Reminder, Subscription, WaitingItem
from app.schemas.planning import (
    CurrencyTotal,
    DecisionCreate,
    DecisionUpdate,
    ReminderCreate,
    ReminderUpdate,
    SubscriptionCreate,
    SubscriptionRead,
    SubscriptionSummary,
    SubscriptionUpdate,
    WaitingCreate,
    WaitingRead,
    WaitingUpdate,
)
from app.services import crud, memories
from app.vault.filters import not_private

# --- Subscriptions -----------------------------------------------------------------


def subscription_view(sub: Subscription, today: date | None = None) -> SubscriptionRead:
    today = today or today_local()
    view = SubscriptionRead.model_validate(sub)
    next_due = None
    if sub.next_billing_date is not None:
        next_due = next_on_or_after(
            sub.next_billing_date, sub.billing_cycle, today, sub.custom_interval_days
        )
    return view.model_copy(
        update={
            "monthly_cost": monthly_cost(sub.amount, sub.billing_cycle, sub.custom_interval_days),
            "next_due": next_due,
        }
    )


def create_subscription(db: Session, data: SubscriptionCreate) -> Subscription:
    sub = Subscription(**data.model_dump(exclude={"currency"}))
    sub.currency = data.currency or get_settings().default_currency
    return crud.save(db, sub)


def get_subscription(db: Session, sub_id: uuid.UUID) -> Subscription:
    return crud.get_or_raise(db, Subscription, sub_id)


def list_subscriptions(db: Session, *, active: bool | None = None) -> list[SubscriptionRead]:
    stmt = select(Subscription).order_by(Subscription.active.desc(), func.lower(Subscription.name))
    if active is not None:
        stmt = stmt.where(Subscription.active.is_(active))
    today = today_local()
    return [subscription_view(s, today) for s in db.scalars(stmt)]


def summarize_subscriptions(db: Session) -> SubscriptionSummary:
    """Monthly and yearly cost of active subscriptions, per currency (never converted)."""
    totals: dict[str, CurrencyTotal] = {}
    active = list_subscriptions(db, active=True)
    for sub in active:
        total = totals.setdefault(
            sub.currency,
            CurrencyTotal(currency=sub.currency, monthly_total=0, yearly_total=0, count=0),
        )
        total.monthly_total += sub.monthly_cost
        total.count += 1
    for total in totals.values():
        total.yearly_total = total.monthly_total * 12
    home = get_settings().default_currency
    ordered = sorted(totals.values(), key=lambda t: (t.currency != home, t.currency))
    return SubscriptionSummary(active_count=len(active), totals=ordered)


def update_subscription(db: Session, sub_id: uuid.UUID, data: SubscriptionUpdate) -> Subscription:
    sub = get_subscription(db, sub_id)
    changes = data.changes()
    cycle = changes.get("billing_cycle", sub.billing_cycle)
    interval = changes.get("custom_interval_days", sub.custom_interval_days)
    if cycle == "custom" and not interval:
        raise DomainError("custom billing_cycle needs custom_interval_days")
    return crud.apply_changes(db, sub, changes)


def delete_subscription(db: Session, sub_id: uuid.UUID) -> None:
    crud.delete(db, get_subscription(db, sub_id))


# --- Reminders ---------------------------------------------------------------------


def create_reminder(db: Session, data: ReminderCreate) -> Reminder:
    return crud.save(db, Reminder(**data.model_dump()))


def get_reminder(db: Session, reminder_id: uuid.UUID) -> Reminder:
    return crud.get_or_raise(db, Reminder, reminder_id)


def list_reminders(
    db: Session,
    *,
    status: str | None = "pending",
    due_before: datetime | None = None,
    query: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Reminder]:
    """Soonest first. ``due_before`` finds due or overdue reminders (what a notifier polls)."""
    stmt = select(Reminder)
    if status is not None:
        stmt = stmt.where(Reminder.status == status)
    if due_before is not None:
        stmt = stmt.where(Reminder.due_at <= due_before)
    if query:
        stmt = stmt.where(Reminder.title.ilike(f"%{query.strip()}%"))
    stmt = stmt.order_by(Reminder.due_at)
    return crud.paginate(db, stmt, limit, offset)


def complete_reminder(db: Session, reminder_id: uuid.UUID) -> Reminder:
    """One-off reminders become completed; recurring ones move to their next occurrence."""
    reminder = get_reminder(db, reminder_id)
    if reminder.status != "pending":
        raise DomainError(f"reminder is already {reminder.status}")
    now = now_local()
    reminder.last_completed_at = now
    if reminder.recurrence_rule:
        reminder.due_at = next_after(reminder.due_at, reminder.recurrence_rule, now)
    else:
        reminder.status = "completed"
    return crud.save(db, reminder)


def update_reminder(db: Session, reminder_id: uuid.UUID, data: ReminderUpdate) -> Reminder:
    return crud.apply_changes(db, get_reminder(db, reminder_id), data.changes())


def delete_reminder(db: Session, reminder_id: uuid.UUID) -> None:
    crud.delete(db, get_reminder(db, reminder_id))


# --- Decisions ---------------------------------------------------------------------


def create_decision(db: Session, data: DecisionCreate) -> Decision:
    crud.ensure_journal_entry(db, data.journal_entry_id)
    decision = Decision(**data.model_dump(exclude={"decision_date"}))
    decision.decision_date = data.decision_date or today_local()
    crud.save(db, decision)
    memories.sync_decision_memory(db, decision)
    return decision


def get_decision(db: Session, decision_id: uuid.UUID) -> Decision:
    return crud.get_or_raise(db, Decision, decision_id)


def list_decisions(
    db: Session,
    *,
    query: str | None = None,
    status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Decision]:
    stmt = select(Decision).where(not_private(Decision))
    if query:
        like = f"%{query.strip()}%"
        stmt = stmt.where(
            or_(
                Decision.title.ilike(like),
                Decision.decision.ilike(like),
                Decision.reasoning.ilike(like),
            )
        )
    if status:
        stmt = stmt.where(Decision.status == status)
    stmt = crud.date_range(stmt, Decision.decision_date, date_from, date_to)
    stmt = stmt.order_by(Decision.decision_date.desc(), Decision.created_at.desc())
    return crud.paginate(db, stmt, limit, offset)


def update_decision(db: Session, decision_id: uuid.UUID, data: DecisionUpdate) -> Decision:
    decision = get_decision(db, decision_id)
    previous_entry_id = decision.journal_entry_id
    changes = data.changes()
    decision = crud.apply_changes(db, decision, changes)
    memories.sync_decision_memory(
        db,
        decision,
        previous_entry_id=previous_entry_id,
        importance_changed="importance_score" in changes,
    )
    return decision


def delete_decision(db: Session, decision_id: uuid.UUID) -> None:
    decision = get_decision(db, decision_id)
    entry_id = decision.journal_entry_id
    crud.delete(db, decision)
    memories.delete_memories_for(db, "decision", decision_id, entry_id)


# --- Waiting items -----------------------------------------------------------------


def waiting_view(db: Session, item: WaitingItem, today: date | None = None) -> WaitingRead:
    today = today or today_local()
    person = db.get(Person, item.related_person_id) if item.related_person_id else None
    return WaitingRead.model_validate(item).model_copy(
        update={
            "related_person_name": person.name if person else None,
            "overdue": item.status == "waiting"
            and item.expected_by is not None
            and item.expected_by < today,
        }
    )


def create_waiting(db: Session, data: WaitingCreate) -> WaitingItem:
    if data.related_person_id is not None:
        crud.get_or_raise(db, Person, data.related_person_id)
    item = WaitingItem(**data.model_dump(exclude={"waiting_since"}))
    item.waiting_since = data.waiting_since or today_local()
    return crud.save(db, item)


def get_waiting(db: Session, item_id: uuid.UUID) -> WaitingItem:
    return crud.get_or_raise(db, WaitingItem, item_id)


def list_waiting(
    db: Session,
    *,
    status: str | None = "waiting",
    query: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[WaitingRead]:
    """Oldest first: the longest wait is the most relevant."""
    stmt = select(WaitingItem)
    if status is not None:
        stmt = stmt.where(WaitingItem.status == status)
    if query:
        stmt = stmt.where(WaitingItem.title.ilike(f"%{query.strip()}%"))
    stmt = stmt.order_by(WaitingItem.waiting_since, WaitingItem.created_at)
    today = today_local()
    return [waiting_view(db, i, today) for i in crud.paginate(db, stmt, limit, offset)]


def update_waiting(db: Session, item_id: uuid.UUID, data: WaitingUpdate) -> WaitingItem:
    item = get_waiting(db, item_id)
    changes = data.changes()
    if changes.get("related_person_id") is not None:
        crud.get_or_raise(db, Person, changes["related_person_id"])
    if "status" in changes:
        # Resolution date follows the status.
        changes["resolved_at"] = None if changes["status"] == "waiting" else today_local()
    return crud.apply_changes(db, item, changes)


def resolve_waiting(
    db: Session, item_id: uuid.UUID, status: str = "received", resolved_on: date | None = None
) -> WaitingItem:
    item = get_waiting(db, item_id)
    item.status = status
    item.resolved_at = resolved_on or today_local()
    return crud.save(db, item)


def delete_waiting(db: Session, item_id: uuid.UUID) -> None:
    crud.delete(db, get_waiting(db, item_id))
