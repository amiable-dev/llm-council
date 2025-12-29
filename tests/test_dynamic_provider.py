"""TDD tests for ADR-026: DynamicMetadataProvider.

Tests for the dynamic metadata provider that fetches from OpenRouter API
with caching and falls back to StaticRegistryProvider.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import os


class TestDynamicMetadataProvider:
    """Test DynamicMetadataProvider implementation."""

    def test_implements_metadata_provider_protocol(self):
        """DynamicMetadataProvider must implement MetadataProvider."""
        from llm_council.metadata.dynamic_provider import DynamicMetadataProvider
        from llm_council.metadata.protocol import MetadataProvider

        provider = DynamicMetadataProvider()
        assert isinstance(provider, MetadataProvider)

    def test_get_model_info_returns_model_info_or_none(self):
        """get_model_info should return ModelInfo or None."""
        from llm_council.metadata.dynamic_provider import DynamicMetadataProvider
        from llm_council.metadata.types import ModelInfo

        provider = DynamicMetadataProvider()
        # With empty cache, should fall back to static
        result = provider.get_model_info("openai/gpt-4o")
        assert result is None or isinstance(result, ModelInfo)

    def test_get_context_window_returns_int(self):
        """get_context_window should always return an int."""
        from llm_council.metadata.dynamic_provider import DynamicMetadataProvider

        provider = DynamicMetadataProvider()
        window = provider.get_context_window("any/model")
        assert isinstance(window, int)
        assert window >= 4096  # Default minimum

    def test_get_pricing_returns_dict(self):
        """get_pricing should return dict."""
        from llm_council.metadata.dynamic_provider import DynamicMetadataProvider

        provider = DynamicMetadataProvider()
        pricing = provider.get_pricing("any/model")
        assert isinstance(pricing, dict)

    def test_list_available_models_returns_list(self):
        """list_available_models should return list of strings."""
        from llm_council.metadata.dynamic_provider import DynamicMetadataProvider

        provider = DynamicMetadataProvider()
        models = provider.list_available_models()
        assert isinstance(models, list)

    def test_supports_reasoning_returns_bool(self):
        """supports_reasoning should return bool."""
        from llm_council.metadata.dynamic_provider import DynamicMetadataProvider

        provider = DynamicMetadataProvider()
        result = provider.supports_reasoning("any/model")
        assert isinstance(result, bool)


class TestDynamicProviderFallback:
    """Test fallback to StaticRegistryProvider."""

    def test_falls_back_to_static_when_cache_empty(self):
        """Should use StaticRegistryProvider when dynamic cache empty."""
        from llm_council.metadata.dynamic_provider import DynamicMetadataProvider

        provider = DynamicMetadataProvider()
        # GPT-4o is in static registry
        window = provider.get_context_window("openai/gpt-4o")

        # Should get data from static registry fallback
        assert window >= 4096

    def test_falls_back_to_static_for_unknown_model(self):
        """Should use safe defaults for unknown models."""
        from llm_council.metadata.dynamic_provider import DynamicMetadataProvider

        provider = DynamicMetadataProvider()
        window = provider.get_context_window("unknown/model")

        # Should get safe default
        assert window == 4096

    def test_prefers_dynamic_data_over_static(self):
        """When cache populated, should prefer dynamic data."""
        from llm_council.metadata.dynamic_provider import DynamicMetadataProvider
        from llm_council.metadata.types import ModelInfo, QualityTier

        provider = DynamicMetadataProvider()

        # Simulate populated cache with different context window
        test_model = ModelInfo(
            id="openai/gpt-4o",
            context_window=999999,  # Different from static
            quality_tier=QualityTier.FRONTIER,
        )
        provider._cache.registry_cache.set("openai/gpt-4o", test_model)

        info = provider.get_model_info("openai/gpt-4o")
        assert info is not None
        assert info.context_window == 999999

    def test_static_models_available_without_api(self):
        """Static registry models should always be available."""
        from llm_council.metadata.dynamic_provider import DynamicMetadataProvider

        provider = DynamicMetadataProvider()

        # These are in static registry
        models = provider.list_available_models()
        assert "openai/gpt-4o" in models
        assert "anthropic/claude-opus-4.5" in models


class TestDynamicProviderRefresh:
    """Test cache refresh functionality."""

    @pytest.mark.asyncio
    async def test_refresh_populates_cache(self):
        """refresh() should populate the registry cache."""
        from llm_council.metadata.dynamic_provider import DynamicMetadataProvider
        from llm_council.metadata.types import ModelInfo, QualityTier

        mock_models = [
            ModelInfo(id="test/model1", context_window=8000, quality_tier=QualityTier.STANDARD),
            ModelInfo(id="test/model2", context_window=16000, quality_tier=QualityTier.STANDARD),
        ]

        provider = DynamicMetadataProvider()

        with patch.object(provider._client, "fetch_models", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_models

            await provider.refresh()

            assert provider.get_model_info("test/model1") is not None
            assert provider.get_model_info("test/model2") is not None

    @pytest.mark.asyncio
    async def test_refresh_handles_api_failure(self):
        """refresh() should not raise on API failure."""
        from llm_council.metadata.dynamic_provider import DynamicMetadataProvider

        provider = DynamicMetadataProvider()

        with patch.object(provider._client, "fetch_models", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = Exception("API Error")

            # Should not raise
            await provider.refresh()

    @pytest.mark.asyncio
    async def test_refresh_handles_empty_response(self):
        """refresh() should handle empty API response."""
        from llm_council.metadata.dynamic_provider import DynamicMetadataProvider

        provider = DynamicMetadataProvider()

        with patch.object(provider._client, "fetch_models", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = []

            await provider.refresh()

            # Should still work with static fallback
            assert len(provider.list_available_models()) > 0

    def test_is_cache_stale_returns_bool(self):
        """is_cache_stale() should return boolean."""
        from llm_council.metadata.dynamic_provider import DynamicMetadataProvider

        provider = DynamicMetadataProvider()
        assert isinstance(provider.is_cache_stale(), bool)

    def test_is_cache_stale_true_when_empty(self):
        """is_cache_stale() should return True when cache is empty."""
        from llm_council.metadata.dynamic_provider import DynamicMetadataProvider

        provider = DynamicMetadataProvider()
        assert provider.is_cache_stale() is True


class TestDynamicProviderOfflineMode:
    """Test offline mode behavior."""

    def test_respects_offline_mode(self):
        """Should not attempt API calls when offline mode enabled."""
        from llm_council.metadata.dynamic_provider import DynamicMetadataProvider

        with patch.dict(os.environ, {"LLM_COUNCIL_OFFLINE": "true"}):
            provider = DynamicMetadataProvider()

            # Should still return data (from static registry)
            models = provider.list_available_models()
            assert len(models) > 0

    def test_uses_static_fallback_in_offline_mode(self):
        """Should use StaticRegistryProvider in offline mode."""
        from llm_council.metadata.dynamic_provider import DynamicMetadataProvider

        with patch.dict(os.environ, {"LLM_COUNCIL_OFFLINE": "true"}):
            provider = DynamicMetadataProvider()

            # GPT-4o from static registry
            info = provider.get_model_info("openai/gpt-4o")
            assert info is not None


class TestGetProviderFactory:
    """Test get_provider() factory with dynamic provider."""

    def test_returns_static_provider_when_offline(self):
        """get_provider() should return StaticRegistryProvider when offline."""
        from llm_council.metadata import get_provider, reload_provider
        from llm_council.metadata.static_registry import StaticRegistryProvider

        with patch.dict(os.environ, {"LLM_COUNCIL_OFFLINE": "true"}):
            reload_provider()
            provider = get_provider()
            assert isinstance(provider, StaticRegistryProvider)

    def test_returns_static_provider_when_intelligence_disabled(self):
        """get_provider() should return StaticRegistryProvider when disabled."""
        from llm_council.metadata import get_provider, reload_provider
        from llm_council.metadata.static_registry import StaticRegistryProvider

        env = os.environ.copy()
        env.pop("LLM_COUNCIL_OFFLINE", None)
        env.pop("LLM_COUNCIL_MODEL_INTELLIGENCE", None)

        with patch.dict(os.environ, env, clear=True):
            reload_provider()
            provider = get_provider()
            assert isinstance(provider, StaticRegistryProvider)

    def test_returns_dynamic_provider_when_enabled(self):
        """get_provider() should return DynamicMetadataProvider when enabled."""
        from llm_council.metadata import get_provider, reload_provider
        from llm_council.metadata.dynamic_provider import DynamicMetadataProvider

        env = {"LLM_COUNCIL_MODEL_INTELLIGENCE": "true"}

        with patch.dict(os.environ, env, clear=False):
            # Ensure offline mode is not set
            if "LLM_COUNCIL_OFFLINE" in os.environ:
                del os.environ["LLM_COUNCIL_OFFLINE"]

            reload_provider()
            provider = get_provider()
            assert isinstance(provider, DynamicMetadataProvider)

    def test_offline_mode_overrides_intelligence_enabled(self):
        """Offline mode should override intelligence enabled."""
        from llm_council.metadata import get_provider, reload_provider
        from llm_council.metadata.static_registry import StaticRegistryProvider

        with patch.dict(
            os.environ, {"LLM_COUNCIL_OFFLINE": "true", "LLM_COUNCIL_MODEL_INTELLIGENCE": "true"}
        ):
            reload_provider()
            provider = get_provider()
            # Offline takes precedence
            assert isinstance(provider, StaticRegistryProvider)


class TestDynamicProviderCacheIntegration:
    """Test cache integration."""

    def test_uses_model_intelligence_cache(self):
        """Should use ModelIntelligenceCache internally."""
        from llm_council.metadata.dynamic_provider import DynamicMetadataProvider
        from llm_council.metadata.cache import ModelIntelligenceCache

        provider = DynamicMetadataProvider()
        assert isinstance(provider._cache, ModelIntelligenceCache)

    def test_cache_ttl_is_configurable(self):
        """Cache TTL should be configurable."""
        from llm_council.metadata.dynamic_provider import DynamicMetadataProvider

        provider = DynamicMetadataProvider(registry_ttl=7200, availability_ttl=600)
        assert provider._cache.registry_cache.ttl == 7200
        assert provider._cache.availability_cache.ttl == 600

    def test_get_cache_stats(self):
        """Should expose cache statistics."""
        from llm_council.metadata.dynamic_provider import DynamicMetadataProvider

        provider = DynamicMetadataProvider()
        stats = provider.get_cache_stats()

        assert "registry" in stats
        assert "availability" in stats
