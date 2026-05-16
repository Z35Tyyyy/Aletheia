"""Cross-encoder reranker. Loaded once per process; ~80MB resident."""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Protocol

from ..config import get_settings
from .hybrid import RetrievedChunk

log = logging.getLogger(__name__)


class Reranker(Protocol):
    def rerank(self, query: str, candidates: list[RetrievedChunk], top_k: int) -> list[RetrievedChunk]: ...


class CrossEncoderReranker:
    def __init__(self, model_name: str) -> None:
        from sentence_transformers import CrossEncoder

        self._model = CrossEncoder(model_name)
        log.info("Loaded cross-encoder: %s", model_name)

    def rerank(
        self, query: str, candidates: list[RetrievedChunk], top_k: int,
    ) -> list[RetrievedChunk]:
        if not candidates:
            return []
        pairs = [(query, c.text) for c in candidates]
        scores = self._model.predict(pairs, show_progress_bar=False)
        ranked = sorted(zip(candidates, scores, strict=True), key=lambda t: -float(t[1]))
        out: list[RetrievedChunk] = []
        for chunk, score in ranked[:top_k]:
            chunk.score = float(score)
            out.append(chunk)
        return out


class IdentityReranker:
    def rerank(
        self, query: str, candidates: list[RetrievedChunk], top_k: int,
    ) -> list[RetrievedChunk]:
        return candidates[:top_k]


@lru_cache(maxsize=1)
def get_reranker() -> Reranker:
    return CrossEncoderReranker(get_settings().reranker_model)


@lru_cache(maxsize=1)
def get_identity_reranker() -> Reranker:
    return IdentityReranker()
