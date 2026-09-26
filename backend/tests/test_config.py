import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.default_timezone == "Asia/Colombo"
    assert settings.default_currency == "LKR"
    assert settings.ollama_model is None


def test_currency_is_normalized() -> None:
    assert Settings(_env_file=None, default_currency=" usd ").default_currency == "USD"


def test_rejects_unknown_timezone() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, default_timezone="Mars/Olympus")


def test_rejects_bad_currency() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, default_currency="RUPEES")
