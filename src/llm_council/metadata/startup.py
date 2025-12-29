"""Application Lifecycle Hooks for Discovery (ADR-028).

This module provides startup and shutdown lifecycle hooks for the
discovery worker. These should be called at application startup/shutdown.

Example:
    >>> import asyncio
    >>> from llm_council.metadata.startup import (
    ...     start_discovery_worker,
    ...     stop_discovery_worker,
    ... )
    >>>
    >>> async def main():
    ...     # Start worker at app startup
    ...     await start_discovery_worker()
    ...
    ...     # Your application runs here...
    ...
    ...     # Stop worker at app shutdown
    ...     await stop_discovery_worker()
"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Module-level state for worker management
_worker_task: Optional[asyncio.Task] = None
_shutdown_event: Optional[asyncio.Event] = None


def _is_discovery_enabled() -> bool:
    """Check if discovery is enabled in configuration.

    Returns:
        True if model_intelligence.enabled AND discovery.enabled
    """
    try:
        from ..unified_config import get_config

        config = get_config()
        return config.model_intelligence.enabled and config.model_intelligence.discovery.enabled
    except Exception:
        return False


def _get_discovery_config():
    """Get discovery configuration.

    Returns:
        DiscoveryConfig or None
    """
    try:
        from ..unified_config import get_config

        return get_config().model_intelligence.discovery
    except Exception:
        return None


async def start_discovery_worker() -> None:
    """Start the discovery worker at application startup.

    This function:
    1. Checks if discovery is enabled
    2. Performs initial registry refresh
    3. Starts background worker task

    Should be called at application startup before serving requests.
    """
    global _worker_task, _shutdown_event

    if not _is_discovery_enabled():
        logger.info("Discovery disabled, skipping worker startup")
        return

    config = _get_discovery_config()
    if config is None:
        logger.warning("Failed to get discovery config, skipping worker startup")
        return

    from .registry import get_registry
    from .worker import run_discovery_worker
    from .dynamic_provider import DynamicMetadataProvider

    registry = get_registry()
    provider = DynamicMetadataProvider()

    # Initial refresh before serving requests
    logger.info("Performing initial registry refresh...")
    try:
        await registry.refresh_registry(provider, max_retries=config.max_refresh_retries)
        logger.info(f"Initial refresh complete: {len(registry._cache)} models")
    except Exception as e:
        logger.error(f"Initial refresh failed: {e}")
        # Continue anyway - worker will retry

    # Create shutdown event
    _shutdown_event = asyncio.Event()

    # Start background worker
    _worker_task = asyncio.create_task(
        run_discovery_worker(
            registry=registry,
            provider=provider,
            interval_seconds=config.refresh_interval_seconds,
            shutdown_event=_shutdown_event,
        )
    )

    logger.info(f"Discovery worker started (interval: {config.refresh_interval_seconds}s)")


async def stop_discovery_worker() -> None:
    """Stop the discovery worker at application shutdown.

    This function:
    1. Signals the worker to stop
    2. Waits for worker to complete

    Should be called at application shutdown.
    """
    global _worker_task, _shutdown_event

    if _shutdown_event is None or _worker_task is None:
        logger.debug("Discovery worker not running, nothing to stop")
        return

    logger.info("Stopping discovery worker...")

    # Signal shutdown
    _shutdown_event.set()

    # Wait for worker to complete
    try:
        await asyncio.wait_for(_worker_task, timeout=5.0)
        logger.info("Discovery worker stopped gracefully")
    except asyncio.TimeoutError:
        logger.warning("Discovery worker did not stop in time, cancelling...")
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass

    # Reset state
    _worker_task = None
    _shutdown_event = None


def get_worker_status() -> dict:
    """Get current worker status for health checks.

    Returns:
        Dict with worker status information
    """
    from .registry import get_registry

    registry = get_registry()

    return {
        "worker_running": _worker_task is not None and not _worker_task.done(),
        "discovery_enabled": _is_discovery_enabled(),
        "registry_status": registry.get_health_status(),
    }


def _reset_worker_state() -> None:
    """Reset worker state for testing.

    This is intended for test cleanup only.
    """
    global _worker_task, _shutdown_event
    _worker_task = None
    _shutdown_event = None
