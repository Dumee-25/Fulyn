"""Chat-completion client for Ollama, behind a small protocol so tests can fake it."""

import json
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Protocol

import httpx

from app.core.config import get_settings
from app.core.errors import DomainError

logger = logging.getLogger(__name__)


class LLMUnavailableError(DomainError):
    """The model could not be reached or is not configured. Message is safe to show."""


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMReply:
    content: str
    tool_calls: list[ToolCall]


class LLMClient(Protocol):
    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMReply: ...


def _parse_arguments(value: Any) -> dict[str, Any]:
    # Most models return an object; some return a JSON string.
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


class OllamaClient:
    def __init__(self, base_url: str, model: str, timeout: float) -> None:
        self.model = model
        self._client = httpx.Client(base_url=base_url, timeout=timeout)

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMReply:
        payload = {"model": self.model, "messages": messages, "tools": tools, "stream": False}
        try:
            response = self._client.post("/api/chat", json=payload)
        except httpx.HTTPError as exc:
            # Never log the payload: it contains the user's messages.
            logger.warning("Ollama request failed: %s", type(exc).__name__)
            raise LLMUnavailableError("The language model is not reachable.") from exc
        if response.status_code != 200:
            logger.warning("Ollama returned HTTP %s", response.status_code)
            raise LLMUnavailableError(
                f"The language model returned an error ({response.status_code})."
            )

        message = response.json().get("message", {})
        calls = [
            ToolCall(
                name=call.get("function", {}).get("name", ""),
                arguments=_parse_arguments(call.get("function", {}).get("arguments")),
                raw=call,
            )
            for call in message.get("tool_calls") or []
        ]
        return LLMReply(content=message.get("content") or "", tool_calls=calls)


@lru_cache
def _ollama_client(base_url: str, model: str, timeout: float) -> OllamaClient:
    return OllamaClient(base_url, model, timeout)


def get_llm() -> LLMClient:
    """FastAPI dependency. Fails clearly when no model is configured."""
    settings = get_settings()
    if not settings.ollama_model:
        raise LLMUnavailableError("No model configured. Set OLLAMA_MODEL in .env.")
    return _ollama_client(
        settings.ollama_base_url, settings.ollama_model, settings.ollama_timeout_seconds
    )
