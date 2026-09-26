"""Life events, timeline and recaps/reports."""

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.routes.reports import optional_llm
from app.core.config import get_settings
from app.core.time import today_local
from app.main import app
from app.reports import stats
from app.schemas.caffeine import CaffeineLogCreate
from app.schemas.expense import ExpenseCreate
from app.schemas.journal import JournalEntryCreate
from app.schemas.mood import MoodLogCreate
from app.schemas.people import InteractionCreate, PersonCreate
from app.schemas.planning import DecisionCreate
from app.schemas.report import LifeEventCreate
from app.schemas.sleep import SleepLogCreate
from app.services import (
    caffeine,
    expenses,
    journal,
    life_events,
    moods,
    people,
    planning,
    reports,
    sleep,
    timeline,
)
from app.services.conversations import get_or_create_conversation
from tests.fake_llm import FakeLLM, call, say, tool_results, tools

TZ = get_settings().tz
DAY = date(2026, 9, 16)  # a Wednesday
WEEK = date(2026, 9, 14)  # its Monday


def _at(day: date, hour: int) -> datetime:
    return datetime(day.year, day.month, day.day, hour, tzinfo=TZ)


@pytest.fixture
def week(db: Session) -> None:
    """A week of data plus one private entry that must never surface."""
    maya = people.create_person(db, PersonCreate(name="Maya"))
    for offset in range(7):
        day = WEEK + timedelta(days=offset)
        drinks = 3 if offset % 2 else 1
        for i in range(drinks):
            caffeine.create_caffeine_log(
                db, CaffeineLogCreate(drink_type="latte", consumed_at=_at(day, 9 + i))
            )
        # Sleep logged on the next morning: shorter after 3-drink days.
        sleep.create_sleep_log(
            db,
            SleepLogCreate(
                sleep_date=day + timedelta(days=1), duration_minutes=300 if drinks == 3 else 480
            ),
        )
        moods.create_mood_log(db, MoodLogCreate(date=day, score=6 + offset % 2, label="good"))
    expenses.create_expense(db, ExpenseCreate(amount="1450", category="Cafe", expense_date=DAY))
    expenses.create_expense(
        db,
        ExpenseCreate(
            amount="28000",
            category="Technology",
            expense_date=DAY,
            is_impulse=True,
            merchant="Keyboard shop",
        ),
    )
    people.create_interaction(
        db,
        InteractionCreate(
            person_id=maya.id, summary="Barista after uni", interaction_date=DAY, location="Barista"
        ),
    )
    life_events.create_life_event(
        db, LifeEventCreate(title="Barista with Maya", event_date=DAY, importance_score=3)
    )
    planning.create_decision(
        db,
        DecisionCreate(
            title="No second keyboard",
            decision="Not buying another",
            reasoning="Already have one",
            decision_date=DAY,
        ),
    )
    journal.create_journal_entry(db, JournalEntryCreate(raw_text="Had a coffee", entry_date=DAY))
    journal.create_journal_entry(
        db, JournalEntryCreate(raw_text="Big exam passed!", entry_date=DAY, importance_score=4)
    )
    # Private: journal entry plus an expense linked to it.
    secret = journal.create_journal_entry(
        db,
        JournalEntryCreate(
            raw_text="Secret gift", entry_date=DAY, is_private=True, importance_score=5
        ),
    )
    expenses.create_expense(
        db, ExpenseCreate(amount="99999", expense_date=DAY, journal_entry_id=secret.id)
    )


class TestTimeline:
    def test_notable_items_only(self, db: Session, week: None) -> None:
        items = timeline.get_timeline(db, date_from=DAY, date_to=DAY)
        kinds = {(i.kind, i.title) for i in items}
        assert ("event", "Barista with Maya") in kinds
        assert ("decision", "No second keyboard") in kinds
        assert ("interaction", "With Maya") in kinds
        assert ("journal", "Big exam passed!") in kinds
        assert ("purchase", "Keyboard shop: Rs. 28,000") in kinds
        titles = " ".join(t for _, t in kinds)
        assert "Had a coffee" not in titles  # routine journal entry
        assert "1,450" not in titles  # not a major purchase
        assert "Secret" not in titles and "99,999" not in titles

    def test_min_importance(self, db: Session, week: None) -> None:
        items = timeline.get_timeline(db, date_from=DAY, date_to=DAY, min_importance=4)
        assert {i.title for i in items} >= {"Big exam passed!"}
        assert "Barista with Maya" not in {i.title for i in items}


class TestStats:
    def test_daily_numbers(self, db: Session, week: None) -> None:
        data = stats.daily(db, DAY)
        assert data["spending"]["total"] == "29450.00"  # private 99,999 excluded
        assert data["spending"]["impulse_total"] == "28000.00"
        assert data["caffeine"]["drinks"] == 1
        assert [i["time"] for i in data["caffeine"]["items"]] == ["09:00"]
        assert data["people"]["by_person"] == [{"name": "Maya", "count": 1}]
        assert data["journal_entries"] == 2  # the private one is not counted

    def test_weekly_coincidence_is_described_not_explained(self, db: Session, week: None) -> None:
        data = stats.weekly(db, WEEK)
        assert data["caffeine_sleep"] == {"pairs": 7, "sleep_difference_minutes": 180}
        content = reports.generate_weekly(db, DAY, None).content
        assert "coincided with shorter sleep" in content
        assert "not a cause" in content
        assert "caused" not in content

    def test_empty_day(self, db: Session) -> None:
        report = reports.generate_daily(db, date(2026, 1, 1), None)
        assert "Nothing was logged" in report.content

    def test_future_period_rejected(self, db: Session) -> None:
        from app.core.errors import DomainError

        with pytest.raises(DomainError):
            reports.generate_daily(db, today_local() + timedelta(days=2), None)


class TestReports:
    def test_daily_render_and_storage(self, db: Session, week: None) -> None:
        report = reports.generate_daily(db, DAY, None)
        content = report.content
        assert content.startswith("# Wednesday, 16 September 2026")
        assert "Rs. 29,450" in content
        assert "latte at 09:00" in content
        assert "Maya at Barista: Barista after uni" in content
        assert "No second keyboard, because Already have one" in content
        assert "Secret" not in content and "99,999" not in content
        assert reports.get_daily(db, DAY).content == content

    def test_regenerate_replaces(self, db: Session, week: None) -> None:
        first = reports.generate_daily(db, DAY, None)
        expenses.create_expense(db, ExpenseCreate(amount="50", expense_date=DAY))
        second = reports.generate_daily(db, DAY, None)
        assert "Rs. 29,500" in second.content and first.content != second.content

    def test_narrative_uses_model_output(self, db: Session, week: None) -> None:
        llm = FakeLLM(say("A busy, good Wednesday with Maya."))
        report = reports.generate_daily(db, DAY, llm)
        assert "A busy, good Wednesday with Maya." in report.content
        # The model only sees computed data, never the private entry.
        assert "Secret" not in str(llm.requests[0])

    def test_monthly_sentence_and_themes(self, db: Session, week: None) -> None:
        llm = FakeLLM(say("A September of coffee and exams.\n- Studying for exams\n- Cafés"))
        report = reports.generate_monthly(db, 2026, 9, llm)
        assert "**The month in one sentence:** A September of coffee and exams." in report.content
        assert "## Recurring themes\n- Studying for exams\n- Cafés" in report.content
        assert "Maya (1)" in report.content
        assert "Secret" not in str(llm.requests[0])

    def test_monthly_without_model(self, db: Session, week: None) -> None:
        report = reports.generate_monthly(db, 2026, 9, None)
        assert "one sentence" not in report.content
        assert "## Money" in report.content


class TestApi:
    def test_events_and_timeline(self, api: TestClient) -> None:
        res = api.post(
            "/api/events",
            json={
                "title": "Passed driving test",
                "event_date": "2026-09-01",
                "importance_score": 4,
            },
        )
        assert res.status_code == 201
        items = api.get("/api/timeline", params={"date_from": "2026-09-01"}).json()
        assert items[0]["title"] == "Passed driving test"

    def test_report_endpoints_without_model(self, api: TestClient, monkeypatch) -> None:
        monkeypatch.setattr(get_settings(), "ollama_model", None)
        assert api.get("/api/reports/daily", params={"date": "2026-09-16"}).status_code == 404
        res = api.post("/api/reports/daily", json={"date": "2026-09-16"})
        assert res.status_code == 200 and res.json()["kind"] == "daily"
        assert api.get("/api/reports/daily", params={"date": "2026-09-16"}).status_code == 200
        weekly = api.post("/api/reports/weekly", json={"date": "2026-09-17"}).json()
        assert weekly["period_start"] == "2026-09-14"
        monthly = api.post("/api/reports/monthly", json={"year": 2026, "month": 9}).json()
        assert monthly["period_end"] == "2026-09-30"

    def test_report_uses_model_when_available(self, api: TestClient) -> None:
        api.post("/api/expenses", json={"amount": "100", "expense_date": "2026-09-16"})
        app.dependency_overrides[optional_llm] = lambda: FakeLLM(say("Quiet day."))
        res = api.post("/api/reports/daily", json={"date": "2026-09-16"})
        assert "Quiet day." in res.json()["content"]


class TestTools:
    def test_recap_tool(self, db: Session, week: None) -> None:
        from app.agent.loop import run_agent

        llm = FakeLLM(
            tools(call("generate_daily_recap", date=DAY.isoformat())),
            say("Narrative for the report."),  # consumed by the report's narrative call
            say("Here's your Wednesday."),
        )
        conversation = get_or_create_conversation(db, None, "recap")
        result = run_agent(db, conversation, "Recap Wednesday the 16th", llm)
        payload = tool_results(llm.requests[2], "generate_daily_recap")[0]
        assert "Rs. 29,450" in payload["content"]
        assert "Narrative for the report." in payload["content"]
        assert result.reply == "Here's your Wednesday."

    def test_life_event_tool_links_journal(self, db: Session) -> None:
        from app.agent.loop import run_agent
        from app.models import LifeEvent

        llm = FakeLLM(
            tools(
                call("create_journal_entry"), call("create_life_event", title="Barista with Maya")
            ),
            say("Logged."),
        )
        conversation = get_or_create_conversation(db, None, "x")
        run_agent(db, conversation, "Went to Barista with Maya", llm)
        event = db.query(LifeEvent).one()
        assert event.journal_entry_id is not None
        assert event.importance_score == 2
