"""CRUD behaviour of the core life-logging endpoints against a real database."""

import uuid
from datetime import date

from fastapi.testclient import TestClient

from app.core.time import today_local


def _create(api: TestClient, path: str, body: dict) -> dict:
    res = api.post(path, json=body)
    assert res.status_code == 201, res.text
    return res.json()


class TestJournal:
    def test_crud_round_trip(self, api: TestClient) -> None:
        text = "Met Alex after uni.  Pretty good day overall."
        entry = _create(api, "/api/journal", {"raw_text": text, "importance_score": 3})
        assert entry["raw_text"] == text
        assert entry["entry_date"] == today_local().isoformat()

        updated = api.patch(f"/api/journal/{entry['id']}", json={"ai_summary": "Saw Alex"})
        assert updated.json()["raw_text"] == text
        assert updated.json()["ai_summary"] == "Saw Alex"

        assert api.delete(f"/api/journal/{entry['id']}").status_code == 204
        assert api.get(f"/api/journal/{entry['id']}").status_code == 404

    def test_private_entries_hidden_by_default(self, api: TestClient) -> None:
        _create(api, "/api/journal", {"raw_text": "public"})
        _create(api, "/api/journal", {"raw_text": "secret", "is_private": True})

        default = [e["raw_text"] for e in api.get("/api/journal").json()]
        assert default == ["public"]

        # The journal API has no way to read private entries; only /api/vault does.
        vault = api.get("/api/vault/entries").json()
        assert [e["raw_text"] for e in vault] == ["secret"]

    def test_text_search(self, api: TestClient) -> None:
        _create(api, "/api/journal", {"raw_text": "Coffee with Sarah"})
        _create(api, "/api/journal", {"raw_text": "Gym"})
        results = api.get("/api/journal", params={"q": "sarah"}).json()
        assert [e["raw_text"] for e in results] == ["Coffee with Sarah"]

    def test_deleting_journal_keeps_linked_records(self, api: TestClient) -> None:
        entry = _create(api, "/api/journal", {"raw_text": "Dinner"})
        expense = _create(api, "/api/expenses", {"amount": "850", "journal_entry_id": entry["id"]})
        api.delete(f"/api/journal/{entry['id']}")
        assert api.get(f"/api/expenses/{expense['id']}").json()["journal_entry_id"] is None


class TestExpenses:
    def test_defaults_and_exact_amount(self, api: TestClient) -> None:
        expense = _create(api, "/api/expenses", {"amount": "1450.00", "merchant": "Barista"})
        assert expense["amount"] == "1450.00"
        assert expense["currency"] == "LKR"
        assert expense["category"] == "Other"
        assert expense["expense_date"] == today_local().isoformat()

    def test_correction_updates_amount(self, api: TestClient) -> None:
        expense = _create(api, "/api/expenses", {"amount": "1450", "category": "cafe"})
        res = api.patch(f"/api/expenses/{expense['id']}", json={"amount": "1550"})
        assert res.json()["amount"] == "1550.00"
        assert res.json()["category"] == "Cafe"

    def test_unmarking_impulse_clears_reason(self, api: TestClient) -> None:
        expense = _create(
            api, "/api/expenses", {"amount": "5000", "is_impulse": True, "impulse_reason": "sale"}
        )
        res = api.patch(f"/api/expenses/{expense['id']}", json={"is_impulse": False})
        assert res.json()["is_impulse"] is False
        assert res.json()["impulse_reason"] is None

    def test_filters(self, api: TestClient) -> None:
        _create(api, "/api/expenses", {"amount": "600", "category": "Transport"})
        _create(api, "/api/expenses", {"amount": "900", "category": "Cafe", "is_impulse": True})
        cafe = api.get("/api/expenses", params={"category": "cafe"}).json()
        assert [e["amount"] for e in cafe] == ["900.00"]
        impulse = api.get("/api/expenses", params={"is_impulse": True}).json()
        assert len(impulse) == 1

    def test_summary(self, api: TestClient) -> None:
        day = "2026-09-01"
        for amount, category, impulse in [
            ("100.10", "Cafe", False),
            ("200.20", "Cafe", True),
            ("0.70", "Food", False),
        ]:
            _create(
                api,
                "/api/expenses",
                {
                    "amount": amount,
                    "category": category,
                    "is_impulse": impulse,
                    "expense_date": day,
                },
            )
        _create(api, "/api/expenses", {"amount": "99", "currency": "USD", "expense_date": day})

        summary = api.get("/api/expenses/summary", params={"date_from": day, "date_to": day}).json()
        assert summary["currency"] == "LKR"
        assert summary["total"] == "301.00"
        assert summary["impulse_total"] == "200.20"
        assert summary["count"] == 3
        assert summary["by_category"][0] == {"category": "Cafe", "total": "300.30", "count": 2}

    def test_unknown_journal_reference_rejected(self, api: TestClient) -> None:
        res = api.post("/api/expenses", json={"amount": "1", "journal_entry_id": str(uuid.uuid4())})
        assert res.status_code == 422

    def test_categories_endpoint(self, api: TestClient) -> None:
        assert "Cafe" in api.get("/api/expenses/categories").json()


class TestMood:
    def test_create_and_correct(self, api: TestClient) -> None:
        mood = _create(api, "/api/moods", {"label": "good", "score": 7})
        assert mood["date"] == today_local().isoformat()
        res = api.patch(f"/api/moods/{mood['id']}", json={"energy_score": 4})
        assert res.json()["score"] == 7
        assert res.json()["energy_score"] == 4


class TestSleep:
    def test_duration_computed_from_times(self, api: TestClient) -> None:
        log = _create(
            api,
            "/api/sleep",
            {
                "sleep_time": "2026-09-26T02:00:00",
                "wake_time": "2026-09-26T07:00:00",
                "is_approximate": True,
            },
        )
        assert log["duration_minutes"] == 300
        assert log["sleep_date"] == "2026-09-26"
        assert log["sleep_time"].endswith("+05:30") or log["sleep_time"].endswith("Z")

    def test_duration_only(self, api: TestClient) -> None:
        log = _create(api, "/api/sleep", {"duration_minutes": 240, "is_approximate": True})
        assert log["sleep_time"] is None
        assert log["sleep_date"] == today_local().isoformat()

    def test_updating_time_recomputes_duration(self, api: TestClient) -> None:
        log = _create(
            api,
            "/api/sleep",
            {"sleep_time": "2026-09-26T02:00:00", "wake_time": "2026-09-26T07:00:00"},
        )
        res = api.patch(f"/api/sleep/{log['id']}", json={"wake_time": "2026-09-26T08:30:00"})
        assert res.json()["duration_minutes"] == 390

    def test_update_rejects_wake_before_sleep(self, api: TestClient) -> None:
        log = _create(
            api,
            "/api/sleep",
            {"sleep_time": "2026-09-26T02:00:00", "wake_time": "2026-09-26T07:00:00"},
        )
        res = api.patch(f"/api/sleep/{log['id']}", json={"wake_time": "2026-09-26T01:00:00"})
        assert res.status_code == 422


class TestCaffeine:
    def test_missing_time_is_flagged_approximate(self, api: TestClient) -> None:
        log = _create(api, "/api/caffeine", {"drink_type": "iced latte"})
        assert log["is_approximate"] is True
        assert log["estimated_caffeine_mg"] is None
        assert log["quantity"] == "1.00"

    def test_date_filter_uses_local_days(self, api: TestClient) -> None:
        # 00:30 in Colombo is still the previous day in UTC.
        _create(
            api,
            "/api/caffeine",
            {"drink_type": "tea", "consumed_at": "2026-09-26T00:30:00+05:30"},
        )
        day = date(2026, 9, 26).isoformat()
        logs = api.get("/api/caffeine", params={"date_from": day, "date_to": day}).json()
        assert len(logs) == 1
        prev = date(2026, 9, 25).isoformat()
        assert api.get("/api/caffeine", params={"date_from": prev, "date_to": prev}).json() == []


def test_unknown_id_returns_404(api: TestClient) -> None:
    for path in ("journal", "expenses", "moods", "sleep", "caffeine"):
        assert api.get(f"/api/{path}/{uuid.uuid4()}").status_code == 404
