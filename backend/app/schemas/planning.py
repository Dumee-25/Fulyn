import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import (
    CurrencyCode,
    ImportanceScore,
    LocalDateTime,
    Money,
    NonBlankStr,
    PatchModel,
    ReadModel,
)
from app.schemas.expense import Category

BillingCycle = Literal["weekly", "monthly", "quarterly", "yearly", "custom"]
RecurrenceRule = Literal["daily", "weekly", "monthly", "yearly"]
ReminderStatus = Literal["pending", "completed", "cancelled"]
DecisionStatus = Literal["active", "reconsidered", "reversed", "completed"]
WaitingStatus = Literal["waiting", "received", "cancelled", "expired"]
Title = Annotated[NonBlankStr, Field(max_length=200)]


# --- Subscriptions -----------------------------------------------------------------


class SubscriptionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[NonBlankStr, Field(max_length=100)]
    amount: Money
    currency: CurrencyCode | None = Field(default=None, description="Defaults to home currency")
    billing_cycle: BillingCycle = "monthly"
    custom_interval_days: int | None = Field(default=None, ge=1, le=3660)
    next_billing_date: date | None = None
    category: Category = "Subscription"
    active: bool = True
    notes: str | None = None

    @model_validator(mode="after")
    def _custom_needs_interval(self) -> "SubscriptionCreate":
        if self.billing_cycle == "custom" and not self.custom_interval_days:
            raise ValueError("custom billing_cycle needs custom_interval_days")
        return self


class SubscriptionUpdate(PatchModel):
    non_nullable = frozenset({"name", "amount", "currency", "billing_cycle", "category", "active"})

    name: Annotated[NonBlankStr, Field(max_length=100)] | None = None
    amount: Money | None = None
    currency: CurrencyCode | None = None
    billing_cycle: BillingCycle | None = None
    custom_interval_days: int | None = Field(default=None, ge=1, le=3660)
    next_billing_date: date | None = None
    category: Category | None = None
    active: bool | None = None
    notes: str | None = None


class SubscriptionRead(ReadModel):
    id: uuid.UUID
    name: str
    amount: Decimal
    currency: str
    billing_cycle: str
    custom_interval_days: int | None
    next_billing_date: date | None
    category: str
    active: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime
    # Derived: average monthly cost and the next billing date on or after today.
    monthly_cost: Decimal = Decimal("0")
    next_due: date | None = None


class CurrencyTotal(BaseModel):
    currency: str
    monthly_total: Decimal
    yearly_total: Decimal
    count: int


class SubscriptionSummary(BaseModel):
    active_count: int
    totals: list[CurrencyTotal]


# --- Reminders ---------------------------------------------------------------------


class ReminderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Title
    description: str | None = None
    due_at: LocalDateTime = Field(description="Local date and time; 09:00 if no time given")
    recurrence_rule: RecurrenceRule | None = None


class ReminderUpdate(PatchModel):
    non_nullable = frozenset({"title", "due_at", "status"})

    title: Title | None = None
    description: str | None = None
    due_at: LocalDateTime | None = None
    recurrence_rule: RecurrenceRule | None = None
    status: ReminderStatus | None = None


class ReminderRead(ReadModel):
    id: uuid.UUID
    title: str
    description: str | None
    due_at: datetime
    recurrence_rule: str | None
    status: str
    last_completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


# --- Decisions ---------------------------------------------------------------------


class DecisionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Title = Field(description="Short name, e.g. 'Not buying the keyboard'")
    decision: NonBlankStr = Field(description="What was decided")
    reasoning: str | None = Field(default=None, description="Why, in the user's words")
    decision_date: date | None = Field(default=None, description="Defaults to today")
    status: DecisionStatus = "active"
    importance_score: ImportanceScore = 2
    journal_entry_id: uuid.UUID | None = None


class DecisionUpdate(PatchModel):
    non_nullable = frozenset({"title", "decision", "decision_date", "status", "importance_score"})

    title: Title | None = None
    decision: NonBlankStr | None = None
    reasoning: str | None = None
    decision_date: date | None = None
    status: DecisionStatus | None = None
    importance_score: ImportanceScore | None = None
    journal_entry_id: uuid.UUID | None = None


class DecisionRead(ReadModel):
    id: uuid.UUID
    title: str
    decision: str
    reasoning: str | None
    decision_date: date
    status: str
    importance_score: int
    journal_entry_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


# --- Waiting items -----------------------------------------------------------------


class WaitingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Title = Field(description="e.g. 'Refund from Daraz'")
    description: str | None = None
    waiting_since: date | None = Field(default=None, description="Defaults to today")
    expected_by: date | None = None
    related_person_id: uuid.UUID | None = None


class WaitingUpdate(PatchModel):
    non_nullable = frozenset({"title", "waiting_since", "status"})

    title: Title | None = None
    description: str | None = None
    waiting_since: date | None = None
    expected_by: date | None = None
    related_person_id: uuid.UUID | None = None
    status: WaitingStatus | None = None


class WaitingRead(ReadModel):
    id: uuid.UUID
    title: str
    description: str | None
    waiting_since: date
    expected_by: date | None
    related_person_id: uuid.UUID | None
    status: str
    resolved_at: date | None
    created_at: datetime
    updated_at: datetime
    related_person_name: str | None = None
    # Derived: still waiting and past expected_by.
    overdue: bool = False
