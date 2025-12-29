"""TDD tests for ADR-026 Phase 3: InternalPerformanceTracker.

Tests for the tracker class with rolling window decay and aggregation.
Written BEFORE implementation per TDD workflow.
"""

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


class TestInternalPerformanceTrackerInit:
    """Test InternalPerformanceTracker initialization."""

    def test_tracker_exists(self):
        """InternalPerformanceTracker class should exist."""
        from llm_council.performance.tracker import InternalPerformanceTracker

        tracker = InternalPerformanceTracker()
        assert tracker is not None

    def test_tracker_accepts_custom_store_path(self):
        """Tracker should accept custom store path."""
        from llm_council.performance.tracker import InternalPerformanceTracker

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "custom.jsonl"
            tracker = InternalPerformanceTracker(store_path=path)
            assert tracker.store_path == path

    def test_tracker_accepts_decay_days(self):
        """Tracker should accept custom decay_days."""
        from llm_council.performance.tracker import InternalPerformanceTracker

        tracker = InternalPerformanceTracker(decay_days=60)
        assert tracker.decay_days == 60

    def test_tracker_default_decay_days(self):
        """Tracker should default to 30 decay_days."""
        from llm_council.performance.tracker import InternalPerformanceTracker

        tracker = InternalPerformanceTracker()
        assert tracker.decay_days == 30


class TestRecordSession:
    """Test record_session() method."""

    def test_record_session_appends_metrics(self):
        """record_session() should append metrics to store."""
        from llm_council.performance.tracker import InternalPerformanceTracker
        from llm_council.performance.types import ModelSessionMetric

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "metrics.jsonl"
            tracker = InternalPerformanceTracker(store_path=path)

            metrics = [
                ModelSessionMetric(
                    session_id="s1",
                    model_id="openai/gpt-4o",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    latency_ms=1500,
                    borda_score=0.75,
                ),
            ]
            count = tracker.record_session("s1", metrics)

            assert count == 1
            assert path.exists()

    def test_record_session_with_multiple_models(self):
        """record_session() should record metrics for multiple models."""
        from llm_council.performance.tracker import InternalPerformanceTracker
        from llm_council.performance.types import ModelSessionMetric

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "metrics.jsonl"
            tracker = InternalPerformanceTracker(store_path=path)

            metrics = [
                ModelSessionMetric(session_id="s1", model_id="openai/gpt-4o", borda_score=0.8),
                ModelSessionMetric(session_id="s1", model_id="anthropic/claude", borda_score=0.7),
                ModelSessionMetric(session_id="s1", model_id="google/gemini", borda_score=0.6),
            ]
            count = tracker.record_session("s1", metrics)

            assert count == 3


class TestGetModelIndex:
    """Test get_model_index() method."""

    def test_get_model_index_returns_aggregated_data(self):
        """get_model_index() should return ModelPerformanceIndex."""
        from llm_council.performance.tracker import InternalPerformanceTracker
        from llm_council.performance.types import ModelPerformanceIndex, ModelSessionMetric

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "metrics.jsonl"
            tracker = InternalPerformanceTracker(store_path=path)

            now = datetime.now(timezone.utc).isoformat()
            metrics = [
                ModelSessionMetric(
                    session_id="s1",
                    model_id="openai/gpt-4o",
                    timestamp=now,
                    latency_ms=1000,
                    borda_score=0.8,
                    parse_success=True,
                ),
                ModelSessionMetric(
                    session_id="s2",
                    model_id="openai/gpt-4o",
                    timestamp=now,
                    latency_ms=1200,
                    borda_score=0.7,
                    parse_success=True,
                ),
            ]
            tracker.record_session("s1", [metrics[0]])
            tracker.record_session("s2", [metrics[1]])

            index = tracker.get_model_index("openai/gpt-4o")

            assert isinstance(index, ModelPerformanceIndex)
            assert index.model_id == "openai/gpt-4o"
            assert index.sample_size == 2

    def test_get_model_index_with_no_data_returns_cold_start(self):
        """get_model_index() should return cold start defaults for unknown model."""
        from llm_council.performance.tracker import InternalPerformanceTracker

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "metrics.jsonl"
            tracker = InternalPerformanceTracker(store_path=path)

            index = tracker.get_model_index("unknown/model")

            assert index.model_id == "unknown/model"
            assert index.sample_size == 0
            assert index.mean_borda_score == 0.5  # Neutral
            assert index.confidence_level == "INSUFFICIENT"

    def test_mean_borda_score_calculation(self):
        """get_model_index() should calculate mean Borda score."""
        from llm_council.performance.tracker import InternalPerformanceTracker
        from llm_council.performance.types import ModelSessionMetric

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "metrics.jsonl"
            tracker = InternalPerformanceTracker(store_path=path)

            now = datetime.now(timezone.utc).isoformat()
            for i, score in enumerate([0.6, 0.8, 0.7]):
                tracker.record_session(
                    f"s{i}",
                    [
                        ModelSessionMetric(
                            session_id=f"s{i}",
                            model_id="test-model",
                            timestamp=now,
                            borda_score=score,
                        ),
                    ],
                )

            index = tracker.get_model_index("test-model")
            # Mean of [0.6, 0.8, 0.7] = 0.7
            assert abs(index.mean_borda_score - 0.7) < 0.01

    def test_parse_success_rate_calculation(self):
        """get_model_index() should calculate parse success rate."""
        from llm_council.performance.tracker import InternalPerformanceTracker
        from llm_council.performance.types import ModelSessionMetric

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "metrics.jsonl"
            tracker = InternalPerformanceTracker(store_path=path)

            now = datetime.now(timezone.utc).isoformat()
            # 3 successes, 1 failure = 75% success rate
            tracker.record_session(
                "s1",
                [
                    ModelSessionMetric(
                        session_id="s1", model_id="m1", timestamp=now, parse_success=True
                    )
                ],
            )
            tracker.record_session(
                "s2",
                [
                    ModelSessionMetric(
                        session_id="s2", model_id="m1", timestamp=now, parse_success=True
                    )
                ],
            )
            tracker.record_session(
                "s3",
                [
                    ModelSessionMetric(
                        session_id="s3", model_id="m1", timestamp=now, parse_success=True
                    )
                ],
            )
            tracker.record_session(
                "s4",
                [
                    ModelSessionMetric(
                        session_id="s4", model_id="m1", timestamp=now, parse_success=False
                    )
                ],
            )

            index = tracker.get_model_index("m1")
            assert index.parse_success_rate == 0.75


class TestLatencyPercentiles:
    """Test latency percentile calculations."""

    def test_p50_latency_calculation(self):
        """get_model_index() should calculate p50 latency."""
        from llm_council.performance.tracker import InternalPerformanceTracker
        from llm_council.performance.types import ModelSessionMetric

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "metrics.jsonl"
            tracker = InternalPerformanceTracker(store_path=path)

            now = datetime.now(timezone.utc).isoformat()
            latencies = [1000, 1200, 1100, 1300, 1150]
            for i, lat in enumerate(latencies):
                tracker.record_session(
                    f"s{i}",
                    [
                        ModelSessionMetric(
                            session_id=f"s{i}", model_id="m1", timestamp=now, latency_ms=lat
                        ),
                    ],
                )

            index = tracker.get_model_index("m1")
            # Sorted: [1000, 1100, 1150, 1200, 1300], median = 1150
            assert index.p50_latency_ms == 1150

    def test_p95_latency_calculation(self):
        """get_model_index() should calculate p95 latency."""
        from llm_council.performance.tracker import InternalPerformanceTracker
        from llm_council.performance.types import ModelSessionMetric

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "metrics.jsonl"
            tracker = InternalPerformanceTracker(store_path=path)

            now = datetime.now(timezone.utc).isoformat()
            # 20 samples to make percentiles meaningful
            latencies = list(range(100, 2100, 100))  # [100, 200, ..., 2000]
            for i, lat in enumerate(latencies):
                tracker.record_session(
                    f"s{i}",
                    [
                        ModelSessionMetric(
                            session_id=f"s{i}", model_id="m1", timestamp=now, latency_ms=lat
                        ),
                    ],
                )

            index = tracker.get_model_index("m1")
            # 95th percentile of [100..2000] should be around 1900-2000
            assert index.p95_latency_ms >= 1800


class TestRollingWindowDecay:
    """Test exponential decay weighting for rolling window."""

    def test_recent_sessions_weighted_higher(self):
        """Recent sessions should have higher weight than older ones."""
        from llm_council.performance.tracker import InternalPerformanceTracker
        from llm_council.performance.types import ModelSessionMetric

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "metrics.jsonl"
            tracker = InternalPerformanceTracker(store_path=path, decay_days=30)

            now = datetime.now(timezone.utc)
            old_date = (now - timedelta(days=60)).isoformat()
            recent_date = now.isoformat()

            # Old session with low score
            tracker.record_session(
                "old",
                [
                    ModelSessionMetric(
                        session_id="old", model_id="m1", timestamp=old_date, borda_score=0.2
                    ),
                ],
            )
            # Recent session with high score
            tracker.record_session(
                "recent",
                [
                    ModelSessionMetric(
                        session_id="recent", model_id="m1", timestamp=recent_date, borda_score=0.9
                    ),
                ],
            )

            index = tracker.get_model_index("m1")
            # With decay, mean should be closer to 0.9 (recent) than 0.55 (simple mean)
            assert index.mean_borda_score > 0.6

    def test_very_old_sessions_have_minimal_weight(self):
        """Sessions older than 2*decay_days should have minimal impact."""
        from llm_council.performance.tracker import InternalPerformanceTracker
        from llm_council.performance.types import ModelSessionMetric

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "metrics.jsonl"
            tracker = InternalPerformanceTracker(store_path=path, decay_days=30)

            now = datetime.now(timezone.utc)
            very_old = (now - timedelta(days=90)).isoformat()
            recent = now.isoformat()

            # Very old session with extreme low score
            tracker.record_session(
                "old",
                [
                    ModelSessionMetric(
                        session_id="old", model_id="m1", timestamp=very_old, borda_score=0.0
                    ),
                ],
            )
            # Recent session with normal score
            tracker.record_session(
                "recent",
                [
                    ModelSessionMetric(
                        session_id="recent", model_id="m1", timestamp=recent, borda_score=0.7
                    ),
                ],
            )

            index = tracker.get_model_index("m1")
            # Very old session should barely affect the score
            assert index.mean_borda_score > 0.6


class TestConfidenceLevels:
    """Test statistical confidence determination."""

    def test_insufficient_below_10_samples(self):
        """Confidence should be INSUFFICIENT for <10 samples."""
        from llm_council.performance.tracker import InternalPerformanceTracker
        from llm_council.performance.types import ModelSessionMetric

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "metrics.jsonl"
            tracker = InternalPerformanceTracker(store_path=path)

            now = datetime.now(timezone.utc).isoformat()
            for i in range(5):
                tracker.record_session(
                    f"s{i}",
                    [
                        ModelSessionMetric(session_id=f"s{i}", model_id="m1", timestamp=now),
                    ],
                )

            index = tracker.get_model_index("m1")
            assert index.confidence_level == "INSUFFICIENT"

    def test_preliminary_10_to_30_samples(self):
        """Confidence should be PRELIMINARY for 10-30 samples."""
        from llm_council.performance.tracker import InternalPerformanceTracker
        from llm_council.performance.types import ModelSessionMetric

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "metrics.jsonl"
            tracker = InternalPerformanceTracker(store_path=path)

            now = datetime.now(timezone.utc).isoformat()
            for i in range(15):
                tracker.record_session(
                    f"s{i}",
                    [
                        ModelSessionMetric(session_id=f"s{i}", model_id="m1", timestamp=now),
                    ],
                )

            index = tracker.get_model_index("m1")
            assert index.confidence_level == "PRELIMINARY"

    def test_moderate_30_to_100_samples(self):
        """Confidence should be MODERATE for 30-100 samples."""
        from llm_council.performance.tracker import InternalPerformanceTracker
        from llm_council.performance.types import ModelSessionMetric

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "metrics.jsonl"
            tracker = InternalPerformanceTracker(store_path=path)

            now = datetime.now(timezone.utc).isoformat()
            for i in range(50):
                tracker.record_session(
                    f"s{i}",
                    [
                        ModelSessionMetric(session_id=f"s{i}", model_id="m1", timestamp=now),
                    ],
                )

            index = tracker.get_model_index("m1")
            assert index.confidence_level == "MODERATE"

    def test_high_100_plus_samples(self):
        """Confidence should be HIGH for 100+ samples."""
        from llm_council.performance.tracker import InternalPerformanceTracker
        from llm_council.performance.types import ModelSessionMetric

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "metrics.jsonl"
            tracker = InternalPerformanceTracker(store_path=path)

            now = datetime.now(timezone.utc).isoformat()
            for i in range(120):
                tracker.record_session(
                    f"s{i}",
                    [
                        ModelSessionMetric(session_id=f"s{i}", model_id="m1", timestamp=now),
                    ],
                )

            index = tracker.get_model_index("m1")
            assert index.confidence_level == "HIGH"


class TestGetQualityScore:
    """Test get_quality_score() method for selection.py integration."""

    def test_get_quality_score_returns_0_100_range(self):
        """get_quality_score() should return 0-100 normalized score."""
        from llm_council.performance.tracker import InternalPerformanceTracker
        from llm_council.performance.types import ModelSessionMetric

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "metrics.jsonl"
            tracker = InternalPerformanceTracker(store_path=path)

            now = datetime.now(timezone.utc).isoformat()
            tracker.record_session(
                "s1",
                [
                    ModelSessionMetric(
                        session_id="s1", model_id="m1", timestamp=now, borda_score=0.75
                    ),
                ],
            )

            score = tracker.get_quality_score("m1")
            assert 0 <= score <= 100

    def test_cold_start_returns_50(self):
        """Cold start models should get neutral 50 score."""
        from llm_council.performance.tracker import InternalPerformanceTracker

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "metrics.jsonl"
            tracker = InternalPerformanceTracker(store_path=path)

            score = tracker.get_quality_score("unknown/model")
            assert score == 50

    def test_quality_score_based_on_borda(self):
        """Quality score should be based on mean Borda score."""
        from llm_council.performance.tracker import InternalPerformanceTracker
        from llm_council.performance.types import ModelSessionMetric

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "metrics.jsonl"
            tracker = InternalPerformanceTracker(store_path=path)

            now = datetime.now(timezone.utc).isoformat()
            # Record high Borda score
            tracker.record_session(
                "s1",
                [
                    ModelSessionMetric(
                        session_id="s1", model_id="m1", timestamp=now, borda_score=0.9
                    ),
                ],
            )

            score = tracker.get_quality_score("m1")
            # 0.9 * 100 = 90
            assert score >= 85


class TestPerformanceTrackerModuleExports:
    """Test that tracker is exported from performance module."""

    def test_exports_internal_performance_tracker(self):
        """performance module should export InternalPerformanceTracker."""
        from llm_council.performance import InternalPerformanceTracker

        assert InternalPerformanceTracker is not None
