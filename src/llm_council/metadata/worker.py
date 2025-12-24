"""Background Discovery Worker for ADR-028.

This module implements the background worker that periodically refreshes
the model registry. It runs in the Control Plane, separate from the
request-time Data Plane operations.

The worker:
- Refreshes the registry at a configurable interval
- Handles errors gracefully with continued operation
- Supports graceful shutdown via event
- Logs refresh events for observability

Example:
    >>> import asyncio
    >>> from llm_council.metadata.worker import run_discovery_worker
    >>> from llm_council.metadata.registry import get_registry
    >>> from llm_council.metadata import get_provider
    >>>
    >>> async def main():
    ...     registry = get_registry()
    ...     provider = get_provider()
    ...     shutdown = asyncio.Event()
    ...
    ...     worker = asyncio.create_task(
    ...         run_discovery_worker(registry, provider, 300, shutdown)
    ...     )
    ...
    ...     # Later, to stop:
    ...     shutdown.set()
    ...     await worker
"""

import asyncio
import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .protocol import MetadataProvider
    from .registry import ModelRegistry

logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_INTERVAL_SECONDS = 300  # 5 minutes


async def run_discovery_worker(
    registry: "ModelRegistry",
    provider: "MetadataProvider",
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
    shutdown_event: Optional[asyncio.Event] = None,
) -> None:
    """Background worker that refreshes model registry periodically.

    This worker runs in the Control Plane and should be started at
    application startup. It refreshes the registry at the specified
    interval, handling errors gracefully.

    Args:
        registry: ModelRegistry to refresh
        provider: MetadataProvider to fetch model list from
        interval_seconds: Seconds between refresh attempts (default: 300)
        shutdown_event: Optional event to signal graceful shutdown

    Raises:
        asyncio.CancelledError: If the worker task is cancelled

    Example:
        >>> shutdown = asyncio.Event()
        >>> worker = asyncio.create_task(
        ...     run_discovery_worker(registry, provider, 300, shutdown)
        ... )
        >>> # To stop:
        >>> shutdown.set()
        >>> await worker
    """
    logger.info(f"Starting discovery worker (interval: {interval_seconds}s)")

    while True:
        try:
            # Check for shutdown before refresh
            if shutdown_event and shutdown_event.is_set():
                logger.info("Discovery worker shutting down")
                break

            # Perform refresh
            logger.debug("Discovery worker starting refresh")
            await registry.refresh_registry(provider)
            logger.debug("Discovery worker refresh complete")

        except asyncio.CancelledError:
            logger.info("Discovery worker cancelled")
            raise

        except Exception as e:
            logger.error(f"Discovery worker error during refresh: {e}")
            # Continue running despite errors

        # Wait for next interval or shutdown
        try:
            if shutdown_event:
                # Use wait_for with timeout to allow shutdown check
                try:
                    await asyncio.wait_for(
                        shutdown_event.wait(),
                        timeout=interval_seconds,
                    )
                    # If we get here, shutdown was signaled
                    logger.info("Discovery worker shutting down")
                    break
                except asyncio.TimeoutError:
                    # Normal timeout, continue to next refresh
                    pass
            else:
                # No shutdown event, just sleep
                await asyncio.sleep(interval_seconds)

        except asyncio.CancelledError:
            logger.info("Discovery worker cancelled during sleep")
            raise

    logger.info("Discovery worker stopped")
