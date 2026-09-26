from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app


def test_health_ok(client: TestClient) -> None:
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["app"] == "Fulyn"


def test_health_degraded_when_db_down(broken_db: MagicMock) -> None:
    app.dependency_overrides[get_db] = lambda: broken_db
    try:
        res = TestClient(app).get("/api/health")
    finally:
        app.dependency_overrides.clear()
    assert res.status_code == 200
    assert res.json()["status"] == "degraded"
    assert res.json()["database"] == "unavailable"


def test_liveness(client: TestClient) -> None:
    assert client.get("/api/health/live").json() == {"status": "ok"}
