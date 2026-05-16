"""Read-only eval endpoints for the dashboard."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from psycopg.rows import dict_row

from ..db import get_pool
from ..schemas import EvalMetricsOut, EvalRunOut

router = APIRouter(prefix="/evals", tags=["evals"])


@router.get("/runs", response_model=list[EvalRunOut])
def list_runs(limit: int = Query(100, le=500)) -> list[EvalRunOut]:
    with get_pool().connection() as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            "SELECT * FROM eval_runs ORDER BY started_at DESC LIMIT %s", (limit,),
        ).fetchall()
    return [_to_out(r) for r in rows]


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> dict:
    with get_pool().connection() as conn:
        conn.row_factory = dict_row
        run = conn.execute("SELECT * FROM eval_runs WHERE id = %s", (run_id,)).fetchone()
        if not run:
            raise HTTPException(404, "run not found")
        results = conn.execute(
            "SELECT * FROM eval_results WHERE eval_run_id = %s ORDER BY created_at ASC",
            (run_id,),
        ).fetchall()
    return {"run": _to_out(run).model_dump(), "results": results}


def _to_out(r: dict) -> EvalRunOut:
    metrics = None
    if r.get("metrics"):
        try:
            metrics = EvalMetricsOut(**r["metrics"])
        except Exception:  # noqa: BLE001
            metrics = None
    return EvalRunOut(
        id=r["id"],
        retrieval_strategy=r["retrieval_strategy"],
        git_sha=r.get("git_sha"),
        status=r["status"],
        metrics=metrics,
        started_at=r["started_at"],
        finished_at=r.get("finished_at"),
    )
