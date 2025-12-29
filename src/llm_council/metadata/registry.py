"""Model Registry for Dynamic Candidate Discovery (ADR-028).

This module implements the Background Registry Pattern for model discovery:
- ModelRegistry: Thread-safe singleton cache of model metadata
- RegistryEntry: Cached model info with timestamp tracking
- get_registry(): Factory function for singleton access

The registry separates Control Plane (background refresh) from Data Plane
(request-time lookup), ensuring zero API calls on the critical request path.

Example:
    >>> registry = get_registry()
    >>> if not registry.is_stale:
    ...     candidates = registry.get_candidates()
    ...     model = registry.get_model("openai/gpt-4o")
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Dict, List, Optional

from .types import ModelInfo, ModelStatus

if TYPE_CHECKING:
    from .protocol import MetadataProvider

logger = logging.getLogger(__name__)


def _emit_discovery_event(event_type, data: dict) -> None:
    """Emit a discovery event for observability.

    Lazy import to avoid circular dependencies.
    """
    try:
        from ..layer_contracts import LayerEventType, emit_layer_event

        emit_layer_event(getattr(LayerEventType, event_type), data)
    except Exception as e:
        logger.debug(f"Failed to emit discovery event {event_type}: {e}")


# Configuration defaults
DEFAULT_STALE_THRESHOLD_MINUTES = 30
DEFAULT_MAX_RETRIES = 3


@dataclass
class RegistryEntry:
    """Cached model information with staleness tracking.

    Attributes:
        info: The ModelInfo for this model
        fetched_at: When this entry was fetched
        is_deprecated: Whether the model is deprecated
    """

    info: ModelInfo
    fetched_at: datetime
    is_deprecated: bool = False


class ModelRegistry:
    """Thread-safe cache of available models with async refresh.

    Implements the Background Registry Pattern from ADR-028:
    - Control Plane: Background task calls refresh_registry() periodically
    - Data Plane: Request handlers call get_candidates()/get_model() without API calls

    The registry uses stale-while-revalidate pattern:
    - If refresh fails, stale data is preserved
    - is_stale property indicates if refresh is needed

    Attributes:
        _cache: Dict mapping model_id to RegistryEntry
        _lock: asyncio.Lock for thread-safe cache mutations
        _last_refresh: When the cache was last successfully refreshed
        _refresh_failures: Count of consecutive refresh failures
        _stale_threshold_minutes: Minutes after which cache is considered stale
    """

    def __init__(self, stale_threshold_minutes: int = DEFAULT_STALE_THRESHOLD_MINUTES):
        """Initialize empty registry.

        Args:
            stale_threshold_minutes: Minutes after which cache is stale (default: 30)
        """
        self._cache: Dict[str, RegistryEntry] = {}
        self._lock: asyncio.Lock = asyncio.Lock()
        self._last_refresh: Optional[datetime] = None
        self._refresh_failures: int = 0
        self._stale_threshold_minutes: int = stale_threshold_minutes

    @property
    def is_stale(self) -> bool:
        """Check if registry needs refresh.

        Returns:
            True if registry has never been refreshed or last refresh
            exceeds the stale threshold.
        """
        if self._last_refresh is None:
            return True
        threshold = timedelta(minutes=self._stale_threshold_minutes)
        return datetime.utcnow() - self._last_refresh > threshold

    def get_candidates(self) -> List[ModelInfo]:
        """Get all cached model info for discovery filtering.

        This is a read-only operation safe for the request path.
        Does NOT call any external APIs.

        Returns:
            List of ModelInfo for all cached models.
        """
        return [entry.info for entry in self._cache.values()]

    def get_model(self, model_id: str) -> Optional[ModelInfo]:
        """Get specific model info by ID (O(1) lookup).

        Args:
            model_id: Full model identifier (e.g., "openai/gpt-4o")

        Returns:
            ModelInfo if found, None otherwise.
        """
        entry = self._cache.get(model_id)
        return entry.info if entry else None

    async def refresh_registry(
        self,
        provider: "MetadataProvider",
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        """Background refresh of model registry.

        Implements stale-while-revalidate pattern:
        - On success: Updates cache, resets failure count
        - On failure: Retries with exponential backoff
        - If all retries fail: Keeps stale cache, increments failure count

        Args:
            provider: MetadataProvider to fetch model list from
            max_retries: Maximum retry attempts (default: 3)
        """
        # Emit start event
        _emit_discovery_event(
            "DISCOVERY_REFRESH_STARTED",
            {"provider": getattr(provider, "__class__", type(provider)).__name__},
        )
        start_time = time.monotonic()

        for attempt in range(max_retries):
            try:
                # Fetch model list from provider
                model_ids = provider.list_available_models()
                now = datetime.utcnow()

                # Build new cache
                new_cache: Dict[str, RegistryEntry] = {}
                for model_id in model_ids:
                    info = provider.get_model_info(model_id)
                    if info is None:
                        continue

                    # Check if model is deprecated (if provider supports status)
                    status = ModelStatus.AVAILABLE
                    if hasattr(provider, "get_model_status"):
                        status = provider.get_model_status(model_id)

                    # Filter deprecated models
                    if status == ModelStatus.DEPRECATED:
                        logger.debug(f"Filtering deprecated model: {model_id}")
                        continue

                    new_cache[model_id] = RegistryEntry(
                        info=info,
                        fetched_at=now,
                        is_deprecated=(status == ModelStatus.DEPRECATED),
                    )

                # Update cache atomically
                async with self._lock:
                    self._cache = new_cache
                    self._last_refresh = now
                    self._refresh_failures = 0

                # Calculate duration and emit success event
                duration_ms = int((time.monotonic() - start_time) * 1000)
                _emit_discovery_event(
                    "DISCOVERY_REFRESH_COMPLETE",
                    {
                        "provider": getattr(provider, "__class__", type(provider)).__name__,
                        "model_count": len(self._cache),
                        "duration_ms": duration_ms,
                    },
                )

                logger.info(f"Registry refreshed: {len(self._cache)} models")
                return

            except Exception as e:
                self._refresh_failures += 1

                # Emit failure event
                _emit_discovery_event(
                    "DISCOVERY_REFRESH_FAILED",
                    {
                        "provider": getattr(provider, "__class__", type(provider)).__name__,
                        "error": str(e),
                        "attempt": attempt + 1,
                        "max_retries": max_retries,
                    },
                )

                logger.warning(
                    f"Discovery refresh failed (attempt {attempt + 1}/{max_retries}): {e}"
                )

                if attempt < max_retries - 1:
                    backoff = 2**attempt  # Exponential backoff: 1, 2, 4 seconds
                    await asyncio.sleep(backoff)

        # All retries failed - keep stale cache and emit stale serve event
        _emit_discovery_event(
            "DISCOVERY_STALE_SERVE",
            {
                "provider": getattr(provider, "__class__", type(provider)).__name__,
                "model_count": len(self._cache),
                "refresh_failures": self._refresh_failures,
            },
        )

        logger.error(
            f"Discovery refresh failed after {max_retries} attempts. "
            f"Serving stale registry ({len(self._cache)} models)."
        )

    def get_health_status(self) -> Dict[str, object]:
        """Get health check status for observability.

        Returns:
            Dict with registry_size, last_refresh, is_stale, refresh_failures,
            stale_threshold_minutes
        """
        return {
            "registry_size": len(self._cache),
            "last_refresh": (self._last_refresh.isoformat() if self._last_refresh else None),
            "is_stale": self.is_stale,
            "refresh_failures": self._refresh_failures,
            "stale_threshold_minutes": self._stale_threshold_minutes,
        }


# Singleton instance
_registry: Optional[ModelRegistry] = None


def get_registry() -> ModelRegistry:
    """Get the singleton ModelRegistry instance.

    Returns:
        The global ModelRegistry instance.
    """
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry


def _reset_registry() -> None:
    """Reset the singleton registry (for testing only).

    This function is intended for test cleanup to ensure
    each test starts with a fresh registry.
    """
    global _registry
    _registry = None
