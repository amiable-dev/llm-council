"""TDD tests for ADR-027: Cost Ceiling Protection.

Tests for the cost ceiling protection that prevents frontier models
from having runaway costs compared to high-tier models.

This implements Issue #113.
"""

import pytest
from typing import Tuple, Optional


class TestApplyCostCeiling:
    """Test apply_cost_ceiling() function."""

    def test_apply_cost_ceiling_returns_tuple(self):
        """apply_cost_ceiling() should return (bool, Optional[str]) tuple."""
        from llm_council.cost_ceiling import apply_cost_ceiling

        result = apply_cost_ceiling(
            model_id="openai/gpt-5.2-pro",
            model_cost=0.010,
            tier="frontier",
            high_tier_avg_cost=0.005,
        )

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert result[1] is None or isinstance(result[1], str)

    def test_model_within_ceiling_allowed(self):
        """Model with cost below ceiling should be allowed."""
        from llm_council.cost_ceiling import apply_cost_ceiling

        # 5x multiplier: ceiling = 0.005 * 5 = 0.025
        # Model cost 0.010 < 0.025, should pass
        allowed, reason = apply_cost_ceiling(
            model_id="openai/gpt-5.2-pro",
            model_cost=0.010,
            tier="frontier",
            high_tier_avg_cost=0.005,
        )

        assert allowed is True
        assert reason is None

    def test_model_exceeding_ceiling_rejected(self):
        """Model with cost above ceiling should be rejected."""
        from llm_council.cost_ceiling import apply_cost_ceiling

        # 5x multiplier: ceiling = 0.005 * 5 = 0.025
        # Model cost 0.030 > 0.025, should fail
        allowed, reason = apply_cost_ceiling(
            model_id="expensive/model",
            model_cost=0.030,
            tier="frontier",
            high_tier_avg_cost=0.005,
        )

        assert allowed is False
        assert reason is not None
        assert "cost" in reason.lower()
        assert "ceiling" in reason.lower()

    def test_non_frontier_bypasses_check(self):
        """Non-frontier tiers should bypass cost ceiling check."""
        from llm_council.cost_ceiling import apply_cost_ceiling

        # Even expensive model is allowed in non-frontier tier
        allowed, reason = apply_cost_ceiling(
            model_id="expensive/model",
            model_cost=0.100,
            tier="high",  # Not frontier
            high_tier_avg_cost=0.005,
        )

        assert allowed is True
        assert reason is None

    def test_custom_multiplier_applied(self):
        """Custom cost multiplier should be applied."""
        from llm_council.cost_ceiling import apply_cost_ceiling

        # Custom 10x multiplier: ceiling = 0.005 * 10 = 0.050
        # Model cost 0.040 < 0.050, should pass
        allowed, reason = apply_cost_ceiling(
            model_id="expensive/model",
            model_cost=0.040,
            tier="frontier",
            high_tier_avg_cost=0.005,
            multiplier=10.0,  # Custom multiplier
        )

        assert allowed is True
        assert reason is None

    def test_custom_multiplier_rejection(self):
        """Custom cost multiplier rejection works correctly."""
        from llm_council.cost_ceiling import apply_cost_ceiling

        # Custom 2x multiplier: ceiling = 0.005 * 2 = 0.010
        # Model cost 0.015 > 0.010, should fail
        allowed, reason = apply_cost_ceiling(
            model_id="expensive/model",
            model_cost=0.015,
            tier="frontier",
            high_tier_avg_cost=0.005,
            multiplier=2.0,  # Stricter multiplier
        )

        assert allowed is False
        assert reason is not None

    def test_exact_ceiling_is_allowed(self):
        """Model at exactly the ceiling should be allowed."""
        from llm_council.cost_ceiling import apply_cost_ceiling

        # 5x multiplier: ceiling = 0.005 * 5 = 0.025
        # Model cost 0.025 == 0.025, should pass
        allowed, reason = apply_cost_ceiling(
            model_id="exact/model",
            model_cost=0.025,
            tier="frontier",
            high_tier_avg_cost=0.005,
        )

        assert allowed is True
        assert reason is None

    def test_zero_high_tier_cost_handled(self):
        """Zero high tier average cost should be handled gracefully."""
        from llm_council.cost_ceiling import apply_cost_ceiling

        # With zero baseline, any cost should be allowed (or use fallback)
        allowed, reason = apply_cost_ceiling(
            model_id="any/model",
            model_cost=0.010,
            tier="frontier",
            high_tier_avg_cost=0.0,
        )

        # Graceful handling: either allow or use fallback ceiling
        assert isinstance(allowed, bool)


class TestDefaultCostMultiplier:
    """Test default cost multiplier constant."""

    def test_default_multiplier_is_five(self):
        """Default cost multiplier should be 5.0 per ADR-027."""
        from llm_council.cost_ceiling import FRONTIER_COST_MULTIPLIER

        assert FRONTIER_COST_MULTIPLIER == 5.0


class TestCostCeilingIntegration:
    """Test cost ceiling integration with model selection."""

    def test_get_high_tier_avg_cost_returns_float(self):
        """get_high_tier_avg_cost() should return float."""
        from llm_council.cost_ceiling import get_high_tier_avg_cost

        cost = get_high_tier_avg_cost()

        assert isinstance(cost, float)
        assert cost >= 0

    def test_check_model_cost_ceiling_convenience_function(self):
        """check_model_cost_ceiling() should be convenient wrapper."""
        from llm_council.cost_ceiling import check_model_cost_ceiling

        # Should work without needing to calculate high_tier_avg_cost
        result = check_model_cost_ceiling(
            model_id="test/model",
            model_cost=0.010,
            tier="frontier",
        )

        assert isinstance(result, tuple)
        assert len(result) == 2
