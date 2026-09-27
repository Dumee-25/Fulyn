"""Slash commands, modifiers and the previous-message tools."""

from datetime import date, datetime, time
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent import commands
from app.agent.llm import optional_llm
from app.core.config import get_settings
from app.core.dates import parse_date, parse_month, parse_time, take_date, take_time
from app.main import app
from app.models import (
    CaffeineLog,
    ChatMessage,
    Expense,
    JournalEntry,
    LifeEvent,
    MoodLog,
    Person,
    PersonInteraction,
    Reminder,
    SleepLog,
)
from app.schemas.journal import JournalEntryCreate
from app.services import journal, memories
from app.services.chat import handle_message
from app.services.conversations import recent_history
from tests.fake_llm import FakeLLM, call, say, tool_results, tools

TZ = get_settings().tz
TODAY = date(2026, 9, 27)  # a Sunday


class TestDates:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("today", TODAY),
            ("yesterday", date(2026, 9, 26)),
            ("3 days ago", date(2026, 9, 24)),
            ("friday", date(2026, 9, 25)),
            ("sun", date(2026, 9, 20)),
            ("2026-09-12", date(2026, 9, 12)),
            ("12/9", date(2026, 9, 12)),
            ("12", date(2026, 9, 12)),
            ("12th", date(2026, 9, 12)),
            ("12 sept", date(2026, 9, 12)),
            ("Sep 12", date(2026, 9, 12)),
            ("12 sep 2025", date(2025, 9, 12)),
            ("31 feb", None),
            ("banana", None),
        ],
    )
    def test_past_dates(self, text: str, expected: date | None) -> None:
        assert parse_date(text, TODAY, "past") == expected

    def test_future_weekday(self) -> None:
        assert parse_date("friday", TODAY, "future") == date(2026, 10, 2)
        assert parse_date("tomorrow", TODAY, "future") == date(2026, 9, 28)

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("9am", time(9)),
            ("9:30pm", time(21, 30)),
            ("21:00", time(21)),
            ("9.15", time(9, 15)),
            ("noon", time(12)),
            ("12am", time(0)),
            ("9", None),
            ("25:00", None),
        ],
    )
    def test_times(self, text: str, expected: time | None) -> None:
        assert parse_time(text) == expected

    def test_take_helpers(self) -> None:
        day, rest = take_date(["next", "week", "call", "mum"], TODAY, "future")
        assert day is None and rest[0] == "next"
        day, rest = take_date(["12", "oct", "call", "the", "bank"], TODAY, "future")
        assert day == date(2026, 10, 12) and rest == ["call", "the", "bank"]
        at, rest = take_time(["iced", "latte", "4", "pm"])
        assert at == time(16) and rest == ["iced", "latte"]

    def test_months(self) -> None:
        assert parse_month("", TODAY) == (2026, 9)
        assert parse_month("last", TODAY) == (2026, 8)
        assert parse_month("august", TODAY) == (2026, 8)
        assert parse_month("december", TODAY) == (2025, 12)
        assert parse_month("2025-03", TODAY) == (2025, 3)


class TestParse:
    def test_standalone_command(self) -> None:
        p = commands.parse("/spent 850 dinner")
        assert (p.command, p.args) == ("spent", "850 dinner")

    def test_modifiers_anywhere(self) -> None:
        p = commands.parse("Dinner with Sarah, spent 2400 /core")
        assert p.command is None and p.modifiers == ["core"]
        assert p.text == "Dinner with Sarah, spent 2400"
        p = commands.parse("/private /important Bought a gift")
        assert p.modifiers == ["private", "important"] and p.text == "Bought a gift"

    def test_unknown(self) -> None:
        assert commands.parse("/frobnicate").command == "unknown"

    def test_plain_message_untouched(self) -> None:
        p = commands.parse("Paid 50/50 with Alex")
        assert p.command is None and p.modifiers == [] and p.text == "Paid 50/50 with Alex"


def _send(db: Session, message: str, llm=None, conversation_id=None):
    return handle_message(db, message, conversation_id, llm)


def _logging_llm(message_extra=None):
    """A fake model that logs a journal entry, an expense and an event."""
    return FakeLLM(
        tools(
            call("create_journal_entry"),
            call("create_expense", amount=2400, merchant="Barista", category="Cafe"),
            call("create_person_interaction", person_name="Sarah", summary="Dinner"),
            call("create_life_event", title="Dinner with Sarah"),
        ),
        say("Logged it."),
    )


class TestQuickLogs:
    def test_spent(self, db: Session) -> None:
        res = _send(db, "/spent 850 lunch at Pilawoos")
        expense = db.scalar(select(Expense))
        assert expense.amount == Decimal("850.00") and expense.merchant == "Pilawoos"
        assert expense.category == "Food" and expense.description == "lunch"
        assert "Rs. 850" in res.reply and res.actions[0].tool == "create_expense"

    def test_spent_bad_amount(self, db: Session) -> None:
        assert "Usage" in _send(db, "/spent lots").reply
        assert db.scalar(select(Expense)) is None

    def test_coffee_mood_slept(self, db: Session) -> None:
        _send(db, "/coffee iced latte 4pm")
        log = db.scalar(select(CaffeineLog))
        assert log.drink_type == "iced latte" and log.consumed_at.astimezone(TZ).hour == 16
        assert not log.is_approximate
        _send(db, "/mood 7 tired")
        mood = db.scalar(select(MoodLog))
        assert (mood.score, mood.label) == (7, "tired")
        _send(db, "/slept 6h30")
        assert db.scalar(select(SleepLog)).duration_minutes == 390

    def test_remind(self, db: Session) -> None:
        res = _send(db, "/remind 12 dec 5pm to call the bank")
        reminder = db.scalar(select(Reminder))
        assert reminder.title == "call the bank"
        assert reminder.due_at.astimezone(TZ).replace(tzinfo=None) == datetime(2026, 12, 12, 17)
        assert "call the bank" in res.reply
        assert "When?" in _send(db, "/remind call mum").reply


class TestLastMessage:
    def test_undo_removes_everything_the_message_created(self, db: Session) -> None:
        first = _send(db, "Dinner with Sarah at Barista, spent 2400", _logging_llm())
        assert db.scalar(select(Person)).name == "Sarah"
        res = _send(db, "/undo", conversation_id=first.conversation_id)
        for model in (JournalEntry, Expense, PersonInteraction, LifeEvent, Person):
            assert db.scalars(select(model)).all() == [], model
        assert "Removed" in res.reply
        assert (
            "no earlier message" in _send(db, "/undo", conversation_id=first.conversation_id).reply
        )

    def test_undo_keeps_people_used_elsewhere(self, db: Session) -> None:
        first = _send(db, "Dinner with Sarah", _logging_llm())
        _send(
            db,
            "Coffee with Sarah",
            FakeLLM(
                tools(call("create_person_interaction", person_name="Sarah", summary="Coffee")),
                say("Logged."),
            ),
            conversation_id=first.conversation_id,
        )
        _send(db, "/undo", conversation_id=first.conversation_id)
        assert db.scalar(select(Person)).name == "Sarah"  # still used by the first message

    def test_date_moves_the_last_message(self, db: Session) -> None:
        first = _send(db, "Dinner with Sarah", _logging_llm())
        res = _send(db, "/date 2026-09-12", conversation_id=first.conversation_id)
        assert db.scalar(select(JournalEntry)).entry_date == date(2026, 9, 12)
        assert db.scalar(select(Expense)).expense_date == date(2026, 9, 12)
        assert db.scalar(select(PersonInteraction)).interaction_date == date(2026, 9, 12)
        assert db.scalar(select(Person)).last_interaction_at == date(2026, 9, 12)
        assert db.scalar(select(LifeEvent)).event_date == date(2026, 9, 12)
        assert "to Sat 12 Sep" in res.reply
        assert (
            "Which day" in _send(db, "/date someday", conversation_id=first.conversation_id).reply
        )

    def test_standalone_core_applies_to_last_message(self, db: Session) -> None:
        first = _send(db, "Dinner with Sarah", _logging_llm())
        _send(db, "/core", conversation_id=first.conversation_id)
        assert db.scalar(select(JournalEntry)).importance_score == 5
        assert db.scalar(select(LifeEvent)).importance_score == 5
        assert db.scalar(select(PersonInteraction)).importance_score == 5
        assert memories.list_memories(db, min_importance=5)

    def test_impulse_toggle(self, db: Session) -> None:
        first = _send(db, "/spent 6000 hoodie")
        _send(db, "/impulse", conversation_id=first.conversation_id)
        assert db.scalar(select(Expense)).is_impulse is True
        _send(db, "/notimpulse", conversation_id=first.conversation_id)
        assert db.scalar(select(Expense)).is_impulse is False


class TestInlineModifiers:
    def test_core_inside_a_message(self, db: Session) -> None:
        llm = _logging_llm()
        res = _send(db, "Dinner with Sarah at Barista, spent 2400 /core", llm)
        # The model never sees the modifier; the journal keeps the clean text.
        assert "/core" not in str(llm.requests[0][-1])
        entry = db.scalar(select(JournalEntry))
        assert entry.raw_text == "Dinner with Sarah at Barista, spent 2400"
        assert entry.importance_score == 5
        assert "core memory" in res.reply

    def test_private_inside_a_message(self, db: Session) -> None:
        res = _send(db, "Bought Sarah a surprise gift /private", _logging_llm())
        assert db.scalar(select(JournalEntry)).is_private is True
        assert "vault" in res.reply
        assert recent_history(db, res.conversation_id, 50) == []

    def test_modifier_with_nothing_logged(self, db: Session) -> None:
        res = _send(db, "How are you? /core", FakeLLM(say("Good!")))
        assert "nothing to apply to" in res.reply

    def test_nolog_uses_read_only_tools(self, db: Session) -> None:
        llm = FakeLLM(tools(call("create_expense", amount=10)), say("Okay."))
        _send(db, "/nolog spent 10 on nothing", llm)
        result = tool_results(llm.requests[1], "create_expense")[0]
        assert result["ok"] is False and "unknown tool" in result["error"]
        assert db.scalar(select(Expense)) is None


class TestViews:
    def test_help_lists_commands(self, db: Session) -> None:
        reply = _send(db, "/help").reply
        for name in ("/core", "/undo", "/date", "/spent", "/who", "/vault"):
            assert name in reply

    def test_unknown_command(self, db: Session) -> None:
        assert "/help" in _send(db, "/frobnicate").reply

    def test_who_and_waiting(self, db: Session) -> None:
        first = _send(db, "Dinner with Sarah", _logging_llm())
        assert "Sarah" in _send(db, "/who sarah", conversation_id=first.conversation_id).reply
        assert "don't have anyone" in _send(db, "/who John").reply
        assert "not waiting" in _send(db, "/waiting").reply

    def test_today_without_model(self, db: Session) -> None:
        _send(db, "/spent 100 snack")
        reply = _send(db, "/today").reply
        assert "Rs. 100" in reply

    def test_vault_search_is_private(self, db: Session) -> None:
        journal.create_journal_entry(
            db, JournalEntryCreate(raw_text="Secret gift for Sarah", is_private=True)
        )
        res = _send(db, "/vault gift")
        assert "Secret gift" in res.reply
        flags = db.scalars(
            select(ChatMessage.is_private).where(ChatMessage.conversation_id == res.conversation_id)
        ).all()
        assert flags and all(flags)


class TestPhraseTools:
    def test_undo_that(self, db: Session) -> None:
        first = _send(db, "Dinner with Sarah", _logging_llm())
        llm = FakeLLM(tools(call("undo_last_message")), say("Done, removed it."))
        _send(db, "scratch that", llm, conversation_id=first.conversation_id)
        assert db.scalars(select(Expense)).all() == []

    def test_that_was_yesterday(self, db: Session) -> None:
        first = _send(db, "Dinner with Sarah", _logging_llm())
        llm = FakeLLM(tools(call("move_last_message", date="2026-09-20")), say("Moved."))
        _send(db, "that was last Sunday", llm, conversation_id=first.conversation_id)
        assert db.scalar(select(Expense)).expense_date == date(2026, 9, 20)

    def test_remember_that_forever(self, db: Session) -> None:
        first = _send(db, "Dinner with Sarah", _logging_llm())
        llm = FakeLLM(tools(call("set_last_message_importance", importance_score=5)), say("Ok."))
        _send(db, "remember that forever", llm, conversation_id=first.conversation_id)
        assert db.scalar(select(JournalEntry)).importance_score == 5


class TestApi:
    def test_commands_endpoint(self, api: TestClient) -> None:
        listed = api.get("/api/chat/commands").json()
        assert {c["name"] for c in listed} >= {"core", "undo", "spent", "help"}

    def test_commands_work_without_the_model(self, api: TestClient) -> None:
        app.dependency_overrides[optional_llm] = lambda: None
        assert api.post("/api/chat", json={"message": "/spent 50 tea"}).status_code == 200
        res = api.post("/api/chat", json={"message": "hello"})
        assert res.status_code == 503 and "/commands" in res.json()["detail"]
