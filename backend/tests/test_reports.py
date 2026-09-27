"""Life events, timeline and recaps/reports."""

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.routes.reports import optional_llm
from app.core.config import get_settings
from app.core.time import today_local
from app.main import app
from app.models.report import DailyRecap
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
    def test_one_card_per_day_with_notable_items_only(self, db: Session, week: None) -> None:
        (day,) = timeline.get_timeline(db, date_from=DAY, date_to=DAY)
        assert day.date == DAY
        assert {m.line for m in day.moments} == {
            "Big exam passed!",
            "Barista with Maya",
            "No second keyboard",
            "With Maya at Barista",
            "Keyboard shop: Rs. 28,000",
        }
        text = day.model_dump_json()
        assert "Had a coffee" not in text  # routine journal entry
        assert "1,450" not in text  # not a major purchase
        assert "Secret" not in text and "99,999" not in text

    def test_headline_importance_summary_and_tags(self, db: Session, week: None) -> None:
        (day,) = timeline.get_timeline(db, date_from=DAY, date_to=DAY)
        # The journal entry is the most important item (4), so it names the day.
        assert (day.headline, day.headline_kind, day.importance_score) == (
            "Big exam passed!",
            "journal",
            4,
        )
        assert day.summary == (
            "With Maya at Barista. Barista with Maya; Decided: No second keyboard. "
            "Spent Rs. 28,000 (Keyboard shop)."
        )
        assert day.summary_source == "records"
        assert [(t.kind, t.label) for t in day.tags] == [
            ("person", "Maya"),
            ("place", "Barista"),
            ("amount", "Rs. 28,000 (Keyboard shop)"),
        ]
        assert day.moments[0].line == "Big exam passed!"  # most important moment first

    def test_min_importance(self, db: Session, week: None) -> None:
        (day,) = timeline.get_timeline(db, date_from=DAY, date_to=DAY, min_importance=4)
        # Major purchases are not filtered by importance, as before.
        assert [m.line for m in day.moments] == ["Big exam passed!", "Keyboard shop: Rs. 28,000"]
        assert [t.kind for t in day.tags] == ["amount"]

    def test_days_newest_first_and_limit_counts_days(self, db: Session) -> None:
        for offset in range(3):
            life_events.create_life_event(
                db,
                LifeEventCreate(title=f"Event {offset}", event_date=DAY + timedelta(days=offset)),
            )
        days = timeline.get_timeline(db, limit=2)
        assert [d.date for d in days] == [DAY + timedelta(days=2), DAY + timedelta(days=1)]

    def test_headline_prefers_event_then_decision_on_equal_importance(self, db: Session) -> None:
        maya = people.create_person(db, PersonCreate(name="Maya"))
        people.create_interaction(
            db, InteractionCreate(person_id=maya.id, summary="Lunch", interaction_date=DAY)
        )
        planning.create_decision(
            db, DecisionCreate(title="Start running", decision="Run", decision_date=DAY)
        )
        (day,) = timeline.get_timeline(db)
        assert (day.headline, day.headline_kind) == ("Start running", "decision")

        life_events.create_life_event(db, LifeEventCreate(title="Open day", event_date=DAY))
        (day,) = timeline.get_timeline(db)
        assert (day.headline, day.headline_kind) == ("Open day", "event")
        assert day.summary == "With Maya. Also: Decided: Start running."

        # A more important record wins over the kind preference.
        people.create_interaction(
            db,
            InteractionCreate(
                person_id=maya.id, summary="Long talk", interaction_date=DAY, importance_score=4
            ),
        )
        (day,) = timeline.get_timeline(db)
        assert (day.headline, day.importance_score) == ("With Maya", 4)

    def test_one_message_is_one_moment(self, db: Session) -> None:
        text = "Went to open day duties with Chamodi, walked the exhibition under one umbrella"
        entry = journal.create_journal_entry(
            db, JournalEntryCreate(raw_text=text, entry_date=DAY, importance_score=3)
        )
        chamodi = people.create_person(db, PersonCreate(name="Chamodi"))
        people.create_interaction(
            db,
            InteractionCreate(
                person_id=chamodi.id,
                summary="Open day duties together",
                interaction_date=DAY,
                location="Exhibition",
                journal_entry_id=entry.id,
            ),
        )
        life_events.create_life_event(
            db, LifeEventCreate(title="Open day duties", event_date=DAY, journal_entry_id=entry.id)
        )
        (day,) = timeline.get_timeline(db)
        (moment,) = day.moments
        assert moment.journal_entry_id == entry.id
        assert moment.kinds == ["event", "interaction", "journal"]
        assert moment.line == "Open day duties, with Chamodi"
        assert moment.text == text
        assert moment.importance_score == 3
        assert day.headline == "Open day duties"
        assert day.summary == "With Chamodi at Exhibition."
        assert [t.label for t in day.tags] == ["Chamodi", "Exhibition"]

    def test_stored_recap_narrative_replaces_summary(self, db: Session, week: None) -> None:
        reports.generate_daily(db, DAY, None)  # no model, so no narrative
        (day,) = timeline.get_timeline(db, date_from=DAY, date_to=DAY)
        assert day.summary_source == "records"

        reports.generate_daily(db, DAY, FakeLLM(say("A busy, good Wednesday with Maya.")))
        (day,) = timeline.get_timeline(db, date_from=DAY, date_to=DAY)
        assert (day.summary, day.summary_source) == ("A busy, good Wednesday with Maya.", "recap")

    def test_narrative_from_recaps_stored_before_it_was_kept_in_data(self, db: Session) -> None:
        life_events.create_life_event(db, LifeEventCreate(title="Open day", event_date=DAY))
        content = "# Wednesday, 16 September 2026\n\nA rainy open day.\n\n## Money\n- Spent Rs. 5\n"
        db.add(DailyRecap(date=DAY, content=content, data={}))
        db.commit()
        (day,) = timeline.get_timeline(db)
        assert day.summary == "A rainy open day."

    def test_vault_moments_never_appear(self, db: Session) -> None:
        secret = journal.create_journal_entry(
            db,
            JournalEntryCreate(
                raw_text="Secret date with Sam", entry_date=DAY, is_private=True, importance_score=5
            ),
        )
        sam = people.create_person(db, PersonCreate(name="Sam"))
        people.create_interaction(
            db,
            InteractionCreate(
                person_id=sam.id, summary="Date", interaction_date=DAY, journal_entry_id=secret.id
            ),
        )
        assert timeline.get_timeline(db, min_importance=0) == []


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
        days = api.get("/api/timeline", params={"date_from": "2026-09-01"}).json()
        assert days[0]["headline"] == "Passed driving test"
        assert days[0]["moments"][0]["kinds"] == ["event"]

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
