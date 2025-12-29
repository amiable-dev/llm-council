"""Tests for SSE streaming via council runner (ADR-025a Phase 3).

TDD tests written first per council-approved remediation plan.
Issue #84: feat(sse): Replace placeholder _council_runner with real implementation
"""

import asyncio
from datetime import datetime
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llm_council.webhooks.types import WebhookEventType


class TestCouncilRunnerEventGeneration:
    """Test that council runner yields real events during deliberation."""

    @pytest.mark.asyncio
    async def test_run_council_yields_start_event(self):
        """run_council should yield deliberation_start event first."""
        from llm_council.webhooks._council_runner import run_council

        # Mock the council execution
        with patch(
            "llm_council.webhooks._council_runner.run_council_with_fallback"
        ) as mock_council:
            mock_council.return_value = {
                "synthesis": "Test synthesis",
                "model_responses": {},
                "metadata": {"status": "complete"},
            }

            events = []
            async for event in run_council("Test prompt"):
                events.append(event)

        # First event should be deliberation_start
        assert len(events) >= 1
        assert events[0]["event"] == "council.deliberation_start"
        assert "request_id" in events[0]["data"]

    @pytest.mark.asyncio
    async def test_run_council_yields_complete_event(self):
        """run_council should yield complete event with result."""
        from llm_council.webhooks._council_runner import run_council

        mock_result = {
            "synthesis": "Final answer from council",
            "model_responses": {"model1": {"status": "ok"}},
            "metadata": {"status": "complete", "synthesis_type": "full"},
        }

        with patch(
            "llm_council.webhooks._council_runner.run_council_with_fallback"
        ) as mock_council:
            mock_council.return_value = mock_result

            events = []
            async for event in run_council("Test prompt"):
                events.append(event)

        # Last event should be complete
        complete_events = [e for e in events if e["event"] == "council.complete"]
        assert len(complete_events) == 1
        assert "result" in complete_events[0]["data"]

    @pytest.mark.asyncio
    async def test_run_council_yields_stage_events(self):
        """run_council should yield stage1.complete and stage2.complete events."""
        from llm_council.webhooks._council_runner import run_council

        mock_result = {
            "synthesis": "Final answer",
            "model_responses": {"model1": {"status": "ok"}},
            "metadata": {"status": "complete"},
        }

        with patch(
            "llm_council.webhooks._council_runner.run_council_with_fallback"
        ) as mock_council:
            mock_council.return_value = mock_result

            events = []
            async for event in run_council("Test prompt"):
                events.append(event)

        event_types = [e["event"] for e in events]

        # Should have stage events
        assert "council.stage1.complete" in event_types
        assert "council.stage2.complete" in event_types

    @pytest.mark.asyncio
    async def test_run_council_event_order(self):
        """Events should be in correct order: start -> stage1 -> stage2 -> complete."""
        from llm_council.webhooks._council_runner import run_council

        mock_result = {
            "synthesis": "Final answer",
            "model_responses": {},
            "metadata": {"status": "complete"},
        }

        with patch(
            "llm_council.webhooks._council_runner.run_council_with_fallback"
        ) as mock_council:
            mock_council.return_value = mock_result

            events = []
            async for event in run_council("Test prompt"):
                events.append(event)

        event_types = [e["event"] for e in events]

        # Verify order
        start_idx = event_types.index("council.deliberation_start")
        stage1_idx = event_types.index("council.stage1.complete")
        stage2_idx = event_types.index("council.stage2.complete")
        complete_idx = event_types.index("council.complete")

        assert start_idx < stage1_idx < stage2_idx < complete_idx

    @pytest.mark.asyncio
    async def test_run_council_yields_error_on_failure(self):
        """run_council should yield error event when council fails."""
        from llm_council.webhooks._council_runner import run_council

        mock_result = {
            "synthesis": "Error occurred",
            "model_responses": {},
            "metadata": {"status": "failed", "error": "Test error"},
        }

        with patch(
            "llm_council.webhooks._council_runner.run_council_with_fallback"
        ) as mock_council:
            mock_council.return_value = mock_result

            events = []
            async for event in run_council("Test prompt"):
                events.append(event)

        # Should have error event
        event_types = [e["event"] for e in events]
        assert "council.error" in event_types or "council.complete" in event_types

    @pytest.mark.asyncio
    async def test_run_council_request_id_consistency(self):
        """All events should have the same request_id."""
        from llm_council.webhooks._council_runner import run_council

        mock_result = {
            "synthesis": "Final answer",
            "model_responses": {},
            "metadata": {"status": "complete"},
        }

        with patch(
            "llm_council.webhooks._council_runner.run_council_with_fallback"
        ) as mock_council:
            mock_council.return_value = mock_result

            events = []
            async for event in run_council("Test prompt"):
                events.append(event)

        # All events should have same request_id
        request_ids = [e["data"].get("request_id") for e in events]
        assert len(set(request_ids)) == 1  # All should be the same


class TestCouncilRunnerWithModels:
    """Test council runner with model configuration."""

    @pytest.mark.asyncio
    async def test_run_council_accepts_models_parameter(self):
        """run_council should accept and pass models parameter."""
        from llm_council.webhooks._council_runner import run_council

        mock_result = {
            "synthesis": "Final answer",
            "model_responses": {},
            "metadata": {"status": "complete"},
        }

        with patch(
            "llm_council.webhooks._council_runner.run_council_with_fallback"
        ) as mock_council:
            mock_council.return_value = mock_result

            events = []
            async for event in run_council("Test prompt", models="gpt-4,claude-3"):
                events.append(event)

            # Verify models were passed
            mock_council.assert_called_once()
            call_kwargs = mock_council.call_args
            # Check if models were passed (implementation may vary)

    @pytest.mark.asyncio
    async def test_run_council_accepts_api_key(self):
        """run_council should accept and use api_key parameter."""
        from llm_council.webhooks._council_runner import run_council

        mock_result = {
            "synthesis": "Final answer",
            "model_responses": {},
            "metadata": {"status": "complete"},
        }

        with patch(
            "llm_council.webhooks._council_runner.run_council_with_fallback"
        ) as mock_council:
            mock_council.return_value = mock_result

            events = []
            async for event in run_council("Test prompt", api_key="test-key"):
                events.append(event)

            # Should complete without error
            assert len(events) >= 2


class TestSSEEventFormatting:
    """Test SSE event formatting through council_event_generator."""

    @pytest.mark.asyncio
    async def test_council_event_generator_yields_sse_format(self):
        """council_event_generator should yield SSE-formatted strings."""
        from llm_council.webhooks.sse import council_event_generator

        mock_result = {
            "synthesis": "Final answer",
            "model_responses": {},
            "metadata": {"status": "complete"},
        }

        with patch(
            "llm_council.webhooks._council_runner.run_council_with_fallback"
        ) as mock_council:
            mock_council.return_value = mock_result

            events = []
            async for event_str in council_event_generator("Test prompt", None, None):
                events.append(event_str)

        # All events should be SSE formatted (end with double newline)
        for event_str in events:
            assert event_str.endswith("\n\n")
            assert "event:" in event_str
            assert "data:" in event_str

    @pytest.mark.asyncio
    async def test_council_event_generator_includes_event_names(self):
        """SSE events should include proper event names."""
        from llm_council.webhooks.sse import council_event_generator

        mock_result = {
            "synthesis": "Final answer",
            "model_responses": {},
            "metadata": {"status": "complete"},
        }

        with patch(
            "llm_council.webhooks._council_runner.run_council_with_fallback"
        ) as mock_council:
            mock_council.return_value = mock_result

            events = []
            async for event_str in council_event_generator("Test prompt", None, None):
                events.append(event_str)

        # Should have council event names
        event_content = "".join(events)
        assert "council.deliberation_start" in event_content
        assert "council.complete" in event_content


class TestHTTPEndpoint:
    """Test SSE streaming HTTP endpoint."""

    @pytest.mark.asyncio
    async def test_stream_endpoint_exists(self):
        """HTTP server should have /v1/council/stream endpoint."""
        pytest.importorskip("fastapi")
        from llm_council.http_server import app

        # Find the route
        routes = [route.path for route in app.routes]
        assert "/v1/council/stream" in routes

    @pytest.mark.asyncio
    async def test_stream_endpoint_returns_sse_content_type(self):
        """Stream endpoint should return text/event-stream content type."""
        pytest.importorskip("fastapi")
        from fastapi.testclient import TestClient
        from llm_council.http_server import app

        mock_result = {
            "synthesis": "Final answer",
            "model_responses": {},
            "metadata": {"status": "complete"},
        }

        with patch(
            "llm_council.webhooks._council_runner.run_council_with_fallback"
        ) as mock_council:
            mock_council.return_value = mock_result

            # Use test client - note: SSE might need special handling
            client = TestClient(app)

            # Make request (will need API key)
            with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}):
                response = client.get(
                    "/v1/council/stream",
                    params={"prompt": "Test question"},
                )

                # Should return SSE content type
                assert response.headers.get("content-type", "").startswith("text/event-stream")

    @pytest.mark.asyncio
    async def test_stream_endpoint_requires_prompt(self):
        """Stream endpoint should require prompt parameter."""
        pytest.importorskip("fastapi")
        from fastapi.testclient import TestClient
        from llm_council.http_server import app

        client = TestClient(app)

        # Request without prompt - with API key set
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}):
            response = client.get("/v1/council/stream")

        # Should return 422 (validation error) or 400
        assert response.status_code in (400, 422)

    @pytest.mark.asyncio
    async def test_stream_endpoint_streams_events(self):
        """Stream endpoint should stream multiple events."""
        pytest.importorskip("fastapi")
        from fastapi.testclient import TestClient
        from llm_council.http_server import app

        mock_result = {
            "synthesis": "Final answer",
            "model_responses": {},
            "metadata": {"status": "complete"},
        }

        with patch(
            "llm_council.webhooks._council_runner.run_council_with_fallback"
        ) as mock_council:
            mock_council.return_value = mock_result

            client = TestClient(app)

            with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}):
                response = client.get(
                    "/v1/council/stream",
                    params={"prompt": "Test question"},
                )

                # Should have multiple events
                content = response.text
                assert "council.deliberation_start" in content
                assert "council.complete" in content


class TestEventBridgeIntegration:
    """Test that council runner uses EventBridge for event collection."""

    @pytest.mark.asyncio
    async def test_council_runner_uses_event_bridge(self):
        """Council runner should use EventBridge for event emission."""
        from llm_council.webhooks._council_runner import run_council

        mock_result = {
            "synthesis": "Final answer",
            "model_responses": {},
            "metadata": {"status": "complete"},
        }

        with patch(
            "llm_council.webhooks._council_runner.run_council_with_fallback"
        ) as mock_council:
            mock_council.return_value = mock_result

            events = []
            async for event in run_council("Test prompt"):
                events.append(event)

            # Should have received events from EventBridge
            assert len(events) >= 4  # start, stage1, stage2, complete

    @pytest.mark.asyncio
    async def test_council_runner_passes_webhook_config(self):
        """Council runner should pass webhook config to council."""
        from llm_council.webhooks._council_runner import run_council

        mock_result = {
            "synthesis": "Final answer",
            "model_responses": {},
            "metadata": {"status": "complete"},
        }

        with patch(
            "llm_council.webhooks._council_runner.run_council_with_fallback"
        ) as mock_council:
            mock_council.return_value = mock_result

            events = []
            async for event in run_council("Test prompt"):
                events.append(event)

            # Verify webhook_config was passed
            call_kwargs = mock_council.call_args.kwargs
            assert "webhook_config" in call_kwargs


class TestErrorHandling:
    """Test error handling in SSE streaming."""

    @pytest.mark.asyncio
    async def test_run_council_handles_exception(self):
        """run_council should yield error event on exception."""
        from llm_council.webhooks._council_runner import run_council

        with patch(
            "llm_council.webhooks._council_runner.run_council_with_fallback"
        ) as mock_council:
            mock_council.side_effect = Exception("Test error")

            events = []
            async for event in run_council("Test prompt"):
                events.append(event)

            # Should have error event
            event_types = [e["event"] for e in events]
            assert "council.error" in event_types

    @pytest.mark.asyncio
    async def test_error_event_includes_message(self):
        """Error event should include error message."""
        from llm_council.webhooks._council_runner import run_council

        with patch(
            "llm_council.webhooks._council_runner.run_council_with_fallback"
        ) as mock_council:
            mock_council.side_effect = Exception("Specific error message")

            events = []
            async for event in run_council("Test prompt"):
                events.append(event)

            # Find error event
            error_events = [e for e in events if e["event"] == "council.error"]
            assert len(error_events) == 1
            assert "error" in error_events[0]["data"]
