"""Tests for retrieval logic — focused on the math, not external services."""
from __future__ import annotations

import pytest

from app.retrieval.hybrid import reciprocal_rank_fusion


class TestReciprocalRankFusion:
    def test_empty_rankings_returns_empty(self):
        assert reciprocal_rank_fusion([]) == []

    def test_single_ranking_preserves_order(self):
        ranking = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        result = reciprocal_rank_fusion([ranking], k=60)
        assert [r[0] for r in result] == ["a", "b", "c"]
        # Scores should be strictly decreasing
        scores = [r[1] for r in result]
        assert scores[0] > scores[1] > scores[2]

    def test_two_rankings_with_overlap(self):
        """A doc appearing in both rankings should beat one appearing in only one."""
        r1 = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        r2 = [{"id": "b"}, {"id": "a"}, {"id": "d"}]
        result = reciprocal_rank_fusion([r1, r2], k=60)
        ids = [r[0] for r in result]
        # 'a' and 'b' both appear in both lists; one of them should top the result.
        assert ids[0] in ("a", "b")
        # 'c' and 'd' appear only once each, should rank below 'a' and 'b'.
        assert set(ids[:2]) == {"a", "b"}
        assert set(ids[2:]) == {"c", "d"}

    def test_rrf_score_formula(self):
        """Spot-check the score formula: 1 / (k + rank), rank is 0-based."""
        r1 = [{"id": "a"}]
        result = reciprocal_rank_fusion([r1], k=60)
        assert result[0][0] == "a"
        assert result[0][1] == pytest.approx(1.0 / 60)

    def test_rrf_sums_across_rankings(self):
        r1 = [{"id": "x"}]   # rank 0 in r1 -> 1/60
        r2 = [{"id": "x"}]   # rank 0 in r2 -> 1/60
        result = reciprocal_rank_fusion([r1, r2], k=60)
        assert result[0][1] == pytest.approx(2.0 / 60)

    def test_ranking_source_tracking(self):
        """The third element in each result tuple records which rankings hit."""
        r1 = [{"id": "a"}, {"id": "b"}]
        r2 = [{"id": "b"}]
        result = reciprocal_rank_fusion([r1, r2], k=60)
        # Find 'b' — should have ranks from both rankings.
        b_entry = next(t for t in result if t[0] == "b")
        assert b_entry[2] == {0: 1, 1: 0}
        a_entry = next(t for t in result if t[0] == "a")
        assert a_entry[2] == {0: 0}

    def test_k_parameter_changes_decay(self):
        """Larger k flattens the curve — lower ranks contribute more, top ranks less."""
        r1 = [{"id": "a"}, {"id": "b"}]
        small_k = reciprocal_rank_fusion([r1], k=1)
        large_k = reciprocal_rank_fusion([r1], k=1000)
        # Ratio of top to second item: should be more peaked at small k.
        small_ratio = small_k[0][1] / small_k[1][1]
        large_ratio = large_k[0][1] / large_k[1][1]
        assert small_ratio > large_ratio
