"""
Tests for eval metrics.

LLM-judge metrics (faithfulness, answer_relevancy, citation_accuracy) need
a stubbed judge; the deterministic ones (context_precision, context_recall,
aggregation) can be tested without any external service.
"""
from __future__ import annotations

import pytest

from app.eval.metrics import aggregate_metrics, context_precision, context_recall


class TestContextPrecision:
    def test_all_retrieved_relevant(self):
        assert context_precision(["a", "b"], ["a", "b", "c"]) == 1.0

    def test_no_retrieved(self):
        assert context_precision([], ["a"]) == 0.0

    def test_no_expected(self):
        assert context_precision(["a", "b"], []) == 0.0

    def test_half_relevant(self):
        # 2 retrieved, 1 in expected -> 0.5
        assert context_precision(["a", "z"], ["a", "b"]) == 0.5


class TestContextRecall:
    def test_all_found(self):
        assert context_recall(["a", "b", "extra"], ["a", "b"]) == 1.0

    def test_none_found(self):
        assert context_recall(["x", "y"], ["a", "b"]) == 0.0

    def test_no_expected(self):
        assert context_recall(["a"], []) == 0.0

    def test_half_recalled(self):
        assert context_recall(["a", "z"], ["a", "b"]) == 0.5


class TestAggregate:
    def test_empty_returns_empty(self):
        assert aggregate_metrics([]) == {}

    def test_aggregates_means_and_percentiles(self):
        per_q = [
            {
                "context_precision": 0.8,
                "context_recall": 0.6,
                "faithfulness": 1.0,
                "answer_relevancy": 0.9,
                "citation_accuracy": 0.7,
                "latency_ms": 100,
                "cost_usd": 0.01,
            },
            {
                "context_precision": 0.6,
                "context_recall": 0.8,
                "faithfulness": 0.8,
                "answer_relevancy": 0.9,
                "citation_accuracy": 0.9,
                "latency_ms": 300,
                "cost_usd": 0.02,
            },
        ]
        agg = aggregate_metrics(per_q)
        assert agg["context_precision"] == pytest.approx(0.7)
        assert agg["context_recall"] == pytest.approx(0.7)
        assert agg["answer_relevancy"] == pytest.approx(0.9)
        assert agg["n_questions"] == 2
        assert agg["cost_usd_total"] == pytest.approx(0.03)
        # Two-point percentiles are linearly interpolated.
        assert agg["latency_p50_ms"] == pytest.approx(200.0)
        assert agg["latency_p95_ms"] == pytest.approx(290.0)

    def test_ignores_missing_keys(self):
        """A question that errored mid-run shouldn't poison the aggregate."""
        per_q = [
            {"context_precision": 0.9, "latency_ms": 100, "cost_usd": 0.01},
            {"latency_ms": 200, "cost_usd": 0.02, "error": "boom"},
        ]
        agg = aggregate_metrics(per_q)
        assert agg["context_precision"] == pytest.approx(0.9)  # only one value
        assert agg["n_questions"] == 2
