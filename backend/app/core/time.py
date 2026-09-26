"""Time helpers. Natural phrases ("today", "last night") are always
interpreted in the configured local timezone, never UTC."""

from datetime import date, datetime

from app.core.config import get_settings


def now_local() -> datetime:
    return datetime.now(get_settings().tz)


def today_local() -> date:
    return now_local().date()


def ensure_aware(value: datetime) -> datetime:
    """Attach the configured timezone to naive datetimes."""
    if value.tzinfo is None:
        return value.replace(tzinfo=get_settings().tz)
    return value
