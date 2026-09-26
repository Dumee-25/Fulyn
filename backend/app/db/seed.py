"""Optional development seed data.

Usage (from backend/):  python -m app.db.seed
Refuses to run when APP_ENV=production. Adds records; it does not wipe existing ones.
"""

import sys
from datetime import datetime, time, timedelta
from decimal import Decimal

from app.core.config import get_settings
from app.core.time import today_local
from app.db.session import SessionLocal
from app.schemas.caffeine import CaffeineLogCreate
from app.schemas.expense import ExpenseCreate
from app.schemas.journal import JournalEntryCreate
from app.schemas.mood import MoodLogCreate
from app.schemas.sleep import SleepLogCreate
from app.services.caffeine import create_caffeine_log
from app.services.expenses import create_expense
from app.services.journal import create_journal_entry
from app.services.moods import create_mood_log
from app.services.sleep import create_sleep_log

DAYS = [
    {
        "text": "Slept around 2 and woke at 7. Iced latte at 10. Went to Barista with Maya "
        "after uni and spent 1450. Pretty nice day honestly.",
        "sleep": (time(2, 0), time(7, 0)),
        "coffee": ("iced latte", time(10, 0)),
        "expenses": [("1450", "Cafe", "Barista", False)],
        "mood": ("good", 7, 6),
        "importance": 3,
    },
    {
        "text": "Long lab session. Uber home because it was raining. Tired.",
        "sleep": (time(0, 30), time(6, 45)),
        "coffee": ("americano", time(9, 15)),
        "expenses": [("600", "Transport", "Uber", False), ("850", "Food", None, False)],
        "mood": ("tired", 5, 3),
        "importance": 2,
    },
    {
        "text": "Bought a mechanical keyboard on a whim. Probably didn't need it.",
        "sleep": (time(1, 0), time(8, 0)),
        "coffee": ("cappuccino", time(11, 0)),
        "expenses": [("28000", "Technology", "Keyboard shop", True)],
        "mood": ("mixed", 6, 6),
        "importance": 2,
    },
    {
        "text": "Quiet day. Read for a while, cooked dinner.",
        "sleep": (time(23, 30), time(7, 30)),
        "coffee": ("tea", time(16, 0)),
        "expenses": [("2300", "Food", "Keells", False)],
        "mood": ("calm", 7, 5),
        "importance": 1,
    },
]


def _at(day, t: time) -> datetime:
    return datetime.combine(day, t, tzinfo=get_settings().tz)


def seed() -> None:
    if get_settings().app_env.lower() == "production":
        sys.exit("Refusing to seed a production database.")

    today = today_local()
    with SessionLocal() as db:
        for offset, day_data in enumerate(DAYS):
            day = today - timedelta(days=offset)
            entry = create_journal_entry(
                db,
                JournalEntryCreate(
                    raw_text=day_data["text"],
                    entry_date=day,
                    importance_score=day_data["importance"],
                ),
            )
            sleep_start, wake = day_data["sleep"]
            # Times after noon belong to the previous evening.
            sleep_day = day - timedelta(days=1) if sleep_start.hour >= 12 else day
            create_sleep_log(
                db,
                SleepLogCreate(
                    sleep_date=day,
                    sleep_time=_at(sleep_day, sleep_start),
                    wake_time=_at(day, wake),
                    is_approximate=True,
                    journal_entry_id=entry.id,
                ),
            )
            drink, drink_time = day_data["coffee"]
            create_caffeine_log(
                db,
                CaffeineLogCreate(
                    drink_type=drink, consumed_at=_at(day, drink_time), journal_entry_id=entry.id
                ),
            )
            for amount, category, merchant, impulse in day_data["expenses"]:
                create_expense(
                    db,
                    ExpenseCreate(
                        amount=Decimal(amount),
                        category=category,
                        merchant=merchant,
                        expense_date=day,
                        is_impulse=impulse,
                        journal_entry_id=entry.id,
                    ),
                )
            label, score, energy = day_data["mood"]
            create_mood_log(
                db,
                MoodLogCreate(
                    date=day,
                    label=label,
                    score=score,
                    energy_score=energy,
                    journal_entry_id=entry.id,
                ),
            )
    print(f"Seeded {len(DAYS)} days of sample data.")


if __name__ == "__main__":
    seed()
