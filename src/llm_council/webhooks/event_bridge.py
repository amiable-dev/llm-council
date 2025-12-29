"""EventBridge - LayerEvent to Webhook dispatch bridge (ADR-025a).

This module bridges the gap between internal LayerEvents (from layer_contracts.py)
and external webhook delivery (via WebhookDispatcher). It implements the Hybrid
Pub/Sub pattern approved by the LLM Council reasoning tier.

Key features:
- Async mode: Events queued for background dispatch (non-blocking)
- Sync mode: Immediate dispatch (for testing and debugging)
- Event filtering: Only dispatches events subscriber is interested in
- Event transformation: Maps LayerEventType to WebhookEventType

Usage:
    from llm_council.webhooks.event_bridge import EventBridge, DispatchMode
    from llm_council.webhooks import WebhookConfig
    from llm_council.layer_contracts import LayerEvent, LayerEventType

    config = WebhookConfig(
        url="https://example.com/webhook",
        events=["council.complete", "council.error"],
    )

    async with EventBridge(webhook_config=config) as bridge:
        await bridge.emit(LayerEvent(
            event_type=LayerEventType.L3_COUNCIL_COMPLETE,
            data={"result": "success"},
        ))

GitHub Issue: #82
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, Optional, Union
from uuid import uuid4

from llm_council.layer_contracts import LayerEvent, LayerEventType
from llm_council.webhooks.types import (
    WebhookConfig,
    WebhookEventType,
    WebhookPayload,
)
from llm_council.webhooks.dispatcher import WebhookDispatcher


logger = logging.getLogger(__name__)


class DispatchMode(Enum):
    """Dispatch mode for the EventBridge.

    ASYNC: Events are queued and dispatched by a background worker.
           Non-blocking, suitable for production.
    SYNC: Events are dispatched immediately in the calling coroutine.
          Blocking, suitable for testing and debugging.
    """

    ASYNC = "async"
    SYNC = "sync"


# Type for mapping functions that handle stage-specific events
StageMapper = Callable[[LayerEvent], Optional[WebhookEventType]]


def _map_stage_complete(event: LayerEvent) -> Optional[WebhookEventType]:
    """Map L3_STAGE_COMPLETE based on stage number in data."""
    stage = event.data.get("stage")
    if stage == 1:
        return WebhookEventType.STAGE1_COMPLETE
    elif stage == 2:
        return WebhookEventType.STAGE2_COMPLETE
    # Stage 3 completion is covered by L3_COUNCIL_COMPLETE
    return None


# Mapping from LayerEventType to WebhookEventType
# Some entries are direct mappings, others are callables for conditional mapping
LAYER_TO_WEBHOOK_MAPPING: Dict[LayerEventType, Union[WebhookEventType, StageMapper]] = {
    LayerEventType.L3_COUNCIL_START: WebhookEventType.DELIBERATION_START,
    LayerEventType.L3_COUNCIL_COMPLETE: WebhookEventType.COMPLETE,
    LayerEventType.L3_STAGE_COMPLETE: _map_stage_complete,
    LayerEventType.L3_MODEL_TIMEOUT: WebhookEventType.ERROR,
    # L4 gateway errors also map to council.error
    LayerEventType.L4_CIRCUIT_BREAKER_OPEN: WebhookEventType.ERROR,
}


def transform_layer_event_to_webhook(
    event: LayerEvent,
    request_id: str,
) -> Optional[WebhookPayload]:
    """Transform a LayerEvent to a WebhookPayload.

    Args:
        event: The LayerEvent to transform.
        request_id: Unique identifier for the council request.

    Returns:
        WebhookPayload if the event type has a mapping, None otherwise.
    """
    mapping = LAYER_TO_WEBHOOK_MAPPING.get(event.event_type)

    if mapping is None:
        # No mapping for this event type
        return None

    # Resolve the webhook event type
    if callable(mapping):
        webhook_type = mapping(event)
        if webhook_type is None:
            return None
    else:
        webhook_type = mapping

    # Extract duration_ms from data if present
    duration_ms = event.data.get("duration_ms")

    return WebhookPayload(
        event=webhook_type.value,
        request_id=request_id,
        timestamp=event.timestamp,
        data=event.data,
        duration_ms=duration_ms,
    )


@dataclass
class EventBridge:
    """Bridge between LayerEvents and webhook dispatch.

    Implements the Hybrid Pub/Sub pattern:
    - Async mode: Non-blocking background dispatch via queue
    - Sync mode: Immediate blocking dispatch for testing

    Attributes:
        webhook_config: Configuration for webhook delivery. If None, operates in no-op mode.
        mode: Dispatch mode (ASYNC or SYNC).
        request_id: Unique identifier for this council session.
    """

    webhook_config: Optional[WebhookConfig] = None
    mode: DispatchMode = DispatchMode.ASYNC
    request_id: Optional[str] = None

    # Private state
    _dispatcher: WebhookDispatcher = field(default_factory=WebhookDispatcher)
    _queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    _worker_task: Optional[asyncio.Task] = field(default=None)
    _running: bool = field(default=False)
    _subscribed_events: set = field(default_factory=set)

    def __post_init__(self):
        """Initialize the EventBridge after dataclass creation."""
        # Generate request_id if not provided
        if self.request_id is None:
            self.request_id = str(uuid4())

        # Parse subscribed events from config
        if self.webhook_config is not None:
            self._subscribed_events = set(self.webhook_config.events)

    @property
    def is_running(self) -> bool:
        """Check if the bridge is running."""
        return self._running

    @property
    def queue_size(self) -> int:
        """Get the number of events in the queue."""
        return self._queue.qsize()

    async def start(self) -> None:
        """Start the EventBridge.

        In ASYNC mode, this starts the background worker task.
        """
        if self._running:
            return

        self._running = True

        if self.mode == DispatchMode.ASYNC and self.webhook_config is not None:
            self._worker_task = asyncio.create_task(self._worker())
            logger.debug("EventBridge worker started (async mode)")
        else:
            logger.debug(
                "EventBridge started (sync mode=%s, has_config=%s)",
                self.mode == DispatchMode.SYNC,
                self.webhook_config is not None,
            )

    async def shutdown(self) -> None:
        """Shutdown the EventBridge.

        Processes all pending events before returning.
        """
        if not self._running:
            return

        self._running = False

        # In async mode, signal worker to stop and wait for pending events
        if self._worker_task is not None:
            # Put sentinel to signal worker to stop
            await self._queue.put(None)

            # Wait for worker to finish
            try:
                await asyncio.wait_for(self._worker_task, timeout=30.0)
            except asyncio.TimeoutError:
                logger.warning("EventBridge worker did not finish within timeout")
                self._worker_task.cancel()

            self._worker_task = None

        logger.debug("EventBridge shutdown complete")

    async def emit(self, event: LayerEvent) -> None:
        """Emit a LayerEvent for webhook dispatch.

        Args:
            event: The LayerEvent to emit.

        Raises:
            RuntimeError: If the bridge is not started.
        """
        if not self._running:
            raise RuntimeError("EventBridge not started. Call start() first.")

        # No-op if no webhook config
        if self.webhook_config is None:
            return

        # Transform to webhook payload
        payload = transform_layer_event_to_webhook(event, self.request_id)

        if payload is None:
            # Event type not mapped to webhook
            logger.debug(
                "Event type %s has no webhook mapping, skipping",
                event.event_type.value,
            )
            return

        # Check if subscriber is interested in this event
        if payload.event not in self._subscribed_events:
            logger.debug(
                "Event %s not in subscription list, skipping",
                payload.event,
            )
            return

        # Dispatch based on mode
        if self.mode == DispatchMode.SYNC:
            await self._dispatch(payload)
        else:
            await self._queue.put(payload)

    async def _dispatch(self, payload: WebhookPayload) -> None:
        """Dispatch a webhook payload.

        Args:
            payload: The payload to dispatch.
        """
        try:
            result = await self._dispatcher.dispatch(self.webhook_config, payload)
            if result.success:
                logger.debug("Webhook dispatched successfully: %s", payload.event)
            else:
                logger.warning(
                    "Webhook dispatch failed: %s - %s",
                    payload.event,
                    result.error,
                )
        except Exception as e:
            logger.error("Webhook dispatch error: %s", e)

    async def _worker(self) -> None:
        """Background worker that processes the event queue."""
        logger.debug("EventBridge worker started")

        while True:
            try:
                # Wait for an event
                payload = await self._queue.get()

                # Check for shutdown sentinel
                if payload is None:
                    break

                # Dispatch the event
                await self._dispatch(payload)

            except asyncio.CancelledError:
                logger.debug("EventBridge worker cancelled")
                break
            except Exception as e:
                logger.error("EventBridge worker error: %s", e)

        # Process remaining events in queue before exiting
        while not self._queue.empty():
            try:
                payload = self._queue.get_nowait()
                if payload is not None:
                    await self._dispatch(payload)
            except asyncio.QueueEmpty:
                break
            except Exception as e:
                logger.error("EventBridge shutdown dispatch error: %s", e)

        logger.debug("EventBridge worker stopped")

    async def __aenter__(self) -> "EventBridge":
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.shutdown()


__all__ = [
    "EventBridge",
    "DispatchMode",
    "transform_layer_event_to_webhook",
    "LAYER_TO_WEBHOOK_MAPPING",
]
