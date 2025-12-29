"""TDD Tests for ADR-029 Phase 4: Quality Percentile Calculation.

Tests are written FIRST (RED phase) per TDD methodology.
Issue: https://github.com/amiable-dev/llm-council/issues/131

This adds get_quality_percentile() to the performance tracker for
EVALUATION → FULL graduation criteria.
"""

import tempfile
from pathlib import Path

import pytest


class TestQualityPercentileUnknownModel:
    """Test percentile for unknown/insufficient data models."""

    def test_percentile_returns_none_for_unknown_model(self):
        """Unknown model returns None."""
        from llm_council.performance.tracker import InternalPerformanceTracker

        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = InternalPerformanceTracker(store_path=Path(tmpdir) / "metrics.jsonl")
            result = tracker.get_quality_percentile("nonexistent/model")
            assert result is None

    def test_percentile_returns_none_with_insufficient_data(self):
        """Model with insufficient sample size returns None."""
        from llm_council.performance.tracker import InternalPerformanceTracker
        from llm_council.performance.types import ModelSessionMetric

        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = InternalPerformanceTracker(store_path=Path(tmpdir) / "metrics.jsonl")

            # Record only 5 sessions (need 10 for PRELIMINARY confidence)
            for i in range(5):
                tracker.record_session(
                    f"session-{i}",
                    [
                        ModelSessionMetric(
                            session_id=f"session-{i}",
                            model_id="openai/gpt-5",
                            latency_ms=1000,
                            borda_score=0.8,
                            parse_success=True,
                        )
                    ],
                )

            result = tracker.get_quality_percentile("openai/gpt-5")
            assert result is None


class TestQualityPercentileSingleModel:
    """Test percentile with single model."""

    def test_percentile_calculation_single_model(self):
        """Single model with sufficient data is at 100th percentile."""
        from llm_council.performance.tracker import InternalPerformanceTracker
        from llm_council.performance.types import ModelSessionMetric

        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = InternalPerformanceTracker(store_path=Path(tmpdir) / "metrics.jsonl")

            # Record 10 sessions (PRELIMINARY confidence)
            for i in range(10):
                tracker.record_session(
                    f"session-{i}",
                    [
                        ModelSessionMetric(
                            session_id=f"session-{i}",
                            model_id="openai/gpt-5",
                            latency_ms=1000,
                            borda_score=0.8,
                            parse_success=True,
                        )
                    ],
                )

            result = tracker.get_quality_percentile("openai/gpt-5")
            # Single model is at 100th percentile (best among 1)
            assert result == 1.0


class TestQualityPercentileMultipleModels:
    """Test percentile with multiple models."""

    def test_percentile_calculation_multiple_models(self):
        """Percentile ranks models correctly."""
        from llm_council.performance.tracker import InternalPerformanceTracker
        from llm_council.performance.types import ModelSessionMetric

        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = InternalPerformanceTracker(store_path=Path(tmpdir) / "metrics.jsonl")

            # Model A: High score (0.9)
            for i in range(10):
                tracker.record_session(
                    f"session-a-{i}",
                    [
                        ModelSessionMetric(
                            session_id=f"session-a-{i}",
                            model_id="model-a",
                            latency_ms=1000,
                            borda_score=0.9,
                            parse_success=True,
                        )
                    ],
                )

            # Model B: Medium score (0.5)
            for i in range(10):
                tracker.record_session(
                    f"session-b-{i}",
                    [
                        ModelSessionMetric(
                            session_id=f"session-b-{i}",
                            model_id="model-b",
                            latency_ms=1000,
                            borda_score=0.5,
                            parse_success=True,
                        )
                    ],
                )

            # Model C: Low score (0.2)
            for i in range(10):
                tracker.record_session(
                    f"session-c-{i}",
                    [
                        ModelSessionMetric(
                            session_id=f"session-c-{i}",
                            model_id="model-c",
                            latency_ms=1000,
                            borda_score=0.2,
                            parse_success=True,
                        )
                    ],
                )

            # Model A should be top (1.0)
            result_a = tracker.get_quality_percentile("model-a")
            assert result_a == 1.0

            # Model B should be middle
            result_b = tracker.get_quality_percentile("model-b")
            assert 0.3 < result_b < 0.8

            # Model C should be bottom
            result_c = tracker.get_quality_percentile("model-c")
            assert result_c < 0.5

    def test_percentile_top_model_is_1_0(self):
        """Best model is at 100th percentile."""
        from llm_council.performance.tracker import InternalPerformanceTracker
        from llm_council.performance.types import ModelSessionMetric

        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = InternalPerformanceTracker(store_path=Path(tmpdir) / "metrics.jsonl")

            # Create 4 models with different scores
            for model_idx, score in enumerate([0.3, 0.5, 0.7, 0.95]):
                model_id = f"model-{model_idx}"
                for i in range(10):
                    tracker.record_session(
                        f"session-{model_id}-{i}",
                        [
                            ModelSessionMetric(
                                session_id=f"session-{model_id}-{i}",
                                model_id=model_id,
                                latency_ms=1000,
                                borda_score=score,
                                parse_success=True,
                            )
                        ],
                    )

            # Best model (0.95 score) should be at 1.0
            result = tracker.get_quality_percentile("model-3")
            assert result == 1.0

    def test_percentile_bottom_model_is_near_0(self):
        """Worst model is at low percentile."""
        from llm_council.performance.tracker import InternalPerformanceTracker
        from llm_council.performance.types import ModelSessionMetric

        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = InternalPerformanceTracker(store_path=Path(tmpdir) / "metrics.jsonl")

            # Create 4 models with different scores
            for model_idx, score in enumerate([0.1, 0.5, 0.7, 0.9]):
                model_id = f"model-{model_idx}"
                for i in range(10):
                    tracker.record_session(
                        f"session-{model_id}-{i}",
                        [
                            ModelSessionMetric(
                                session_id=f"session-{model_id}-{i}",
                                model_id=model_id,
                                latency_ms=1000,
                                borda_score=score,
                                parse_success=True,
                            )
                        ],
                    )

            # Worst model (0.1 score) should be below 0.5
            result = tracker.get_quality_percentile("model-0")
            assert result < 0.5


class TestQualityPercentile75thThreshold:
    """Test the 75th percentile threshold for graduation."""

    def test_percentile_75th_threshold(self):
        """Models can correctly pass/fail 75th percentile check."""
        from llm_council.performance.tracker import InternalPerformanceTracker
        from llm_council.performance.types import ModelSessionMetric

        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = InternalPerformanceTracker(store_path=Path(tmpdir) / "metrics.jsonl")

            # Create 8 models with evenly distributed scores
            # Scores: 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8
            for model_idx in range(8):
                score = 0.1 * (model_idx + 1)
                model_id = f"model-{model_idx}"
                for i in range(10):
                    tracker.record_session(
                        f"session-{model_id}-{i}",
                        [
                            ModelSessionMetric(
                                session_id=f"session-{model_id}-{i}",
                                model_id=model_id,
                                latency_ms=1000,
                                borda_score=score,
                                parse_success=True,
                            )
                        ],
                    )

            # Top 2 models (model-6, model-7) should be >= 75th percentile
            assert tracker.get_quality_percentile("model-7") >= 0.75  # score 0.8
            assert tracker.get_quality_percentile("model-6") >= 0.75  # score 0.7

            # Bottom 6 models should be < 75th percentile
            assert tracker.get_quality_percentile("model-0") < 0.75  # score 0.1


class TestGetAllModelScores:
    """Test get_all_model_scores helper method."""

    def test_get_all_model_scores_returns_all_tracked(self):
        """get_all_model_scores returns scores for all tracked models."""
        from llm_council.performance.tracker import InternalPerformanceTracker
        from llm_council.performance.types import ModelSessionMetric

        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = InternalPerformanceTracker(store_path=Path(tmpdir) / "metrics.jsonl")

            # Record sessions for 3 models
            for model_id, score in [("a", 0.8), ("b", 0.5), ("c", 0.3)]:
                for i in range(10):
                    tracker.record_session(
                        f"session-{model_id}-{i}",
                        [
                            ModelSessionMetric(
                                session_id=f"session-{model_id}-{i}",
                                model_id=model_id,
                                latency_ms=1000,
                                borda_score=score,
                                parse_success=True,
                            )
                        ],
                    )

            scores = tracker.get_all_model_scores()

            assert len(scores) == 3
            assert "a" in scores
            assert "b" in scores
            assert "c" in scores
            # Verify approximate scores (may have decay effects)
            assert scores["a"] > scores["b"] > scores["c"]
