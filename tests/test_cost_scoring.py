"""TDD Tests for ADR-030 Phase 1: Cost Scoring Algorithms.

Tests are written FIRST (RED phase) per TDD methodology.
Issue: https://github.com/amiable-dev/llm-council/issues/137

Cost scoring algorithms must:
1. Handle exponential price differences (log-ratio)
2. Never return negative values
3. Return 1.0 for free models
4. Be configurable via environment and config
"""

import math
import os
from unittest.mock import patch

import pytest


class TestLogRatioCostScoring:
    """Test log-ratio cost scoring algorithm.

    Formula: score = 0.5 - (log10(price/reference_high) * 0.25)
    Clamp to [0, 1]
    """

    def test_free_model_returns_one(self):
        """Free models (price=0) should return score of 1.0."""
        from llm_council.metadata.scoring import get_cost_score_log_ratio

        score = get_cost_score_log_ratio(0.0)
        assert score == 1.0

    def test_reference_price_returns_half(self):
        """Reference price ($0.015) should return score of 0.5.

        At reference: log10(0.015/0.015) = log10(1) = 0
        score = 0.5 - (0 * 0.25) = 0.5
        """
        from llm_council.metadata.scoring import get_cost_score_log_ratio

        score = get_cost_score_log_ratio(0.015, reference_high=0.015)
        assert score == pytest.approx(0.5, abs=0.01)

    def test_cheap_model_returns_high_score(self):
        """Cheap models ($0.001) should return high scores (>0.7).

        At $0.001: log10(0.001/0.015) = log10(0.0667) = -1.18
        score = 0.5 - (-1.18 * 0.25) = 0.5 + 0.295 = 0.795
        """
        from llm_council.metadata.scoring import get_cost_score_log_ratio

        score = get_cost_score_log_ratio(0.001, reference_high=0.015)
        assert score > 0.7
        assert score < 1.0

    def test_expensive_model_returns_low_score(self):
        """Expensive models ($0.030) should return lower scores but still positive.

        At $0.030: log10(0.030/0.015) = log10(2) = 0.301
        score = 0.5 - (0.301 * 0.25) = 0.5 - 0.075 = 0.425
        """
        from llm_council.metadata.scoring import get_cost_score_log_ratio

        score = get_cost_score_log_ratio(0.030, reference_high=0.015)
        assert score > 0.0
        assert score < 0.5
        assert score == pytest.approx(0.425, abs=0.05)

    def test_very_expensive_model_stays_positive(self):
        """Very expensive models ($0.15 = 10x reference) stay positive.

        At $0.15: log10(0.15/0.015) = log10(10) = 1
        score = 0.5 - (1 * 0.25) = 0.25
        """
        from llm_council.metadata.scoring import get_cost_score_log_ratio

        score = get_cost_score_log_ratio(0.15, reference_high=0.015)
        assert score == pytest.approx(0.25, abs=0.01)

    def test_never_returns_negative(self):
        """Even extremely expensive models must never return negative."""
        from llm_council.metadata.scoring import get_cost_score_log_ratio

        # Test at 100x reference price
        score = get_cost_score_log_ratio(1.5, reference_high=0.015)
        assert score >= 0.0

        # Test at 1000x reference price
        score = get_cost_score_log_ratio(15.0, reference_high=0.015)
        assert score >= 0.0

    def test_never_exceeds_one(self):
        """Score must never exceed 1.0."""
        from llm_council.metadata.scoring import get_cost_score_log_ratio

        # Test at extremely low price
        score = get_cost_score_log_ratio(0.0000001, reference_high=0.015)
        assert score <= 1.0

    def test_minimum_price_floor(self):
        """Price floor prevents log(0) errors."""
        from llm_council.metadata.scoring import MIN_PRICE, get_cost_score_log_ratio

        # Zero price should be treated as MIN_PRICE
        score_zero = get_cost_score_log_ratio(0.0)
        score_min = get_cost_score_log_ratio(MIN_PRICE)

        # Both should return valid scores (floor applied)
        assert score_zero >= 0.0
        assert score_zero <= 1.0

    def test_custom_reference_high(self):
        """Custom reference_high parameter works correctly."""
        from llm_council.metadata.scoring import get_cost_score_log_ratio

        # At reference price, should return 0.5
        score = get_cost_score_log_ratio(0.10, reference_high=0.10)
        assert score == pytest.approx(0.5, abs=0.01)


class TestExponentialCostScoring:
    """Test exponential decay cost scoring algorithm.

    Formula: score = exp(-price / reference_high)
    """

    def test_free_model_returns_one(self):
        """Free models (price=0) should return score of 1.0."""
        from llm_council.metadata.scoring import get_cost_score_exponential

        score = get_cost_score_exponential(0.0)
        assert score == pytest.approx(1.0, abs=0.001)

    def test_exponential_decay_curve(self):
        """Verify exponential decay behavior."""
        from llm_council.metadata.scoring import get_cost_score_exponential

        # At reference price: exp(-1) = 0.368
        score_ref = get_cost_score_exponential(0.015, reference_high=0.015)
        assert score_ref == pytest.approx(math.exp(-1), abs=0.01)

        # At 2x reference: exp(-2) = 0.135
        score_2x = get_cost_score_exponential(0.030, reference_high=0.015)
        assert score_2x == pytest.approx(math.exp(-2), abs=0.01)

        # Verify monotonically decreasing
        assert score_ref > score_2x

    def test_exponential_never_negative(self):
        """Exponential function is always positive."""
        from llm_council.metadata.scoring import get_cost_score_exponential

        score = get_cost_score_exponential(100.0)
        assert score >= 0.0

    def test_exponential_approaches_zero(self):
        """Very expensive models approach but never reach zero."""
        from llm_council.metadata.scoring import get_cost_score_exponential

        score = get_cost_score_exponential(1.0, reference_high=0.015)
        assert score > 0.0
        assert score < 0.01  # Very small but positive


class TestLinearCostScoring:
    """Test backward-compatible linear cost scoring.

    Formula: score = 1.0 - (price / reference_high)
    Clamp to [0, 1]

    Note: This formula breaks for expensive models (negative values before clamping).
    """

    def test_free_model_returns_one(self):
        """Free models should return 1.0."""
        from llm_council.metadata.scoring import get_cost_score_linear

        score = get_cost_score_linear(0.0)
        assert score == 1.0

    def test_reference_price_returns_zero(self):
        """Reference price returns 0.0 (after clamping)."""
        from llm_council.metadata.scoring import get_cost_score_linear

        score = get_cost_score_linear(0.015, reference_high=0.015)
        assert score == 0.0

    def test_linear_clamps_at_zero(self):
        """Expensive models should clamp at 0, not go negative."""
        from llm_council.metadata.scoring import get_cost_score_linear

        # 2x reference would be -1.0 without clamping
        score = get_cost_score_linear(0.030, reference_high=0.015)
        assert score == 0.0

    def test_linear_backward_compatible(self):
        """Verify linear matches legacy behavior (with clamping)."""
        from llm_council.metadata.scoring import get_cost_score_linear

        # Cheap model
        score = get_cost_score_linear(0.001, reference_high=0.015)
        expected = 1.0 - (0.001 / 0.015)
        assert score == pytest.approx(expected, abs=0.01)


class TestCostScoreAlgorithmSelection:
    """Test unified get_cost_score with algorithm selection."""

    def test_default_algorithm_is_log_ratio(self):
        """Default algorithm should be log_ratio per ADR-030."""
        from llm_council.metadata.scoring import get_cost_score

        # Without specifying algorithm, should use log_ratio
        score = get_cost_score(0.015, reference_high=0.015)
        # Log-ratio returns 0.5 at reference price
        assert score == pytest.approx(0.5, abs=0.01)

    def test_linear_algorithm_backward_compatible(self):
        """Explicit linear algorithm for backward compatibility."""
        from llm_council.metadata.scoring import get_cost_score

        score = get_cost_score(0.015, reference_high=0.015, algorithm="linear")
        # Linear returns 0.0 at reference price
        assert score == 0.0

    def test_exponential_algorithm_selection(self):
        """Explicit exponential algorithm selection."""
        from llm_council.metadata.scoring import get_cost_score

        score = get_cost_score(0.015, reference_high=0.015, algorithm="exponential")
        # Exponential returns exp(-1) at reference price
        assert score == pytest.approx(math.exp(-1), abs=0.01)

    def test_invalid_algorithm_raises_error(self):
        """Invalid algorithm name should raise ValueError."""
        from llm_council.metadata.scoring import get_cost_score

        with pytest.raises(ValueError, match="Unknown cost scoring algorithm"):
            get_cost_score(0.01, algorithm="invalid")


class TestCostScoreConfiguration:
    """Test configuration of cost scoring via config and environment."""

    def test_env_var_overrides_default_algorithm(self):
        """LLM_COUNCIL_COST_SCALE env var overrides default algorithm."""
        from llm_council.metadata.scoring import get_cost_score_with_config

        with patch.dict(os.environ, {"LLM_COUNCIL_COST_SCALE": "exponential"}):
            score = get_cost_score_with_config(0.015, reference_high=0.015)
            # Exponential returns exp(-1) at reference price
            assert score == pytest.approx(math.exp(-1), abs=0.01)

    def test_env_var_linear_override(self):
        """LLM_COUNCIL_COST_SCALE=linear selects linear algorithm."""
        from llm_council.metadata.scoring import get_cost_score_with_config

        with patch.dict(os.environ, {"LLM_COUNCIL_COST_SCALE": "linear"}):
            score = get_cost_score_with_config(0.015, reference_high=0.015)
            # Linear returns 0.0 at reference price
            assert score == 0.0

    def test_env_var_log_ratio_override(self):
        """LLM_COUNCIL_COST_SCALE=log_ratio selects log_ratio algorithm."""
        from llm_council.metadata.scoring import get_cost_score_with_config

        with patch.dict(os.environ, {"LLM_COUNCIL_COST_SCALE": "log_ratio"}):
            score = get_cost_score_with_config(0.015, reference_high=0.015)
            # Log-ratio returns 0.5 at reference price
            assert score == pytest.approx(0.5, abs=0.01)

    def test_invalid_env_var_uses_default(self):
        """Invalid env var value falls back to default (log_ratio)."""
        from llm_council.metadata.scoring import get_cost_score_with_config

        with patch.dict(os.environ, {"LLM_COUNCIL_COST_SCALE": "invalid_value"}):
            # Should use default (log_ratio) and not crash
            score = get_cost_score_with_config(0.015, reference_high=0.015)
            assert score == pytest.approx(0.5, abs=0.01)


class TestCostScoreEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_negative_price_treated_as_zero(self):
        """Negative prices (invalid) should be treated as zero."""
        from llm_council.metadata.scoring import get_cost_score_log_ratio

        score = get_cost_score_log_ratio(-0.01)
        assert score == 1.0

    def test_none_price_raises_error(self):
        """None price should raise TypeError."""
        from llm_council.metadata.scoring import get_cost_score_log_ratio

        with pytest.raises(TypeError):
            get_cost_score_log_ratio(None)

    def test_very_small_reference_high(self):
        """Very small reference_high should still work."""
        from llm_council.metadata.scoring import get_cost_score_log_ratio

        score = get_cost_score_log_ratio(0.0001, reference_high=0.0001)
        assert score == pytest.approx(0.5, abs=0.01)

    def test_zero_reference_high_raises_error(self):
        """Zero reference_high should raise ValueError."""
        from llm_council.metadata.scoring import get_cost_score_log_ratio

        with pytest.raises((ValueError, ZeroDivisionError)):
            get_cost_score_log_ratio(0.01, reference_high=0.0)


class TestCostScoreComparison:
    """Compare behavior of different algorithms for documentation."""

    def test_algorithm_comparison_table(self):
        """Generate comparison of algorithms at various price points.

        This test documents the behavior differences for ADR-030.
        """
        from llm_council.metadata.scoring import (
            get_cost_score_exponential,
            get_cost_score_linear,
            get_cost_score_log_ratio,
        )

        prices = [0.0, 0.001, 0.005, 0.015, 0.030, 0.060, 0.150]
        ref = 0.015

        for price in prices:
            linear = get_cost_score_linear(price, ref)
            log_ratio = get_cost_score_log_ratio(price, ref)
            exponential = get_cost_score_exponential(price, ref)

            # All algorithms should return valid scores
            assert 0.0 <= linear <= 1.0, f"Linear out of range at price={price}"
            assert 0.0 <= log_ratio <= 1.0, f"Log-ratio out of range at price={price}"
            assert 0.0 <= exponential <= 1.0, f"Exponential out of range at price={price}"

            # Log-ratio should be more forgiving for expensive models
            if price > ref:
                assert log_ratio > linear, f"Log-ratio not more forgiving at price={price}"


class TestModuleExports:
    """Test module exports and constants."""

    def test_min_price_constant_exported(self):
        """MIN_PRICE constant is exported."""
        from llm_council.metadata.scoring import MIN_PRICE

        assert MIN_PRICE > 0
        assert MIN_PRICE < 0.001  # Should be very small

    def test_cost_scale_algorithm_type_exported(self):
        """CostScaleAlgorithm type is exported."""
        from llm_council.metadata.scoring import CostScaleAlgorithm

        # Should be a type alias for Literal
        assert CostScaleAlgorithm is not None

    def test_all_functions_exported(self):
        """All expected functions are exported."""
        from llm_council.metadata import scoring

        assert hasattr(scoring, "get_cost_score")
        assert hasattr(scoring, "get_cost_score_log_ratio")
        assert hasattr(scoring, "get_cost_score_exponential")
        assert hasattr(scoring, "get_cost_score_linear")
        assert hasattr(scoring, "get_cost_score_with_config")
        assert hasattr(scoring, "MIN_PRICE")
        assert hasattr(scoring, "CostScaleAlgorithm")
