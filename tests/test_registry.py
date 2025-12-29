"""TDD tests for ADR-028: ModelRegistry (Issue #120).

Tests for the ModelRegistry class that provides thread-safe cached
model metadata with background refresh capability.

These tests implement the RED phase of TDD.
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llm_council.metadata.types import ModelInfo, ModelStatus, QualityTier


class TestModelStatusEnum:
    """Test ModelStatus enum for model availability states."""

    def test_model_status_has_available(self):
        """ModelStatus should have AVAILABLE state."""
        assert ModelStatus.AVAILABLE.value == "available"

    def test_model_status_has_deprecated(self):
        """ModelStatus should have DEPRECATED state."""
        assert ModelStatus.DEPRECATED.value == "deprecated"

    def test_model_status_has_preview(self):
        """ModelStatus should have PREVIEW state."""
        assert ModelStatus.PREVIEW.value == "preview"

    def test_model_status_has_beta(self):
        """ModelStatus should have BETA state."""
        assert ModelStatus.BETA.value == "beta"


class TestRegistryEntry:
    """Test RegistryEntry dataclass for cached model info."""

    def test_registry_entry_has_required_fields(self):
        """RegistryEntry should have info, fetched_at, and is_deprecated."""
        from llm_council.metadata.registry import RegistryEntry

        info = ModelInfo(
            id="openai/gpt-4o",
            context_window=128000,
            quality_tier=QualityTier.FRONTIER,
        )
        now = datetime.utcnow()
        entry = RegistryEntry(info=info, fetched_at=now)

        assert entry.info == info
        assert entry.fetched_at == now
        assert entry.is_deprecated is False

    def test_registry_entry_deprecated_flag(self):
        """RegistryEntry should support is_deprecated flag."""
        from llm_council.metadata.registry import RegistryEntry

        info = ModelInfo(
            id="openai/gpt-3.5-turbo",
            context_window=16385,
            quality_tier=QualityTier.STANDARD,
        )
        entry = RegistryEntry(
            info=info,
            fetched_at=datetime.utcnow(),
            is_deprecated=True,
        )

        assert entry.is_deprecated is True


class TestModelRegistry:
    """Test ModelRegistry class for thread-safe cached model metadata."""

    def test_registry_singleton_returns_same_instance(self):
        """get_registry() should return the same singleton instance."""
        from llm_council.metadata.registry import get_registry, _reset_registry

        # Reset to ensure clean state
        _reset_registry()

        registry1 = get_registry()
        registry2 = get_registry()

        assert registry1 is registry2

        # Cleanup
        _reset_registry()

    def test_get_candidates_returns_empty_when_cache_empty(self):
        """get_candidates() should return empty list when cache is empty."""
        from llm_council.metadata.registry import ModelRegistry

        registry = ModelRegistry()
        candidates = registry.get_candidates()

        assert candidates == []

    def test_get_model_returns_none_for_unknown(self):
        """get_model() should return None for unknown model ID."""
        from llm_council.metadata.registry import ModelRegistry

        registry = ModelRegistry()
        result = registry.get_model("unknown/model")

        assert result is None

    def test_is_stale_true_when_never_refreshed(self):
        """is_stale should be True when registry has never been refreshed."""
        from llm_council.metadata.registry import ModelRegistry

        registry = ModelRegistry()

        assert registry.is_stale is True

    def test_is_stale_true_after_threshold(self):
        """is_stale should be True when last refresh exceeds threshold."""
        from llm_council.metadata.registry import ModelRegistry

        registry = ModelRegistry()
        # Manually set last_refresh to 31 minutes ago (threshold is 30)
        registry._last_refresh = datetime.utcnow() - timedelta(minutes=31)

        assert registry.is_stale is True

    def test_is_stale_false_when_fresh(self):
        """is_stale should be False when recently refreshed."""
        from llm_council.metadata.registry import ModelRegistry

        registry = ModelRegistry()
        registry._last_refresh = datetime.utcnow()

        assert registry.is_stale is False

    def test_get_model_returns_cached_info(self):
        """get_model() should return ModelInfo from cache."""
        from llm_council.metadata.registry import ModelRegistry, RegistryEntry

        registry = ModelRegistry()
        info = ModelInfo(
            id="openai/gpt-4o",
            context_window=128000,
            quality_tier=QualityTier.FRONTIER,
        )
        registry._cache["openai/gpt-4o"] = RegistryEntry(
            info=info,
            fetched_at=datetime.utcnow(),
        )

        result = registry.get_model("openai/gpt-4o")

        assert result == info

    def test_get_candidates_returns_all_cached_models(self):
        """get_candidates() should return all ModelInfo from cache."""
        from llm_council.metadata.registry import ModelRegistry, RegistryEntry

        registry = ModelRegistry()
        info1 = ModelInfo(
            id="openai/gpt-4o",
            context_window=128000,
            quality_tier=QualityTier.FRONTIER,
        )
        info2 = ModelInfo(
            id="anthropic/claude-3-opus",
            context_window=200000,
            quality_tier=QualityTier.FRONTIER,
        )
        registry._cache["openai/gpt-4o"] = RegistryEntry(info=info1, fetched_at=datetime.utcnow())
        registry._cache["anthropic/claude-3-opus"] = RegistryEntry(
            info=info2, fetched_at=datetime.utcnow()
        )

        candidates = registry.get_candidates()

        assert len(candidates) == 2
        assert info1 in candidates
        assert info2 in candidates


class TestRegistryRefresh:
    """Test async refresh functionality of ModelRegistry."""

    @pytest.mark.asyncio
    async def test_refresh_populates_cache(self):
        """refresh_registry() should populate cache from provider."""
        from llm_council.metadata.registry import ModelRegistry

        registry = ModelRegistry()

        # Mock provider that returns models
        mock_provider = MagicMock()
        mock_provider.list_available_models = MagicMock(
            return_value=["openai/gpt-4o", "anthropic/claude-3-opus"]
        )
        mock_provider.get_model_info = MagicMock(
            side_effect=lambda model_id: ModelInfo(
                id=model_id,
                context_window=128000,
                quality_tier=QualityTier.FRONTIER,
            )
        )

        await registry.refresh_registry(mock_provider)

        assert len(registry._cache) == 2
        assert "openai/gpt-4o" in registry._cache
        assert "anthropic/claude-3-opus" in registry._cache
        assert registry._last_refresh is not None

    @pytest.mark.asyncio
    async def test_refresh_filters_deprecated_models(self):
        """refresh_registry() should filter out deprecated models."""
        from llm_council.metadata.registry import ModelRegistry

        registry = ModelRegistry()

        # Mock provider with one deprecated model
        mock_provider = MagicMock()
        mock_provider.list_available_models = MagicMock(
            return_value=["openai/gpt-4o", "openai/gpt-3.5-turbo-deprecated"]
        )

        def get_model_info(model_id):
            info = ModelInfo(
                id=model_id,
                context_window=128000,
                quality_tier=QualityTier.FRONTIER,
            )
            return info

        mock_provider.get_model_info = MagicMock(side_effect=get_model_info)
        mock_provider.get_model_status = MagicMock(
            side_effect=lambda m: (
                ModelStatus.DEPRECATED if "deprecated" in m else ModelStatus.AVAILABLE
            )
        )

        await registry.refresh_registry(mock_provider)

        # Deprecated model should be filtered
        assert "openai/gpt-3.5-turbo-deprecated" not in registry._cache
        assert "openai/gpt-4o" in registry._cache

    @pytest.mark.asyncio
    async def test_refresh_handles_failures_with_backoff(self):
        """refresh_registry() should retry with exponential backoff on failure."""
        from llm_council.metadata.registry import ModelRegistry

        registry = ModelRegistry()

        # Mock provider that fails twice then succeeds
        mock_provider = MagicMock()
        call_count = 0

        def list_models():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("API unavailable")
            return ["openai/gpt-4o"]

        mock_provider.list_available_models = MagicMock(side_effect=list_models)
        mock_provider.get_model_info = MagicMock(
            return_value=ModelInfo(
                id="openai/gpt-4o",
                context_window=128000,
                quality_tier=QualityTier.FRONTIER,
            )
        )

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await registry.refresh_registry(mock_provider, max_retries=3)

            # Should have retried with backoff
            assert mock_sleep.call_count == 2  # 2 failures before success
            assert len(registry._cache) == 1

    @pytest.mark.asyncio
    async def test_refresh_serves_stale_on_failure(self):
        """refresh_registry() should keep stale cache if all retries fail."""
        from llm_council.metadata.registry import ModelRegistry, RegistryEntry

        registry = ModelRegistry()

        # Pre-populate cache with stale data
        stale_info = ModelInfo(
            id="openai/gpt-4o-stale",
            context_window=128000,
            quality_tier=QualityTier.FRONTIER,
        )
        registry._cache["openai/gpt-4o-stale"] = RegistryEntry(
            info=stale_info,
            fetched_at=datetime.utcnow() - timedelta(hours=1),
        )
        registry._last_refresh = datetime.utcnow() - timedelta(hours=1)

        # Mock provider that always fails
        mock_provider = MagicMock()
        mock_provider.list_available_models = MagicMock(
            side_effect=ConnectionError("API unavailable")
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await registry.refresh_registry(mock_provider, max_retries=2)

        # Stale cache should be preserved
        assert "openai/gpt-4o-stale" in registry._cache
        assert registry._refresh_failures == 2

    @pytest.mark.asyncio
    async def test_refresh_resets_failure_count_on_success(self):
        """refresh_registry() should reset failure count on successful refresh."""
        from llm_council.metadata.registry import ModelRegistry

        registry = ModelRegistry()
        registry._refresh_failures = 5  # Previous failures

        mock_provider = MagicMock()
        mock_provider.list_available_models = MagicMock(return_value=["openai/gpt-4o"])
        mock_provider.get_model_info = MagicMock(
            return_value=ModelInfo(
                id="openai/gpt-4o",
                context_window=128000,
                quality_tier=QualityTier.FRONTIER,
            )
        )

        await registry.refresh_registry(mock_provider)

        assert registry._refresh_failures == 0


class TestRegistryThreadSafety:
    """Test thread safety of ModelRegistry."""

    @pytest.mark.asyncio
    async def test_registry_has_async_lock(self):
        """ModelRegistry should use asyncio.Lock for thread safety."""
        from llm_council.metadata.registry import ModelRegistry

        registry = ModelRegistry()

        assert hasattr(registry, "_lock")
        assert isinstance(registry._lock, asyncio.Lock)
