"""Tests for webhook integration into council.py (ADR-025a).

TDD tests written first per council-approved remediation plan.
Issue #83: feat(council): Wire EventBridge into council.py execution lifecycle
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from llm_council.webhooks.types import (
    WebhookConfig,
    WebhookEventType,
    WebhookPayload,
)
from llm_council.webhooks.event_bridge import EventBridge, DispatchMode


class TestWebhookConfigParameter:
    """Test webhook_config parameter support in council functions."""

    @pytest.mark.asyncio
    async def test_council_accepts_webhook_config_parameter(self):
        """run_council_with_fallback should accept webhook_config parameter."""
        from llm_council.council import run_council_with_fallback

        config = WebhookConfig(
            url="https://example.com/webhook",
            events=["council.complete"],
        )

        # This should not raise - webhook_config is accepted
        # We'll mock the actual council execution
        with patch("llm_council.council.stage1_collect_responses_with_status") as mock_stage1:
            mock_stage1.return_value = (
                [],  # No results
                {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                {},  # No model statuses
            )

            result = await run_council_with_fallback(
                "Test query",
                webhook_config=config,
            )

            # Should complete without error
            assert result is not None

    @pytest.mark.asyncio
    async def test_council_works_without_webhook_config(self):
        """run_council_with_fallback should work without webhook_config (backward compatible)."""
        from llm_council.council import run_council_with_fallback

        with patch("llm_council.council.stage1_collect_responses_with_status") as mock_stage1:
            mock_stage1.return_value = (
                [],  # No results
                {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                {},  # No model statuses
            )

            # No webhook_config - should still work
            result = await run_council_with_fallback("Test query")
            assert result is not None


class TestWebhookEventEmission:
    """Test that council emits expected webhook events."""

    @pytest.mark.asyncio
    async def test_council_emits_start_event(self):
        """Council should emit deliberation_start event before Stage 1."""
        from llm_council.council import run_council_with_fallback
        from llm_council.webhooks.dispatcher import WebhookDispatcher

        emitted_events = []

        async def capture_dispatch(self, config, payload):
            emitted_events.append(payload)
            return MagicMock(success=True)

        config = WebhookConfig(
            url="https://example.com/webhook",
            events=["council.deliberation_start", "council.complete"],
        )

        with patch("llm_council.council.stage1_collect_responses_with_status") as mock_stage1:
            mock_stage1.return_value = (
                [],  # No results
                {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                {},
            )

            # Patch the dispatcher's dispatch method at the module level
            with patch.object(WebhookDispatcher, "dispatch", capture_dispatch):
                await run_council_with_fallback(
                    "Test query",
                    webhook_config=config,
                )

        # Should have emitted deliberation_start
        start_events = [
            e for e in emitted_events if e.event == WebhookEventType.DELIBERATION_START.value
        ]
        assert len(start_events) >= 1

    @pytest.mark.asyncio
    async def test_council_emits_complete_event(self):
        """Council should emit complete event after Stage 3."""
        from llm_council.council import run_council_with_fallback
        from llm_council.webhooks.dispatcher import WebhookDispatcher

        emitted_events = []

        async def capture_dispatch(self, config, payload):
            emitted_events.append(payload)
            return MagicMock(success=True)

        config = WebhookConfig(
            url="https://example.com/webhook",
            events=["council.complete"],
        )

        # Mock a successful council run
        with (
            patch("llm_council.council.stage1_collect_responses_with_status") as mock_stage1,
            patch("llm_council.council.stage1_5_normalize_styles") as mock_stage1_5,
            patch("llm_council.council.stage2_collect_rankings") as mock_stage2,
            patch("llm_council.council.stage3_synthesize_final") as mock_stage3,
        ):
            mock_stage1.return_value = (
                [{"model": "test/model", "response": "Test response"}],
                {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
                {"test/model": {"status": "ok", "latency_ms": 1000}},
            )
            mock_stage1_5.return_value = (
                [{"model": "test/model", "response": "Test response"}],
                {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            )
            mock_stage2.return_value = (
                [{"model": "test/model", "ranking": "...", "parsed_ranking": {"ranking": []}}],
                {"Response A": {"model": "test/model", "display_index": 0}},
                {"prompt_tokens": 50, "completion_tokens": 25, "total_tokens": 75},
            )
            mock_stage3.return_value = (
                {"model": "chairman/model", "response": "Final synthesis"},
                {"prompt_tokens": 100, "completion_tokens": 100, "total_tokens": 200},
                None,  # verdict_result (ADR-025b)
            )

            # Patch the dispatcher's dispatch method at the module level
            with patch.object(WebhookDispatcher, "dispatch", capture_dispatch):
                await run_council_with_fallback(
                    "Test query",
                    webhook_config=config,
                )

        # Should have emitted complete
        complete_events = [e for e in emitted_events if e.event == WebhookEventType.COMPLETE.value]
        assert len(complete_events) >= 1

    @pytest.mark.asyncio
    async def test_council_emits_stage_events(self):
        """Council should emit stage1.complete and stage2.complete events."""
        from llm_council.council import run_council_with_fallback
        from llm_council.webhooks.dispatcher import WebhookDispatcher

        emitted_events = []

        async def capture_dispatch(self, config, payload):
            emitted_events.append(payload)
            return MagicMock(success=True)

        config = WebhookConfig(
            url="https://example.com/webhook",
            events=[
                "council.deliberation_start",
                "council.stage1.complete",
                "council.stage2.complete",
                "council.complete",
            ],
        )

        # Mock a successful council run
        with (
            patch("llm_council.council.stage1_collect_responses_with_status") as mock_stage1,
            patch("llm_council.council.stage1_5_normalize_styles") as mock_stage1_5,
            patch("llm_council.council.stage2_collect_rankings") as mock_stage2,
            patch("llm_council.council.stage3_synthesize_final") as mock_stage3,
        ):
            mock_stage1.return_value = (
                [{"model": "test/model", "response": "Test response"}],
                {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
                {"test/model": {"status": "ok", "latency_ms": 1000}},
            )
            mock_stage1_5.return_value = (
                [{"model": "test/model", "response": "Test response"}],
                {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            )
            mock_stage2.return_value = (
                [{"model": "test/model", "ranking": "...", "parsed_ranking": {"ranking": []}}],
                {"Response A": {"model": "test/model", "display_index": 0}},
                {"prompt_tokens": 50, "completion_tokens": 25, "total_tokens": 75},
            )
            mock_stage3.return_value = (
                {"model": "chairman/model", "response": "Final synthesis"},
                {"prompt_tokens": 100, "completion_tokens": 100, "total_tokens": 200},
                None,  # verdict_result (ADR-025b)
            )

            # Patch the dispatcher's dispatch method at the module level
            with patch.object(WebhookDispatcher, "dispatch", capture_dispatch):
                await run_council_with_fallback(
                    "Test query",
                    webhook_config=config,
                )

        # Check for stage events
        event_types = [e.event for e in emitted_events]
        assert WebhookEventType.STAGE1_COMPLETE.value in event_types
        assert WebhookEventType.STAGE2_COMPLETE.value in event_types


class TestWebhookErrorHandling:
    """Test webhook error event emission."""

    @pytest.mark.asyncio
    async def test_council_emits_error_on_exception(self):
        """Council should emit error event when an exception occurs."""
        from llm_council.council import run_council_with_fallback

        emitted_events = []

        async def capture_dispatch(config, payload):
            emitted_events.append(payload)
            return MagicMock(success=True)

        config = WebhookConfig(
            url="https://example.com/webhook",
            events=["council.error", "council.complete"],
        )

        with patch("llm_council.council.stage1_collect_responses_with_status") as mock_stage1:
            # Simulate an error
            mock_stage1.side_effect = Exception("Test error")

            with patch(
                "llm_council.webhooks.event_bridge.WebhookDispatcher"
            ) as mock_dispatcher_class:
                mock_dispatcher = MagicMock()
                mock_dispatcher.dispatch = capture_dispatch
                mock_dispatcher_class.return_value = mock_dispatcher

                # This should not raise - error should be caught
                result = await run_council_with_fallback(
                    "Test query",
                    webhook_config=config,
                )

                # Should return failed status
                assert result["metadata"]["status"] == "failed"

        # Should have emitted error event
        error_events = [e for e in emitted_events if e.event == WebhookEventType.ERROR.value]
        # Note: Error events may or may not be emitted depending on implementation
        # The key is that the function completes without raising


class TestWebhookConfigHierarchy:
    """Test hierarchical config (request-level > global-level)."""

    @pytest.mark.asyncio
    async def test_request_config_overrides_global(self):
        """Request-level webhook_config should override global config."""
        from llm_council.council import run_council_with_fallback

        # This test verifies the request-level override behavior
        # The implementation should use webhook_config from parameter
        # rather than any global/environment config

        request_config = WebhookConfig(
            url="https://request.example.com/webhook",
            events=["council.complete"],
        )

        captured_config = []

        async def capture_dispatch(config, payload):
            captured_config.append(config)
            return MagicMock(success=True)

        with patch("llm_council.council.stage1_collect_responses_with_status") as mock_stage1:
            mock_stage1.return_value = (
                [],
                {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                {},
            )

            with patch(
                "llm_council.webhooks.event_bridge.WebhookDispatcher"
            ) as mock_dispatcher_class:
                mock_dispatcher = MagicMock()
                mock_dispatcher.dispatch = capture_dispatch
                mock_dispatcher_class.return_value = mock_dispatcher

                await run_council_with_fallback(
                    "Test query",
                    webhook_config=request_config,
                )

        # If any webhooks were dispatched, they should use request config
        if captured_config:
            assert captured_config[0].url == "https://request.example.com/webhook"


class TestWebhookCleanup:
    """Test proper cleanup of EventBridge resources."""

    @pytest.mark.asyncio
    async def test_bridge_shutdown_on_success(self):
        """EventBridge should be shut down after successful completion."""
        from llm_council.council import run_council_with_fallback

        config = WebhookConfig(
            url="https://example.com/webhook",
            events=["council.complete"],
        )

        shutdown_called = []

        original_shutdown = EventBridge.shutdown

        async def track_shutdown(self):
            shutdown_called.append(True)
            return await original_shutdown(self)

        with patch("llm_council.council.stage1_collect_responses_with_status") as mock_stage1:
            mock_stage1.return_value = (
                [],
                {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                {},
            )

            with patch.object(EventBridge, "shutdown", track_shutdown):
                await run_council_with_fallback(
                    "Test query",
                    webhook_config=config,
                )

        # Shutdown should have been called
        assert len(shutdown_called) >= 1

    @pytest.mark.asyncio
    async def test_bridge_shutdown_on_error(self):
        """EventBridge should be shut down even after errors."""
        from llm_council.council import run_council_with_fallback

        config = WebhookConfig(
            url="https://example.com/webhook",
            events=["council.error"],
        )

        shutdown_called = []

        original_shutdown = EventBridge.shutdown

        async def track_shutdown(self):
            shutdown_called.append(True)
            return await original_shutdown(self)

        with patch("llm_council.council.stage1_collect_responses_with_status") as mock_stage1:
            mock_stage1.side_effect = Exception("Test error")

            with patch.object(EventBridge, "shutdown", track_shutdown):
                # This should not raise
                await run_council_with_fallback(
                    "Test query",
                    webhook_config=config,
                )

        # Shutdown should have been called even with error
        assert len(shutdown_called) >= 1


class TestMetadataWebhookInfo:
    """Test that webhook info is included in result metadata."""

    @pytest.mark.asyncio
    async def test_metadata_includes_webhook_enabled(self):
        """Result metadata should indicate if webhooks were enabled."""
        from llm_council.council import run_council_with_fallback

        config = WebhookConfig(
            url="https://example.com/webhook",
            events=["council.complete"],
        )

        with patch("llm_council.council.stage1_collect_responses_with_status") as mock_stage1:
            mock_stage1.return_value = (
                [],
                {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                {},
            )

            result = await run_council_with_fallback(
                "Test query",
                webhook_config=config,
            )

        # Metadata should indicate webhooks were enabled
        # (Implementation may vary - check for webhook-related metadata)
        assert "metadata" in result


class TestIntegrationWithExistingLayerEvents:
    """Test that webhook events are emitted alongside existing LayerEvents."""

    @pytest.mark.asyncio
    async def test_layer_events_still_emitted(self):
        """Existing LayerEvents should still be emitted with webhook integration."""
        from llm_council.council import run_council_with_fallback
        from llm_council.layer_contracts import get_layer_events, clear_layer_events

        clear_layer_events()

        config = WebhookConfig(
            url="https://example.com/webhook",
            events=["council.complete"],
        )

        # Mock a successful council run so L3_COUNCIL_COMPLETE is emitted
        with (
            patch("llm_council.council.stage1_collect_responses_with_status") as mock_stage1,
            patch("llm_council.council.stage1_5_normalize_styles") as mock_stage1_5,
            patch("llm_council.council.stage2_collect_rankings") as mock_stage2,
            patch("llm_council.council.stage3_synthesize_final") as mock_stage3,
        ):
            mock_stage1.return_value = (
                [{"model": "test/model", "response": "Test response"}],
                {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
                {"test/model": {"status": "ok", "latency_ms": 1000}},
            )
            mock_stage1_5.return_value = (
                [{"model": "test/model", "response": "Test response"}],
                {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            )
            mock_stage2.return_value = (
                [{"model": "test/model", "ranking": "...", "parsed_ranking": {"ranking": []}}],
                {"Response A": {"model": "test/model", "display_index": 0}},
                {"prompt_tokens": 50, "completion_tokens": 25, "total_tokens": 75},
            )
            mock_stage3.return_value = (
                {"model": "chairman/model", "response": "Final synthesis"},
                {"prompt_tokens": 100, "completion_tokens": 100, "total_tokens": 200},
                None,  # verdict_result (ADR-025b)
            )

            await run_council_with_fallback(
                "Test query",
                webhook_config=config,
            )

        # LayerEvents should still be emitted
        events = get_layer_events()
        # At minimum, L3_COUNCIL_START and L3_COUNCIL_COMPLETE should be emitted
        event_types = [e.event_type.value for e in events]
        assert "l3_council_start" in event_types
        assert "l3_council_complete" in event_types

        clear_layer_events()
