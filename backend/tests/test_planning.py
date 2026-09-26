"""Subscriptions, reminders, decisions, waiting items and impulse handling."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.loop import run_agent
from app.core.config import get_settings
from app.core.recurrence import add_months, monthly_cost, next_after, next_on_or_after
from app.models import Decision, Expense, Memory, Reminder, WaitingItem
from app.schemas.planning import (
    DecisionCreate,
    ReminderCreate,
    SubscriptionCreate,
    WaitingCreate,
)
from app.services import memories, planning
from app.services.conversations import get_or_create_conversation
from tests.fake_llm import FakeLLM, call, say, tool_results, tools

TZ = get_settings().tz


class TestRecurrence:
    def test_add_months_clamps(self) -> None:
        assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
        assert add_months(date(2028, 1, 31), 1) == date(2028, 2, 29)
        assert add_months(date(2026, 11, 15), 3) == date(2027, 2, 15)

    @pytest.mark.parametrize(
        ("amount", "cycle", "days", "expected"),
        [
            ("1200", "monthly", None, "1200.00"),
            ("1200", "yearly", None, "100.00"),
            ("300", "quarterly", None, "100.00"),
            ("1000", "weekly", None, "4333.33"),
            ("100", "custom", 14, "217.41"),
        ],
    )
    def test_monthly_cost(self, amount: str, cycle: str, days: int | None, expected: str) -> None:
        assert monthly_cost(Decimal(amount), cycle, days) == Decimal(expected)

    def test_next_billing_rolls_forward(self) -> None:
        assert next_on_or_after(date(2026, 1, 31), "monthly", date(2026, 3, 1)) == date(2026, 3, 28)

    def test_recurring_reminder_skips_missed(self) -> None:
        start = datetime(2026, 9, 1, 9, tzinfo=TZ)
        now = datetime(2026, 9, 26, 12, tzinfo=TZ)
        assert next_after(start, "weekly", now) == datetime(2026, 9, 29, 9, tzinfo=TZ)


class TestSubscriptions:
    def test_summary_per_currency(self, db: Session) -> None:
        planning.create_subscription(db, SubscriptionCreate(name="Netflix", amount="2500"))
        planning.create_subscription(
            db, SubscriptionCreate(name="iCloud", amount="1200", billing_cycle="yearly")
        )
        planning.create_subscription(
            db, SubscriptionCreate(name="Old gym", amount="5000", active=False)
        )
        planning.create_subscription(
            db, SubscriptionCreate(name="GitHub", amount="4", currency="usd")
        )
        summary = planning.summarize_subscriptions(db)
        assert summary.active_count == 3
        lkr, usd = summary.totals
        assert (lkr.currency, lkr.monthly_total, lkr.yearly_total) == (
            "LKR",
            Decimal("2600.00"),
            Decimal("31200.00"),
        )
        assert (usd.currency, usd.monthly_total) == ("USD", Decimal("4.00"))

    def test_custom_cycle_requires_interval(self) -> None:
        with pytest.raises(ValidationError):
            SubscriptionCreate(name="X", amount=1, billing_cycle="custom")

    def test_api(self, api: TestClient) -> None:
        res = api.post(
            "/api/subscriptions",
            json={"name": "Spotify", "amount": "1150", "next_billing_date": "2020-01-15"},
        )
        assert res.status_code == 201
        body = res.json()
        assert body["monthly_cost"] == "1150.00"
        assert date.fromisoformat(body["next_due"]) >= date.today() - timedelta(days=1)
        assert api.get("/api/subscriptions/summary").json()["totals"][0]["monthly_total"] == (
            "1150.00"
        )


class TestReminders:
    def test_one_off_completes(self, db: Session) -> None:
        reminder = planning.create_reminder(
            db, ReminderCreate(title="Pay rent", due_at="2026-10-01T09:00:00")
        )
        assert reminder.due_at == datetime(2026, 10, 1, 9, tzinfo=TZ)
        done = planning.complete_reminder(db, reminder.id)
        assert done.status == "completed" and done.last_completed_at is not None

    def test_recurring_moves_to_next_occurrence(self, db: Session) -> None:
        reminder = planning.create_reminder(
            db,
            ReminderCreate(
                title="Water plants", due_at="2026-09-01T08:00:00", recurrence_rule="weekly"
            ),
        )
        with patch(
            "app.services.planning.now_local",
            return_value=datetime(2026, 9, 26, 12, tzinfo=TZ),
        ):
            done = planning.complete_reminder(db, reminder.id)
        assert done.status == "pending"
        assert done.due_at.astimezone(TZ) == datetime(2026, 9, 29, 8, tzinfo=TZ)

    def test_due_filter_and_order(self, db: Session) -> None:
        for title, when in [("later", "2099-01-01T09:00"), ("past", "2020-01-01T09:00")]:
            planning.create_reminder(db, ReminderCreate(title=title, due_at=when))
        all_pending = planning.list_reminders(db)
        assert [r.title for r in all_pending] == ["past", "later"]
        due = planning.list_reminders(db, due_before=datetime.now(TZ))
        assert [r.title for r in due] == ["past"]

    def test_cannot_complete_twice(self, api: TestClient) -> None:
        rid = api.post(
            "/api/reminders", json={"title": "Call bank", "due_at": "2026-10-01T09:00:00"}
        ).json()["id"]
        assert api.post(f"/api/reminders/{rid}/complete").status_code == 200
        assert api.post(f"/api/reminders/{rid}/complete").status_code == 422


class TestDecisions:
    def test_decision_is_a_searchable_memory(self, db: Session) -> None:
        decision = planning.create_decision(
            db,
            DecisionCreate(
                title="Not buying the keyboard",
                decision="Decided not to buy the mechanical keyboard",
                reasoning="I already have one and it's 28k",
            ),
        )
        memory = db.scalar(select(Memory).where(Memory.source_id == decision.id))
        assert memory.memory_type == "decision"
        assert "28k" in memory.content
        assert memories.search_memories(db, "keyboard").results[0].source_id == decision.id
        assert planning.list_decisions(db, query="28k")[0].id == decision.id


class TestWaiting:
    def test_overdue_and_resolve(self, db: Session) -> None:
        item = planning.create_waiting(
            db, WaitingCreate(title="Refund", expected_by=date(2020, 1, 1))
        )
        view = planning.list_waiting(db)[0]
        assert view.overdue is True
        planning.resolve_waiting(db, item.id)
        assert planning.list_waiting(db) == []
        received = planning.list_waiting(db, status="received")[0]
        assert received.resolved_at is not None and received.overdue is False


def _run(db: Session, message: str, llm, conversation=None):
    conversation = conversation or get_or_create_conversation(db, None, message)
    return run_agent(db, conversation, message, llm), conversation


class TestTools:
    def test_decision_linked_to_journal(self, db: Session) -> None:
        llm = FakeLLM(
            tools(
                call("create_journal_entry"),
                call(
                    "create_decision",
                    title="No keyboard",
                    decision="Not buying the keyboard",
                    reasoning="Already have one; 28k",
                ),
            ),
            say("Noted."),
        )
        _run(
            db, "I've decided not to buy the keyboard because I already have one and it's 28k.", llm
        )
        decision = db.scalar(select(Decision))
        assert decision.journal_entry_id is not None

    def test_reminder_and_waiting_do_not_create_journal(self, db: Session) -> None:
        from app.models import JournalEntry

        llm = FakeLLM(
            tools(
                call("create_reminder", title="Call the bank", due_at="2026-10-01T09:00:00"),
                call("create_waiting_item", title="File from Alex", related_person_name="Alex"),
            ),
            say("Done."),
        )
        _run(db, "Remind me to call the bank on Oct 1. Also waiting on Alex for the file.", llm)
        assert db.scalars(select(JournalEntry)).all() == []
        item = db.scalar(select(WaitingItem))
        assert item.related_person_id is not None
        assert db.scalar(select(Reminder)).due_at == datetime(2026, 10, 1, 9, tzinfo=TZ)

    def test_subscription_totals_tool(self, db: Session) -> None:
        planning.create_subscription(db, SubscriptionCreate(name="Netflix", amount="2500"))
        llm = FakeLLM(tools(call("get_subscriptions")), say("Rs. 2,500 a month."))
        _run(db, "How much do subscriptions cost me every month?", llm)
        found = tool_results(llm.requests[1], "get_subscriptions")[0]
        assert found["summary"]["totals"][0]["monthly_total"] == "2500.00"
        assert found["subscriptions"][0]["monthly_cost"] == "2500.00"

    def test_update_subscription_keeps_derived_fields(self, db: Session) -> None:
        sub = planning.create_subscription(db, SubscriptionCreate(name="Netflix", amount="2500"))
        llm = FakeLLM(
            tools(call("update_subscription", subscription_id=str(sub.id), amount="3000")),
            say("Updated."),
        )
        _run(db, "Netflix went up to 3000", llm)
        record = tool_results(llm.requests[1], "update_subscription")[0]["record"]
        assert record["monthly_cost"] == "3000.00"

    def test_impulse_flag_can_be_removed(self, db: Session) -> None:
        from app.schemas.expense import ExpenseCreate
        from app.services import expenses

        expense = expenses.create_expense(
            db, ExpenseCreate(amount="5000", is_impulse=True, impulse_reason="sale")
        )
        llm = FakeLLM(
            tools(call("update_expense", expense_id=str(expense.id), is_impulse=False)),
            say("Okay, not counted as impulse."),
        )
        _run(db, "That wasn't an impulse purchase.", llm)
        db.refresh(expense)
        assert expense.is_impulse is False and expense.impulse_reason is None
        assert db.scalar(select(Expense)).is_impulse is False
