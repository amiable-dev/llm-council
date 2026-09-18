"""Tests for tier-specific model pools (ADR-022).

TDD: Write these tests first, then implement the configuration.

ADR-032: Updated to use unified_config and tier_contract instead of config.py.
"""

import os
import pytest
from unittest.mock import patch


class TestTierModelPoolsStructure:
    """Test that tier model pools have correct structure."""

    def test_tier_model_pools_has_all_tiers(self):
        """Tier pools must contain quick, balanced, high, reasoning, frontier tiers."""
        from llm_council.tier_contract import _get_tier_model_pools

        pools = _get_tier_model_pools()
        assert "quick" in pools
        assert "balanced" in pools
        assert "high" in pools
        assert "reasoning" in pools
        assert "frontier" in pools

    def test_each_tier_has_model_list(self):
        """Each tier must have a list of model identifiers."""
        from llm_council.tier_contract import _get_tier_model_pools

        pools = _get_tier_model_pools()
        for tier, models in pools.items():
            assert isinstance(models, list), f"Tier {tier} should have list of models"
            assert len(models) >= 2, f"Tier {tier} should have at least 2 models"

    def test_models_are_valid_identifiers(self):
        """Models should be valid OpenRouter-style identifiers (provider/model)."""
        from llm_council.tier_contract import _get_tier_model_pools

        pools = _get_tier_model_pools()
        for tier, models in pools.items():
            for model in models:
                assert isinstance(model, str), f"Model in {tier} should be string"
                assert "/" in model, f"Model '{model}' should have provider/model format"


class TestDefaultTierModelPools:
    """Test default tier model pool values."""

    def test_quick_tier_has_fast_models(self):
        """Quick tier should have fast, low-latency models."""
        from llm_council.tier_contract import _DEFAULT_TIER_MODEL_POOLS

        quick_models = _DEFAULT_TIER_MODEL_POOLS["quick"]
        # Quick tier should include mini/flash variants
        model_names = " ".join(quick_models).lower()
        assert any(
            fast in model_names for fast in ["mini", "flash", "haiku"]
        ), "Quick tier should have fast model variants"

    def test_reasoning_tier_has_reasoning_models(self):
        """Reasoning tier should have deep reasoning models."""
        from llm_council.tier_contract import _DEFAULT_TIER_MODEL_POOLS

        reasoning_models = _DEFAULT_TIER_MODEL_POOLS["reasoning"]
        model_names = " ".join(reasoning_models).lower()
        # Should include o1, deepseek-r1, or similar reasoning models
        assert any(
            r in model_names for r in ["o1", "r1", "gpt-5"]
        ), "Reasoning tier should have reasoning model variants"

    def test_default_pools_are_the_sep_2026_refresh(self):
        """The Sept-2026 state, asserted as PROPERTIES rather than as a copy
        of the pool lists.

        The previous version pasted `high` out in full. That made it a fourth
        transcription of the pools — the exact thing #690 is about — and it
        would have stayed green against a stale wheel, because it read the
        same literal the shipping code read. Exact equality against the single
        source lives in `test_issue690_pool_single_source.py`; what belongs
        here is the catalogue decisions, each naming why it holds.
        """
        from llm_council.tier_contract import _DEFAULT_TIER_MODEL_POOLS, TIER_AGGREGATORS

        high = _DEFAULT_TIER_MODEL_POOLS["high"]
        # #685: the preview left the default council for frontier (ADR-027),
        # and glm-5.3 took the seat — measured, cheaper, a fourth provider.
        assert "z-ai/glm-5.3" in high
        assert "google/gemini-3.1-pro-preview" not in high
        assert "google/gemini-3.1-pro-preview" not in _DEFAULT_TIER_MODEL_POOLS["reasoning"]
        assert "z-ai/glm-5.3" in _DEFAULT_TIER_MODEL_POOLS["reasoning"]

        # #685: luna measures 35.3s against quick's 30s budget. It keeps its
        # balanced seat, where 35.3s fits the 90s budget.
        assert "openai/gpt-5.6-luna" not in _DEFAULT_TIER_MODEL_POOLS["quick"]
        assert "openai/gpt-5.6-luna" in _DEFAULT_TIER_MODEL_POOLS["balanced"]

        frontier = _DEFAULT_TIER_MODEL_POOLS["frontier"]
        assert "anthropic/claude-fable-5" in frontier
        assert "x-ai/grok-4.6" in frontier
        assert "google/gemini-3.1-pro-preview" in frontier
        # The 2026-09 flagships audition here; nothing has measured them yet.
        for newcomer in (
            "anthropic/claude-fable-5.1",
            "openai/gpt-6-astra",
            "google/gemini-3.8-flash",
            "deepseek/deepseek-v4.1-flash",
        ):
            assert newcomer in frontier, f"{newcomer} should be auditioning"
        # gpt-5.5-pro exits (Pareto-dominated by the GPT-5.6 family)
        assert "openai/gpt-5.5-pro" not in frontier

        # #690: quick's aggregator was luna, labelled "speed-matched" while
        # exceeding the tier's own budget.
        assert TIER_AGGREGATORS == {
            "quick": "anthropic/claude-haiku-4.5",
            "balanced": "anthropic/claude-sonnet-5",
            "high": "openai/gpt-5.6-sol",
            "reasoning": "anthropic/claude-opus-5",
            "frontier": "anthropic/claude-opus-5",
        }

    def test_high_tier_is_default_equivalent(self):
        """High tier should be similar to current default COUNCIL_MODELS."""
        from llm_council.tier_contract import _DEFAULT_TIER_MODEL_POOLS

        high_models = _DEFAULT_TIER_MODEL_POOLS["high"]
        # High tier should have 4+ models for full council
        assert len(high_models) >= 4, "High tier should have 4+ models for full council"


class TestProviderDiversity:
    """Test that tiers maintain provider diversity (ADR-022 council recommendation)."""

    def test_quick_tier_has_minimum_two_providers(self):
        """Quick tier must have at least 2 different providers."""
        from llm_council.tier_contract import _get_tier_model_pools

        pools = _get_tier_model_pools()
        quick_models = pools["quick"]
        providers = {model.split("/")[0] for model in quick_models}
        assert len(providers) >= 2, "Quick tier needs minimum 2 providers"

    def test_balanced_tier_has_minimum_two_providers(self):
        """Balanced tier must have at least 2 different providers."""
        from llm_council.tier_contract import _get_tier_model_pools

        pools = _get_tier_model_pools()
        balanced_models = pools["balanced"]
        providers = {model.split("/")[0] for model in balanced_models}
        assert len(providers) >= 2, "Balanced tier needs minimum 2 providers"

    def test_high_tier_has_minimum_three_providers(self):
        """High tier should have at least 3 different providers for diversity."""
        from llm_council.tier_contract import _get_tier_model_pools

        pools = _get_tier_model_pools()
        high_models = pools["high"]
        providers = {model.split("/")[0] for model in high_models}
        assert len(providers) >= 3, "High tier needs minimum 3 providers for diversity"


class TestGetTierModels:
    """Test getting tier models via unified_config."""

    def test_get_tier_models_returns_list(self):
        """Getting tier models returns a list of model identifiers."""
        from llm_council.tier_contract import _get_tier_model_pools

        pools = _get_tier_model_pools()
        models = pools["quick"]
        assert isinstance(models, list)
        assert len(models) >= 2

    def test_get_tier_models_for_all_tiers(self):
        """Can get models for all tiers."""
        from llm_council.tier_contract import _get_tier_model_pools

        pools = _get_tier_model_pools()
        for tier in ["quick", "balanced", "high", "reasoning", "frontier"]:
            models = pools[tier]
            assert isinstance(models, list)
            assert len(models) >= 2, f"{tier} tier should have at least 2 models"


class TestEnvironmentVariableOverrides:
    """Test per-tier environment variable overrides."""

    def test_quick_tier_env_override(self):
        """LLM_COUNCIL_MODELS_QUICK overrides quick tier models."""
        from llm_council import unified_config
        from llm_council.tier_contract import _get_tier_model_pools

        with patch.dict(os.environ, {"LLM_COUNCIL_MODELS_QUICK": "test/model-a,test/model-b"}):
            unified_config.reload_config()
            pools = _get_tier_model_pools()
            assert pools["quick"] == ["test/model-a", "test/model-b"]

        # Cleanup
        unified_config.reload_config()

    def test_balanced_tier_env_override(self):
        """LLM_COUNCIL_MODELS_BALANCED overrides balanced tier models."""
        from llm_council import unified_config
        from llm_council.tier_contract import _get_tier_model_pools

        with patch.dict(
            os.environ, {"LLM_COUNCIL_MODELS_BALANCED": "custom/model-1,custom/model-2"}
        ):
            unified_config.reload_config()
            pools = _get_tier_model_pools()
            assert pools["balanced"] == ["custom/model-1", "custom/model-2"]

        # Cleanup
        unified_config.reload_config()

    def test_high_tier_env_override(self):
        """LLM_COUNCIL_MODELS_HIGH overrides high tier models."""
        from llm_council import unified_config
        from llm_council.tier_contract import _get_tier_model_pools

        with patch.dict(os.environ, {"LLM_COUNCIL_MODELS_HIGH": "a/1,b/2,c/3,d/4"}):
            unified_config.reload_config()
            pools = _get_tier_model_pools()
            assert pools["high"] == ["a/1", "b/2", "c/3", "d/4"]

        # Cleanup
        unified_config.reload_config()

    def test_reasoning_tier_env_override(self):
        """LLM_COUNCIL_MODELS_REASONING overrides reasoning tier models."""
        from llm_council import unified_config
        from llm_council.tier_contract import _get_tier_model_pools

        with patch.dict(
            os.environ, {"LLM_COUNCIL_MODELS_REASONING": "openai/o1-preview,deepseek/deepseek-r1"}
        ):
            unified_config.reload_config()
            pools = _get_tier_model_pools()
            assert pools["reasoning"] == ["openai/o1-preview", "deepseek/deepseek-r1"]

        # Cleanup
        unified_config.reload_config()

    def test_env_override_strips_whitespace(self):
        """Environment variable values should have whitespace stripped."""
        from llm_council import unified_config
        from llm_council.tier_contract import _get_tier_model_pools

        with patch.dict(os.environ, {"LLM_COUNCIL_MODELS_QUICK": " model/a , model/b "}):
            unified_config.reload_config()
            pools = _get_tier_model_pools()
            assert pools["quick"] == ["model/a", "model/b"]

        # Cleanup
        unified_config.reload_config()


class TestBackwardCompatibility:
    """Test backward compatibility with existing COUNCIL_MODELS."""

    def test_council_models_available_via_config(self):
        """Council models should be available via unified_config."""
        from llm_council.unified_config import get_config

        config = get_config()
        council_models = config.council.models
        assert isinstance(council_models, list)
        assert len(council_models) >= 2

    def test_high_tier_has_sufficient_models(self):
        """High tier should have enough models for a full council."""
        from llm_council.unified_config import get_config
        from llm_council.tier_contract import _get_tier_model_pools

        config = get_config()
        pools = _get_tier_model_pools()
        high_models = pools["high"]
        council_models = config.council.models
        # At minimum, high tier should work as a council
        assert len(high_models) >= len(council_models)
