from decimal import Decimal
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment variables / .env."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Fulyn"
    app_env: str = "development"
    log_level: str = "INFO"

    database_url: str = Field(
        default="postgresql+psycopg://fulyn:fulyn@127.0.0.1:5432/fulyn",
        description="SQLAlchemy URL. Must use the psycopg (v3) driver.",
    )

    ollama_base_url: str = "http://127.0.0.1:11434"
    # Deliberately no default: the model must be chosen in the environment.
    ollama_model: str | None = None
    ollama_timeout_seconds: float = 180.0
    # Embedding model for semantic memory search (e.g. nomic-embed-text, 768 dimensions).
    # Unset: memory search falls back to full-text matching only.
    ollama_embed_model: str | None = None
    # Optional task prefixes some embedding models expect (e.g. "search_query: ").
    embed_document_prefix: str = ""
    embed_query_prefix: str = ""

    # Agent loop guards.
    agent_max_tool_iterations: int = Field(default=8, ge=1, le=20)
    # Recent chat messages (user, assistant and tool) sent back to the model as context.
    agent_history_messages: int = Field(default=30, ge=0, le=200)

    default_timezone: str = "Asia/Colombo"
    default_currency: str = "LKR"
    expense_categories: list[str] = [
        "Food",
        "Cafe",
        "Transport",
        "Shopping",
        "Entertainment",
        "Subscription",
        "Education",
        "Health",
        "Bills",
        "Technology",
        "Other",
    ]

    # Expenses at or above this amount (home currency) appear on the life timeline.
    major_purchase_amount: Decimal = Decimal("10000")

    cors_origins: list[str] = ["http://localhost:3000"]

    @field_validator("default_timezone")
    @classmethod
    def _validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown timezone: {value}") from exc
        return value

    @field_validator("default_currency")
    @classmethod
    def _validate_currency(cls, value: str) -> str:
        value = value.strip().upper()
        if len(value) != 3 or not value.isalpha():
            raise ValueError("default_currency must be a 3-letter ISO 4217 code")
        return value

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.default_timezone)


@lru_cache
def get_settings() -> Settings:
    return Settings()
