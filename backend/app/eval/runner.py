"""
Eval runner — single-agent, single-DB version.

Drives the same retrieval path as the runtime query endpoint and writes
per-question + aggregated results to eval_results / eval_runs. Designed to
be called from `scripts/run_eval.py` as a CLI.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from psycopg.rows import dict_row

from ..config import get_settings
from ..db import get_pool, store
from ..llm.client import get_llm
from ..retrieval import hybrid as hyb
from ..retrieval.embedder import get_embedder
from ..retrieval.reranker import get_identity_reranker, get_reranker
from . import metrics

log = logging.getLogger(__name__)


def run_eval(
    questions: list[dict],
    retrieval_strategy: str,
    git_sha: str | None = None,
) -> dict:
    """Run eval over the supplied questions. Returns aggregated metrics dict.

    Each `questions` item: {question, reference_answer, expected_chunk_ids}.
    """
    eval_run_id = _create_run(retrieval_strategy, git_sha)

    embedder = get_embedder()
    llm = get_llm()
    judge = llm  # In production you'd want a separate, stronger judge.

    per_q: list[dict[str, Any]] = []
    for q in questions:
        try:
            result = _evaluate_one(q, embedder, llm, judge, retrieval_strategy)
            per_q.append(result)
            _write_result(eval_run_id, q, result)
        except Exception as e:  # noqa: BLE001
            log.exception("eval question failed: %s", q.get("question"))
            per_q.append({"latency_ms": 0, "cost_usd": 0.0, "error": str(e)})

    agg = metrics.aggregate_metrics(per_q)
    _finalise(eval_run_id, agg)
    log.info("Eval complete: %s", agg)
    return agg


def _evaluate_one(q: dict, embedder, llm, judge, strategy: str) -> dict[str, Any]:
    from ..routers.query import SYSTEM_PROMPT, _format_sources_block

    settings = get_settings()
    t0 = time.perf_counter()

    if strategy == "vector":
        candidates = hyb.vector_only(store, embedder, q["question"], settings.rerank_top_k)
    else:
        candidates = hyb.hybrid(store, embedder, q["question"], settings.retrieve_top_k)
        if strategy == "hybrid_rerank":
            candidates = get_reranker().rerank(q["question"], candidates, settings.rerank_top_k)
        else:
            candidates = get_identity_reranker().rerank(q["question"], candidates, settings.rerank_top_k)

    chunks_for_metrics = [{"id": c.id, "text": c.text} for c in candidates]
    sources_block = _format_sources_block(candidates)
    user_prompt = f"Sources:\n{sources_block}\n\nQuestion: {q['question']}\n\nAnswer:"

    answer_parts: list[str] = []
    total_in, total_out = 0, 0
    for delta in llm.stream(system=SYSTEM_PROMPT, user=user_prompt, max_tokens=600):
        if delta.kind == "text":
            answer_parts.append(delta.text)
        elif delta.kind == "usage":
            total_in = delta.input_tokens
            total_out = delta.output_tokens
    answer = "".join(answer_parts)

    latency_ms = int((time.perf_counter() - t0) * 1000)
    cost = llm.cost_usd(total_in, total_out)
    retrieved_ids = [c.id for c in candidates]

    return {
        "context_precision": metrics.context_precision(retrieved_ids, q["expected_chunk_ids"]),
        "context_recall": metrics.context_recall(retrieved_ids, q["expected_chunk_ids"]),
        "faithfulness": metrics.faithfulness(answer, chunks_for_metrics, judge),
        "answer_relevancy": metrics.answer_relevancy(q["question"], answer, embedder, judge),
        "citation_accuracy": metrics.citation_accuracy(answer, chunks_for_metrics, judge),
        "retrieved_ids": retrieved_ids,
        "answer": answer,
        "latency_ms": latency_ms,
        "cost_usd": cost,
    }


def _create_run(strategy: str, git_sha: str | None) -> str:
    with get_pool().connection() as conn:
        conn.row_factory = dict_row
        row = conn.execute(
            """
            INSERT INTO eval_runs (retrieval_strategy, git_sha, status)
            VALUES (%s, %s, 'running') RETURNING id
            """,
            (strategy, git_sha),
        ).fetchone()
    return str(row["id"])


def _write_result(run_id: str, q: dict, result: dict) -> None:
    keys = {"context_precision", "context_recall", "faithfulness", "answer_relevancy", "citation_accuracy"}
    per_q_metrics = {k: result.get(k) for k in keys}
    with get_pool().connection() as conn:
        conn.execute(
            """
            INSERT INTO eval_results
              (eval_run_id, question, reference_answer, expected_chunk_ids, retrieved_ids, answer, metrics, latency_ms)
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)
            """,
            (
                run_id,
                q["question"],
                q.get("reference_answer"),
                q.get("expected_chunk_ids", []),
                result.get("retrieved_ids", []),
                result.get("answer", ""),
                json.dumps(per_q_metrics),
                result.get("latency_ms", 0),
            ),
        )


def _finalise(run_id: str, agg: dict) -> None:
    with get_pool().connection() as conn:
        conn.execute(
            "UPDATE eval_runs SET status='completed', metrics=%s::jsonb, finished_at=now() WHERE id=%s",
            (json.dumps(agg), run_id),
        )
