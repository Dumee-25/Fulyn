import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DbSession, ListQuery
from app.core.time import ensure_aware
from app.schemas.planning import (
    DecisionCreate,
    DecisionRead,
    DecisionStatus,
    DecisionUpdate,
    ReminderCreate,
    ReminderRead,
    ReminderStatus,
    ReminderUpdate,
    SubscriptionCreate,
    SubscriptionRead,
    SubscriptionSummary,
    SubscriptionUpdate,
    WaitingCreate,
    WaitingRead,
    WaitingStatus,
    WaitingUpdate,
)
from app.services import planning as service

subscriptions_router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])
reminders_router = APIRouter(prefix="/reminders", tags=["reminders"])
decisions_router = APIRouter(prefix="/decisions", tags=["decisions"])
waiting_router = APIRouter(prefix="/waiting", tags=["waiting"])

Search = Annotated[str | None, Query(max_length=200)]


# --- Subscriptions -----------------------------------------------------------------


@subscriptions_router.get("", response_model=list[SubscriptionRead])
def list_subscriptions(db: DbSession, active: bool | None = None):
    return service.list_subscriptions(db, active=active)


@subscriptions_router.get("/summary", response_model=SubscriptionSummary)
def subscription_summary(db: DbSession):
    return service.summarize_subscriptions(db)


@subscriptions_router.post("", response_model=SubscriptionRead, status_code=status.HTTP_201_CREATED)
def create_subscription(db: DbSession, data: SubscriptionCreate):
    return service.subscription_view(service.create_subscription(db, data))


@subscriptions_router.get("/{sub_id}", response_model=SubscriptionRead)
def get_subscription(db: DbSession, sub_id: uuid.UUID):
    return service.subscription_view(service.get_subscription(db, sub_id))


@subscriptions_router.patch("/{sub_id}", response_model=SubscriptionRead)
def update_subscription(db: DbSession, sub_id: uuid.UUID, data: SubscriptionUpdate):
    return service.subscription_view(service.update_subscription(db, sub_id, data))


@subscriptions_router.delete("/{sub_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_subscription(db: DbSession, sub_id: uuid.UUID) -> None:
    service.delete_subscription(db, sub_id)


# --- Reminders ---------------------------------------------------------------------


@reminders_router.get("", response_model=list[ReminderRead])
def list_reminders(
    db: DbSession,
    status: ReminderStatus | None = "pending",
    due_before: Annotated[
        datetime | None, Query(description="Only reminders due at or before this time")
    ] = None,
    q: Search = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
):
    return service.list_reminders(
        db,
        status=status,
        due_before=ensure_aware(due_before) if due_before else None,
        query=q,
        limit=limit,
    )


@reminders_router.post("", response_model=ReminderRead, status_code=status.HTTP_201_CREATED)
def create_reminder(db: DbSession, data: ReminderCreate):
    return service.create_reminder(db, data)


@reminders_router.post("/{reminder_id}/complete", response_model=ReminderRead)
def complete_reminder(db: DbSession, reminder_id: uuid.UUID):
    return service.complete_reminder(db, reminder_id)


@reminders_router.get("/{reminder_id}", response_model=ReminderRead)
def get_reminder(db: DbSession, reminder_id: uuid.UUID):
    return service.get_reminder(db, reminder_id)


@reminders_router.patch("/{reminder_id}", response_model=ReminderRead)
def update_reminder(db: DbSession, reminder_id: uuid.UUID, data: ReminderUpdate):
    return service.update_reminder(db, reminder_id, data)


@reminders_router.delete("/{reminder_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_reminder(db: DbSession, reminder_id: uuid.UUID) -> None:
    service.delete_reminder(db, reminder_id)


# --- Decisions ---------------------------------------------------------------------


@decisions_router.get("", response_model=list[DecisionRead])
def list_decisions(
    db: DbSession, params: ListQuery, q: Search = None, status: DecisionStatus | None = None
):
    return service.list_decisions(db, query=q, status=status, **params.model_dump())


@decisions_router.post("", response_model=DecisionRead, status_code=status.HTTP_201_CREATED)
def create_decision(db: DbSession, data: DecisionCreate):
    return service.create_decision(db, data)


@decisions_router.get("/{decision_id}", response_model=DecisionRead)
def get_decision(db: DbSession, decision_id: uuid.UUID):
    return service.get_decision(db, decision_id)


@decisions_router.patch("/{decision_id}", response_model=DecisionRead)
def update_decision(db: DbSession, decision_id: uuid.UUID, data: DecisionUpdate):
    return service.update_decision(db, decision_id, data)


@decisions_router.delete("/{decision_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_decision(db: DbSession, decision_id: uuid.UUID) -> None:
    service.delete_decision(db, decision_id)


# --- Waiting -----------------------------------------------------------------------


@waiting_router.get("", response_model=list[WaitingRead])
def list_waiting(
    db: DbSession,
    status: WaitingStatus | None = "waiting",
    q: Search = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
):
    return service.list_waiting(db, status=status, query=q, limit=limit)


@waiting_router.post("", response_model=WaitingRead, status_code=status.HTTP_201_CREATED)
def create_waiting(db: DbSession, data: WaitingCreate):
    return service.waiting_view(db, service.create_waiting(db, data))


@waiting_router.get("/{item_id}", response_model=WaitingRead)
def get_waiting(db: DbSession, item_id: uuid.UUID):
    return service.waiting_view(db, service.get_waiting(db, item_id))


@waiting_router.patch("/{item_id}", response_model=WaitingRead)
def update_waiting(db: DbSession, item_id: uuid.UUID, data: WaitingUpdate):
    return service.waiting_view(db, service.update_waiting(db, item_id, data))


@waiting_router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_waiting(db: DbSession, item_id: uuid.UUID) -> None:
    service.delete_waiting(db, item_id)
