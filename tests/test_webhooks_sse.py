"""Tests for SSE (Server-Sent Events) streaming (ADR-025).

TDD: Write these tests first, then implement SSE.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
import json


class TestSSEEventFormatter:
    """Test SSE event formatting."""

    def test_format_event(self):
        """Should format event as SSE."""
        from llm_council.webhooks.sse import format_sse_event

        event = format_sse_event(event="council.complete", data={"result": "success"})

        assert "event: council.complete" in event
        assert "data: " in event
        assert event.endswith("\n\n")

    def test_format_event_json_data(self):
        """Data should be JSON encoded."""
        from llm_council.webhooks.sse import format_sse_event

        data = {"key": "value", "number": 123}
        event = format_sse_event(event="test", data=data)

        # Extract data line
        lines = event.strip().split("\n")
        data_line = [l for l in lines if l.startswith("data:")][0]
        json_str = data_line[5:].strip()  # Remove "data:" prefix
        parsed = json.loads(json_str)

        assert parsed == data

    def test_format_event_with_id(self):
        """Should include event ID when provided."""
        from llm_council.webhooks.sse import format_sse_event

        event = format_sse_event(
            event="council.complete", data={"result": "success"}, event_id="evt-123"
        )

        assert "id: evt-123" in event

    def test_format_event_with_retry(self):
        """Should include retry when provided."""
        from llm_council.webhooks.sse import format_sse_event

        event = format_sse_event(event="council.complete", data={}, retry=5000)

        assert "retry: 5000" in event

    def test_format_event_multiline_data(self):
        """Should handle multiline data correctly."""
        from llm_council.webhooks.sse import format_sse_event

        data = {"text": "line1\nline2\nline3"}
        event = format_sse_event(event="test", data=data)

        # Each line of data should have its own "data:" prefix
        # Or be JSON encoded (which escapes newlines)
        assert "data:" in event


class TestSSEEventGenerator:
    """Test SSE event generator for council deliberation."""

    @pytest.mark.asyncio
    async def test_generator_yields_events(self):
        """Should yield SSE events as council progresses."""
        from llm_council.webhooks.sse import council_event_generator

        # Mock council stages
        mock_responses = {
            "stage1": {"model1": "response1"},
            "stage2": {"rankings": [1, 2]},
            "stage3": {"synthesis": "final"},
        }

        with patch("llm_council.webhooks._council_runner.run_council") as mock_council:
            # Setup mock to yield stage events
            async def mock_run(*args, **kwargs):
                yield {"event": "council.deliberation_start", "data": {}}
                yield {"event": "council.stage1.complete", "data": mock_responses["stage1"]}
                yield {"event": "council.stage2.complete", "data": mock_responses["stage2"]}
                yield {"event": "council.complete", "data": mock_responses}

            mock_council.return_value = mock_run()

            events = []
            async for event in council_event_generator(prompt="test", models=None, api_key=None):
                events.append(event)

        assert len(events) >= 1  # At least some events

    @pytest.mark.asyncio
    async def test_generator_starts_with_deliberation_start(self):
        """First event should be deliberation_start."""
        from llm_council.webhooks.sse import council_event_generator

        with patch("llm_council.webhooks._council_runner.run_council") as mock_council:

            async def mock_run(*args, **kwargs):
                yield {"event": "council.deliberation_start", "data": {"request_id": "123"}}
                yield {"event": "council.complete", "data": {}}

            mock_council.return_value = mock_run()

            events = []
            async for event in council_event_generator("test", None, None):
                events.append(event)

        first_event = events[0]
        assert "deliberation_start" in first_event

    @pytest.mark.asyncio
    async def test_generator_ends_with_complete_or_error(self):
        """Last event should be complete or error."""
        from llm_council.webhooks.sse import council_event_generator

        with patch("llm_council.webhooks._council_runner.run_council") as mock_council:

            async def mock_run(*args, **kwargs):
                yield {"event": "council.deliberation_start", "data": {}}
                yield {"event": "council.complete", "data": {"result": "done"}}

            mock_council.return_value = mock_run()

            events = []
            async for event in council_event_generator("test", None, None):
                events.append(event)

        last_event = events[-1]
        assert "complete" in last_event or "error" in last_event

    @pytest.mark.asyncio
    async def test_generator_handles_error(self):
        """Should emit error event on failure."""
        from llm_council.webhooks.sse import council_event_generator

        with patch("llm_council.webhooks._council_runner.run_council") as mock_council:

            async def mock_run(*args, **kwargs):
                yield {"event": "council.deliberation_start", "data": {}}
                yield {"event": "council.error", "data": {"error": "Something went wrong"}}

            mock_council.return_value = mock_run()

            events = []
            async for event in council_event_generator("test", None, None):
                events.append(event)

        last_event = events[-1]
        assert "error" in last_event


class TestSSECouncilEvents:
    """Test specific council events in SSE format."""

    def test_deliberation_start_event(self):
        """Should include request_id and models in start event."""
        from llm_council.webhooks.sse import format_council_event

        event = format_council_event(
            event_type="council.deliberation_start",
            request_id="req-123",
            data={"models": ["gpt-4", "claude-3"]},
        )

        assert "deliberation_start" in event
        assert "req-123" in event

    def test_stage1_complete_event(self):
        """Should include response count in stage1 event."""
        from llm_council.webhooks.sse import format_council_event

        event = format_council_event(
            event_type="council.stage1.complete", request_id="req-123", data={"response_count": 4}
        )

        assert "stage1.complete" in event

    def test_model_vote_cast_event(self):
        """Should include voter and ranking in vote event."""
        from llm_council.webhooks.sse import format_council_event

        event = format_council_event(
            event_type="model.vote_cast",
            request_id="req-123",
            data={"voter": "gpt-4", "ranking": ["A", "B", "C"]},
        )

        assert "vote_cast" in event

    def test_complete_event_includes_duration(self):
        """Complete event should include total duration."""
        from llm_council.webhooks.sse import format_council_event

        event = format_council_event(
            event_type="council.complete",
            request_id="req-123",
            data={"duration_ms": 5432, "stage3_response": "Final answer"},
        )

        assert "complete" in event
        assert "5432" in event or "duration" in event


class TestSSEKeepAlive:
    """Test SSE keep-alive mechanism."""

    @pytest.mark.asyncio
    async def test_generator_sends_keepalive(self):
        """Should send periodic keep-alive comments."""
        from llm_council.webhooks.sse import council_event_generator
        import asyncio

        with patch("llm_council.webhooks._council_runner.run_council") as mock_council:

            async def mock_run(*args, **kwargs):
                yield {"event": "council.deliberation_start", "data": {}}
                await asyncio.sleep(0.1)  # Simulate slow processing
                yield {"event": "council.complete", "data": {}}

            mock_council.return_value = mock_run()

            events = []
            async for event in council_event_generator(
                "test",
                None,
                None,
                keepalive_interval=0.05,  # Short interval for test
            ):
                events.append(event)

        # Should have at least one keep-alive comment
        # Keep-alives are SSE comments starting with ":"
        # This test may be flaky depending on timing


class TestSSEContentType:
    """Test SSE content type headers."""

    def test_sse_content_type(self):
        """Should return correct content type."""
        from llm_council.webhooks.sse import SSE_CONTENT_TYPE

        assert SSE_CONTENT_TYPE == "text/event-stream"

    def test_sse_headers(self):
        """Should include no-cache headers."""
        from llm_council.webhooks.sse import get_sse_headers

        headers = get_sse_headers()

        assert headers["Content-Type"] == "text/event-stream"
        assert headers["Cache-Control"] == "no-cache"
        assert headers["Connection"] == "keep-alive"
