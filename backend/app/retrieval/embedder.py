"""Embeddings. OpenAI text-embedding-3-small by default; local fallback for keyless dev."""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Protocol

import numpy as np

from ..config import get_settings

log = logging.getLogger(__name__)


class Embedder(Protocol):
    dim: int
    def embed_query(self, text: str) -> np.ndarray: ...
    def embed_documents(self, texts: list[str]) -> np.ndarray: ...


class OpenAIEmbedder:
    def __init__(self, api_key: str, model: str = "text-embedding-3-small") -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self._model = model
        self.dim = 1536

    def embed_query(self, text: str) -> np.ndarray:
        resp = self._client.embeddings.create(model=self._model, input=text)
        v = np.asarray(resp.data[0].embedding, dtype=np.float32)
        return v / (np.linalg.norm(v) + 1e-12)

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        out = []
        for i in range(0, len(texts), 128):
            resp = self._client.embeddings.create(model=self._model, input=texts[i : i + 128])
            out.extend(d.embedding for d in resp.data)
        arr = np.asarray(out, dtype=np.float32)
        return arr / (np.linalg.norm(arr, axis=1, keepdims=True) + 1e-12)


class LocalEmbedder:
    """sentence-transformers fallback. all-MiniLM-L6-v2 is 384-dim — change
    the migration to vector(384) before using this against a fresh database."""

    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)
        self.dim = self._model.get_sentence_embedding_dimension() or 384

    def embed_query(self, text: str) -> np.ndarray:
        v = self._model.encode([text], normalize_embeddings=True, convert_to_numpy=True)[0]
        return v.astype(np.float32)

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return self._model.encode(
            texts, normalize_embeddings=True, convert_to_numpy=True,
            batch_size=32, show_progress_bar=False,
        ).astype(np.float32)


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    s = get_settings()
    if s.embedder_provider == "openai" and s.openai_api_key:
        return OpenAIEmbedder(s.openai_api_key, s.embedder_model)
    log.info("Using local embedder: %s", s.embedder_model)
    return LocalEmbedder("sentence-transformers/all-MiniLM-L6-v2")
