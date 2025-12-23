"""TDD tests for ADR-026: Tier Selection Algorithm.

Tests for the tier-specific model selection with weights and anti-herding.
"""

import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass
from typing import List, Optional
import os


class TestTierWeights:
    """Test tier-specific weighting matrices."""

    def test_tier_weights_exist_for_all_tiers(self):
        """Weights should be defined for quick, balanced, high, reasoning."""
        from llm_council.metadata.selection import TIER_WEIGHTS

        assert "quick" in TIER_WEIGHTS
        assert "balanced" in TIER_WEIGHTS
        assert "high" in TIER_WEIGHTS
        assert "reasoning" in TIER_WEIGHTS

    def test_tier_weights_sum_to_one(self):
        """Each tier's weights should sum to 1.0."""
        from llm_council.metadata.selection import TIER_WEIGHTS

        for tier, weights in TIER_WEIGHTS.items():
            weight_sum = sum(weights.values())
            assert abs(weight_sum - 1.0) < 0.01, f"{tier} weights sum to {weight_sum}"

    def test_tier_weights_have_all_dimensions(self):
        """Each tier should have all weight dimensions."""
        from llm_council.metadata.selection import TIER_WEIGHTS

        required_dims = {"latency", "cost", "quality", "availability", "diversity"}
        for tier, weights in TIER_WEIGHTS.items():
            assert set(weights.keys()) == required_dims, f"{tier} missing dimensions"

    def test_quick_tier_prioritizes_latency(self):
        """Quick tier should have latency as highest weight."""
        from llm_council.metadata.selection import TIER_WEIGHTS

        quick = TIER_WEIGHTS["quick"]
        assert quick["latency"] >= max(
            quick["quality"],
            quick["cost"],
            quick["diversity"]
        )

    def test_reasoning_tier_prioritizes_quality(self):
        """Reasoning tier should have quality as highest weight."""
        from llm_council.metadata.selection import TIER_WEIGHTS

        reasoning = TIER_WEIGHTS["reasoning"]
        assert reasoning["quality"] >= max(
            reasoning["latency"],
            reasoning["cost"],
            reasoning["diversity"]
        )

    def test_balanced_tier_weights_balanced(self):
        """Balanced tier should have balanced weights."""
        from llm_council.metadata.selection import TIER_WEIGHTS

        balanced = TIER_WEIGHTS["balanced"]
        # No single weight should dominate excessively
        max_weight = max(balanced.values())
        assert max_weight <= 0.40


class TestAntiHerding:
    """Test anti-herding penalty logic."""

    def test_no_penalty_below_threshold(self):
        """Models with <30% traffic should not be penalized."""
        from llm_council.metadata.selection import apply_anti_herding_penalty

        score = 1.0
        traffic = 0.25  # 25% of recent traffic

        adjusted = apply_anti_herding_penalty(score, traffic)
        assert adjusted == score

    def test_no_penalty_at_threshold(self):
        """Models with exactly 30% traffic should not be penalized."""
        from llm_council.metadata.selection import apply_anti_herding_penalty

        score = 1.0
        traffic = 0.3  # 30% of recent traffic

        adjusted = apply_anti_herding_penalty(score, traffic)
        assert adjusted == score

    def test_penalty_above_threshold(self):
        """Models with >30% traffic should be penalized."""
        from llm_council.metadata.selection import apply_anti_herding_penalty

        score = 1.0
        traffic = 0.5  # 50% of recent traffic

        adjusted = apply_anti_herding_penalty(score, traffic)
        assert adjusted < score

    def test_penalty_proportional_to_traffic(self):
        """Penalty should increase with traffic share."""
        from llm_council.metadata.selection import apply_anti_herding_penalty

        score = 1.0
        low_traffic = 0.4
        high_traffic = 0.6

        low_adjusted = apply_anti_herding_penalty(score, low_traffic)
        high_adjusted = apply_anti_herding_penalty(score, high_traffic)

        assert high_adjusted < low_adjusted

    def test_max_penalty_is_35_percent(self):
        """Penalty should cap at 35% score reduction."""
        from llm_council.metadata.selection import apply_anti_herding_penalty

        score = 1.0
        traffic = 1.0  # 100% of traffic (extreme case)

        adjusted = apply_anti_herding_penalty(score, traffic)
        assert adjusted >= score * 0.65  # Max 35% penalty

    def test_penalty_with_zero_traffic(self):
        """Zero traffic should have no penalty."""
        from llm_council.metadata.selection import apply_anti_herding_penalty

        score = 1.0
        traffic = 0.0

        adjusted = apply_anti_herding_penalty(score, traffic)
        assert adjusted == score


class TestDiversityEnforcement:
    """Test provider diversity constraints."""

    def test_selects_from_multiple_providers(self):
        """Selection should include at least 2 providers when possible."""
        from llm_council.metadata.selection import select_with_diversity

        scored = [
            ("openai/gpt-4o", 0.95),
            ("openai/gpt-4o-mini", 0.90),
            ("anthropic/claude-opus", 0.85),
            ("anthropic/claude-sonnet", 0.80),
        ]

        selected = select_with_diversity(scored, count=3, min_providers=2)

        providers = set(m.split("/")[0] for m in selected)
        assert len(providers) >= 2

    def test_respects_count_limit(self):
        """Should return exactly count models."""
        from llm_council.metadata.selection import select_with_diversity

        scored = [
            ("model1/a", 0.9),
            ("model2/b", 0.8),
            ("model3/c", 0.7),
            ("model4/d", 0.6),
        ]

        selected = select_with_diversity(scored, count=3)
        assert len(selected) == 3

    def test_returns_fewer_if_not_enough_candidates(self):
        """Should return available models if fewer than count."""
        from llm_council.metadata.selection import select_with_diversity

        scored = [
            ("model1/a", 0.9),
            ("model2/b", 0.8),
        ]

        selected = select_with_diversity(scored, count=5)
        assert len(selected) == 2

    def test_prefers_higher_scored_models(self):
        """Higher scored models should be preferred."""
        from llm_council.metadata.selection import select_with_diversity

        scored = [
            ("best/model", 0.95),
            ("good/model", 0.80),
            ("ok/model", 0.70),
            ("worst/model", 0.50),
        ]

        selected = select_with_diversity(scored, count=2)
        assert "best/model" in selected

    def test_handles_single_provider(self):
        """Should work even with single provider."""
        from llm_council.metadata.selection import select_with_diversity

        scored = [
            ("openai/gpt-4o", 0.95),
            ("openai/gpt-4o-mini", 0.90),
        ]

        selected = select_with_diversity(scored, count=2, min_providers=2)
        # Should still return models even if can't meet diversity
        assert len(selected) > 0


class TestSelectTierModels:
    """Test main select_tier_models() function."""

    def test_returns_list_of_model_ids(self):
        """Should return list of model ID strings."""
        from llm_council.metadata.selection import select_tier_models

        models = select_tier_models(tier="high")

        assert isinstance(models, list)
        assert all(isinstance(m, str) for m in models)

    def test_returns_default_count_of_4(self):
        """Should return 4 models by default."""
        from llm_council.metadata.selection import select_tier_models

        models = select_tier_models(tier="high")

        assert len(models) == 4

    def test_respects_count_parameter(self):
        """Should return specified number of models."""
        from llm_council.metadata.selection import select_tier_models

        models = select_tier_models(tier="high", count=3)

        assert len(models) == 3

    def test_returns_models_for_all_tiers(self):
        """Should work for all tier levels."""
        from llm_council.metadata.selection import select_tier_models

        for tier in ["quick", "balanced", "high", "reasoning"]:
            models = select_tier_models(tier=tier)
            assert len(models) > 0, f"No models for tier {tier}"

    def test_falls_back_to_static_config_when_no_candidates(self):
        """Should use static config when dynamic selection fails."""
        from llm_council.metadata.selection import select_tier_models

        # Even with no dynamic candidates, should fall back to static
        models = select_tier_models(tier="high")
        assert len(models) > 0


class TestModelCandidateScoring:
    """Test model candidate scoring."""

    def test_calculate_model_score_returns_float(self):
        """calculate_model_score should return a float."""
        from llm_council.metadata.selection import calculate_model_score, ModelCandidate

        candidate = ModelCandidate(
            model_id="test/model",
            latency_score=0.8,
            cost_score=0.7,
            quality_score=0.9,
            availability_score=0.95,
            diversity_score=0.5,
        )

        score = calculate_model_score(candidate, tier="high")
        assert isinstance(score, float)
        assert 0 <= score <= 1

    def test_score_uses_tier_weights(self):
        """Scores should differ based on tier weights."""
        from llm_council.metadata.selection import calculate_model_score, ModelCandidate

        # Low latency, low quality
        candidate = ModelCandidate(
            model_id="test/model",
            latency_score=0.95,  # Fast
            cost_score=0.8,
            quality_score=0.5,   # Low quality
            availability_score=0.99,
            diversity_score=0.5,
        )

        quick_score = calculate_model_score(candidate, tier="quick")
        reasoning_score = calculate_model_score(candidate, tier="reasoning")

        # Quick tier prioritizes latency, so this model should score higher
        assert quick_score > reasoning_score


class TestModelCandidate:
    """Test ModelCandidate dataclass."""

    def test_model_candidate_creation(self):
        """Should be able to create a ModelCandidate."""
        from llm_council.metadata.selection import ModelCandidate

        candidate = ModelCandidate(
            model_id="test/model",
            latency_score=0.8,
            cost_score=0.7,
            quality_score=0.9,
            availability_score=0.95,
            diversity_score=0.5,
        )

        assert candidate.model_id == "test/model"
        assert candidate.latency_score == 0.8

    def test_model_candidate_optional_traffic(self):
        """Traffic should be optional with default 0."""
        from llm_council.metadata.selection import ModelCandidate

        candidate = ModelCandidate(
            model_id="test/model",
            latency_score=0.8,
            cost_score=0.7,
            quality_score=0.9,
            availability_score=0.95,
            diversity_score=0.5,
        )

        assert candidate.recent_traffic == 0.0


class TestUnifiedConfigIntegration:
    """Test unified_config.py integration."""

    def test_model_intelligence_config_exists(self):
        """UnifiedConfig should have model_intelligence section."""
        from llm_council.unified_config import UnifiedConfig

        config = UnifiedConfig()
        assert hasattr(config, "model_intelligence")

    def test_model_intelligence_has_enabled_flag(self):
        """model_intelligence should have enabled flag."""
        from llm_council.unified_config import UnifiedConfig

        config = UnifiedConfig()
        assert hasattr(config.model_intelligence, "enabled")
        assert isinstance(config.model_intelligence.enabled, bool)

    def test_model_intelligence_has_refresh_config(self):
        """model_intelligence should have refresh configuration."""
        from llm_council.unified_config import UnifiedConfig

        config = UnifiedConfig()
        assert hasattr(config.model_intelligence, "refresh")
        assert hasattr(config.model_intelligence.refresh, "registry_ttl")
        assert hasattr(config.model_intelligence.refresh, "availability_ttl")

    def test_model_intelligence_has_selection_config(self):
        """model_intelligence should have selection configuration."""
        from llm_council.unified_config import UnifiedConfig

        config = UnifiedConfig()
        assert hasattr(config.model_intelligence, "selection")
        assert hasattr(config.model_intelligence.selection, "min_providers")

    def test_model_intelligence_has_anti_herding_config(self):
        """model_intelligence should have anti_herding configuration."""
        from llm_council.unified_config import UnifiedConfig

        config = UnifiedConfig()
        assert hasattr(config.model_intelligence, "anti_herding")
        assert hasattr(config.model_intelligence.anti_herding, "enabled")
        assert hasattr(config.model_intelligence.anti_herding, "traffic_threshold")

    def test_model_intelligence_disabled_by_default(self):
        """model_intelligence should be disabled by default."""
        from llm_council.unified_config import UnifiedConfig

        config = UnifiedConfig()
        assert config.model_intelligence.enabled is False


class TestTierContractIntegration:
    """Test tier_contract.py integration."""

    def test_create_tier_contract_accepts_task_domain(self):
        """create_tier_contract should accept task_domain parameter."""
        from llm_council.tier_contract import create_tier_contract

        # Should not raise
        contract = create_tier_contract(tier="high", task_domain="coding")
        assert contract is not None

    def test_tier_contract_has_allowed_models(self):
        """TierContract should have allowed_models populated."""
        from llm_council.tier_contract import create_tier_contract

        contract = create_tier_contract(tier="high")
        assert len(contract.allowed_models) > 0

    def test_tier_contract_uses_static_when_intelligence_disabled(self):
        """Should use static config when intelligence disabled."""
        from llm_council.tier_contract import create_tier_contract
        from llm_council.config import TIER_MODEL_POOLS

        # Ensure intelligence is disabled
        with patch.dict(os.environ, {"LLM_COUNCIL_MODEL_INTELLIGENCE": "false"}):
            contract = create_tier_contract(tier="high")
            # Should use static pools
            for model in contract.allowed_models:
                assert model in TIER_MODEL_POOLS["high"]
