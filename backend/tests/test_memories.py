"""Memory layer: sync from journal, hybrid search, importance, privacy, embedding failures."""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import JournalEntry, Memory
from app.schemas.journal import JournalEntryCreate, JournalEntryUpdate
from app.schemas.memory import MemoryUpdate
from app.services import journal, memories
from tests.fake_embeddings import FakeEmbeddings


def _entry(db: Session, text: str, **kw) -> JournalEntry:
    return journal.create_journal_entry(db, JournalEntryCreate(raw_text=text, **kw))


def _memory_for(db: Session, entry: JournalEntry) -> Memory:
    return db.scalar(select(Memory).where(Memory.source_id == entry.id))


class TestSync:
    def test_journal_entry_creates_embedded_memory(self, db: Session) -> None:
        entry = _entry(
            db,
            "Coffee with Sarah at the library.\nWe talked a lot.",
            importance_score=3,
            entry_date=date(2026, 9, 1),
        )
        memory = _memory_for(db, entry)
        assert memory.memory_type == "journal"
        assert memory.content == entry.raw_text
        assert memory.title == "Coffee with Sarah at the library."
        assert memory.memory_date == date(2026, 9, 1)
        assert memory.importance_score == 3
        assert memory.embedding is not None
        assert memory.embedding_model == "fake-embed"

    def test_update_syncs_and_reembeds_only_on_text_change(
        self, db: Session, fake_embeddings: FakeEmbeddings
    ) -> None:
        entry = _entry(db, "Gym")
        calls = fake_embeddings.calls
        journal.update_journal_entry(db, entry.id, JournalEntryUpdate(importance_score=4))
        assert _memory_for(db, entry).importance_score == 4
        assert fake_embeddings.calls == calls  # importance change: no re-embed

        journal.update_journal_entry(db, entry.id, JournalEntryUpdate(ai_summary="Leg day"))
        assert _memory_for(db, entry).title == "Leg day"
        assert fake_embeddings.calls == calls + 1

    def test_delete_removes_memory(self, db: Session) -> None:
        entry = _entry(db, "Gym")
        journal.delete_journal_entry(db, entry.id)
        assert db.scalars(select(Memory)).all() == []

    def test_embedding_outage_does_not_block_logging(
        self, db: Session, fake_embeddings: FakeEmbeddings
    ) -> None:
        fake_embeddings.available = False
        entry = _entry(db, "Rainy day, stayed in")
        memory = _memory_for(db, entry)
        assert memory.embedding is None

        fake_embeddings.available = True
        assert memories.backfill_embeddings(db) == 1
        db.refresh(memory)
        assert memory.embedding is not None

    def test_model_change_triggers_reembedding(
        self, db: Session, fake_embeddings: FakeEmbeddings
    ) -> None:
        _entry(db, "Gym")
        fake_embeddings.model = "another-model"
        assert memories.backfill_embeddings(db) == 1


class TestSearch:
    @pytest.fixture
    def seeded(self, db: Session) -> None:
        _entry(db, "Coffee with Sarah at the library, talked about her internship.")
        _entry(db, "Long lab session. Uber home because it was raining.")
        _entry(db, "Bought a mechanical keyboard on a whim.", importance_score=1)
        _entry(db, "Quiet day. Read for a while and cooked dinner.")

    def test_finds_by_name(self, db: Session, seeded: None) -> None:
        response = memories.search_memories(db, "memories about Sarah")
        top = response.results[0]
        assert "Sarah" in top.content
        assert top.keyword_match is True
        assert response.semantic is True

    def test_unrelated_query_has_no_keyword_matches(self, db: Session, seeded: None) -> None:
        response = memories.search_memories(db, "John")
        assert all(not r.keyword_match for r in response.results)

    def test_importance_breaks_ties(self, db: Session) -> None:
        _entry(db, "Dinner at home", importance_score=0)
        _entry(db, "Dinner at home", importance_score=5)
        results = memories.search_memories(db, "dinner").results
        assert [r.importance_score for r in results] == [5, 0]

    def test_filters(self, db: Session) -> None:
        _entry(db, "Dinner in August", entry_date=date(2026, 8, 10))
        _entry(db, "Dinner in September", entry_date=date(2026, 9, 10), importance_score=4)
        in_sept = memories.search_memories(
            db, "dinner", date_from=date(2026, 9, 1), date_to=date(2026, 9, 30)
        )
        assert [r.content for r in in_sept.results] == ["Dinner in September"]
        important = memories.search_memories(db, "dinner", min_importance=4)
        assert len(important.results) == 1

    def test_private_memories_excluded(self, db: Session) -> None:
        _entry(db, "Secret thoughts about Sarah", is_private=True)
        _entry(db, "Lunch with Sarah")
        results = memories.search_memories(db, "Sarah").results
        assert [r.content for r in results] == ["Lunch with Sarah"]
        assert memories.list_memories(db) and all(
            not m.is_private for m in memories.list_memories(db)
        )

    def test_keyword_only_when_embeddings_down(
        self, db: Session, seeded: None, fake_embeddings: FakeEmbeddings
    ) -> None:
        fake_embeddings.available = False
        response = memories.search_memories(db, "keyboard")
        assert response.semantic is False
        assert [r.keyword_match for r in response.results] == [True]
        assert response.results[0].similarity is None

    def test_no_results(self, db: Session) -> None:
        assert memories.search_memories(db, "anything").results == []


class TestImportance:
    def test_memory_importance_updates_journal(self, db: Session) -> None:
        entry = _entry(db, "Great evening at Barista with Maya")
        memory = _memory_for(db, entry)
        memories.set_memory_importance(db, memory.id, 5)
        db.refresh(entry)
        assert entry.importance_score == 5

    @pytest.mark.parametrize("score", [-1, 6])
    def test_out_of_range_rejected(self, score: int) -> None:
        with pytest.raises(ValidationError):
            MemoryUpdate(importance_score=score)


class TestApi:
    def test_search_and_update(self, api: TestClient) -> None:
        api.post("/api/journal", json={"raw_text": "Coffee with Sarah"})
        api.post("/api/journal", json={"raw_text": "Secret", "is_private": True})

        found = api.get("/api/memories/search", params={"q": "Sarah"}).json()
        assert found["results"][0]["content"] == "Coffee with Sarah"
        memory_id = found["results"][0]["id"]

        res = api.patch(f"/api/memories/{memory_id}", json={"importance_score": 5})
        assert res.json()["importance_score"] == 5
        core = api.get("/api/memories", params={"min_importance": 5}).json()
        assert [m["id"] for m in core] == [memory_id]

        assert all(m["content"] != "Secret" for m in api.get("/api/memories").json())

    def test_private_memory_hidden_by_id(self, api: TestClient, db: Session) -> None:
        api.post("/api/journal", json={"raw_text": "Secret", "is_private": True})
        memory = db.scalar(select(Memory))
        assert api.get(f"/api/memories/{memory.id}").status_code == 404
