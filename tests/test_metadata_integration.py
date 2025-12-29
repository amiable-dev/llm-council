"""TDD tests for ADR-026: Metadata Integration.

End-to-end integration tests for the metadata system including:
- Static registry provider (blocking conditions)
- Dynamic metadata provider (Phase 1)
- Tier selection integration (Phase 1)
"""

import pytest
from unittest.mock import patch, AsyncMock
import os


class TestMetadataProviderFactory:
    """Test get_provider() factory function."""

    def test_get_provider_returns_singleton(self):
        """get_provider() should return cached instance."""
        from llm_council.metadata import get_provider, reload_provider

        reload_provider()  # Start fresh
        provider1 = get_provider()
        provider2 = get_provider()
        assert provider1 is provider2

    def test_get_provider_can_be_reloaded(self):
        """reload_provider() should create fresh instance."""
        from llm_council.metadata import get_provider, reload_provider

        provider1 = get_provider()
        reload_provider()
        provider2 = get_provider()
        assert provider1 is not provider2


class TestMetadataWithTierConfig:
    """Test metadata integration with tier configuration."""

    def test_tier_models_have_metadata(self):
        """All tier models should have metadata available."""
        from llm_council.metadata import get_provider, reload_provider
        from llm_council.tier_contract import _DEFAULT_TIER_MODEL_POOLS

        reload_provider()
        provider = get_provider()

        # Check that most tier models have metadata
        for tier, models in _DEFAULT_TIER_MODEL_POOLS.items():
            for model_id in models:
                # Every configured model should have context window
                window = provider.get_context_window(model_id)
                assert window >= 4096, f"{model_id} should have context window"


class TestBundledRegistryContent:
    """Test the bundled registry has required models."""

    def test_registry_has_openai_models(self):
        """Registry should include OpenAI models."""
        from llm_council.metadata import get_provider, reload_provider

        reload_provider()
        provider = get_provider()
        models = provider.list_available_models()

        openai_models = [m for m in models if m.startswith("openai/")]
        assert len(openai_models) >= 5
        assert "openai/gpt-4o" in models
        assert "openai/gpt-4o-mini" in models

    def test_registry_has_anthropic_models(self):
        """Registry should include Anthropic models."""
        from llm_council.metadata import get_provider, reload_provider

        reload_provider()
        provider = get_provider()
        models = provider.list_available_models()

        anthropic_models = [m for m in models if m.startswith("anthropic/")]
        assert len(anthropic_models) >= 4
        assert "anthropic/claude-opus-4.5" in models

    def test_registry_has_google_models(self):
        """Registry should include Google models."""
        from llm_council.metadata import get_provider, reload_provider

        reload_provider()
        provider = get_provider()
        models = provider.list_available_models()

        google_models = [m for m in models if m.startswith("google/")]
        assert len(google_models) >= 3

    def test_registry_has_local_models(self):
        """Registry should include Ollama local models."""
        from llm_council.metadata import get_provider, reload_provider

        reload_provider()
        provider = get_provider()
        models = provider.list_available_models()

        ollama_models = [m for m in models if m.startswith("ollama/")]
        assert len(ollama_models) >= 2

    def test_registry_has_30_plus_models(self):
        """Registry should have at least 30 models per ADR-026."""
        from llm_council.metadata import get_provider, reload_provider

        reload_provider()
        provider = get_provider()
        models = provider.list_available_models()

        assert len(models) >= 30, f"Expected 30+ models, got {len(models)}"


class TestReasoningModelDetection:
    """Test reasoning model detection for parameter optimization."""

    def test_detects_openai_o1_as_reasoning(self):
        """Should detect OpenAI o1 as reasoning model."""
        from llm_council.metadata import get_provider, reload_provider

        reload_provider()
        provider = get_provider()

        assert provider.supports_reasoning("openai/o1") is True

    def test_detects_openai_o1_preview_as_reasoning(self):
        """Should detect OpenAI o1-preview as reasoning model."""
        from llm_council.metadata import get_provider, reload_provider

        reload_provider()
        provider = get_provider()

        assert provider.supports_reasoning("openai/o1-preview") is True

    def test_detects_openai_o1_mini_as_reasoning(self):
        """Should detect OpenAI o1-mini as reasoning model."""
        from llm_council.metadata import get_provider, reload_provider

        reload_provider()
        provider = get_provider()

        assert provider.supports_reasoning("openai/o1-mini") is True

    def test_detects_deepseek_r1_as_reasoning(self):
        """Should detect DeepSeek R1 as reasoning model."""
        from llm_council.metadata import get_provider, reload_provider

        reload_provider()
        provider = get_provider()

        assert provider.supports_reasoning("deepseek/deepseek-r1") is True

    def test_detects_non_reasoning_models(self):
        """Should correctly identify non-reasoning models."""
        from llm_council.metadata import get_provider, reload_provider

        reload_provider()
        provider = get_provider()

        assert provider.supports_reasoning("openai/gpt-4o-mini") is False
        assert provider.supports_reasoning("anthropic/claude-3-5-haiku-20241022") is False


class TestModelInfoContent:
    """Test ModelInfo content for registered models."""

    def test_gpt4o_has_correct_metadata(self):
        """GPT-4o should have correct metadata."""
        from llm_council.metadata import get_provider, reload_provider
        from llm_council.metadata.types import QualityTier

        reload_provider()
        provider = get_provider()
        info = provider.get_model_info("openai/gpt-4o")

        assert info is not None
        assert info.id == "openai/gpt-4o"
        assert info.context_window == 128000
        assert "vision" in info.modalities
        assert info.quality_tier == QualityTier.FRONTIER

    def test_claude_opus_has_correct_metadata(self):
        """Claude Opus 4.5 should have correct metadata."""
        from llm_council.metadata import get_provider, reload_provider
        from llm_council.metadata.types import QualityTier

        reload_provider()
        provider = get_provider()
        info = provider.get_model_info("anthropic/claude-opus-4.5")

        assert info is not None
        assert info.id == "anthropic/claude-opus-4.5"
        assert info.context_window == 200000
        assert "vision" in info.modalities
        assert info.quality_tier == QualityTier.FRONTIER

    def test_ollama_model_has_local_tier(self):
        """Ollama models should have LOCAL quality tier."""
        from llm_council.metadata import get_provider, reload_provider
        from llm_council.metadata.types import QualityTier

        reload_provider()
        provider = get_provider()
        info = provider.get_model_info("ollama/llama3.2")

        assert info is not None
        assert info.quality_tier == QualityTier.LOCAL
        # Local models should have zero pricing
        assert info.pricing.get("prompt", 0) == 0
        assert info.pricing.get("completion", 0) == 0


# =============================================================================
# ADR-026 Phase 1: Dynamic Provider Integration Tests
# =============================================================================


class TestDynamicProviderIntegration:
    """Test DynamicMetadataProvider integration with the system."""

    def test_dynamic_provider_enabled_via_env(self):
        """Dynamic provider should activate with LLM_COUNCIL_MODEL_INTELLIGENCE=true."""
        from llm_council.metadata import get_provider, reload_provider
        from llm_council.metadata.dynamic_provider import DynamicMetadataProvider

        with patch.dict(os.environ, {"LLM_COUNCIL_MODEL_INTELLIGENCE": "true"}):
            if "LLM_COUNCIL_OFFLINE" in os.environ:
                del os.environ["LLM_COUNCIL_OFFLINE"]
            reload_provider()
            provider = get_provider()
            assert isinstance(provider, DynamicMetadataProvider)

    def test_offline_mode_overrides_dynamic_provider(self):
        """Offline mode should force static provider even when intelligence enabled."""
        from llm_council.metadata import get_provider, reload_provider
        from llm_council.metadata.static_registry import StaticRegistryProvider

        with patch.dict(
            os.environ,
            {
                "LLM_COUNCIL_MODEL_INTELLIGENCE": "true",
                "LLM_COUNCIL_OFFLINE": "true",
            },
        ):
            reload_provider()
            provider = get_provider()
            assert isinstance(provider, StaticRegistryProvider)

    def test_dynamic_provider_falls_back_to_static(self):
        """Dynamic provider should use static registry as fallback."""
        from llm_council.metadata import reload_provider
        from llm_council.metadata.dynamic_provider import DynamicMetadataProvider

        with patch.dict(os.environ, {"LLM_COUNCIL_MODEL_INTELLIGENCE": "true"}):
            if "LLM_COUNCIL_OFFLINE" in os.environ:
                del os.environ["LLM_COUNCIL_OFFLINE"]
            reload_provider()

            provider = DynamicMetadataProvider()
            # Without cache populated, should use static fallback
            window = provider.get_context_window("openai/gpt-4o")
            assert window >= 4096

    def test_dynamic_provider_lists_static_models(self):
        """Dynamic provider should list models from static registry."""
        from llm_council.metadata.dynamic_provider import DynamicMetadataProvider

        provider = DynamicMetadataProvider()
        models = provider.list_available_models()

        # Should include static registry models
        assert "openai/gpt-4o" in models
        assert "anthropic/claude-opus-4.5" in models


class TestTierSelectionIntegration:
    """Test tier selection integration with metadata system."""

    def test_select_tier_models_returns_models(self):
        """select_tier_models should return model IDs."""
        from llm_council.metadata.selection import select_tier_models

        models = select_tier_models(tier="high")

        assert isinstance(models, list)
        # Should return at least 1 model, up to count (default 4)
        # Exact count may vary due to tier intersection filtering
        assert len(models) >= 1
        assert len(models) <= 4
        assert all(isinstance(m, str) for m in models)

    def test_select_tier_models_all_tiers(self):
        """select_tier_models should work for all tiers."""
        from llm_council.metadata.selection import select_tier_models

        for tier in ["quick", "balanced", "high", "reasoning"]:
            models = select_tier_models(tier=tier)
            assert len(models) > 0, f"No models for tier {tier}"

    def test_tier_contract_uses_selection(self):
        """TierContract should use dynamic selection when enabled."""
        from llm_council.tier_contract import create_tier_contract

        # Without intelligence enabled, uses static pools
        with patch.dict(os.environ, {"LLM_COUNCIL_MODEL_INTELLIGENCE": "false"}):
            contract = create_tier_contract("high")
            assert len(contract.allowed_models) > 0

    def test_tier_contract_accepts_task_domain(self):
        """TierContract should accept task_domain parameter."""
        from llm_council.tier_contract import create_tier_contract

        contract = create_tier_contract(tier="high", task_domain="coding")
        assert contract is not None
        assert len(contract.allowed_models) > 0


class TestUnifiedConfigModelIntelligence:
    """Test ModelIntelligenceConfig in UnifiedConfig."""

    def test_unified_config_has_model_intelligence(self):
        """UnifiedConfig should have model_intelligence section."""
        from llm_council.unified_config import UnifiedConfig

        config = UnifiedConfig()
        assert hasattr(config, "model_intelligence")

    def test_model_intelligence_defaults(self):
        """model_intelligence should have correct defaults."""
        from llm_council.unified_config import UnifiedConfig

        config = UnifiedConfig()
        mi = config.model_intelligence

        assert mi.enabled is False
        assert mi.refresh.registry_ttl == 3600
        assert mi.refresh.availability_ttl == 300
        assert mi.selection.min_providers == 2
        assert mi.anti_herding.enabled is True
        assert mi.anti_herding.traffic_threshold == 0.30

    def test_model_intelligence_env_override(self):
        """model_intelligence.enabled should be overrideable via env."""
        from llm_council.unified_config import get_effective_config, reload_config

        with patch.dict(os.environ, {"LLM_COUNCIL_MODEL_INTELLIGENCE": "true"}):
            reload_config()
            config = get_effective_config()
            assert config.model_intelligence.enabled is True


class TestCacheIntegration:
    """Test cache integration with providers."""

    def test_cache_ttl_is_configurable(self):
        """Cache TTL should be configurable via DynamicMetadataProvider."""
        from llm_council.metadata.dynamic_provider import DynamicMetadataProvider

        provider = DynamicMetadataProvider(
            registry_ttl=7200,
            availability_ttl=600,
        )

        assert provider._cache.registry_cache.ttl == 7200
        assert provider._cache.availability_cache.ttl == 600

    def test_cache_stats_available(self):
        """Cache stats should be available."""
        from llm_council.metadata.dynamic_provider import DynamicMetadataProvider

        provider = DynamicMetadataProvider()
        stats = provider.get_cache_stats()

        assert "registry" in stats
        assert "availability" in stats
