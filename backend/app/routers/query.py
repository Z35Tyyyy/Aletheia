"""
The streaming query endpoint.

POST /query
  → SSE events:
      meta  {trace_id, n_candidates}
      text  "partial answer"
      cite  {n, chunk_id, source_url, text, highlight_start, highlight_end}
      done  {latency_ms, cost_usd, query_log_id}
      error {message}

Flow: hybrid retrieve → rerank → numbered-prompt → stream LLM, intercepting
[SOURCE N] markers to emit `cite` events to the widget.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from typing import AsyncIterator

from fastapi import APIRouter
from psycopg.rows import dict_row
from sse_starlette.sse import EventSourceResponse

from ..config import get_settings
from ..db import get_pool, store
from ..llm.client import get_llm
from ..retrieval import hybrid as hyb
from ..retrieval.embedder import get_embedder
from ..retrieval.hybrid import RetrievedChunk
from ..retrieval.reranker import get_identity_reranker, get_reranker
from ..schemas import FeedbackRequest, QueryRequest

log = logging.getLogger(__name__)
router = APIRouter(tags=["query"])

CITATION_PATTERN = re.compile(r"\[SOURCE\s+(\d+)\]")

SYSTEM_PROMPT = """You are a helpful assistant that answers questions strictly from the provided sources.

Rules:
- Cite every factual claim with [SOURCE N] inline, where N matches the source number below.
- If the sources don't contain the answer, say so honestly. Do NOT invent details.
- Be concise. Aim for 2-4 sentences unless the question demands more."""


@router.post("/query")
async def query_stream(body: QueryRequest, strategy: str = "hybrid_rerank"):
    """SSE stream. `strategy` overrides the default for A/B comparison from the dashboard."""
    settings = get_settings()
    if strategy not in ("vector", "hybrid", "hybrid_rerank"):
        strategy = "hybrid_rerank"
    trace_id = uuid.uuid4().hex[:12]

    async def event_gen() -> AsyncIterator[dict]:
        t0 = time.perf_counter()
        try:
            embedder = get_embedder()
            if strategy == "vector":
                candidates = hyb.vector_only(store, embedder, body.query, settings.rerank_top_k)
            else:
                candidates = hyb.hybrid(store, embedder, body.query, settings.retrieve_top_k)
                if strategy == "hybrid_rerank":
                    candidates = get_reranker().rerank(body.query, candidates, settings.rerank_top_k)
                else:
                    candidates = get_identity_reranker().rerank(body.query, candidates, settings.rerank_top_k)

            yield {"event": "meta", "data": json.dumps({"trace_id": trace_id, "n_candidates": len(candidates)})}

            if not candidates:
                yield {"event": "text", "data": json.dumps(
                    "I couldn't find anything in the docs relevant to your question."
                )}
                yield {"event": "done", "data": json.dumps(
                    {"latency_ms": int((time.perf_counter() - t0) * 1000), "cost_usd": 0.0, "query_log_id": ""}
                )}
                return

            sources_block = _format_sources_block(candidates)
            user_prompt = f"Sources:\n{sources_block}\n\nQuestion: {body.query}\n\nAnswer:"

            llm = get_llm()
            buf = ""
            cited: set[int] = set()
            full: list[str] = []
            total_in, total_out = 0, 0

            for delta in llm.stream(system=SYSTEM_PROMPT, user=user_prompt, max_tokens=1024):
                if delta.kind == "usage":
                    total_in = delta.input_tokens
                    total_out = delta.output_tokens
                    continue

                buf += delta.text
                full.append(delta.text)
                emit_text, remainder = _split_safe_to_emit(buf)
                buf = remainder

                for m in CITATION_PATTERN.finditer(emit_text):
                    n = int(m.group(1))
                    if 1 <= n <= len(candidates) and n not in cited:
                        cited.add(n)
                        yield {"event": "cite", "data": json.dumps(_build_citation(n, candidates[n - 1], body.query))}

                if emit_text:
                    yield {"event": "text", "data": json.dumps(emit_text)}
                await asyncio.sleep(0)

            # Flush any remaining buffer.
            if buf:
                for m in CITATION_PATTERN.finditer(buf):
                    n = int(m.group(1))
                    if 1 <= n <= len(candidates) and n not in cited:
                        cited.add(n)
                        yield {"event": "cite", "data": json.dumps(_build_citation(n, candidates[n - 1], body.query))}
                yield {"event": "text", "data": json.dumps(buf)}

            latency_ms = int((time.perf_counter() - t0) * 1000)
            cost = llm.cost_usd(total_in, total_out)
            answer = "".join(full)
            query_log_id = _log_query(body.query, [c.id for c in candidates], answer, latency_ms, cost, trace_id)

            yield {"event": "done", "data": json.dumps({
                "latency_ms": latency_ms,
                "cost_usd": round(cost, 6),
                "query_log_id": query_log_id,
                "trace_id": trace_id,
            })}

        except Exception as e:  # noqa: BLE001
            log.exception("Query failed (trace=%s)", trace_id)
            yield {"event": "error", "data": json.dumps({"message": str(e), "trace_id": trace_id})}

    return EventSourceResponse(event_gen())


@router.post("/feedback", status_code=204)
def submit_feedback(body: FeedbackRequest) -> None:
    with get_pool().connection() as conn:
        conn.execute(
            "UPDATE query_logs SET user_feedback = %s WHERE id = %s",
            (body.feedback, str(body.query_log_id)),
        )


@router.get("/config")
def public_config() -> dict:
    """What the widget grabs on boot. No secrets — only display config."""
    return {
        "name": "ragfast",
        "color": "#c8472b",
        "greeting": "Hi! Ask me anything about FastAPI.",
        "placeholder": "How do I declare a path parameter?",
        "suggested_questions": [
            "How do I declare a path parameter?",
            "What's the difference between Query and Path?",
            "How do dependencies work in FastAPI?",
        ],
    }


# ----- internals -----

def _format_sources_block(chunks: list[RetrievedChunk]) -> str:
    lines = []
    for i, c in enumerate(chunks, start=1):
        url = f" ({c.source_url})" if c.source_url else ""
        lines.append(f"[SOURCE {i}]{url}\n{c.text}")
    return "\n\n".join(lines)


def _split_safe_to_emit(buf: str) -> tuple[str, str]:
    """Hold back partial [SOURCE N] tokens so we don't split the marker mid-stream."""
    tail = buf[-20:]
    last_open = tail.rfind("[")
    if last_open >= 0 and "]" not in tail[last_open:]:
        cut = len(buf) - len(tail) + last_open
        return buf[:cut], buf[cut:]
    return buf, ""


def _build_citation(n: int, chunk: RetrievedChunk, query: str) -> dict:
    """Highlight the sentence with most query-term overlap (cheap heuristic).
    The WRITEUP notes that running the cross-encoder at sentence granularity here
    would produce more precise highlights — left as next-up work."""
    sentences = _split_sentences(chunk.text)
    if not sentences:
        return {"n": n, "chunk_id": chunk.id, "source_url": chunk.source_url,
                "source_title": chunk.source_title, "text": chunk.text,
                "highlight_start": 0, "highlight_end": 0}

    q_terms = {t for t in query.lower().split() if len(t) > 2}
    best_idx, best_score = 0, -1
    for i, s in enumerate(sentences):
        s_terms = {t.strip(".,;:!?\"'") for t in s.lower().split()}
        overlap = len(q_terms & s_terms)
        if overlap > best_score:
            best_idx, best_score = i, overlap

    offset = 0
    for s in sentences[:best_idx]:
        offset = chunk.text.find(s, offset) + len(s)
    start = chunk.text.find(sentences[best_idx], offset)
    if start < 0:
        start = 0
    end = start + len(sentences[best_idx])

    return {
        "n": n,
        "chunk_id": chunk.id,
        "source_url": chunk.source_url,
        "source_title": chunk.source_title,
        "text": chunk.text,
        "highlight_start": start,
        "highlight_end": end,
    }


def _split_sentences(text: str) -> list[str]:
    return [p for p in re.split(r"(?<=[.!?])\s+(?=[A-Z])", text.strip()) if p]


def _log_query(query: str, retrieved_ids: list[str], answer: str,
               latency_ms: int, cost_usd: float, trace_id: str) -> str:
    with get_pool().connection() as conn:
        conn.row_factory = dict_row
        row = conn.execute(
            """
            INSERT INTO query_logs (query, retrieved_ids, answer, latency_ms, cost_usd, trace_id)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
            """,
            (query, retrieved_ids, answer, latency_ms, cost_usd, trace_id),
        ).fetchone()
    return str(row["id"])
