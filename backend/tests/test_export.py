"""Data export: contents, formats and vault separation."""

import csv
import io
import json
import zipfile
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.exports import service
from app.schemas.expense import ExpenseCreate
from app.schemas.journal import JournalEntryCreate
from app.schemas.mood import MoodLogCreate
from app.schemas.people import PersonCreate
from app.services import expenses, journal, moods, people

DAY = date(2026, 9, 26)


@pytest.fixture
def data(db: Session) -> None:
    entry = journal.create_journal_entry(
        db, JournalEntryCreate(raw_text="Today was good.", entry_date=DAY, importance_score=4)
    )
    moods.create_mood_log(db, MoodLogCreate(date=DAY, label="good", journal_entry_id=entry.id))
    expenses.create_expense(
        db,
        ExpenseCreate(
            amount="1450.50", merchant="Barista", expense_date=DAY, journal_entry_id=entry.id
        ),
    )
    journal.create_journal_entry(db, JournalEntryCreate(raw_text="Second entry.", entry_date=DAY))
    people.create_person(db, PersonCreate(name="Maya"))
    secret = journal.create_journal_entry(
        db, JournalEntryCreate(raw_text="Private thoughts", entry_date=DAY, is_private=True)
    )
    expenses.create_expense(
        db, ExpenseCreate(amount="9999", expense_date=DAY, journal_entry_id=secret.id)
    )


def _zip(content: bytes) -> dict[str, str]:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        return {name: archive.read(name).decode("utf-8") for name in archive.namelist()}


def test_zip_layout_and_journal_markdown(db: Session, data: None) -> None:
    files = _zip(service.build_zip(db))
    expected = {
        "README.txt",
        "journal/2026-09-26.md",
        "expenses.csv",
        "moods.csv",
        "sleep.csv",
        "caffeine.csv",
        "people.csv",
        "interactions.csv",
        "music_memories.csv",
        "subscriptions.csv",
        "reminders.csv",
        "decisions.csv",
        "waiting_items.csv",
        "life_events.csv",
        "memories.json",
        "conversations.json",
    }
    assert set(files) == expected
    md = files["journal/2026-09-26.md"]
    assert md.startswith("# September 26, 2026\n\nToday was good.\n\nMood: Good\nImportance: 4")
    assert "---\n\nSecond entry." in md
    assert "Private thoughts" not in "".join(files.values())


def test_csv_is_exact_and_excludes_vault(db: Session, data: None) -> None:
    rows = list(csv.DictReader(io.StringIO(service.expenses_csv(db))))
    assert [r["amount"] for r in rows] == ["1450.50"]
    assert rows[0]["merchant"] == "Barista"
    assert "embedding" not in rows[0]


def test_memories_json_has_no_embeddings(db: Session, data: None) -> None:
    memories = json.loads(_zip(service.build_zip(db))["memories.json"])
    assert memories and all("embedding" not in m and "search_vector" not in m for m in memories)
    assert all(not m["is_private"] for m in memories)


def test_vault_export_is_separate(db: Session, data: None) -> None:
    files = _zip(service.build_zip(db, private=True))
    assert "VAULT" in files["README.txt"]
    assert "Private thoughts" in files["journal/2026-09-26.md"]
    assert "Today was good" not in "".join(files.values())
    assert [r["amount"] for r in csv.DictReader(io.StringIO(files["expenses.csv"]))] == ["9999.00"]
    assert "people.csv" not in files and "conversations.json" not in files


def test_full_json(db: Session, data: None) -> None:
    exported = service.full_json(db)
    assert exported["settings"]["currency"] == "LKR"
    assert [e["raw_text"] for e in exported["journal_entries"]] == [
        "Today was good.",
        "Second entry.",
    ]
    assert exported["expenses"][0]["amount"] == "1450.50"
    assert exported["people"][0]["name"] == "Maya"
    assert "Private" not in json.dumps(exported)


def test_endpoints(api: TestClient, data: None) -> None:
    res = api.get("/api/export/zip")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/zip"
    assert "attachment" in res.headers["content-disposition"]
    assert "journal/2026-09-26.md" in _zip(res.content)
    assert api.get("/api/export/vault.zip").status_code == 200
    assert api.get("/api/export/expenses.csv").text.startswith("id,amount,")
    assert api.get("/api/export/json").json()["app_version"]
    settings = api.get("/api/settings").json()
    assert settings["timezone"] == "Asia/Colombo"
    assert "database_url" not in settings and "password" not in json.dumps(settings).lower()


def test_delete_all_conversations(api: TestClient) -> None:
    assert api.delete("/api/chat/conversations").status_code == 204
    assert api.get("/api/chat/conversations").json() == []
