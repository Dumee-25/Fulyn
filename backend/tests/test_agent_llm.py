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
from app.models import (
    CaffeineLog,
    Decision,
    Expense,
    JournalEntry,
    LifeEvent,
    MoodLog,
    MusicMemory,
    Person,
    PersonInteraction,
    Reminder,
    SleepLog,
    Subscription,
    WaitingItem,
)
from app.services.conversations import get_or_create_conversation
from app.services.embeddings import set_embedding_service

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
def chat(db: Session, fake_embeddings, monkeypatch: pytest.MonkeyPatch) -> Chat:
    # Override the model with TEST_OLLAMA_MODEL.
    monkeypatch.setattr(
        get_settings(),
        "ollama_model",
        os.environ.get("TEST_OLLAMA_MODEL", "nemotron-3-ultra:cloud"),
    )
    set_embedding_service(None)  # use the configured embedding model too
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
    """Spec section 47: every expected record, then correction, core memory and recall."""
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

    (maya,) = chat.all(Person)
    assert maya.name == "Maya"
    (interaction,) = chat.all(PersonInteraction)
    assert interaction.person_id == maya.id

    (event,) = chat.all(LifeEvent)
    assert "maya" in event.title.lower() or "barista" in event.title.lower()

    for record in (sleep, coffee, expense, mood, interaction, event):
        assert record.journal_entry_id == entry.id

    chat.send("Actually the Barista bill was 1550.")
    chat.db.refresh(expense)
    assert expense.amount == Decimal("1550.00")
    assert len(chat.all(Expense)) == 1

    chat.send("Make that evening a core memory.")
    # Any record of that evening counts: the journal entry, the outing or the interaction.
    for record in (entry, event, interaction):
        chat.db.refresh(record)
    assert 5 in (entry.importance_score, event.importance_score, interaction.importance_score)

    result = chat.send("What did I do that day?")
    assert "1550" in result.reply.replace(",", "") or "1,550" in result.reply
    assert "maya" in result.reply.lower()


def test_memory_questions_use_memory_search(chat: Chat) -> None:
    chat.send("Had coffee with Sarah at the library, she told me about her internship.")
    result = chat.send("Show me memories about Sarah.")
    assert "search_memories" in [a.tool for a in result.actions]
    assert "internship" in result.reply.lower() or "library" in result.reply.lower()


def test_unknown_person_is_not_invented(chat: Chat) -> None:
    chat.send("Had coffee with Sarah at the library.")
    result = chat.send("What do I remember about John?")
    reply = result.reply.lower()
    assert "sarah" not in reply or "john" in reply
    assert any(
        p in reply
        for p in ("couldn't find", "could not find", "no record", "don't have", "no memories")
    )


def test_last_seen(chat: Chat) -> None:
    chat.send("Yesterday I had lunch with Alex at the canteen.")
    (alex,) = chat.all(Person)
    assert alex.last_interaction_at is not None
    result = chat.send("When did I last see Alex?")
    day = alex.last_interaction_at
    assert "get_person_interactions" in [a.tool for a in result.actions] or "yesterday" in (
        result.reply.lower()
    )
    assert str(day.day) in result.reply or "yesterday" in result.reply.lower()


def test_music_memory(chat: Chat) -> None:
    chat.send("Yellow by Coldplay always reminds me of the drive home with Sarah.")
    (song,) = chat.all(MusicMemory)
    assert song.song.lower() == "yellow"
    assert (song.artist or "").lower() == "coldplay"
    assert song.person_id == chat.all(Person)[0].id
    result = chat.send("What songs do I connect with Sarah?")
    assert "yellow" in result.reply.lower()


def test_decision_recall(chat: Chat) -> None:
    chat.send("I've decided not to buy the keyboard because I already have one and it's 28k.")
    (decision,) = chat.all(Decision)
    assert "28" in (decision.reasoning or "") + decision.decision
    result = chat.send("Why did I decide not to buy that keyboard?")
    assert "already have" in result.reply.lower() or "28" in result.reply


def test_subscriptions_total(chat: Chat) -> None:
    chat.send("I pay 2500 a month for Netflix and 12000 a year for iCloud.")
    assert len(chat.all(Subscription)) == 2
    assert chat.all(Expense) == []
    result = chat.send("How much do subscriptions cost me every month?")
    assert "3,500" in result.reply or "3500" in result.reply


def test_waiting_and_reminder(chat: Chat) -> None:
    chat.send("I'm still waiting for the Daraz refund. Remind me to follow up on Friday.")
    (item,) = chat.all(WaitingItem)
    assert "refund" in item.title.lower()
    (reminder,) = chat.all(Reminder)
    assert reminder.due_at.astimezone(TZ).weekday() == 4  # Friday
    result = chat.send("What am I still waiting for?")
    assert "refund" in result.reply.lower()


def test_impulse_purchase(chat: Chat) -> None:
    chat.send("Bought a 6000 hoodie on a whim, total impulse buy.")
    (expense,) = chat.all(Expense)
    assert expense.is_impulse
    chat.send("Actually don't count that as impulse, I'd planned it.")
    chat.db.refresh(expense)
    assert not expense.is_impulse


def test_daily_recap_is_grounded(chat: Chat) -> None:
    chat.send("Spent 1200 on lunch with Maya, had two coffees, slept 6 hours last night.")
    result = chat.send("Give me a recap of today.")
    assert "generate_daily_recap" in [a.tool for a in result.actions]
    reply = result.reply.replace(",", "")
    assert "1200" in reply
    assert "maya" in result.reply.lower()


def test_cross_domain_spending(chat: Chat) -> None:
    from datetime import timedelta

    from app.core.time import today_local
    from app.schemas.expense import ExpenseCreate
    from app.schemas.people import InteractionCreate, PersonCreate
    from app.services import expenses, people

    maya = people.create_person(chat.db, PersonCreate(name="Maya"))
    today = today_local()
    for offset in range(1, 15):
        day = today - timedelta(days=offset)
        out = offset % 3 == 0
        expenses.create_expense(
            chat.db, ExpenseCreate(amount="3000" if out else "500", expense_date=day)
        )
        if out:
            people.create_interaction(
                chat.db,
                InteractionCreate(person_id=maya.id, summary="Dinner", interaction_date=day),
            )
    result = chat.send("How much do I usually spend on days I go out compared to other days?")
    assert "compare_life" in [a.tool for a in result.actions]
    reply = result.reply.replace(",", "")
    assert "3000" in reply and "500" in reply


def _private_gift(chat: Chat) -> None:
    from app.schemas.journal import JournalEntryCreate
    from app.services import journal

    journal.create_journal_entry(
        chat.db,
        JournalEntryCreate(
            raw_text="Bought Sarah a surprise gift for her birthday.", is_private=True
        ),
    )
    journal.create_journal_entry(chat.db, JournalEntryCreate(raw_text="Had lunch with Sarah."))


def test_normal_memory_search_excludes_vault(chat: Chat) -> None:
    _private_gift(chat)
    result = chat.send("Show me memories about Sarah.")
    tools_used = [a.tool for a in result.actions]
    assert "search_private_memories" not in tools_used
    assert "gift" not in result.reply.lower()


def test_private_search_when_asked(chat: Chat) -> None:
    _private_gift(chat)
    result = chat.send("Search my private memories about Sarah.")
    assert "search_private_memories" in [a.tool for a in result.actions]
    assert "gift" in result.reply.lower()
