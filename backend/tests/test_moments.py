"""One memory per moment: records logged with a journal entry share its memory."""

import importlib.util
from datetime import date
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import JournalEntry, LifeEvent, Memory, PersonInteraction
from app.schemas.journal import JournalEntryCreate, JournalEntryUpdate
from app.schemas.people import InteractionCreate, InteractionUpdate, PersonCreate, PersonUpdate
from app.schemas.planning import DecisionCreate
from app.schemas.report import LifeEventCreate, LifeEventUpdate
from app.services import journal, life_events, memories, people, planning
from app.services.chat import handle_message
from app.vault import service as vault
from tests.fake_embeddings import FakeEmbeddings
from tests.fake_llm import FakeLLM, call, say, tools

DAY = date(2026, 9, 20)
MESSAGE = (
    "Went to open day duties with Chamodi, walked the exhibition under one umbrella "
    "and got soaked anyway"
)
MIGRATION = (
    Path(__file__).parents[1] / "alembic" / "versions" / "20260927_0010_one_memory_per_moment.py"
)


def _all_memories(db: Session) -> list[Memory]:
    return list(db.scalars(select(Memory)))


def _journal_memory(db: Session, entry: JournalEntry) -> Memory:
    return db.scalar(
        select(Memory).where(Memory.memory_type == "journal", Memory.source_id == entry.id)
    )


def _moment(db: Session, importance: int = 2) -> tuple[JournalEntry, PersonInteraction, LifeEvent]:
    """What one chat message creates: a journal entry, an interaction and a life event."""
    entry = journal.create_journal_entry(
        db, JournalEntryCreate(raw_text=MESSAGE, entry_date=DAY, importance_score=importance)
    )
    chamodi = people.create_person(db, PersonCreate(name="Chamodi"))
    interaction = people.create_interaction(
        db,
        InteractionCreate(
            person_id=chamodi.id,
            summary="Open day duties together",
            interaction_date=DAY,
            location="Exhibition hall",
            journal_entry_id=entry.id,
            importance_score=importance,
        ),
    )
    event = life_events.create_life_event(
        db,
        LifeEventCreate(
            title="Open day duties",
            event_date=DAY,
            journal_entry_id=entry.id,
            importance_score=importance,
        ),
    )
    return entry, interaction, event


def _scores(db: Session, *records: Any) -> set[int]:
    for record in records:
        db.refresh(record)
    return {r.importance_score for r in records}


class TestOneMemoryPerMoment:
    def test_message_with_journal_interaction_and_event_is_one_memory(self, db: Session) -> None:
        entry, _, _ = _moment(db)
        (memory,) = _all_memories(db)
        assert (memory.memory_type, memory.source_id) == ("journal", entry.id)
        assert memory.content == MESSAGE
        assert memory.tags.splitlines() == ["Chamodi", "Exhibition hall", "Open day duties"]
        assert memory.embedding is not None

    @pytest.mark.parametrize("query", ["Chamodi", "Open day duties", "exhibition hall"])
    def test_search_finds_the_moment_once(self, db: Session, query: str) -> None:
        entry, _, _ = _moment(db)
        results = memories.search_memories(db, query).results
        assert [r.source_id for r in results] == [entry.id]
        assert results[0].keyword_match
        assert "Chamodi" in results[0].tags

    def test_tags_reach_the_embedding(self, db: Session, fake_embeddings: FakeEmbeddings) -> None:
        entry, _, _ = _moment(db)
        memory = _journal_memory(db, entry)
        assert "Chamodi, Exhibition hall, Open day duties" in memories._embedding_text(memory)

    def test_agent_turn_yields_one_memory(self, db: Session) -> None:
        llm = FakeLLM(
            tools(
                call("create_journal_entry"),
                call(
                    "create_person_interaction",
                    person_name="Chamodi",
                    summary="Open day duties",
                    importance_score=3,
                ),
                call("create_life_event", title="Open day duties"),
            ),
            say("Logged it."),
        )
        handle_message(db, MESSAGE, None, llm)
        (memory,) = _all_memories(db)
        assert memory.memory_type == "journal"
        assert memory.importance_score == 3  # the moment takes its most important record
        assert "Chamodi" in memory.tags.splitlines()

    def test_records_linked_after_the_turn_fold_into_the_journal(self, db: Session) -> None:
        # The model forgot the journal entry: finalize_turn saves one and links the records.
        llm = FakeLLM(
            tools(
                call("create_person_interaction", person_name="Chamodi", summary="Open day"),
                call("create_life_event", title="Open day duties", importance_score=4),
            ),
            say("Logged it."),
        )
        handle_message(db, MESSAGE, None, llm)
        (memory,) = _all_memories(db)
        entry = db.scalar(select(JournalEntry))
        assert (memory.memory_type, memory.source_id) == ("journal", entry.id)
        assert memory.tags.splitlines() == ["Chamodi", "Open day duties"]
        assert memory.importance_score == entry.importance_score == 4
        assert {i.importance_score for i in db.scalars(select(PersonInteraction))} == {4}

    def test_manual_records_without_journal_keep_their_own_memory(self, db: Session) -> None:
        maya = people.create_person(db, PersonCreate(name="Maya"))
        interaction = people.create_interaction(
            db, InteractionCreate(person_id=maya.id, summary="Coffee", interaction_date=DAY)
        )
        event = life_events.create_life_event(db, LifeEventCreate(title="Graduation"))
        decision = planning.create_decision(
            db, DecisionCreate(title="Sell the bike", decision="Selling it")
        )
        found = {(m.memory_type, m.source_id) for m in _all_memories(db)}
        assert found == {
            ("person_interaction", interaction.id),
            ("event", event.id),
            ("decision", decision.id),
        }
        assert memories.search_memories(db, "Maya").results[0].source_id == interaction.id

    def test_record_changes_refresh_the_journal_memory(self, db: Session) -> None:
        entry, interaction, event = _moment(db)
        chamodi_id = interaction.person_id
        life_events.update_life_event(db, event.id, LifeEventUpdate(title="Open day 2026"))
        assert "Open day 2026" in _journal_memory(db, entry).tags.splitlines()

        people.update_person(db, chamodi_id, PersonUpdate(name="Chamodi Perera"))
        assert "Chamodi Perera" in _journal_memory(db, entry).tags.splitlines()

        life_events.delete_life_event(db, event.id)
        assert _journal_memory(db, entry).tags.splitlines() == [
            "Chamodi Perera",
            "Exhibition hall",
        ]
        assert len(_all_memories(db)) == 1

    def test_unlinking_or_relinking_moves_the_record(self, db: Session) -> None:
        entry, interaction, _ = _moment(db)
        other = journal.create_journal_entry(db, JournalEntryCreate(raw_text="Later that day"))

        people.update_interaction(db, interaction.id, InteractionUpdate(journal_entry_id=other.id))
        assert "Chamodi" not in _journal_memory(db, entry).tags.splitlines()
        assert _journal_memory(db, other).tags.splitlines() == ["Chamodi", "Exhibition hall"]

        people.update_interaction(db, interaction.id, InteractionUpdate(journal_entry_id=None))
        assert _journal_memory(db, other).tags is None
        own = db.scalar(select(Memory).where(Memory.source_id == interaction.id))
        assert own.memory_type == "person_interaction"

    def test_deleting_the_journal_gives_records_their_memory_back(self, db: Session) -> None:
        entry, interaction, event = _moment(db, importance=4)
        journal.delete_journal_entry(db, entry.id)
        found = {(m.memory_type, m.source_id, m.importance_score) for m in _all_memories(db)}
        assert found == {("person_interaction", interaction.id, 4), ("event", event.id, 4)}

    def test_privacy_follows_the_journal_entry(self, db: Session) -> None:
        entry, _, _ = _moment(db)
        vault.set_entry_private(db, entry.id, True)
        assert memories.search_memories(db, "Chamodi").results == []
        assert [r.source_id for r in vault.search(db, "Chamodi").results] == [entry.id]


class TestImportancePerMoment:
    def test_memory_importance_applies_to_every_record(self, db: Session) -> None:
        entry, interaction, event = _moment(db)
        memories.set_memory_importance(db, _journal_memory(db, entry).id, 5)
        assert _scores(db, entry, interaction, event) == {5}
        assert _journal_memory(db, entry).importance_score == 5

    def test_changing_a_linked_record_changes_the_moment(self, db: Session) -> None:
        entry, interaction, event = _moment(db)
        people.update_interaction(db, interaction.id, InteractionUpdate(importance_score=4))
        assert _scores(db, entry, interaction, event) == {4}
        assert _journal_memory(db, entry).importance_score == 4

        # Lowering works too: an explicit change sets the moment, it does not take the max.
        life_events.update_life_event(db, event.id, LifeEventUpdate(importance_score=1))
        assert _scores(db, entry, interaction, event) == {1}

    def test_changing_the_journal_entry_changes_the_moment(self, db: Session) -> None:
        entry, interaction, event = _moment(db)
        journal.update_journal_entry(db, entry.id, JournalEntryUpdate(importance_score=5))
        assert _scores(db, entry, interaction, event) == {5}

    def test_meh_command_applies_to_the_whole_moment(self, db: Session) -> None:
        llm = FakeLLM(
            tools(
                call("create_journal_entry", importance_score=4),
                call("create_person_interaction", person_name="Chamodi", summary="Open day"),
                call("create_life_event", title="Open day duties"),
            ),
            say("Logged it."),
        )
        first = handle_message(db, MESSAGE, None, llm)
        handle_message(db, "/meh", first.conversation_id, None)
        (memory,) = _all_memories(db)
        assert memory.importance_score == 1
        assert {e.importance_score for e in db.scalars(select(LifeEvent))} == {1}
        assert {i.importance_score for i in db.scalars(select(PersonInteraction))} == {1}

    def test_manual_record_importance_stays_its_own(self, db: Session) -> None:
        event = life_events.create_life_event(db, LifeEventCreate(title="Graduation"))
        memory = db.scalar(select(Memory).where(Memory.source_id == event.id))
        memories.set_memory_importance(db, memory.id, 5)
        db.refresh(event)
        assert event.importance_score == memory.importance_score == 5


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_0010", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestMigration:
    def test_folds_existing_record_memories_into_the_journal(self, db: Session) -> None:
        entry, interaction, event = _moment(db, importance=2)
        standalone = life_events.create_life_event(db, LifeEventCreate(title="Graduation"))
        # Recreate the state before the migration: every linked record had its own memory,
        # the event was more important than the entry, and the journal memory had no tags.
        conn = db.connection()
        conn.execute(
            text("UPDATE life_events SET importance_score = 4 WHERE id = :id"), {"id": event.id}
        )
        for memory_type, source_id in (
            ("person_interaction", interaction.id),
            ("event", event.id),
        ):
            db.add(
                Memory(
                    memory_type=memory_type,
                    source_id=source_id,
                    title="old",
                    content="old copy",
                    memory_date=DAY,
                    importance_score=2,
                )
            )
        journal_memory = _journal_memory(db, entry)
        journal_memory.tags = None
        db.commit()
        assert len(_all_memories(db)) == 4

        counts = _load_migration().fold_moments(db.connection())
        db.expire_all()

        assert counts == {
            "moments": 1,
            "entries_raised": 1,
            "records_aligned": 1,
            "memories_deleted": 2,
            "journal_memories_updated": 1,
        }
        found = {(m.memory_type, m.source_id) for m in _all_memories(db)}
        assert found == {("journal", entry.id), ("event", standalone.id)}
        memory = _journal_memory(db, entry)
        assert memory.tags.splitlines() == ["Chamodi", "Exhibition hall", "Open day duties"]
        assert memory.importance_score == 4
        assert memory.embedding is None  # re-embedded with the tags by the backfill
        assert _scores(db, entry, interaction, event) == {4}
        assert memories.backfill_embeddings(db) == 1
        results = memories.search_memories(db, "Chamodi").results
        assert [r.source_id for r in results if r.keyword_match] == [entry.id]

    def test_tags_match_the_service(self, db: Session) -> None:
        entry, _, _ = _moment(db)
        from_migration = _load_migration()._moment_tags(db.connection(), entry.id)
        assert from_migration == _journal_memory(db, entry).tags.splitlines()
