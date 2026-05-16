"""
Hybrid retrieval: pgvector cosine search + Postgres FTS, fused with RRF.

RRF formula (Cormack 2009): score(d) = Σ over rankings R of 1 / (k + rank_R(d)).
Docs absent from a ranking contribute 0 from that ranking. The lower the
rank, the higher the contribution — but no single ranking dominates, which
is what makes RRF robust to mixed score scales (cosine ∈ [-1,1] vs
ts_rank_cd unbounded).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..config import get_settings

if TYPE_CHECKING:
    from ..db import VectorStore
    from .embedder import Embedder


@dataclass(slots=True)
class RetrievedChunk:
    id: str
    text: str
    source_url: str | None
    source_title: str | None
    metadata: dict[str, Any]
    score: float
    vector_rank: int | None = None
    fts_rank: int | None = None


def reciprocal_rank_fusion(
    rankings: list[list[dict[str, Any]]],
    k: int = 60,
) -> list[tuple[str, float, dict[int, int]]]:
    """Pure RRF. Returns (id, fused_score, {ranking_idx: rank}) sorted desc."""
    scores: dict[str, float] = {}
    sources: dict[str, dict[int, int]] = {}
    for ranking_idx, ranking in enumerate(rankings):
        for rank, chunk in enumerate(ranking):
            cid = chunk["id"]
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
            sources.setdefault(cid, {})[ranking_idx] = rank
    return sorted(
        ((cid, s, sources[cid]) for cid, s in scores.items()),
        key=lambda t: -t[1],
    )


def vector_only(
    store: "VectorStore", embedder: "Embedder", query: str, top_k: int,
) -> list[RetrievedChunk]:
    qv = embedder.embed_query(query)
    return [_to_retrieved(r, vector_rank=r["rank"]) for r in store.vector_search(qv, top_k)]


def hybrid(
    store: "VectorStore", embedder: "Embedder", query: str, top_k: int,
    rrf_k: int | None = None,
) -> list[RetrievedChunk]:
    """Run vector + FTS in parallel, fuse with RRF, return top_k."""
    rrf_k = rrf_k or get_settings().rrf_k
    qv = embedder.embed_query(query)

    with ThreadPoolExecutor(max_workers=2) as ex:
        f_vec = ex.submit(store.vector_search, qv, top_k)
        f_fts = ex.submit(store.fts_search, query, top_k)
        vec_results = f_vec.result()
        fts_results = f_fts.result()

    fused = reciprocal_rank_fusion([vec_results, fts_results], k=rrf_k)
    fused_ids = [cid for cid, _, _ in fused[:top_k]]

    by_id: dict[str, dict[str, Any]] = {c["id"]: c for c in vec_results}
    for c in fts_results:
        by_id.setdefault(c["id"], c)

    missing = [cid for cid in fused_ids if cid not in by_id]
    if missing:
        for c in store.get_chunks(missing):
            by_id[c["id"]] = c

    out: list[RetrievedChunk] = []
    for cid, score, ranks in fused[:top_k]:
        c = by_id.get(cid)
        if c is None:
            continue
        out.append(_to_retrieved(c, fused_score=score,
                                 vector_rank=ranks.get(0), fts_rank=ranks.get(1)))
    return out


def _to_retrieved(
    c: dict[str, Any],
    fused_score: float | None = None,
    vector_rank: int | None = None,
    fts_rank: int | None = None,
) -> RetrievedChunk:
    return RetrievedChunk(
        id=c["id"],
        text=c.get("text", ""),
        source_url=c.get("source_url"),
        source_title=c.get("source_title"),
        metadata=c.get("metadata") or {},
        score=fused_score if fused_score is not None else float(c.get("score", 0.0)),
        vector_rank=vector_rank,
        fts_rank=fts_rank,
    )
