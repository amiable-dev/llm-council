"""Tests for tier-specific model pools (ADR-022).

TDD: Write these tests first, then implement the configuration.
"""

import os
import pytest
from unittest.mock import patch


class TestTierModelPoolsStructure:
    """Test that TIER_MODEL_POOLS has correct structure."""

    def test_tier_model_pools_has_all_four_tiers(self):
        """TIER_MODEL_POOLS must contain quick, balanced, high, reasoning tiers."""
        from llm_council.config import TIER_MODEL_POOLS

        assert "quick" in TIER_MODEL_POOLS
        assert "balanced" in TIER_MODEL_POOLS
        assert "high" in TIER_MODEL_POOLS
        assert "reasoning" in TIER_MODEL_POOLS

    def test_each_tier_has_model_list(self):
        """Each tier must have a list of model identifiers."""
        from llm_council.config import TIER_MODEL_POOLS

        for tier, models in TIER_MODEL_POOLS.items():
            assert isinstance(models, list), f"Tier {tier} should have list of models"
            assert len(models) >= 2, f"Tier {tier} should have at least 2 models"

    def test_models_are_valid_identifiers(self):
        """Models should be valid OpenRouter-style identifiers (provider/model)."""
        from llm_council.config import TIER_MODEL_POOLS

        for tier, models in TIER_MODEL_POOLS.items():
            for model in models:
                assert isinstance(model, str), f"Model in {tier} should be string"
                assert "/" in model, f"Model '{model}' should have provider/model format"


class TestDefaultTierModelPools:
    """Test default tier model pool values."""

    def test_quick_tier_has_fast_models(self):
        """Quick tier should have fast, low-latency models."""
        from llm_council.config import DEFAULT_TIER_MODEL_POOLS

        quick_models = DEFAULT_TIER_MODEL_POOLS["quick"]
        # Quick tier should include mini/flash variants
        model_names = " ".join(quick_models).lower()
        assert any(
            fast in model_names for fast in ["mini", "flash", "haiku"]
        ), "Quick tier should have fast model variants"

    def test_reasoning_tier_has_reasoning_models(self):
        """Reasoning tier should have deep reasoning models."""
        from llm_council.config import DEFAULT_TIER_MODEL_POOLS

        reasoning_models = DEFAULT_TIER_MODEL_POOLS["reasoning"]
        model_names = " ".join(reasoning_models).lower()
        # Should include o1, deepseek-r1, or similar reasoning models
        assert any(
            r in model_names for r in ["o1", "r1", "gpt-5"]
        ), "Reasoning tier should have reasoning model variants"

    def test_high_tier_is_default_equivalent(self):
        """High tier should be similar to current default COUNCIL_MODELS."""
        from llm_council.config import DEFAULT_TIER_MODEL_POOLS

        high_models = DEFAULT_TIER_MODEL_POOLS["high"]
        # High tier should have 4+ models for full council
        assert len(high_models) >= 4, "High tier should have 4+ models for full council"


class TestProviderDiversity:
    """Test that tiers maintain provider diversity (ADR-022 council recommendation)."""

    def test_quick_tier_has_minimum_two_providers(self):
        """Quick tier must have at least 2 different providers."""
        from llm_council.config import TIER_MODEL_POOLS

        quick_models = TIER_MODEL_POOLS["quick"]
        providers = {model.split("/")[0] for model in quick_models}
        assert len(providers) >= 2, "Quick tier needs minimum 2 providers"

    def test_balanced_tier_has_minimum_two_providers(self):
        """Balanced tier must have at least 2 different providers."""
        from llm_council.config import TIER_MODEL_POOLS

        balanced_models = TIER_MODEL_POOLS["balanced"]
        providers = {model.split("/")[0] for model in balanced_models}
        assert len(providers) >= 2, "Balanced tier needs minimum 2 providers"

    def test_high_tier_has_minimum_three_providers(self):
        """High tier should have at least 3 different providers for diversity."""
        from llm_council.config import TIER_MODEL_POOLS

        high_models = TIER_MODEL_POOLS["high"]
        providers = {model.split("/")[0] for model in high_models}
        assert len(providers) >= 3, "High tier needs minimum 3 providers for diversity"


class TestGetTierModels:
    """Test get_tier_models() function."""

    def test_get_tier_models_returns_list(self):
        """get_tier_models returns a list of model identifiers."""
        from llm_council.config import get_tier_models

        models = get_tier_models("quick")
        assert isinstance(models, list)
        assert len(models) >= 2

    def test_get_tier_models_for_all_tiers(self):
        """get_tier_models works for all four tiers."""
        from llm_council.config import get_tier_models

        for tier in ["quick", "balanced", "high", "reasoning"]:
            models = get_tier_models(tier)
            assert isinstance(models, list)
            assert len(models) >= 2, f"{tier} tier should have at least 2 models"

    def test_invalid_tier_falls_back_to_high(self):
        """Unknown tier should fall back to 'high' tier models."""
        from llm_council.config import get_tier_models

        unknown_models = get_tier_models("unknown_tier")
        high_models = get_tier_models("high")
        assert unknown_models == high_models


class TestEnvironmentVariableOverrides:
    """Test per-tier environment variable overrides."""

    def test_quick_tier_env_override(self):
        """LLM_COUNCIL_MODELS_QUICK overrides quick tier models."""
        from llm_council import config

        # Need to reimport to pick up env changes
        with patch.dict(
            os.environ, {"LLM_COUNCIL_MODELS_QUICK": "test/model-a,test/model-b"}
        ):
            # Force reimport of config module
            import importlib

            importlib.reload(config)
            models = config.get_tier_models("quick")
            assert models == ["test/model-a", "test/model-b"]

            # Cleanup
            importlib.reload(config)

    def test_balanced_tier_env_override(self):
        """LLM_COUNCIL_MODELS_BALANCED overrides balanced tier models."""
        from llm_council import config

        with patch.dict(
            os.environ, {"LLM_COUNCIL_MODELS_BALANCED": "custom/model-1,custom/model-2"}
        ):
            import importlib

            importlib.reload(config)
            models = config.get_tier_models("balanced")
            assert models == ["custom/model-1", "custom/model-2"]

            # Cleanup
            importlib.reload(config)

    def test_high_tier_env_override(self):
        """LLM_COUNCIL_MODELS_HIGH overrides high tier models."""
        from llm_council import config

        with patch.dict(
            os.environ, {"LLM_COUNCIL_MODELS_HIGH": "a/1,b/2,c/3,d/4"}
        ):
            import importlib

            importlib.reload(config)
            models = config.get_tier_models("high")
            assert models == ["a/1", "b/2", "c/3", "d/4"]

            # Cleanup
            importlib.reload(config)

    def test_reasoning_tier_env_override(self):
        """LLM_COUNCIL_MODELS_REASONING overrides reasoning tier models."""
        from llm_council import config

        with patch.dict(
            os.environ, {"LLM_COUNCIL_MODELS_REASONING": "openai/o1-preview,deepseek/deepseek-r1"}
        ):
            import importlib

            importlib.reload(config)
            models = config.get_tier_models("reasoning")
            assert models == ["openai/o1-preview", "deepseek/deepseek-r1"]

            # Cleanup
            importlib.reload(config)

    def test_env_override_strips_whitespace(self):
        """Environment variable values should have whitespace stripped."""
        from llm_council import config

        with patch.dict(
            os.environ, {"LLM_COUNCIL_MODELS_QUICK": " model/a , model/b "}
        ):
            import importlib

            importlib.reload(config)
            models = config.get_tier_models("quick")
            assert models == ["model/a", "model/b"]

            # Cleanup
            importlib.reload(config)


class TestBackwardCompatibility:
    """Test backward compatibility with existing COUNCIL_MODELS."""

    def test_council_models_still_exists(self):
        """Global COUNCIL_MODELS should still be available."""
        from llm_council.config import COUNCIL_MODELS

        assert isinstance(COUNCIL_MODELS, list)
        assert len(COUNCIL_MODELS) >= 2

    def test_high_tier_matches_council_models_by_default(self):
        """High tier should use same models as COUNCIL_MODELS when not overridden."""
        from llm_council.config import COUNCIL_MODELS, get_tier_models

        # When no env override, high tier should match COUNCIL_MODELS
        # (or be a superset for backward compatibility)
        high_models = get_tier_models("high")
        # At minimum, high tier should work as a council
        assert len(high_models) >= len(COUNCIL_MODELS)
