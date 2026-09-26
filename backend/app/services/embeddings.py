"""Embedding generation behind a small interface, so the model can be swapped."""

import logging
from functools import lru_cache
from typing import Literal, Protocol

import httpx

from app.core.config import get_settings
from app.core.errors import DomainError
from app.models.memory import EMBEDDING_DIMENSIONS

logger = logging.getLogger(__name__)

EmbedKind = Literal["document", "query"]


class EmbeddingUnavailableError(DomainError):
    pass


class EmbeddingService(Protocol):
    model: str

    def embed(self, texts: list[str], kind: EmbedKind) -> list[list[float]]: ...


class OllamaEmbeddingService:
    def __init__(
        self, base_url: str, model: str, document_prefix: str, query_prefix: str, timeout: float
    ) -> None:
        self.model = model
        self._prefix = {"document": document_prefix, "query": query_prefix}
        self._client = httpx.Client(base_url=base_url, timeout=timeout)

    def embed(self, texts: list[str], kind: EmbedKind) -> list[list[float]]:
        if not texts:
            return []
        payload = {"model": self.model, "input": [self._prefix[kind] + t for t in texts]}
        try:
            response = self._client.post("/api/embed", json=payload)
        except httpx.HTTPError as exc:
            logger.warning("Embedding request failed: %s", type(exc).__name__)
            raise EmbeddingUnavailableError("embedding model not reachable") from exc
        if response.status_code != 200:
            logger.warning("Embedding request returned HTTP %s", response.status_code)
            raise EmbeddingUnavailableError(f"embedding model error ({response.status_code})")
        vectors = response.json().get("embeddings") or []
        if len(vectors) != len(texts) or any(len(v) != EMBEDDING_DIMENSIONS for v in vectors):
            raise EmbeddingUnavailableError(
                f"embedding model must return {EMBEDDING_DIMENSIONS}-dimension vectors"
            )
        return vectors


_override: EmbeddingService | None = None


def set_embedding_service(service: EmbeddingService | None) -> None:
    """Replace the embedding service (used by tests)."""
    global _override
    _override = service


@lru_cache
def _ollama_service(
    base_url: str, model: str, document_prefix: str, query_prefix: str, timeout: float
) -> OllamaEmbeddingService:
    return OllamaEmbeddingService(base_url, model, document_prefix, query_prefix, timeout)


def get_embedding_service() -> EmbeddingService | None:
    """The configured service, or None when OLLAMA_EMBED_MODEL is not set."""
    if _override is not None:
        return _override
    settings = get_settings()
    if not settings.ollama_embed_model:
        return None
    return _ollama_service(
        settings.ollama_base_url,
        settings.ollama_embed_model,
        settings.embed_document_prefix,
        settings.embed_query_prefix,
        30.0,
    )
