"""
Database access.

One Postgres connection pool. Vectors and FTS live in the same `chunks`
table — that's the whole reason this single-tenant variant gets to drop
MongoDB Atlas. pgvector handles dense retrieval, the generated tsvector
column handles keyword retrieval.
"""
from __future__ import annotations

import logging
import threading
from typing import Any

import numpy as np
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import get_settings

log = logging.getLogger(__name__)

_pool: ConnectionPool | None = None
_pool_lock = threading.Lock()


def get_pool() -> ConnectionPool:
    """Lazy singleton."""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = ConnectionPool(
                    conninfo=get_settings().database_url,
                    min_size=2,
                    max_size=10,
                    kwargs={"autocommit": True},
                )
                _register_vector(_pool)
    return _pool


def _register_vector(pool: ConnectionPool) -> None:
    """Tell psycopg how to (de)serialise the pgvector type."""
    from pgvector.psycopg import register_vector

    with pool.connection() as conn:
        register_vector(conn)


class VectorStore:
    """All retrieval over the single `chunks` table."""

    def upsert(self, chunks: list[dict[str, Any]]) -> int:
        """Insert (or replace) chunks. `chunks` items: id, source_url,
        source_title, text, metadata, embedding (np.ndarray or list[float])."""
        if not chunks:
            return 0
        with get_pool().connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO chunks (id, source_url, source_title, text, metadata, embedding)
                    VALUES (%s, %s, %s, %s, %s::jsonb, %s)
                    ON CONFLICT (id) DO UPDATE
                      SET source_url = EXCLUDED.source_url,
                          source_title = EXCLUDED.source_title,
                          text = EXCLUDED.text,
                          metadata = EXCLUDED.metadata,
                          embedding = EXCLUDED.embedding
                    """,
                    [
                        (
                            c["id"],
                            c.get("source_url"),
                            c.get("source_title"),
                            c["text"],
                            _to_json(c.get("metadata") or {}),
                            _to_vector(c["embedding"]),
                        )
                        for c in chunks
                    ],
                )
        return len(chunks)

    def vector_search(self, query_emb: np.ndarray, k: int) -> list[dict[str, Any]]:
        """Cosine-similarity nearest neighbours via pgvector (<=> is cosine distance)."""
        with get_pool().connection() as conn:
            conn.row_factory = dict_row
            rows = conn.execute(
                """
                SELECT id, source_url, source_title, text, metadata,
                       1 - (embedding <=> %s) AS score
                FROM chunks
                ORDER BY embedding <=> %s
                LIMIT %s
                """,
                (_to_vector(query_emb), _to_vector(query_emb), k),
            ).fetchall()
        return [_add_rank(r, i) for i, r in enumerate(rows)]

    def fts_search(self, query: str, k: int) -> list[dict[str, Any]]:
        """Postgres full-text search ranked by ts_rank_cd (TF-IDF-flavoured)."""
        with get_pool().connection() as conn:
            conn.row_factory = dict_row
            rows = conn.execute(
                """
                SELECT id, source_url, source_title, text, metadata,
                       ts_rank_cd(text_tsv, plainto_tsquery('english', %s)) AS score
                FROM chunks
                WHERE text_tsv @@ plainto_tsquery('english', %s)
                ORDER BY score DESC
                LIMIT %s
                """,
                (query, query, k),
            ).fetchall()
        return [_add_rank(r, i) for i, r in enumerate(rows)]

    def get_chunks(self, ids: list[str]) -> list[dict[str, Any]]:
        if not ids:
            return []
        with get_pool().connection() as conn:
            conn.row_factory = dict_row
            return conn.execute(
                "SELECT id, source_url, source_title, text, metadata FROM chunks WHERE id = ANY(%s)",
                (ids,),
            ).fetchall()

    def chunk_count(self) -> int:
        with get_pool().connection() as conn:
            return conn.execute("SELECT count(*) FROM chunks").fetchone()[0]

    def find_chunks_by_url_substring(self, patterns: list[str]) -> list[str]:
        """For eval bootstrap: turn a 'expected_url_contains' list into chunk IDs."""
        if not patterns:
            return []
        with get_pool().connection() as conn:
            ors = " OR ".join(["source_url ILIKE %s"] * len(patterns))
            args = tuple(f"%{p}%" for p in patterns)
            rows = conn.execute(
                f"SELECT id FROM chunks WHERE {ors}",
                args,
            ).fetchall()
        return [r[0] for r in rows]


def _to_vector(v):
    """pgvector psycopg adapter accepts np.ndarray and list both, but be explicit."""
    if isinstance(v, np.ndarray):
        return v
    return np.asarray(v, dtype=np.float32)


def _to_json(d: dict) -> str:
    import json
    return json.dumps(d)


def _add_rank(row: dict, rank: int) -> dict:
    row["rank"] = rank
    return row


# Module-level singleton; one store for the whole app.
store = VectorStore()
