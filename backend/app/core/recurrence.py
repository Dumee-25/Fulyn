"""Calendar arithmetic for billing cycles and recurring reminders. No external deps."""

import calendar
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal


def add_months(value: date, months: int) -> date:
    """Same day of month, clamped to the month's end (Jan 31 + 1 month = Feb 28/29)."""
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def step(value: date, cycle: str, custom_days: int | None = None) -> date:
    """One cycle after ``value``. Works for dates and datetimes."""
    if cycle == "daily":
        return value + timedelta(days=1)
    if cycle == "weekly":
        return value + timedelta(weeks=1)
    if cycle == "monthly":
        return add_months(value, 1)
    if cycle == "quarterly":
        return add_months(value, 3)
    if cycle == "yearly":
        return add_months(value, 12)
    if cycle == "custom" and custom_days:
        return value + timedelta(days=custom_days)
    raise ValueError(f"unknown cycle {cycle!r}")


def next_on_or_after(start: date, cycle: str, today: date, custom_days: int | None = None) -> date:
    """First occurrence of the cycle, starting at ``start``, that is not before ``today``."""
    current = start
    while current < today:
        current = step(current, cycle, custom_days)
    return current


def next_after(start: datetime, rule: str, now: datetime) -> datetime:
    """First occurrence strictly after ``now`` (recurring reminders skip missed ones)."""
    current = step(start, rule)
    while current <= now:
        current = step(current, rule)
    return current


CENT = Decimal("0.01")
_MONTHLY_FACTOR = {
    "weekly": Decimal(52) / Decimal(12),
    "monthly": Decimal(1),
    "quarterly": Decimal(1) / Decimal(3),
    "yearly": Decimal(1) / Decimal(12),
}
DAYS_PER_MONTH = Decimal("365.25") / Decimal(12)


def monthly_cost(amount: Decimal, cycle: str, custom_days: int | None = None) -> Decimal:
    """Average cost per month, rounded half-up to cents."""
    if cycle == "custom":
        if not custom_days:
            raise ValueError("custom cycle needs custom_days")
        factor = DAYS_PER_MONTH / Decimal(custom_days)
    else:
        factor = _MONTHLY_FACTOR[cycle]
    return (amount * factor).quantize(CENT, rounding=ROUND_HALF_UP)
