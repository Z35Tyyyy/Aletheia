"""Env-driven config."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://rag:rag@localhost:5432/rag"

    # LLM
    llm_provider: str = "openai"      # "openai" | "echo"
    llm_model: str = "gpt-4o-mini"
    openai_api_key: str = ""

    # Embedder
    embedder_provider: str = "openai"   # "openai" | "local"
    embedder_model: str = "text-embedding-3-small"
    # The schema is hard-coded to 1536 in 001_init.sql for text-embedding-3-small.
    # If you switch to all-MiniLM-L6-v2 (384), update the migration too.
    embedding_dim: int = 1536

    # Reranker
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # Retrieval params
    retrieve_top_k: int = 20
    rerank_top_k: int = 6
    rrf_k: int = 60

    allowed_origins: str = "http://localhost:5173,http://localhost:5174"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
