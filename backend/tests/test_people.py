"""People, interactions and music: matching, dates, memory mirroring, API and tools."""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.loop import run_agent
from app.models import Memory, MusicMemory, Person, PersonInteraction
from app.schemas.journal import JournalEntryCreate, JournalEntryUpdate
from app.schemas.people import InteractionCreate, MusicCreate, PersonCreate, PersonUpdate
from app.services import journal, memories, people
from app.services.conversations import get_or_create_conversation
from tests.fake_llm import FakeLLM, call, say, tool_results, tools


def _person(db: Session, name: str, **kw) -> Person:
    return people.create_person(db, PersonCreate(name=name, **kw))


def _meet(db: Session, person: Person, day: date, summary: str = "Met up") -> PersonInteraction:
    return people.create_interaction(
        db, InteractionCreate(person_id=person.id, interaction_date=day, summary=summary)
    )


class TestMatching:
    def test_exact_nickname_and_first_name(self, db: Session) -> None:
        sarah = _person(db, "Sarah Perera", nickname="Saz")
        assert people.find_people(db, "sarah perera") == [sarah]
        assert people.find_people(db, "SAZ") == [sarah]
        assert people.find_people(db, "Sarah") == [sarah]
        assert people.find_people(db, "Sar") == []

    def test_exact_match_beats_first_name(self, db: Session) -> None:
        sarah = _person(db, "Sarah")
        _person(db, "Sarah Perera")
        assert people.find_people(db, "sarah") == [sarah]

    def test_ambiguous_names_raise(self, db: Session) -> None:
        _person(db, "Sarah Perera")
        _person(db, "Sarah Silva")
        with pytest.raises(people.AmbiguousPersonError, match="Ask which one"):
            people.resolve_person(db, "Sarah", create=True)

    def test_resolve_creates_when_missing(self, db: Session) -> None:
        person, created = people.resolve_person(db, "Maya", create=True)
        assert created and person.name == "Maya"
        again, created = people.resolve_person(db, "maya", create=True)
        assert again.id == person.id and not created


class TestInteractions:
    def test_person_dates_follow_interactions(self, db: Session) -> None:
        maya = _person(db, "Maya")
        _meet(db, maya, date(2026, 9, 10))
        latest = _meet(db, maya, date(2026, 9, 20))
        _meet(db, maya, date(2020, 1, 1))
        db.refresh(maya)
        assert maya.last_interaction_at == date(2026, 9, 20)
        assert maya.first_mentioned_at == date(2020, 1, 1)

        people.delete_interaction(db, latest.id)
        db.refresh(maya)
        assert maya.last_interaction_at == date(2026, 9, 10)

    def test_interaction_is_a_searchable_memory(self, db: Session) -> None:
        maya = _person(db, "Maya")
        interaction = _meet(db, maya, date(2026, 9, 26), "Went to Barista after uni")
        memory = db.scalar(select(Memory).where(Memory.source_id == interaction.id))
        assert memory.memory_type == "person_interaction"
        assert memory.title == "With Maya"
        results = memories.search_memories(db, "Maya").results
        assert results[0].source_id == interaction.id

    def test_renaming_person_updates_memories(self, db: Session) -> None:
        maya = _person(db, "Maya")
        interaction = _meet(db, maya, date(2026, 9, 26))
        people.update_person(db, maya.id, PersonUpdate(name="Maya Fernando"))
        memory = db.scalar(select(Memory).where(Memory.source_id == interaction.id))
        assert memory.title == "With Maya Fernando"

    def test_deleting_person_removes_interactions_and_memories(self, db: Session) -> None:
        maya = _person(db, "Maya")
        _meet(db, maya, date(2026, 9, 26))
        song = people.create_music(db, MusicCreate(song="Yellow", person_id=maya.id))
        people.delete_person(db, maya.id)
        assert db.scalars(select(PersonInteraction)).all() == []
        assert (
            db.scalars(select(Memory).where(Memory.memory_type == "person_interaction")).all() == []
        )
        db.refresh(song)
        assert song.person_id is None

    def test_private_journal_makes_interaction_memory_private(self, db: Session) -> None:
        entry = journal.create_journal_entry(db, JournalEntryCreate(raw_text="Saw Maya"))
        maya = _person(db, "Maya")
        people.create_interaction(
            db,
            InteractionCreate(person_id=maya.id, summary="Saw Maya", journal_entry_id=entry.id),
        )
        journal.update_journal_entry(db, entry.id, JournalEntryUpdate(is_private=True))
        assert memories.search_memories(db, "Maya").results == []

    def test_interaction_importance_syncs_from_memory(self, db: Session) -> None:
        interaction = _meet(db, _person(db, "Maya"), date(2026, 9, 26))
        memory = db.scalar(select(Memory).where(Memory.source_id == interaction.id))
        memories.set_memory_importance(db, memory.id, 5)
        db.refresh(interaction)
        assert interaction.importance_score == 5


class TestMusic:
    def test_music_memory_and_top_songs(self, db: Session) -> None:
        sarah = _person(db, "Sarah")
        for day in (1, 5):
            people.create_music(
                db,
                MusicCreate(
                    song="Yellow",
                    artist="Coldplay",
                    memory_date=date(2026, 9, day),
                    person_id=sarah.id,
                    emotion="nostalgic",
                ),
            )
        people.create_music(db, MusicCreate(song="Clocks", memory_date=date(2026, 9, 3)))
        top = people.top_songs(db, date_from=date(2026, 9, 1), date_to=date(2026, 9, 30))
        assert (top[0].song, top[0].count) == ("Yellow", 2)
        assert len(people.list_music(db, person_id=sarah.id)) == 2
        assert len(people.list_music(db, query="coldplay")) == 2
        music_memories = memories.search_memories(db, "Yellow", memory_type="music").results
        assert "Connected to Sarah" in music_memories[0].content


class TestApi:
    def test_people_flow(self, api: TestClient) -> None:
        person = api.post("/api/people", json={"name": "Maya", "relationship_type": "friend"})
        assert person.status_code == 201
        pid = person.json()["id"]
        res = api.post(
            "/api/interactions",
            json={"person_id": pid, "summary": "Coffee", "interaction_date": "2026-09-26"},
        )
        assert res.status_code == 201 and res.json()["person_name"] == "Maya"

        listed = api.get("/api/people").json()
        assert listed[0]["interaction_count"] == 1
        assert listed[0]["last_interaction_at"] == "2026-09-26"
        assert len(api.get("/api/interactions", params={"person_id": pid}).json()) == 1

    def test_rejects_unknown_relationship(self, api: TestClient) -> None:
        res = api.post("/api/people", json={"name": "X", "relationship_type": "enemy"})
        assert res.status_code == 422

    def test_music_endpoints(self, api: TestClient) -> None:
        api.post("/api/music", json={"song": "Yellow", "memory_date": "2026-09-02"})
        assert api.get("/api/music", params={"q": "yell"}).json()[0]["song"] == "Yellow"
        top = api.get("/api/music/top", params={"date_from": "2026-09-01"}).json()
        assert top == [{"song": "Yellow", "artist": None, "count": 1}]


def _run(db: Session, message: str, llm, conversation=None):
    conversation = conversation or get_or_create_conversation(db, None, message)
    return run_agent(db, conversation, message, llm), conversation


class TestTools:
    def test_interaction_creates_person_and_links_journal(self, db: Session) -> None:
        message = "Went to Barista with Maya after uni."
        llm = FakeLLM(
            tools(
                call("create_journal_entry"),
                call(
                    "create_person_interaction",
                    person_name="Maya",
                    summary="Went to Barista after uni",
                    location="Barista",
                ),
            ),
            say("Logged your time with Maya."),
        )
        _run(db, message, llm)
        result = tool_results(llm.requests[1], "create_person_interaction")[0]
        assert result["person_created"] is True
        interaction = db.scalar(select(PersonInteraction))
        assert interaction.raw_context == message
        assert interaction.journal_entry_id is not None

    def test_ambiguous_person_returns_error_to_model(self, db: Session) -> None:
        _person(db, "Sarah Perera")
        _person(db, "Sarah Silva")
        llm = FakeLLM(
            tools(call("create_person_interaction", person_name="Sarah", summary="Lunch")),
            say("Which Sarah do you mean?"),
        )
        result, _ = _run(db, "Lunch with Sarah", llm)
        error = tool_results(llm.requests[1], "create_person_interaction")[0]["error"]
        assert "Sarah Perera" in error and "Sarah Silva" in error
        assert db.scalars(select(PersonInteraction)).all() == []
        assert result.reply == "Which Sarah do you mean?"

    def test_last_seen_with_journal_text(self, db: Session) -> None:
        entry = journal.create_journal_entry(
            db, JournalEntryCreate(raw_text="Long talk with Alex about exams.")
        )
        alex = _person(db, "Alex")
        people.create_interaction(
            db,
            InteractionCreate(
                person_id=alex.id,
                summary="Talked about exams",
                interaction_date=date(2026, 9, 20),
                journal_entry_id=entry.id,
            ),
        )
        llm = FakeLLM(tools(call("get_person_interactions", person_name="alex")), say("..."))
        _run(db, "When did I last see Alex?", llm)
        found = tool_results(llm.requests[1], "get_person_interactions")[0]
        assert found["person"]["last_interaction_at"] == "2026-09-20"
        assert found["interactions"][0]["journal_text"] == "Long talk with Alex about exams."

    def test_unknown_person_query(self, db: Session) -> None:
        llm = FakeLLM(tools(call("get_person_interactions", person_name="John")), say("None."))
        _run(db, "When did I last see John?", llm)
        found = tool_results(llm.requests[1], "get_person_interactions")[0]
        assert found["count"] == 0 and "no person" in found["note"]
        assert db.scalars(select(Person)).all() == []

    def test_music_tool_with_person(self, db: Session) -> None:
        llm = FakeLLM(
            tools(
                call(
                    "create_music_memory",
                    song="Yellow",
                    artist="Coldplay",
                    person_name="Sarah",
                    memory_text="Played on the drive home",
                )
            ),
            tools(call("search_music_memories", person_name="Sarah")),
            say("Yellow by Coldplay."),
        )
        _run(db, "Yellow by Coldplay reminds me of the drive home with Sarah", llm)
        found = tool_results(llm.requests[2], "search_music_memories")[0]
        assert found["music"][0]["person_name"] == "Sarah"
        assert db.scalar(select(MusicMemory)).journal_entry_id is not None
