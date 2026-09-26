"""Dashboard data and cross-domain comparisons."""

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.schemas.caffeine import CaffeineLogCreate
from app.schemas.expense import ExpenseCreate
from app.schemas.journal import JournalEntryCreate
from app.schemas.mood import MoodLogCreate
from app.schemas.people import InteractionCreate, MusicCreate, PersonCreate
from app.schemas.sleep import SleepLogCreate
from app.services import analytics, caffeine, expenses, journal, moods, people, sleep
from app.services.conversations import get_or_create_conversation
from tests.fake_llm import FakeLLM, call, say, tool_results, tools

TZ = get_settings().tz
START = date(2026, 8, 3)  # a Monday
END = START + timedelta(days=27)  # four full weeks


@pytest.fixture
def month(db: Session) -> None:
    """Four weeks: out with Maya every Friday and Saturday (spending more), more sleep
    in weeks 1 and 3 (with better mood), caffeine at 09:00 daily."""
    maya = people.create_person(db, PersonCreate(name="Maya Perera"))
    for offset in range(28):
        day = START + timedelta(days=offset)
        week = offset // 7
        out = day.weekday() in (4, 5)
        journal.create_journal_entry(
            db, JournalEntryCreate(raw_text=f"Day {offset}", entry_date=day)
        )
        expenses.create_expense(
            db, ExpenseCreate(amount="3000" if out else "500", expense_date=day, category="Food")
        )
        if out:
            people.create_interaction(
                db, InteractionCreate(person_id=maya.id, summary="Dinner", interaction_date=day)
            )
        sleep.create_sleep_log(
            db, SleepLogCreate(sleep_date=day, duration_minutes=480 if week in (0, 2) else 360)
        )
        moods.create_mood_log(db, MoodLogCreate(date=day, score=8 if week in (0, 2) else 5))
        caffeine.create_caffeine_log(
            db,
            CaffeineLogCreate(
                drink_type="latte", consumed_at=datetime(day.year, day.month, day.day, 9, tzinfo=TZ)
            ),
        )
    # A private day must not count.
    secret = journal.create_journal_entry(
        db, JournalEntryCreate(raw_text="secret", entry_date=START, is_private=True)
    )
    expenses.create_expense(
        db, ExpenseCreate(amount="100000", expense_date=START, journal_entry_id=secret.id)
    )


def _group(result: dict, index: int) -> dict:
    return result["groups"][index]


class TestCompare:
    def test_spending_on_days_out(self, db: Session, month: None) -> None:
        result = analytics.analyze(
            db, metric="spending", group_by="went_out", date_from=START, date_to=END
        )
        out, stayed = result["groups"]
        assert (out["days"], out["average"]) == (8, "3000.00")
        assert (stayed["days"], stayed["average"]) == (20, "500.00")  # private excluded
        assert result["enough_data"] is True
        assert "not what caused" in result["caveat"]

    def test_saw_person_matches_first_name(self, db: Session, month: None) -> None:
        result = analytics.analyze(
            db,
            metric="spending",
            group_by="saw_person",
            person_name="maya",
            date_from=START,
            date_to=END,
        )
        assert _group(result, 0)["days"] == 8
        assert _group(result, 0)["group"] == "saw maya"

    def test_mood_in_weeks_with_more_sleep(self, db: Session, month: None) -> None:
        result = analytics.analyze(
            db,
            metric="mood",
            group_by="more_sleep",
            granularity="week",
            date_from=START,
            date_to=END,
        )
        more, less = result["groups"]
        assert (more["weeks"], more["average"]) == (2, 8.0)
        assert (less["weeks"], less["average"]) == (2, 5.0)
        assert result["enough_data"] is False  # only two weeks each
        assert "anecdotal" in result["note"]

    def test_weekend(self, db: Session, month: None) -> None:
        result = analytics.analyze(
            db, metric="caffeine_drinks", group_by="weekend", date_from=START, date_to=END
        )
        assert [g["days"] for g in result["groups"]] == [8, 20]

    def test_validation(self, db: Session) -> None:
        from app.core.errors import DomainError

        with pytest.raises(DomainError):
            analytics.analyze(db, metric="mood", group_by="saw_person")
        with pytest.raises(DomainError):
            analytics.analyze(db, metric="mood", group_by="weekend", granularity="week")

    def test_no_data(self, db: Session) -> None:
        result = analytics.analyze(db, metric="mood", group_by="went_out")
        assert [g["average"] for g in result["groups"]] == [None, None]
        assert result["enough_data"] is False


class TestPositiveSongs:
    def test_emotion_or_good_mood_day(self, db: Session) -> None:
        good_day, bad_day = date(2026, 9, 1), date(2026, 9, 2)
        moods.create_mood_log(db, MoodLogCreate(date=good_day, score=9))
        moods.create_mood_log(db, MoodLogCreate(date=bad_day, score=3))
        for song, day, emotion in [
            ("Yellow", good_day, None),
            ("Yellow", bad_day, "happy"),
            ("Clocks", bad_day, "sad"),
        ]:
            people.create_music(db, MusicCreate(song=song, memory_date=day, emotion=emotion))
        result = analytics.songs_in_positive_memories(db)
        assert result["songs"] == [{"song": "Yellow", "artist": None, "count": 2}]
        assert result["positive_music_memories"] == 2


class TestDashboard:
    def test_shape_and_privacy(self, db: Session, month: None) -> None:
        data = analytics.dashboard(db, today=END, days=28)
        assert len(data["mood"]["daily"]) == 28
        assert data["sleep"]["average_minutes"] == 420.0
        assert data["caffeine"]["by_hour"][9]["drinks"] == 28
        assert data["spending"]["month_total"] == "34000.00"  # August, private excluded
        assert data["people"]["counts"] == [{"name": "Maya Perera", "count": 8}]
        assert "100000" not in str(data)

    def test_api(self, api: TestClient) -> None:
        assert api.get("/api/analytics/dashboard").status_code == 200
        res = api.get("/api/analytics/compare", params={"metric": "mood", "group_by": "weekend"})
        assert res.status_code == 200 and len(res.json()["groups"]) == 2
        assert (
            api.get(
                "/api/analytics/compare", params={"metric": "x", "group_by": "weekend"}
            ).status_code
            == 422
        )
        assert api.get("/api/analytics/positive-songs").status_code == 200


def test_compare_tool(db: Session, month: None) -> None:
    from app.agent.loop import run_agent

    llm = FakeLLM(
        tools(
            call(
                "compare_life",
                metric="spending",
                group_by="went_out",
                date_from=START.isoformat(),
                date_to=END.isoformat(),
            )
        ),
        say("About Rs. 3,000 on days out vs Rs. 500 otherwise."),
    )
    conversation = get_or_create_conversation(db, None, "q")
    run_agent(db, conversation, "How much do I usually spend on days I go out?", llm)
    result = tool_results(llm.requests[1], "compare_life")[0]
    assert result["groups"][0]["average"] == "3000.00"
