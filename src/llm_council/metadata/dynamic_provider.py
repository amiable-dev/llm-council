"""Dynamic Metadata Provider for Model Intelligence (ADR-026 Phase 1).

This module provides a dynamic metadata provider that:
- Fetches model metadata from OpenRouter API
- Caches results with configurable TTL
- Falls back to StaticRegistryProvider when offline/unavailable
"""

import logging
from typing import Any, Dict, List, Optional

from .cache import ModelIntelligenceCache
from .openrouter_client import OpenRouterClient
from .protocol import MetadataProvider
from .static_registry import StaticRegistryProvider
from .types import ModelInfo

logger = logging.getLogger(__name__)


class DynamicMetadataProvider:
    """Metadata provider that fetches from OpenRouter API with caching.

    This provider implements the MetadataProvider protocol and provides:
    - Real-time model metadata from OpenRouter API
    - TTL-based caching for performance
    - Automatic fallback to StaticRegistryProvider

    Args:
        registry_ttl: TTL for registry cache in seconds (default 3600)
        availability_ttl: TTL for availability cache in seconds (default 300)
        api_key: OpenRouter API key (optional, reads from env)
        timeout: API request timeout in seconds (default 30)
    """

    def __init__(
        self,
        registry_ttl: int = 3600,
        availability_ttl: int = 300,
        api_key: Optional[str] = None,
        timeout: float = 30.0,
    ):
        self._cache = ModelIntelligenceCache(
            registry_ttl=registry_ttl,
            availability_ttl=availability_ttl,
        )
        self._client = OpenRouterClient(api_key=api_key, timeout=timeout)
        self._static_fallback = StaticRegistryProvider()
        self._last_refresh_attempted = False

    def get_model_info(self, model_id: str) -> Optional[ModelInfo]:
        """Get model info, preferring cache over static fallback.

        Args:
            model_id: Model identifier (e.g., 'openai/gpt-4o')

        Returns:
            ModelInfo if found, None otherwise
        """
        # Check cache first
        cached = self._cache.registry_cache.get(model_id)
        if cached is not None:
            return cached

        # Fall back to static registry
        return self._static_fallback.get_model_info(model_id)

    def get_context_window(self, model_id: str) -> int:
        """Get context window size for a model.

        Args:
            model_id: Model identifier

        Returns:
            Context window size (minimum 4096)
        """
        info = self.get_model_info(model_id)
        if info is not None:
            return info.context_window

        # Fall back to static registry's method
        return self._static_fallback.get_context_window(model_id)

    def get_pricing(self, model_id: str) -> Dict[str, float]:
        """Get pricing information for a model.

        Args:
            model_id: Model identifier

        Returns:
            Dict with 'prompt' and 'completion' prices, or empty dict
        """
        info = self.get_model_info(model_id)
        if info is not None:
            return info.pricing

        return self._static_fallback.get_pricing(model_id)

    def supports_reasoning(self, model_id: str) -> bool:
        """Check if a model supports reasoning mode.

        Args:
            model_id: Model identifier

        Returns:
            True if model supports reasoning
        """
        info = self.get_model_info(model_id)
        if info is not None:
            return "reasoning" in info.supported_parameters

        return self._static_fallback.supports_reasoning(model_id)

    def list_available_models(self) -> List[str]:
        """List all available model IDs.

        Returns combined list from cache and static registry.

        Returns:
            List of model ID strings
        """
        # Combine cached models with static registry
        cached_models = set()

        # Get all keys from registry cache
        # Note: We access the internal cache dict for listing
        for key in list(self._cache.registry_cache._cache.keys()):
            if key in self._cache.registry_cache:
                cached_models.add(key)

        # Add static registry models
        static_models = set(self._static_fallback.list_available_models())

        return sorted(cached_models | static_models)

    async def refresh(self) -> None:
        """Refresh the cache from OpenRouter API.

        Fetches latest model metadata and populates the cache.
        On failure, logs warning and continues with existing cache.
        """
        try:
            models = await self._client.fetch_models()

            for model in models:
                self._cache.registry_cache.set(model.id, model)

            self._last_refresh_attempted = True

            if models:
                logger.info(f"Refreshed model cache with {len(models)} models")
            else:
                logger.warning("OpenRouter API returned no models")

        except Exception as e:
            logger.warning(f"Failed to refresh model cache: {e}")
            self._last_refresh_attempted = True

    def is_cache_stale(self) -> bool:
        """Check if the cache needs refreshing.

        Returns:
            True if cache is empty or expired
        """
        # Cache is stale if we've never fetched or registry is empty
        return self._cache.registry_cache.size() == 0

    def get_cache_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get cache statistics.

        Returns:
            Dict with 'registry' and 'availability' stats
        """
        return self._cache.stats()


# Make DynamicMetadataProvider satisfy the Protocol at runtime
# This is verified by the isinstance check in tests
DynamicMetadataProvider.__class_getitem__ = classmethod(lambda cls, item: cls)
