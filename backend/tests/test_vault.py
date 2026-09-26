"""Private vault: isolation everywhere, explicit-only agent access, clean chat history."""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.loop import run_agent
from app.models import ChatMessage, JournalEntry
from app.schemas.expense import ExpenseCreate
from app.schemas.journal import JournalEntryCreate
from app.schemas.people import InteractionCreate, PersonCreate
from app.services import expenses, journal, memories, people, timeline
from app.services.conversations import get_or_create_conversation, recent_history
from app.vault import service as vault
from tests.fake_llm import FakeLLM, call, say, tool_results, tools

DAY = date(2026, 9, 20)


@pytest.fixture
def secret(db: Session) -> JournalEntry:
    """A private entry with an expense and an interaction linked to it."""
    entry = journal.create_journal_entry(
        db,
        JournalEntryCreate(
            raw_text="Bought Sarah a surprise gift",
            entry_date=DAY,
            is_private=True,
            importance_score=5,
        ),
    )
    expenses.create_expense(
        db, ExpenseCreate(amount="7500", expense_date=DAY, journal_entry_id=entry.id)
    )
    sarah = people.create_person(db, PersonCreate(name="Sarah"))
    people.create_interaction(
        db,
        InteractionCreate(
            person_id=sarah.id,
            summary="Gave her the gift",
            interaction_date=DAY,
            journal_entry_id=entry.id,
        ),
    )
    journal.create_journal_entry(
        db, JournalEntryCreate(raw_text="Lunch with Sarah", entry_date=DAY)
    )
    return entry


class TestIsolation:
    def test_hidden_from_every_normal_path(self, db: Session, secret: JournalEntry) -> None:
        assert [e.raw_text for e in journal.list_journal_entries(db)] == ["Lunch with Sarah"]
        assert expenses.list_expenses(db) == []
        assert expenses.summarize_expenses(db).total == 0
        assert people.list_interactions(db) == []
        assert people.list_people(db)[0].interaction_count == 0
        found = memories.search_memories(db, "Sarah gift").results
        assert all("gift" not in r.content for r in found)
        assert all(
            "gift" not in (i.detail or "") for i in timeline.get_timeline(db, min_importance=0)
        )

    def test_vault_sees_only_private(self, db: Session, secret: JournalEntry) -> None:
        assert [e.raw_text for e in vault.list_entries(db)] == ["Bought Sarah a surprise gift"]
        results = vault.search(db, "gift").results
        assert results and all(r.is_private for r in results)
        assert vault.linked_counts(db, secret.id) == {"expenses": 1, "interactions": 1}

    def test_move_out_and_back(self, db: Session, secret: JournalEntry) -> None:
        vault.set_entry_private(db, secret.id, False)
        assert len(expenses.list_expenses(db)) == 1
        assert any("gift" in r.content for r in memories.search_memories(db, "gift").results)
        vault.set_entry_private(db, secret.id, True)
        assert expenses.list_expenses(db) == []
        assert vault.search(db, "gift").results


class TestApi:
    def test_journal_api_cannot_read_private(
        self, api: TestClient, db: Session, secret: JournalEntry
    ) -> None:
        assert api.get(f"/api/journal/{secret.id}").status_code == 404
        assert api.get("/api/expenses").json() == []
        assert api.get(f"/api/vault/entries/{secret.id}").json()["linked"] == {
            "expenses": 1,
            "interactions": 1,
        }

    def test_vault_routes(self, api: TestClient) -> None:
        entry = api.post("/api/journal", json={"raw_text": "Something personal"}).json()
        assert api.put(f"/api/vault/entries/{entry['id']}").json()["is_private"] is True
        assert api.get("/api/journal").json() == []
        assert api.get("/api/vault/search", params={"q": "personal"}).json()["results"]
        assert api.get("/api/vault").json() == {"entries": 1, "memories": 1}
        api.delete(f"/api/vault/entries/{entry['id']}")
        assert len(api.get("/api/journal").json()) == 1
        # Public entries are not served by the vault.
        assert api.get(f"/api/vault/entries/{entry['id']}").status_code == 404


def _run(db: Session, message: str, llm, conversation=None):
    conversation = conversation or get_or_create_conversation(db, None, message)
    return run_agent(db, conversation, message, llm), conversation


class TestAgent:
    def test_normal_question_uses_normal_search(self, db: Session, secret: JournalEntry) -> None:
        llm = FakeLLM(tools(call("search_memories", query="Sarah")), say("Lunch with Sarah."))
        _run(db, "Show me memories about Sarah.", llm)
        found = tool_results(llm.requests[1], "search_memories")[0]
        assert all("gift" not in r["content"] for r in found["results"])

    def test_vault_tool_refused_without_explicit_request(
        self, db: Session, secret: JournalEntry
    ) -> None:
        llm = FakeLLM(tools(call("search_private_memories", query="Sarah")), say("..."))
        _, conversation = _run(db, "Show me memories about Sarah.", llm)
        result = tool_results(llm.requests[1], "search_private_memories")[0]
        assert result["ok"] is False and "explicitly" in result["error"]
        assert "gift" not in str(llm.requests[1])
        # Nothing private was read, so the turn stays in normal history.
        assert recent_history(db, conversation.id, 10)

    def test_explicit_request_allowed_and_kept_out_of_history(
        self, db: Session, secret: JournalEntry
    ) -> None:
        llm = FakeLLM(
            tools(call("search_private_memories", query="Sarah")),
            say("You bought Sarah a surprise gift."),
        )
        _, conversation = _run(db, "Search my private memories about Sarah.", llm)
        result = tool_results(llm.requests[1], "search_private_memories")[0]
        assert "gift" in result["results"][0]["content"]
        assert recent_history(db, conversation.id, 30) == []

        # The next, unrelated turn does not carry the private answer to the model.
        follow_up = FakeLLM(say("Sure."))
        _run(db, "What's the weather like for journaling?", follow_up, conversation)
        assert "gift" not in str(follow_up.requests[0])

    def test_put_that_in_the_vault(self, db: Session) -> None:
        first = FakeLLM(
            tools(call("create_journal_entry"), call("create_expense", amount=5000)), say("Logged.")
        )
        _, conversation = _run(db, "Spent 5000 on a present for Maya", first)

        def move(messages):
            entry = tool_results(messages, "create_journal_entry")[0]["record"]
            return tools(call("move_to_vault", journal_entry_id=entry["id"]))

        _run(db, "Put that in the private vault.", FakeLLM(move, say("Done.")), conversation)
        assert expenses.list_expenses(db) == []
        # The original message and this turn are no longer sent to the model.
        history = recent_history(db, conversation.id, 50)
        assert all("present" not in m["content"] for m in history)

    def test_vault_turns_marked_private(self, db: Session, secret: JournalEntry) -> None:
        llm = FakeLLM(tools(call("list_vault_entries")), say("One private entry."))
        _, conversation = _run(db, "What's in my vault?", llm)
        flags = db.scalars(
            select(ChatMessage.is_private).where(ChatMessage.conversation_id == conversation.id)
        ).all()
        assert flags and all(flags)
