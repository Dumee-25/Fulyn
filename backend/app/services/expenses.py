import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.time import today_local
from app.models.expense import Expense
from app.schemas.expense import CategoryTotal, ExpenseCreate, ExpenseSummary, ExpenseUpdate
from app.services import crud

ZERO = Decimal("0.00")


def create_expense(db: Session, data: ExpenseCreate) -> Expense:
    crud.ensure_journal_entry(db, data.journal_entry_id)
    expense = Expense(**data.model_dump(exclude={"currency", "expense_date"}))
    expense.currency = data.currency or get_settings().default_currency
    expense.expense_date = data.expense_date or today_local()
    return crud.save(db, expense)


def get_expense(db: Session, expense_id: uuid.UUID) -> Expense:
    return crud.get_or_raise(db, Expense, expense_id)


def list_expenses(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    category: str | None = None,
    merchant: str | None = None,
    is_impulse: bool | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Expense]:
    stmt = crud.date_range(select(Expense), Expense.expense_date, date_from, date_to)
    if category:
        stmt = stmt.where(func.lower(Expense.category) == category.lower())
    if merchant:
        stmt = stmt.where(Expense.merchant.ilike(f"%{merchant}%"))
    if is_impulse is not None:
        stmt = stmt.where(Expense.is_impulse.is_(is_impulse))
    stmt = stmt.order_by(Expense.expense_date.desc(), Expense.created_at.desc())
    return crud.paginate(db, stmt, limit, offset)


def update_expense(db: Session, expense_id: uuid.UUID, data: ExpenseUpdate) -> Expense:
    changes = data.changes()
    # Un-marking an impulse purchase also clears the stated reason.
    if changes.get("is_impulse") is False and "impulse_reason" not in changes:
        changes["impulse_reason"] = None
    return crud.apply_changes(db, get_expense(db, expense_id), changes)


def delete_expense(db: Session, expense_id: uuid.UUID) -> None:
    crud.delete(db, get_expense(db, expense_id))


def summarize_expenses(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    currency: str | None = None,
) -> ExpenseSummary:
    currency = (currency or get_settings().default_currency).upper()
    stmt = (
        select(
            Expense.category,
            func.coalesce(func.sum(Expense.amount), ZERO),
            func.coalesce(
                func.sum(case((Expense.is_impulse.is_(True), Expense.amount), else_=ZERO)), ZERO
            ),
            func.count(),
        )
        .where(Expense.currency == currency)
        .group_by(Expense.category)
        .order_by(func.sum(Expense.amount).desc())
    )
    stmt = crud.date_range(stmt, Expense.expense_date, date_from, date_to)
    rows = db.execute(stmt).all()
    return ExpenseSummary(
        currency=currency,
        total=sum((row[1] for row in rows), ZERO),
        impulse_total=sum((row[2] for row in rows), ZERO),
        count=sum(row[3] for row in rows),
        by_category=[CategoryTotal(category=r[0], total=r[1], count=r[3]) for r in rows],
    )
