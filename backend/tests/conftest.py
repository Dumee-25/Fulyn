from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db.session import get_db
from app.main import app


@pytest.fixture
def fake_db() -> MagicMock:
    return MagicMock()


@pytest.fixture
def client(fake_db: MagicMock) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: fake_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def broken_db() -> MagicMock:
    db = MagicMock()
    db.execute.side_effect = OperationalError("SELECT 1", {}, Exception("down"))
    return db
