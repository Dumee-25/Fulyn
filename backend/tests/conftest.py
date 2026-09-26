"""Shared fixtures.

DB-backed tests run against a separate database (``TEST_DATABASE_URL``, default: the
configured database name with a ``_test`` suffix), created on demand. Each test runs
inside a transaction that is rolled back afterwards. If PostgreSQL is unreachable,
DB tests are skipped rather than failing.
"""

import os
from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.main import app
from app.models import Base


def _test_database_url() -> str:
    if url := os.environ.get("TEST_DATABASE_URL"):
        return url
    url = make_url(get_settings().database_url)
    return url.set(database=f"{url.database}_test").render_as_string(hide_password=False)


def _ensure_database(url: str) -> None:
    target = make_url(url)
    admin = create_engine(
        target.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 3},
    )
    try:
        with admin.connect() as conn:
            exists = conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": target.database},
            )
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{target.database}"'))
    finally:
        admin.dispose()


@pytest.fixture(scope="session")
def db_engine() -> Iterator[Engine]:
    url = _test_database_url()
    try:
        _ensure_database(url)
    except OperationalError:
        pytest.skip("PostgreSQL is not reachable; start it with `docker compose up -d db`")
    engine = create_engine(url, connect_args={"connect_timeout": 3})
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db(db_engine: Engine) -> Iterator[Session]:
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
    )
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def api(db: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


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
