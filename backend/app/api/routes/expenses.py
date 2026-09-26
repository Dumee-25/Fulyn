import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DbSession, ListQuery
from app.core.config import get_settings
from app.schemas.expense import ExpenseCreate, ExpenseRead, ExpenseSummary, ExpenseUpdate
from app.services import expenses as service

router = APIRouter(prefix="/expenses", tags=["expenses"])


@router.get("", response_model=list[ExpenseRead])
def list_expenses(
    db: DbSession,
    params: ListQuery,
    category: str | None = None,
    merchant: Annotated[str | None, Query(max_length=200)] = None,
    is_impulse: bool | None = None,
):
    return service.list_expenses(
        db, category=category, merchant=merchant, is_impulse=is_impulse, **params.model_dump()
    )


@router.get("/categories", response_model=list[str])
def list_categories() -> list[str]:
    return get_settings().expense_categories


@router.get("/summary", response_model=ExpenseSummary)
def summary(
    db: DbSession,
    date_from: date | None = None,
    date_to: date | None = None,
    currency: Annotated[str | None, Query(pattern=r"^[A-Za-z]{3}$")] = None,
):
    return service.summarize_expenses(db, date_from=date_from, date_to=date_to, currency=currency)


@router.post("", response_model=ExpenseRead, status_code=status.HTTP_201_CREATED)
def create_expense(db: DbSession, data: ExpenseCreate):
    return service.create_expense(db, data)


@router.get("/{expense_id}", response_model=ExpenseRead)
def get_expense(db: DbSession, expense_id: uuid.UUID):
    return service.get_expense(db, expense_id)


@router.patch("/{expense_id}", response_model=ExpenseRead)
def update_expense(db: DbSession, expense_id: uuid.UUID, data: ExpenseUpdate):
    return service.update_expense(db, expense_id, data)


@router.delete("/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_expense(db: DbSession, expense_id: uuid.UUID) -> None:
    service.delete_expense(db, expense_id)
