"""Regression tests for pre-existing tracker debt (#370)."""

import pytest

from llm_council.performance.tracker import InternalPerformanceTracker


def _tracker(tmp_path, scores):
    t = InternalPerformanceTracker(store_path=tmp_path / "perf.jsonl")
    t.get_all_model_scores = lambda: scores  # type: ignore[method-assign]
    return t


class TestPercentileSelfExclusion:
    def test_excludes_self_from_ranking(self, tmp_path):
        # B=0.5 ranked among OTHERS {A:0.9, C:0.4, D:0.3}: beats C,D -> 2/3.
        # (Self-inclusive would wrongly give 3/4 = 0.75.)
        t = _tracker(tmp_path, {"A": 0.9, "B": 0.5, "C": 0.4, "D": 0.3})
        assert t.get_quality_percentile("B") == pytest.approx(2 / 3)

    def test_top_model_is_100th_percentile(self, tmp_path):
        t = _tracker(tmp_path, {"A": 0.9, "B": 0.5, "C": 0.4})
        assert t.get_quality_percentile("A") == pytest.approx(1.0)

    def test_single_model_is_top(self, tmp_path):
        t = _tracker(tmp_path, {"only": 0.5})
        assert t.get_quality_percentile("only") == 1.0

    def test_unknown_model_returns_none(self, tmp_path):
        t = _tracker(tmp_path, {"A": 0.9})
        assert t.get_quality_percentile("missing") is None
