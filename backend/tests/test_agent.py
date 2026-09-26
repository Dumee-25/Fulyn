"""Agent loop behaviour with a scripted model: tool dispatch, validation, provenance."""

import json
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.llm import _parse_arguments, get_llm
from app.agent.loop import STEP_LIMIT_REPLY, run_agent
from app.core.config import get_settings
from app.main import app
from app.models import Expense, JournalEntry, SleepLog
from app.services.conversations import get_or_create_conversation
from app.tools.catalog import build_registry
from tests.fake_llm import FakeLLM, LoopingLLM, call, say, tool_results, tools


def _run(db: Session, message: str, llm: Any, conversation=None):
    conversation = conversation or get_or_create_conversation(db, None, message)
    return run_agent(db, conversation, message, llm), conversation


def _all(db: Session, model: type) -> list[Any]:
    return list(db.scalars(select(model)))


class TestLogging:
    def test_single_expense_linked_to_verbatim_journal(self, db: Session) -> None:
        message = "Spent 500 on coffee."
        llm = FakeLLM(
            tools(
                call("create_journal_entry"),
                call("create_expense", amount=500, category="Cafe", description="coffee"),
            ),
            say("Logged Rs. 500 on coffee."),
        )
        result, _ = _run(db, message, llm)

        assert result.reply == "Logged Rs. 500 on coffee."
        assert [a.tool for a in result.actions] == ["create_journal_entry", "create_expense"]
        assert all(a.ok for a in result.actions)
        (entry,) = _all(db, JournalEntry)
        (expense,) = _all(db, Expense)
        assert entry.raw_text == message
        assert expense.amount == Decimal("500.00")
        assert expense.journal_entry_id == entry.id

    def test_multiple_records_from_one_message(self, db: Session) -> None:
        llm = FakeLLM(
            tools(
                call("create_expense", amount="500", category="cafe"),
                call("create_sleep_log", duration_minutes=300, is_approximate=True),
                call("create_journal_entry", importance_score=2),
            ),
            say("Logged both."),
        )
        _run(db, "Spent 500 on coffee and slept 5 hours.", llm)

        (entry,) = _all(db, JournalEntry)
        (expense,) = _all(db, Expense)
        (sleep,) = _all(db, SleepLog)
        # Records created before the journal entry are linked at the end of the turn.
        assert expense.journal_entry_id == entry.id
        assert sleep.journal_entry_id == entry.id
        assert sleep.duration_minutes == 300

    def test_journal_created_when_model_forgets(self, db: Session) -> None:
        message = "Paid 600 for Uber"
        llm = FakeLLM(tools(call("create_expense", amount=600, category="Transport")), say("Ok"))
        _run(db, message, llm)
        (entry,) = _all(db, JournalEntry)
        assert entry.raw_text == message
        assert _all(db, Expense)[0].journal_entry_id == entry.id

    def test_second_journal_call_does_not_duplicate(self, db: Session) -> None:
        llm = FakeLLM(
            tools(call("create_journal_entry"), call("create_journal_entry")), say("Saved")
        )
        _run(db, "A quiet day.", llm)
        assert len(_all(db, JournalEntry)) == 1

    def test_questions_create_nothing(self, db: Session) -> None:
        llm = FakeLLM(
            tools(
                call(
                    "search_journal_entries",
                    query="Sarah",
                    date_from="2024-01-01",
                    date_to="2024-12-31",
                )
            ),
            say("I couldn't find any record of that."),
        )
        result, _ = _run(db, "What happened with Sarah in 2024?", llm)
        assert _all(db, JournalEntry) == []
        assert tool_results(llm.requests[-1], "search_journal_entries")[0]["count"] == 0
        assert "couldn't find" in result.reply


class TestValidation:
    def test_model_cannot_supply_journal_text(self, db: Session) -> None:
        message = "Slept like shit last night."
        llm = FakeLLM(
            tools(call("create_journal_entry", raw_text="User slept poorly.")),
            tools(call("create_journal_entry")),
            say("Saved."),
        )
        result, _ = _run(db, message, llm)
        first = tool_results(llm.requests[1], "create_journal_entry")[0]
        assert first["ok"] is False and "raw_text" in first["error"]
        assert [a.ok for a in result.actions] == [False, True]
        assert _all(db, JournalEntry)[0].raw_text == message

    def test_invalid_arguments_are_returned_to_model(self, db: Session) -> None:
        llm = FakeLLM(tools(call("create_expense", amount=-5)), say("Sorry"))
        result, _ = _run(db, "spent -5", llm)
        error = tool_results(llm.requests[1], "create_expense")[0]["error"]
        assert error.startswith("invalid arguments") and "amount" in error
        assert _all(db, Expense) == []
        assert result.actions[0].error == error

    def test_unknown_tool(self, db: Session) -> None:
        llm = FakeLLM(tools(call("drop_database")), say("Can't do that."))
        result, _ = _run(db, "hi", llm)
        assert result.actions[0].ok is False
        assert "unknown tool" in result.actions[0].error

    def test_domain_error_keeps_transcript(self, db: Session) -> None:
        llm = FakeLLM(
            tools(
                call("update_expense", expense_id="00000000-0000-0000-0000-000000000000", amount=10)
            ),
            say("I couldn't find that expense."),
        )
        result, conversation = _run(db, "change it to 10", llm)
        assert result.actions[0].error == "Expense not found"
        from app.services.chat import transcript

        roles = [m.role for m in transcript(db, conversation.id)]
        assert roles == ["user", "assistant"]

    def test_iteration_limit(self, db: Session) -> None:
        llm = LoopingLLM()
        result, _ = _run(db, "loop", llm)
        assert result.reply == STEP_LIMIT_REPLY
        assert llm.calls == get_settings().agent_max_tool_iterations


class TestCorrections:
    def test_correction_uses_id_from_history(self, db: Session) -> None:
        first = FakeLLM(
            tools(
                call("create_journal_entry"),
                call("create_expense", amount=1450, merchant="Barista", category="Cafe"),
            ),
            say("Logged Rs. 1,450 at Barista."),
        )
        _, conversation = _run(db, "Went to Barista with Maya and spent 1450.", first)

        def correct(messages: list[dict[str, Any]]):
            # The previous turn's tool results must be in the context.
            expense = tool_results(messages, "create_expense")[0]["record"]
            return tools(call("update_expense", expense_id=expense["id"], amount="1550"))

        second = FakeLLM(correct, say("Updated to Rs. 1,550."))
        result, _ = _run(db, "Actually the Barista bill was 1550.", second, conversation)

        (expense,) = _all(db, Expense)
        assert expense.amount == Decimal("1550.00")
        assert result.actions[0].tool == "update_expense"
        # A correction is not a new journal entry.
        assert len(_all(db, JournalEntry)) == 1

    def test_make_it_a_core_memory(self, db: Session) -> None:
        first = FakeLLM(tools(call("create_journal_entry")), say("Saved."))
        _, conversation = _run(db, "Great evening at Barista with Maya.", first)

        def promote(messages: list[dict[str, Any]]):
            entry = tool_results(messages, "create_journal_entry")[0]["record"]
            return tools(
                call("update_journal_entry", journal_entry_id=entry["id"], importance_score=5)
            )

        _run(db, "Make that evening a core memory.", FakeLLM(promote, say("Done.")), conversation)
        assert _all(db, JournalEntry)[0].importance_score == 5


class TestTools:
    def test_private_journal_entries_not_searchable(self, db: Session) -> None:
        db.add(
            JournalEntry(raw_text="secret about Sarah", entry_date="2026-09-01", is_private=True)
        )
        db.add(JournalEntry(raw_text="coffee with Sarah", entry_date="2026-09-02"))
        db.commit()
        llm = FakeLLM(tools(call("search_journal_entries", query="Sarah")), say("Found one."))
        _run(db, "memories about Sarah", llm)
        found = tool_results(llm.requests[1], "search_journal_entries")[0]
        assert [r["raw_text"] for r in found["records"]] == ["coffee with Sarah"]

    def test_times_in_results_are_local(self, db: Session) -> None:
        llm = FakeLLM(
            tools(
                call(
                    "create_caffeine_log",
                    drink_type="iced latte",
                    consumed_at="2026-09-26T16:00:00",
                )
            ),
            say("Logged."),
        )
        _run(db, "iced latte at 4", llm)
        record = tool_results(llm.requests[1], "create_caffeine_log")[0]["record"]
        assert record["consumed_at"] == "2026-09-26T16:00+05:30"

    def test_schemas_are_model_friendly(self) -> None:
        schemas = {
            s["function"]["name"]: s["function"]["parameters"] for s in build_registry().schemas()
        }
        text = json.dumps(schemas)
        assert "$ref" not in text and '"title"' not in text and '"null"' not in text
        assert "raw_text" not in schemas["create_journal_entry"]["properties"]
        assert "journal_entry_id" not in schemas["create_expense"]["properties"]
        assert schemas["create_expense"]["required"] == ["amount"]

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [({"a": 1}, {"a": 1}), ('{"a": 1}', {"a": 1}), ("not json", {}), (None, {})],
    )
    def test_argument_parsing(self, raw: Any, expected: dict) -> None:
        assert _parse_arguments(raw) == expected


class TestChatApi:
    def test_chat_round_trip(self, api: TestClient) -> None:
        llm = FakeLLM(
            tools(call("create_journal_entry"), call("create_expense", amount=850)),
            say("Logged Rs. 850."),
        )
        app.dependency_overrides[get_llm] = lambda: llm
        res = api.post("/api/chat", json={"message": "Spent 850 on dinner."})
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["reply"] == "Logged Rs. 850."
        assert [a["tool"] for a in body["actions"]] == ["create_journal_entry", "create_expense"]

        messages = api.get(f"/api/chat/conversations/{body['conversation_id']}/messages").json()
        assert [m["role"] for m in messages] == ["user", "assistant"]
        assert len(messages[1]["actions"]) == 2
        assert api.get("/api/chat/conversations").json()[0]["id"] == body["conversation_id"]

    def test_unknown_conversation(self, api: TestClient) -> None:
        app.dependency_overrides[get_llm] = lambda: FakeLLM()
        res = api.post(
            "/api/chat",
            json={"message": "hi", "conversation_id": "00000000-0000-0000-0000-000000000000"},
        )
        assert res.status_code == 404

    def test_missing_model_config_is_503(self, api: TestClient, monkeypatch) -> None:
        monkeypatch.setattr(get_settings(), "ollama_model", None)
        res = api.post("/api/chat", json={"message": "hi"})
        assert res.status_code == 503
        assert "OLLAMA_MODEL" in res.json()["detail"]


class TestMemoryTools:
    def test_search_memories_tool(self, db: Session) -> None:
        from app.schemas.journal import JournalEntryCreate
        from app.services import journal

        journal.create_journal_entry(db, JournalEntryCreate(raw_text="Coffee with Sarah"))
        journal.create_journal_entry(db, JournalEntryCreate(raw_text="Gym session"))
        llm = FakeLLM(tools(call("search_memories", query="Sarah")), say("You had coffee."))
        _run(db, "Show me memories about Sarah.", llm)

        found = tool_results(llm.requests[1], "search_memories")[0]
        assert found["results"][0]["content"] == "Coffee with Sarah"
        assert found["results"][0]["keyword_match"] is True
        assert "is_private" not in found["results"][0]
        # A question is not a journal entry.
        assert len(_all(db, JournalEntry)) == 2

    def test_set_memory_importance_tool(self, db: Session) -> None:
        first = FakeLLM(tools(call("create_journal_entry")), say("Saved."))
        _, conversation = _run(db, "Evening at Barista with Maya.", first)

        def find(messages):
            return tools(call("search_memories", query="Barista Maya"))

        def promote(messages):
            memory = tool_results(messages, "search_memories")[0]["results"][0]
            return tools(call("set_memory_importance", memory_id=memory["id"], importance_score=5))

        _run(
            db,
            "Make that evening a core memory.",
            FakeLLM(find, promote, say("Done.")),
            conversation,
        )
        assert _all(db, JournalEntry)[0].importance_score == 5

    def test_listing_without_query(self, db: Session) -> None:
        from app.schemas.journal import JournalEntryCreate
        from app.services import journal

        journal.create_journal_entry(db, JournalEntryCreate(raw_text="Big day", importance_score=5))
        journal.create_journal_entry(db, JournalEntryCreate(raw_text="Normal day"))
        llm = FakeLLM(tools(call("search_memories", min_importance=5)), say("One."))
        _run(db, "What are my core memories?", llm)
        found = tool_results(llm.requests[1], "search_memories")[0]
        assert [r["content"] for r in found["results"]] == ["Big day"]
