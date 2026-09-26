"""Deterministic bag-of-words embeddings: texts sharing words are similar."""

import hashlib
import math
import re

from app.models.memory import EMBEDDING_DIMENSIONS
from app.services.embeddings import EmbeddingUnavailableError, EmbedKind


class FakeEmbeddings:
    model = "fake-embed"

    def __init__(self) -> None:
        self.available = True
        self.calls = 0

    def embed(self, texts: list[str], kind: EmbedKind) -> list[list[float]]:
        if not self.available:
            raise EmbeddingUnavailableError("fake embedding service is down")
        self.calls += 1
        return [self._vector(text) for text in texts]

    @staticmethod
    def _vector(text: str) -> list[float]:
        vector = [0.0] * EMBEDDING_DIMENSIONS
        for word in re.findall(r"[a-z]+", text.lower()):
            index = int(hashlib.md5(word.encode()).hexdigest(), 16) % EMBEDDING_DIMENSIONS
            vector[index] += 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        # Never all-zero: cosine distance is undefined for zero vectors.
        return (
            [v / norm for v in vector]
            if any(vector)
            else [1.0] + [0.0] * (EMBEDDING_DIMENSIONS - 1)
        )
