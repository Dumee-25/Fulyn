"""Agent behaviour against the real configured Ollama model.

Opt-in because they are slow and depend on the model:  RUN_LLM_TESTS=1 pytest -m llm
Assertions check what was stored, not exact wording.
"""

import os
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.llm import get_llm
from app.agent.loop import AgentResult, run_agent
from app.core.config import get_settings
from app.models import CaffeineLog, Expense, JournalEntry, MoodLog, SleepLog
from app.services.conversations import get_or_create_conversation

TZ = get_settings().tz

pytestmark = [
    pytest.mark.llm,
    pytest.mark.skipif(os.environ.get("RUN_LLM_TESTS") != "1", reason="set RUN_LLM_TESTS=1 to run"),
]


class Chat:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.llm = get_llm()
        self.conversation = None

    def send(self, message: str) -> AgentResult:
        if self.conversation is None:
            self.conversation = get_or_create_conversation(self.db, None, message)
        return run_agent(self.db, self.conversation, message, self.llm)

    def all(self, model: type) -> list:
        return list(self.db.scalars(select(model)))


@pytest.fixture
def chat(db: Session) -> Chat:
    return Chat(db)


def test_single_expense(chat: Chat) -> None:
    chat.send("Spent 500 on coffee.")
    (expense,) = chat.all(Expense)
    assert expense.amount == Decimal("500.00")
    assert expense.currency == "LKR"


def test_expense_and_sleep(chat: Chat) -> None:
    chat.send("Spent 500 on coffee and slept 5 hours.")
    assert len(chat.all(Expense)) == 1
    (sleep,) = chat.all(SleepLog)
    assert sleep.duration_minutes == 300


def test_admits_missing_records(chat: Chat) -> None:
    result = chat.send("What happened with Sarah in 2024?")
    assert chat.all(JournalEntry) == []
    assert chat.all(Expense) == []
    reply = result.reply.lower()
    assert any(p in reply for p in ("couldn't find", "could not find", "no record", "don't have"))


def test_acceptance_conversation(chat: Chat) -> None:
    """Spec section 47, for the parts built so far (people and events come later)."""
    message = (
        "Slept around 2 last night and woke at 7. Had an iced latte at 10. Went to Barista "
        "with Maya after uni and spent 1450. Pretty nice day honestly."
    )
    chat.send(message)

    (entry,) = chat.all(JournalEntry)
    assert entry.raw_text == message

    (sleep,) = chat.all(SleepLog)
    assert sleep.duration_minutes == 300
    assert sleep.is_approximate
    assert (sleep.sleep_time.astimezone(TZ).hour, sleep.wake_time.astimezone(TZ).hour) == (2, 7)

    (coffee,) = chat.all(CaffeineLog)
    assert "latte" in coffee.drink_type.lower()
    assert coffee.consumed_at.astimezone(TZ).hour == 10

    (expense,) = chat.all(Expense)
    assert expense.amount == Decimal("1450.00")
    assert expense.category == "Cafe"

    (mood,) = chat.all(MoodLog)
    assert (mood.score or 0) >= 6 or mood.label in ("good", "great", "calm")

    for record in (sleep, coffee, expense, mood):
        assert record.journal_entry_id == entry.id

    chat.send("Actually the Barista bill was 1550.")
    chat.db.refresh(expense)
    assert expense.amount == Decimal("1550.00")
    assert len(chat.all(Expense)) == 1

    chat.send("Make that evening a core memory.")
    chat.db.refresh(entry)
    assert entry.importance_score == 5

    result = chat.send("What did I do that day?")
    assert "1550" in result.reply.replace(",", "") or "1,550" in result.reply
    assert "maya" in result.reply.lower()
