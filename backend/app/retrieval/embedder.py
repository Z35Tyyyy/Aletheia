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


class FastEmbedder:
    """FastEmbed (ONNX) implementation. Light memory footprint (~300MB RAM).
    all-MiniLM-L6-v2 is 384-dim by default.
    """

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5") -> None:
        from fastembed import TextEmbedding

        # BAAI/bge-small-en-v1.5 is 384-dim, very high quality for its size.
        self._model = TextEmbedding(model_name=model_name)
        # FastEmbed handles the dimension detection
        self.dim = 384 if "small" in model_name or "MiniLM" in model_name else 768

    def embed_query(self, text: str) -> np.ndarray:
        # embed() returns a generator of numpy arrays
        v = next(self._model.embed([text]))
        return v.astype(np.float32)

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        # Convert generator to a single numpy array
        embeddings = list(self._model.embed(texts))
        return np.asarray(embeddings, dtype=np.float32)


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    s = get_settings()
    if s.embedder_provider == "openai" and s.openai_api_key:
        return OpenAIEmbedder(s.openai_api_key, s.embedder_model)

    log.info("Using local FastEmbed: %s", s.embedder_model)
    # Map 'local' or 'fastembed' to FastEmbedder
    # Default to BAAI/bge-small-en-v1.5 which is 384-dim
    model = s.embedder_model if s.embedder_model != "text-embedding-3-small" else "BAAI/bge-small-en-v1.5"
    return FastEmbedder(model)
