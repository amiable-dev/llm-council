"""TDD tests for ADR-020 Tier 1: Shadow Council Sampling.

Tests the shadow sampling mechanism that randomly samples fast-path queries
through the full council to measure "regret rate" and detect routing drift.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass
import random

from llm_council.triage.shadow_sampling import (
    ShadowSampler,
    ShadowSamplingConfig,
    ShadowSampleResult,
    DisagreementDetector,
    ShadowMetricStore,
)


class TestShadowSamplingConfig:
    """Test ShadowSamplingConfig defaults and validation."""

    def test_default_config(self):
        """Default config should have sensible values."""
        config = ShadowSamplingConfig()
        assert config.enabled is True  # Enabled when fast path is enabled
        assert config.sampling_rate == 0.05  # 5% default
        assert config.disagreement_threshold == 0.08  # 8% default
        assert config.window_size == 100

    def test_config_from_env(self):
        """Config should be loadable from environment variables."""
        with patch.dict(
            "os.environ",
            {
                "LLM_COUNCIL_SHADOW_SAMPLING_RATE": "0.10",
                "LLM_COUNCIL_SHADOW_DISAGREEMENT_THRESHOLD": "0.15",
                "LLM_COUNCIL_SHADOW_WINDOW_SIZE": "200",
            },
        ):
            config = ShadowSamplingConfig.from_env()
            assert config.sampling_rate == 0.10
            assert config.disagreement_threshold == 0.15
            assert config.window_size == 200

    def test_config_validation_rate_range(self):
        """Sampling rate must be between 0 and 1."""
        with pytest.raises(ValueError, match="rate"):
            ShadowSamplingConfig(sampling_rate=1.5)

        with pytest.raises(ValueError, match="rate"):
            ShadowSamplingConfig(sampling_rate=-0.1)


class TestShadowSampler:
    """Test ShadowSampler random selection."""

    @pytest.fixture
    def sampler(self):
        """Create a sampler with 5% rate."""
        config = ShadowSamplingConfig(sampling_rate=0.05)
        return ShadowSampler(config)

    def test_should_sample_respects_rate(self, sampler):
        """Over many iterations, sampling should match configured rate."""
        # Set seed for reproducibility
        random.seed(42)

        sampled = sum(1 for _ in range(10000) if sampler.should_sample())

        # Should be approximately 5% (±2% tolerance)
        rate = sampled / 10000
        assert 0.03 <= rate <= 0.07

    def test_should_sample_deterministic(self):
        """Deterministic mode should always return same result for same input."""
        config = ShadowSamplingConfig(sampling_rate=0.05, deterministic_seed=42)
        sampler = ShadowSampler(config)

        # Same seed should give same sequence
        results1 = [sampler.should_sample() for _ in range(100)]

        # Reset
        sampler = ShadowSampler(config)
        results2 = [sampler.should_sample() for _ in range(100)]

        assert results1 == results2

    def test_should_sample_query_hash_deterministic(self, sampler):
        """Same query should consistently be sampled or not."""
        query = "What is 2+2?"

        # Same query should give same result
        result1 = sampler.should_sample_query(query)
        result2 = sampler.should_sample_query(query)
        assert result1 == result2


class TestShadowSampleResult:
    """Test ShadowSampleResult dataclass."""

    def test_agreement_result(self):
        """Result when fast path agrees with council."""
        result = ShadowSampleResult(
            query_hash="abc123",
            fast_path_model="openai/gpt-4o-mini",
            fast_path_response="The answer is 4.",
            council_consensus="The answer is 4.",
            agreement_score=0.98,
            timestamp=1234567890.0,
        )
        assert result.is_agreement is True
        assert result.agreement_score >= 0.9

    def test_disagreement_result(self):
        """Result when fast path disagrees with council."""
        result = ShadowSampleResult(
            query_hash="abc123",
            fast_path_model="openai/gpt-4o-mini",
            fast_path_response="The answer is 5.",
            council_consensus="The answer is 4.",
            agreement_score=0.45,
            timestamp=1234567890.0,
        )
        assert result.is_agreement is False
        assert result.agreement_score < 0.9


class TestDisagreementDetector:
    """Test DisagreementDetector comparison logic."""

    @pytest.fixture
    def detector(self):
        """Create a disagreement detector."""
        return DisagreementDetector()

    def test_exact_match_high_agreement(self, detector):
        """Exact text match should have high agreement."""
        score = detector.compute_agreement(
            "The answer is 42.",
            "The answer is 42.",
        )
        assert score >= 0.99

    def test_semantic_similar_high_agreement(self, detector):
        """Semantically similar should have high agreement."""
        # Use responses with significant word overlap
        score = detector.compute_agreement(
            "The answer to your question is 42. This is the correct result.",
            "The answer to your question is 42. This is the right result.",
        )
        # Word-based similarity won't be perfect for synonyms
        assert score >= 0.7

    def test_different_answers_low_agreement(self, detector):
        """Different answers should have low agreement."""
        score = detector.compute_agreement(
            "The answer is 42.",
            "The answer is 100.",
        )
        # Low but not zero (some words match)
        assert score < 0.8

    def test_completely_different_lowest_agreement(self, detector):
        """Completely different responses should have very low agreement."""
        score = detector.compute_agreement(
            "The quick brown fox jumps over the lazy dog.",
            "Python is a programming language.",
        )
        assert score < 0.5

    def test_normalized_comparison(self, detector):
        """Comparison should be case-insensitive and ignore whitespace."""
        score = detector.compute_agreement(
            "  The Answer Is 42.  ",
            "the answer is 42",
        )
        assert score >= 0.9


class TestShadowMetricStore:
    """Test ShadowMetricStore persistence and rate calculation."""

    @pytest.fixture
    def store(self, tmp_path):
        """Create a metric store with temp file."""
        config = ShadowSamplingConfig(window_size=10)
        store_path = tmp_path / "shadow_metrics.jsonl"
        return ShadowMetricStore(config, store_path=str(store_path))

    def test_record_result(self, store):
        """Should record shadow sampling results."""
        result = ShadowSampleResult(
            query_hash="abc123",
            fast_path_model="openai/gpt-4o-mini",
            fast_path_response="Answer A",
            council_consensus="Answer A",
            agreement_score=0.95,
            timestamp=1234567890.0,
        )

        store.record(result)
        assert len(store.get_recent_results()) == 1

    def test_calculate_disagreement_rate_all_agree(self, store):
        """Rate should be 0 when all samples agree."""
        for i in range(10):
            store.record(
                ShadowSampleResult(
                    query_hash=f"hash{i}",
                    fast_path_model="openai/gpt-4o-mini",
                    fast_path_response="Same answer",
                    council_consensus="Same answer",
                    agreement_score=0.95,
                    timestamp=float(i),
                )
            )

        rate = store.get_disagreement_rate()
        assert rate == 0.0

    def test_calculate_disagreement_rate_half_disagree(self, store):
        """Rate should reflect actual disagreement proportion."""
        # 5 agreements
        for i in range(5):
            store.record(
                ShadowSampleResult(
                    query_hash=f"agree{i}",
                    fast_path_model="openai/gpt-4o-mini",
                    fast_path_response="Answer A",
                    council_consensus="Answer A",
                    agreement_score=0.95,
                    timestamp=float(i),
                )
            )

        # 5 disagreements
        for i in range(5):
            store.record(
                ShadowSampleResult(
                    query_hash=f"disagree{i}",
                    fast_path_model="openai/gpt-4o-mini",
                    fast_path_response="Answer A",
                    council_consensus="Answer B",
                    agreement_score=0.40,
                    timestamp=float(i + 5),
                )
            )

        rate = store.get_disagreement_rate()
        assert rate == 0.5

    def test_rolling_window(self, store):
        """Store should only keep last N results (window_size)."""
        # Add more than window_size results
        for i in range(20):
            store.record(
                ShadowSampleResult(
                    query_hash=f"hash{i}",
                    fast_path_model="openai/gpt-4o-mini",
                    fast_path_response="Answer",
                    council_consensus="Answer",
                    agreement_score=0.95,
                    timestamp=float(i),
                )
            )

        # Should only have window_size (10) results
        recent = store.get_recent_results()
        assert len(recent) == 10

    def test_threshold_breach_detection(self, store):
        """Should detect when disagreement rate exceeds threshold."""
        # Add 9 disagreements (90% disagreement rate)
        for i in range(9):
            store.record(
                ShadowSampleResult(
                    query_hash=f"hash{i}",
                    fast_path_model="openai/gpt-4o-mini",
                    fast_path_response="Fast answer",
                    council_consensus="Council answer",
                    agreement_score=0.30,
                    timestamp=float(i),
                )
            )

        # Add 1 agreement
        store.record(
            ShadowSampleResult(
                query_hash="agree",
                fast_path_model="openai/gpt-4o-mini",
                fast_path_response="Same",
                council_consensus="Same",
                agreement_score=0.95,
                timestamp=10.0,
            )
        )

        # 90% disagreement should exceed 8% threshold
        assert store.is_threshold_breached() is True

    def test_persistence(self, store, tmp_path):
        """Results should persist across store instances."""
        store.record(
            ShadowSampleResult(
                query_hash="persist_test",
                fast_path_model="openai/gpt-4o-mini",
                fast_path_response="Answer",
                council_consensus="Answer",
                agreement_score=0.95,
                timestamp=1234567890.0,
            )
        )

        # Create new store instance with same path
        config = ShadowSamplingConfig(window_size=10)
        store_path = tmp_path / "shadow_metrics.jsonl"
        new_store = ShadowMetricStore(config, store_path=str(store_path))

        # Should load persisted result
        results = new_store.get_recent_results()
        assert len(results) == 1
        assert results[0].query_hash == "persist_test"


class TestShadowSamplingIntegration:
    """Test shadow sampling integration with fast path."""

    @pytest.mark.asyncio
    async def test_shadow_sample_runs_council_in_parallel(self):
        """Shadow sampling should run council alongside fast path."""
        from llm_council.triage.shadow_sampling import run_shadow_sample

        # Patch at the module where it's imported
        with patch("llm_council.council.run_full_council") as mock_council:
            mock_council.return_value = {
                "stage3": {"content": "Council answer"},
            }

            fast_path_result = MagicMock()
            fast_path_result.response = "Fast path answer"
            fast_path_result.model = "openai/gpt-4o-mini"

            result = await run_shadow_sample(
                query="What is 2+2?",
                fast_path_result=fast_path_result,
            )

            # Council should have been called
            mock_council.assert_called_once()
            assert result is not None
