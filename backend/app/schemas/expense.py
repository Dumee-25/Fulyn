import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.core.config import get_settings
from app.schemas.common import CurrencyCode, Money, PatchModel, ReadModel


def normalize_category(value: str) -> str:
    """Match case-insensitively against the configured categories."""
    categories = get_settings().expense_categories
    for category in categories:
        if category.lower() == value.strip().lower():
            return category
    raise ValueError(f"unknown category; expected one of {categories}")


Category = Annotated[str, AfterValidator(normalize_category)]


class ExpenseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Money
    currency: CurrencyCode | None = Field(default=None, description="Defaults to DEFAULT_CURRENCY")
    category: Category = "Other"
    merchant: str | None = Field(default=None, max_length=200)
    description: str | None = None
    expense_date: date | None = Field(default=None, description="Defaults to today (local time)")
    is_impulse: bool = False
    impulse_reason: str | None = None
    journal_entry_id: uuid.UUID | None = None


class ExpenseUpdate(PatchModel):
    non_nullable = frozenset({"amount", "currency", "category", "expense_date", "is_impulse"})

    amount: Money | None = None
    currency: CurrencyCode | None = None
    category: Category | None = None
    merchant: str | None = Field(default=None, max_length=200)
    description: str | None = None
    expense_date: date | None = None
    is_impulse: bool | None = None
    impulse_reason: str | None = None
    journal_entry_id: uuid.UUID | None = None


class ExpenseRead(ReadModel):
    id: uuid.UUID
    amount: Decimal
    currency: str
    category: str
    merchant: str | None
    description: str | None
    expense_date: date
    is_impulse: bool
    impulse_reason: str | None
    journal_entry_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class CategoryTotal(BaseModel):
    category: str
    total: Decimal
    count: int


class ExpenseSummary(BaseModel):
    """Totals for one currency over a date range. Amounts in other currencies are excluded."""

    currency: str
    total: Decimal
    impulse_total: Decimal
    count: int
    by_category: list[CategoryTotal]
