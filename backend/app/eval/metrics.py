"""
Eval metrics — RAGAS-shaped + the custom citation_accuracy from §6.1.

Each metric is a free function so they're individually testable and
recomposable. All return floats in [0, 1] except cost (USD) and latency (ms).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from ..llm.client import LLMClient
    from ..retrieval.embedder import Embedder

CITATION_PATTERN = re.compile(r"\[SOURCE\s+(\d+)\]")


@dataclass
class QuestionEvalInputs:
    question: str
    reference_answer: str | None
    expected_source_ids: list[str]      # ground-truth chunk IDs
    retrieved_chunks: list[dict]        # {id, text}
    answer: str                          # generated answer including [SOURCE N] markers


# ---------- Context precision / recall ----------

def context_precision(retrieved_ids: list[str], expected_ids: list[str]) -> float:
    """
    Of the chunks we retrieved, how many were actually relevant?
    Computed against expected_source_ids (the ground truth).

    Note: this is the simple deterministic variant. The full RAGAS definition
    uses an LLM judge for relevance; in MVP we use exact ID match because
    synthetic questions have a guaranteed chunk_id, and curated questions
    are hand-labeled with explicit expected_source_ids.
    """
    if not retrieved_ids:
        return 0.0
    expected = set(expected_ids)
    if not expected:
        return 0.0
    hits = sum(1 for i in retrieved_ids if i in expected)
    return hits / len(retrieved_ids)


def context_recall(retrieved_ids: list[str], expected_ids: list[str]) -> float:
    """Of the chunks needed to answer the question, how many were retrieved?"""
    if not expected_ids:
        return 0.0
    expected = set(expected_ids)
    found = sum(1 for i in expected if i in retrieved_ids)
    return found / len(expected)


# ---------- Faithfulness (LLM judge) ----------

FAITHFULNESS_DECOMPOSE_PROMPT = (
    "Decompose the following answer into a list of distinct factual claims. "
    "Return one claim per line, with no numbering, no bullet points, no extra commentary.\n\n"
    "Answer:\n{answer}\n\nClaims:"
)

FAITHFULNESS_CHECK_PROMPT = (
    "Given the following context, decide whether the claim is fully supported.\n\n"
    "Context:\n{context}\n\n"
    "Claim: {claim}\n\n"
    "Answer with exactly one word: YES if fully supported by the context, NO otherwise."
)


def faithfulness(answer: str, retrieved_chunks: list[dict], judge: "LLMClient") -> float:
    """
    Decompose the answer into claims; for each claim, ask whether it's
    supported by the retrieved context. Fraction supported = faithfulness.
    """
    if not answer.strip() or not retrieved_chunks:
        return 0.0

    # Strip citation markers before evaluating — they aren't claims.
    clean_answer = CITATION_PATTERN.sub("", answer).strip()
    claims_raw = judge.complete(
        FAITHFULNESS_DECOMPOSE_PROMPT.format(answer=clean_answer),
        system="You decompose answers into atomic factual claims.",
        max_tokens=400,
    )
    claims = [c.strip() for c in claims_raw.splitlines() if c.strip()]
    if not claims:
        return 0.0

    context = "\n\n".join(c["text"] for c in retrieved_chunks)
    supported = 0
    for claim in claims:
        verdict = judge.complete(
            FAITHFULNESS_CHECK_PROMPT.format(context=context, claim=claim),
            system="You evaluate whether claims are supported by provided context.",
            max_tokens=10,
        ).strip().upper()
        if verdict.startswith("YES"):
            supported += 1

    return supported / len(claims)


# ---------- Answer relevancy (embedding similarity with perturbations) ----------

ANSWER_RELEVANCY_PROMPT = (
    "Given the answer below, produce ONE question that this answer is responding to. "
    "Output only the question.\n\nAnswer:\n{answer}\n\nQuestion:"
)


def answer_relevancy(
    question: str,
    answer: str,
    embedder: "Embedder",
    judge: "LLMClient",
    n_perturbations: int = 3,
) -> float:
    """
    Generate N candidate questions from the answer; compute the average
    embedding similarity between the original question and these generated
    questions. High similarity = the answer is on-topic.
    """
    if not answer.strip():
        return 0.0

    clean_answer = CITATION_PATTERN.sub("", answer).strip()
    generated = []
    for _ in range(n_perturbations):
        q = judge.complete(
            ANSWER_RELEVANCY_PROMPT.format(answer=clean_answer),
            system="You reverse-engineer a question from an answer.",
            max_tokens=80,
        ).strip()
        if q:
            generated.append(q)

    if not generated:
        return 0.0

    q_emb = embedder.embed_query(question)
    g_embs = embedder.embed_documents(generated)
    # Cosine sim (embeddings are L2-normalised)
    sims = g_embs @ q_emb
    return float(np.clip(sims.mean(), 0.0, 1.0))


# ---------- Citation accuracy (custom, per §6.1) ----------

def citation_accuracy(
    answer: str,
    retrieved_chunks: list[dict],
    judge: "LLMClient",
) -> float:
    """
    For each [SOURCE N] in the answer:
      - The cited chunk exists in the retrieved set (always true by construction)
      - The cited chunk supports the claim immediately preceding the marker

    Pulls one sentence/clause ending at each citation marker, asks the
    judge: "Does <cited_chunk> support <preceding_clause>?".
    Returns fraction of citations that pass.
    """
    citations = list(CITATION_PATTERN.finditer(answer))
    if not citations:
        return 0.0  # No citations means we can't verify grounding at all.

    chunk_by_n = {i + 1: c for i, c in enumerate(retrieved_chunks)}
    correct = 0
    for m in citations:
        n = int(m.group(1))
        cited = chunk_by_n.get(n)
        if not cited:
            continue
        # Pull the clause ending at this citation: from previous sentence
        # boundary (or start) up to the marker.
        start = max(0, m.start() - 400)
        clause_search = answer[start : m.start()]
        # Last sentence boundary in clause_search:
        boundaries = [i for i, ch in enumerate(clause_search) if ch in ".!?\n"]
        clause_start = boundaries[-1] + 1 if boundaries else 0
        clause = clause_search[clause_start:].strip()
        if not clause:
            continue

        verdict = judge.complete(
            (
                "Does the following context support the claim?\n\n"
                f"Context:\n{cited['text']}\n\n"
                f"Claim: {clause}\n\n"
                "Answer YES or NO."
            ),
            system="You verify whether claims are supported.",
            max_tokens=10,
        ).strip().upper()
        if verdict.startswith("YES"):
            correct += 1

    return correct / len(citations)


# ---------- Aggregation ----------

def aggregate_metrics(per_question: list[dict]) -> dict:
    """Average each metric across questions; compute latency percentiles."""
    if not per_question:
        return {}
    keys = [
        "context_precision",
        "context_recall",
        "faithfulness",
        "answer_relevancy",
        "citation_accuracy",
    ]
    out: dict[str, float] = {}
    for k in keys:
        vals = [q.get(k) for q in per_question if q.get(k) is not None]
        out[k] = float(np.mean(vals)) if vals else 0.0

    latencies = [q.get("latency_ms", 0) for q in per_question]
    if latencies:
        out["latency_p50_ms"] = float(np.percentile(latencies, 50))
        out["latency_p95_ms"] = float(np.percentile(latencies, 95))
    else:
        out["latency_p50_ms"] = 0.0
        out["latency_p95_ms"] = 0.0

    out["cost_usd_total"] = float(sum(q.get("cost_usd", 0.0) for q in per_question))
    out["n_questions"] = len(per_question)
    return out
