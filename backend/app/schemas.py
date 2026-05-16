"""Request/response models."""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)


class Citation(BaseModel):
    n: int
    chunk_id: str
    source_url: str | None
    source_title: str | None
    text: str
    highlight_start: int
    highlight_end: int


class FeedbackRequest(BaseModel):
    query_log_id: UUID
    feedback: Literal["up", "down"]


class EvalMetricsOut(BaseModel):
    context_precision: float
    context_recall: float
    faithfulness: float
    answer_relevancy: float
    citation_accuracy: float
    latency_p50_ms: float
    latency_p95_ms: float
    cost_usd_total: float
    n_questions: int


class EvalRunOut(BaseModel):
    id: UUID
    retrieval_strategy: str
    git_sha: str | None
    status: str
    metrics: EvalMetricsOut | None
    started_at: datetime
    finished_at: datetime | None
