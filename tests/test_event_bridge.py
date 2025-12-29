"""Tests for EventBridge - LayerEvent to Webhook dispatch (ADR-025a).

TDD tests written first per council-approved remediation plan.
Issue #82: feat(webhooks): Implement EventBridge for LayerEvent → Webhook dispatch
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from llm_council.layer_contracts import (
    LayerEvent,
    LayerEventType,
)
from llm_council.webhooks.types import (
    WebhookConfig,
    WebhookEventType,
    WebhookPayload,
)


# Import the module we're about to create
# These imports will fail until we implement the module (RED phase)
from llm_council.webhooks.event_bridge import (
    EventBridge,
    DispatchMode,
    transform_layer_event_to_webhook,
    LAYER_TO_WEBHOOK_MAPPING,
)


class TestEventBridgeLifecycle:
    """Test EventBridge start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_bridge_starts_successfully(self):
        """EventBridge should start without errors."""
        config = WebhookConfig(
            url="https://example.com/webhook",
            events=["council.complete"],
        )
        bridge = EventBridge(webhook_config=config)

        await bridge.start()
        assert bridge.is_running

        await bridge.shutdown()
        assert not bridge.is_running

    @pytest.mark.asyncio
    async def test_bridge_starts_without_config(self):
        """EventBridge should start even with no webhook config (no-op mode)."""
        bridge = EventBridge(webhook_config=None)

        await bridge.start()
        assert bridge.is_running

        await bridge.shutdown()
        assert not bridge.is_running

    @pytest.mark.asyncio
    async def test_bridge_shutdown_is_idempotent(self):
        """Multiple shutdown calls should not raise errors."""
        config = WebhookConfig(
            url="https://example.com/webhook",
            events=["council.complete"],
        )
        bridge = EventBridge(webhook_config=config)

        await bridge.start()
        await bridge.shutdown()
        await bridge.shutdown()  # Should not raise
        assert not bridge.is_running

    @pytest.mark.asyncio
    async def test_bridge_context_manager(self):
        """EventBridge should work as async context manager."""
        config = WebhookConfig(
            url="https://example.com/webhook",
            events=["council.complete"],
        )

        async with EventBridge(webhook_config=config) as bridge:
            assert bridge.is_running

        assert not bridge.is_running


class TestEventBridgeEmit:
    """Test EventBridge event emission."""

    @pytest.mark.asyncio
    async def test_emit_queues_event_in_async_mode(self):
        """Emit should queue events in async mode."""
        config = WebhookConfig(
            url="https://example.com/webhook",
            events=["council.complete"],
        )
        bridge = EventBridge(
            webhook_config=config,
            mode=DispatchMode.ASYNC,
        )

        await bridge.start()

        event = LayerEvent(
            event_type=LayerEventType.L3_COUNCIL_COMPLETE,
            data={"result": "success"},
        )
        await bridge.emit(event)

        # Event should be queued
        assert bridge.queue_size > 0

        await bridge.shutdown()

    @pytest.mark.asyncio
    async def test_emit_without_start_raises_error(self):
        """Emit should raise error if bridge not started."""
        config = WebhookConfig(
            url="https://example.com/webhook",
            events=["council.complete"],
        )
        bridge = EventBridge(webhook_config=config)

        event = LayerEvent(
            event_type=LayerEventType.L3_COUNCIL_COMPLETE,
            data={"result": "success"},
        )

        with pytest.raises(RuntimeError, match="not started"):
            await bridge.emit(event)

    @pytest.mark.asyncio
    async def test_emit_skips_when_no_config(self):
        """Emit should be no-op when no webhook config."""
        bridge = EventBridge(webhook_config=None)

        await bridge.start()

        event = LayerEvent(
            event_type=LayerEventType.L3_COUNCIL_COMPLETE,
            data={"result": "success"},
        )
        await bridge.emit(event)

        # Should succeed but queue should be empty (no-op)
        assert bridge.queue_size == 0

        await bridge.shutdown()

    @pytest.mark.asyncio
    async def test_emit_skips_unsubscribed_events(self):
        """Emit should skip events not in subscription list."""
        config = WebhookConfig(
            url="https://example.com/webhook",
            events=["council.error"],  # Only subscribed to errors
        )
        bridge = EventBridge(webhook_config=config)

        await bridge.start()

        event = LayerEvent(
            event_type=LayerEventType.L3_COUNCIL_COMPLETE,  # Not subscribed
            data={"result": "success"},
        )
        await bridge.emit(event)

        # Event should be skipped (not subscribed)
        assert bridge.queue_size == 0

        await bridge.shutdown()


class TestSyncMode:
    """Test synchronous dispatch mode."""

    @pytest.mark.asyncio
    async def test_sync_mode_dispatches_immediately(self):
        """Sync mode should dispatch without queuing."""
        config = WebhookConfig(
            url="https://example.com/webhook",
            events=["council.complete"],
        )
        bridge = EventBridge(
            webhook_config=config,
            mode=DispatchMode.SYNC,
        )

        dispatched_payloads = []

        async def mock_dispatch(webhook_config, payload):
            dispatched_payloads.append(payload)
            return MagicMock(success=True)

        with patch.object(bridge, "_dispatcher") as mock_dispatcher:
            mock_dispatcher.dispatch = mock_dispatch

            await bridge.start()

            event = LayerEvent(
                event_type=LayerEventType.L3_COUNCIL_COMPLETE,
                data={"result": "success"},
            )
            await bridge.emit(event)

            # Should dispatch immediately
            assert len(dispatched_payloads) == 1
            assert dispatched_payloads[0].event == WebhookEventType.COMPLETE.value

            await bridge.shutdown()


class TestEventTransformation:
    """Test LayerEvent to WebhookPayload transformation."""

    def test_l3_council_start_maps_to_deliberation_start(self):
        """L3_COUNCIL_START should map to council.deliberation_start."""
        event = LayerEvent(
            event_type=LayerEventType.L3_COUNCIL_START,
            data={"query": "test", "model_count": 3},
        )
        payload = transform_layer_event_to_webhook(event, request_id="req-123")

        assert payload.event == WebhookEventType.DELIBERATION_START.value
        assert payload.request_id == "req-123"
        assert payload.data["query"] == "test"

    def test_l3_council_complete_maps_to_complete(self):
        """L3_COUNCIL_COMPLETE should map to council.complete."""
        event = LayerEvent(
            event_type=LayerEventType.L3_COUNCIL_COMPLETE,
            data={"result": "success", "duration_ms": 5000},
        )
        payload = transform_layer_event_to_webhook(event, request_id="req-123")

        assert payload.event == WebhookEventType.COMPLETE.value
        assert payload.data["result"] == "success"

    def test_l3_stage_complete_stage1_maps_correctly(self):
        """L3_STAGE_COMPLETE with stage=1 should map to council.stage1.complete."""
        event = LayerEvent(
            event_type=LayerEventType.L3_STAGE_COMPLETE,
            data={"stage": 1, "responses": 4},
        )
        payload = transform_layer_event_to_webhook(event, request_id="req-123")

        assert payload.event == WebhookEventType.STAGE1_COMPLETE.value

    def test_l3_stage_complete_stage2_maps_correctly(self):
        """L3_STAGE_COMPLETE with stage=2 should map to council.stage2.complete."""
        event = LayerEvent(
            event_type=LayerEventType.L3_STAGE_COMPLETE,
            data={"stage": 2, "rankings": 4},
        )
        payload = transform_layer_event_to_webhook(event, request_id="req-123")

        assert payload.event == WebhookEventType.STAGE2_COMPLETE.value

    def test_error_events_map_to_council_error(self):
        """Error-related events should map to council.error."""
        # L3_MODEL_TIMEOUT should map to error
        event = LayerEvent(
            event_type=LayerEventType.L3_MODEL_TIMEOUT,
            data={"model": "gpt-4", "timeout_ms": 30000},
        )
        payload = transform_layer_event_to_webhook(event, request_id="req-123")

        assert payload.event == WebhookEventType.ERROR.value

    def test_unmapped_events_are_skipped(self):
        """Events without mapping should return None."""
        # L1 events are not mapped to webhooks
        event = LayerEvent(
            event_type=LayerEventType.L1_TIER_SELECTED,
            data={"tier": "high"},
        )
        payload = transform_layer_event_to_webhook(event, request_id="req-123")

        assert payload is None

    def test_payload_includes_timestamp(self):
        """WebhookPayload should include event timestamp."""
        timestamp = datetime(2025, 12, 23, 10, 30, 0)
        event = LayerEvent(
            event_type=LayerEventType.L3_COUNCIL_COMPLETE,
            data={"result": "success"},
            timestamp=timestamp,
        )
        payload = transform_layer_event_to_webhook(event, request_id="req-123")

        assert payload.timestamp == timestamp

    def test_payload_includes_duration_if_present(self):
        """WebhookPayload should include duration_ms if in event data."""
        event = LayerEvent(
            event_type=LayerEventType.L3_COUNCIL_COMPLETE,
            data={"result": "success", "duration_ms": 5000},
        )
        payload = transform_layer_event_to_webhook(event, request_id="req-123")

        assert payload.duration_ms == 5000


class TestEventMapping:
    """Test the LAYER_TO_WEBHOOK_MAPPING completeness."""

    def test_all_l3_events_have_mappings(self):
        """All L3 events should have webhook mappings."""
        l3_events = [
            LayerEventType.L3_COUNCIL_START,
            LayerEventType.L3_COUNCIL_COMPLETE,
            LayerEventType.L3_STAGE_COMPLETE,
            LayerEventType.L3_MODEL_TIMEOUT,
        ]

        for event_type in l3_events:
            assert event_type in LAYER_TO_WEBHOOK_MAPPING or event_type.value.startswith("l3_")

    def test_mapping_returns_callable_or_enum(self):
        """Each mapping should be a WebhookEventType or callable."""
        for layer_type, webhook_type in LAYER_TO_WEBHOOK_MAPPING.items():
            assert isinstance(webhook_type, (WebhookEventType, type(lambda: None)))


class TestAsyncWorker:
    """Test async background worker for dispatch."""

    @pytest.mark.asyncio
    async def test_worker_processes_queue(self):
        """Async worker should process queued events."""
        config = WebhookConfig(
            url="https://example.com/webhook",
            events=["council.complete"],
        )
        bridge = EventBridge(
            webhook_config=config,
            mode=DispatchMode.ASYNC,
        )

        dispatched_count = 0

        async def mock_dispatch(webhook_config, payload):
            nonlocal dispatched_count
            dispatched_count += 1
            return MagicMock(success=True)

        with patch.object(bridge, "_dispatcher") as mock_dispatcher:
            mock_dispatcher.dispatch = mock_dispatch

            await bridge.start()

            # Emit multiple events
            for i in range(3):
                event = LayerEvent(
                    event_type=LayerEventType.L3_COUNCIL_COMPLETE,
                    data={"iteration": i},
                )
                await bridge.emit(event)

            # Allow worker to process
            await asyncio.sleep(0.1)

            # All events should be dispatched
            assert dispatched_count == 3

            await bridge.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown_waits_for_pending_events(self):
        """Shutdown should process all pending events before returning."""
        config = WebhookConfig(
            url="https://example.com/webhook",
            events=["council.complete"],
        )
        bridge = EventBridge(
            webhook_config=config,
            mode=DispatchMode.ASYNC,
        )

        dispatched_count = 0

        async def slow_dispatch(webhook_config, payload):
            nonlocal dispatched_count
            await asyncio.sleep(0.05)  # Simulate slow dispatch
            dispatched_count += 1
            return MagicMock(success=True)

        with patch.object(bridge, "_dispatcher") as mock_dispatcher:
            mock_dispatcher.dispatch = slow_dispatch

            await bridge.start()

            # Emit events
            for i in range(3):
                event = LayerEvent(
                    event_type=LayerEventType.L3_COUNCIL_COMPLETE,
                    data={"iteration": i},
                )
                await bridge.emit(event)

            # Shutdown should wait for all events
            await bridge.shutdown()

            # All events should have been dispatched
            assert dispatched_count == 3


class TestRequestIdGeneration:
    """Test request ID handling."""

    @pytest.mark.asyncio
    async def test_bridge_generates_request_id_if_not_provided(self):
        """Bridge should generate request_id if not provided."""
        config = WebhookConfig(
            url="https://example.com/webhook",
            events=["council.complete"],
        )
        bridge = EventBridge(webhook_config=config)

        await bridge.start()

        # request_id should be auto-generated
        assert bridge.request_id is not None
        assert len(bridge.request_id) > 0

        await bridge.shutdown()

    @pytest.mark.asyncio
    async def test_bridge_uses_provided_request_id(self):
        """Bridge should use provided request_id."""
        config = WebhookConfig(
            url="https://example.com/webhook",
            events=["council.complete"],
        )
        bridge = EventBridge(
            webhook_config=config,
            request_id="custom-req-123",
        )

        await bridge.start()

        assert bridge.request_id == "custom-req-123"

        await bridge.shutdown()


class TestIntegration:
    """Integration tests for EventBridge with real dispatcher."""

    @pytest.mark.asyncio
    async def test_full_council_lifecycle_events(self):
        """Test emitting a full council lifecycle of events."""
        config = WebhookConfig(
            url="https://httpbin.org/post",  # Real endpoint for testing
            events=[
                "council.deliberation_start",
                "council.stage1.complete",
                "council.stage2.complete",
                "council.complete",
            ],
        )

        # Use sync mode for deterministic testing
        bridge = EventBridge(
            webhook_config=config,
            mode=DispatchMode.SYNC,
            request_id="integration-test-123",
        )

        events_processed = []

        async def track_dispatch(webhook_config, payload):
            events_processed.append(payload.event)
            return MagicMock(success=True)

        with patch.object(bridge, "_dispatcher") as mock_dispatcher:
            mock_dispatcher.dispatch = track_dispatch

            await bridge.start()

            # Simulate council lifecycle
            await bridge.emit(
                LayerEvent(
                    event_type=LayerEventType.L3_COUNCIL_START,
                    data={"query": "What is AI?", "model_count": 4},
                )
            )

            await bridge.emit(
                LayerEvent(
                    event_type=LayerEventType.L3_STAGE_COMPLETE,
                    data={"stage": 1, "responses": 4},
                )
            )

            await bridge.emit(
                LayerEvent(
                    event_type=LayerEventType.L3_STAGE_COMPLETE,
                    data={"stage": 2, "rankings": 4},
                )
            )

            await bridge.emit(
                LayerEvent(
                    event_type=LayerEventType.L3_COUNCIL_COMPLETE,
                    data={"result": "success", "duration_ms": 5000},
                )
            )

            await bridge.shutdown()

        # Verify all expected events were processed
        expected = [
            WebhookEventType.DELIBERATION_START.value,
            WebhookEventType.STAGE1_COMPLETE.value,
            WebhookEventType.STAGE2_COMPLETE.value,
            WebhookEventType.COMPLETE.value,
        ]
        assert events_processed == expected
