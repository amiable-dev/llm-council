"""Tests for webhook dispatcher (ADR-025).

TDD: Write these tests first, then implement the dispatcher.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime


class TestWebhookDispatcher:
    """Test WebhookDispatcher class."""

    def test_dispatcher_creation(self):
        """Should create dispatcher with config."""
        from llm_council.webhooks.dispatcher import WebhookDispatcher

        dispatcher = WebhookDispatcher()

        assert dispatcher is not None

    def test_dispatcher_with_custom_timeout(self):
        """Should accept custom timeout."""
        from llm_council.webhooks.dispatcher import WebhookDispatcher

        dispatcher = WebhookDispatcher(timeout=10.0)

        assert dispatcher._timeout == 10.0

    def test_dispatcher_with_custom_retries(self):
        """Should accept custom max retries."""
        from llm_council.webhooks.dispatcher import WebhookDispatcher

        dispatcher = WebhookDispatcher(max_retries=5)

        assert dispatcher._max_retries == 5


class TestWebhookDispatch:
    """Test async dispatch functionality."""

    @pytest.mark.asyncio
    async def test_dispatch_success(self):
        """Should dispatch webhook successfully."""
        from llm_council.webhooks.dispatcher import WebhookDispatcher
        from llm_council.webhooks.types import WebhookConfig, WebhookPayload, WebhookDeliveryResult

        dispatcher = WebhookDispatcher()
        config = WebhookConfig(url="https://example.com/webhook")
        payload = WebhookPayload(
            event="council.complete",
            request_id="req-123",
            timestamp=datetime.now(),
            data={"result": "success"},
        )

        # Mock httpx
        with patch("llm_council.webhooks.dispatcher.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            result = await dispatcher.dispatch(config, payload)

        assert isinstance(result, WebhookDeliveryResult)
        assert result.success is True
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_dispatch_with_hmac(self):
        """Should include HMAC headers when secret provided."""
        from llm_council.webhooks.dispatcher import WebhookDispatcher
        from llm_council.webhooks.types import WebhookConfig, WebhookPayload

        dispatcher = WebhookDispatcher()
        config = WebhookConfig(url="https://example.com/webhook", secret="my-secret")
        payload = WebhookPayload(
            event="council.complete", request_id="req-123", timestamp=datetime.now(), data={}
        )

        with patch("llm_council.webhooks.dispatcher.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post

            await dispatcher.dispatch(config, payload)

            # Check headers were passed
            call_kwargs = mock_post.call_args.kwargs
            headers = call_kwargs.get("headers", {})
            assert "X-Council-Signature" in headers
            assert headers["X-Council-Signature"].startswith("sha256=")

    @pytest.mark.asyncio
    async def test_dispatch_retry_on_5xx(self):
        """Should retry on 5xx errors."""
        from llm_council.webhooks.dispatcher import WebhookDispatcher
        from llm_council.webhooks.types import WebhookConfig, WebhookPayload

        dispatcher = WebhookDispatcher(max_retries=3)
        config = WebhookConfig(url="https://example.com/webhook")
        payload = WebhookPayload(
            event="council.complete", request_id="req-123", timestamp=datetime.now(), data={}
        )

        with patch("llm_council.webhooks.dispatcher.httpx.AsyncClient") as mock_client:
            # First two calls fail with 500, third succeeds
            mock_responses = [
                MagicMock(status_code=500),
                MagicMock(status_code=502),
                MagicMock(status_code=200),
            ]
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=mock_responses
            )

            result = await dispatcher.dispatch(config, payload)

        assert result.success is True
        assert result.attempt == 3

    @pytest.mark.asyncio
    async def test_dispatch_no_retry_on_4xx(self):
        """Should not retry on 4xx errors (except 429)."""
        from llm_council.webhooks.dispatcher import WebhookDispatcher
        from llm_council.webhooks.types import WebhookConfig, WebhookPayload

        dispatcher = WebhookDispatcher(max_retries=3)
        config = WebhookConfig(url="https://example.com/webhook")
        payload = WebhookPayload(
            event="council.complete", request_id="req-123", timestamp=datetime.now(), data={}
        )

        with patch("llm_council.webhooks.dispatcher.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock(status_code=400)
            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post

            result = await dispatcher.dispatch(config, payload)

        # Should fail immediately without retry
        assert result.success is False
        assert result.attempt == 1

    @pytest.mark.asyncio
    async def test_dispatch_retry_on_429(self):
        """Should retry on 429 rate limit."""
        from llm_council.webhooks.dispatcher import WebhookDispatcher
        from llm_council.webhooks.types import WebhookConfig, WebhookPayload

        dispatcher = WebhookDispatcher(max_retries=2)
        config = WebhookConfig(url="https://example.com/webhook")
        payload = WebhookPayload(
            event="council.complete", request_id="req-123", timestamp=datetime.now(), data={}
        )

        with patch("llm_council.webhooks.dispatcher.httpx.AsyncClient") as mock_client:
            mock_responses = [
                MagicMock(status_code=429, headers={"Retry-After": "1"}),
                MagicMock(status_code=200),
            ]
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=mock_responses
            )

            result = await dispatcher.dispatch(config, payload)

        assert result.success is True
        assert result.attempt == 2

    @pytest.mark.asyncio
    async def test_dispatch_max_retries_exceeded(self):
        """Should return failure after max retries."""
        from llm_council.webhooks.dispatcher import WebhookDispatcher
        from llm_council.webhooks.types import WebhookConfig, WebhookPayload

        dispatcher = WebhookDispatcher(max_retries=3)
        config = WebhookConfig(url="https://example.com/webhook")
        payload = WebhookPayload(
            event="council.complete", request_id="req-123", timestamp=datetime.now(), data={}
        )

        with patch("llm_council.webhooks.dispatcher.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock(status_code=500)
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            result = await dispatcher.dispatch(config, payload)

        assert result.success is False
        assert result.attempt == 3
        assert result.status_code == 500

    @pytest.mark.asyncio
    async def test_dispatch_timeout_handling(self):
        """Should handle timeout errors."""
        from llm_council.webhooks.dispatcher import WebhookDispatcher
        from llm_council.webhooks.types import WebhookConfig, WebhookPayload
        import httpx

        dispatcher = WebhookDispatcher(timeout=1.0)
        config = WebhookConfig(url="https://example.com/webhook")
        payload = WebhookPayload(
            event="council.complete", request_id="req-123", timestamp=datetime.now(), data={}
        )

        with patch("llm_council.webhooks.dispatcher.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=httpx.TimeoutException("Timeout")
            )

            result = await dispatcher.dispatch(config, payload)

        assert result.success is False
        assert "timeout" in result.error.lower()

    @pytest.mark.asyncio
    async def test_dispatch_connection_error(self):
        """Should handle connection errors."""
        from llm_council.webhooks.dispatcher import WebhookDispatcher
        from llm_council.webhooks.types import WebhookConfig, WebhookPayload
        import httpx

        dispatcher = WebhookDispatcher()
        config = WebhookConfig(url="https://example.com/webhook")
        payload = WebhookPayload(
            event="council.complete", request_id="req-123", timestamp=datetime.now(), data={}
        )

        with patch("llm_council.webhooks.dispatcher.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )

            result = await dispatcher.dispatch(config, payload)

        assert result.success is False
        assert result.error is not None


class TestWebhookEventFiltering:
    """Test event filtering based on subscribed events."""

    @pytest.mark.asyncio
    async def test_dispatch_only_subscribed_events(self):
        """Should only dispatch subscribed events."""
        from llm_council.webhooks.dispatcher import WebhookDispatcher
        from llm_council.webhooks.types import WebhookConfig, WebhookPayload

        dispatcher = WebhookDispatcher()
        config = WebhookConfig(
            url="https://example.com/webhook",
            events=["council.complete"],  # Only subscribed to complete
        )

        # Event that matches subscription
        payload_complete = WebhookPayload(
            event="council.complete", request_id="req-123", timestamp=datetime.now(), data={}
        )

        # Event that doesn't match subscription
        payload_start = WebhookPayload(
            event="council.deliberation_start",
            request_id="req-123",
            timestamp=datetime.now(),
            data={},
        )

        with patch("llm_council.webhooks.dispatcher.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock(status_code=200)
            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post

            # Should dispatch complete event
            result = await dispatcher.dispatch(config, payload_complete)
            assert result.success is True

            # Should skip non-subscribed event
            result = await dispatcher.dispatch(config, payload_start)
            assert result.success is True
            assert result.status_code == -1  # Skipped indicator


class TestDispatcherHTTPSOnly:
    """Test HTTPS-only requirement in production."""

    def test_https_only_default_enabled(self):
        """HTTPS-only should be configurable."""
        from llm_council.webhooks.dispatcher import WebhookDispatcher

        dispatcher = WebhookDispatcher(https_only=True)
        assert dispatcher._https_only is True

    @pytest.mark.asyncio
    async def test_https_only_rejects_http(self):
        """Should reject HTTP URLs in production mode."""
        from llm_council.webhooks.dispatcher import WebhookDispatcher
        from llm_council.webhooks.types import WebhookConfig, WebhookPayload

        dispatcher = WebhookDispatcher(https_only=True)
        config = WebhookConfig(url="http://example.com/webhook")  # HTTP!
        payload = WebhookPayload(
            event="council.complete", request_id="req-123", timestamp=datetime.now(), data={}
        )

        result = await dispatcher.dispatch(config, payload)

        assert result.success is False
        assert "https" in result.error.lower()

    @pytest.mark.asyncio
    async def test_https_only_allows_localhost(self):
        """Should allow localhost HTTP for development."""
        from llm_council.webhooks.dispatcher import WebhookDispatcher
        from llm_council.webhooks.types import WebhookConfig, WebhookPayload

        dispatcher = WebhookDispatcher(https_only=True)
        config = WebhookConfig(url="http://localhost:8080/webhook")
        payload = WebhookPayload(
            event="council.complete", request_id="req-123", timestamp=datetime.now(), data={}
        )

        with patch("llm_council.webhooks.dispatcher.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock(status_code=200)
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            result = await dispatcher.dispatch(config, payload)

        # localhost should be allowed even with https_only
        assert result.success is True


class TestBatchDispatch:
    """Test batch dispatching to multiple webhooks."""

    @pytest.mark.asyncio
    async def test_dispatch_to_multiple_webhooks(self):
        """Should dispatch to multiple webhook endpoints."""
        from llm_council.webhooks.dispatcher import WebhookDispatcher
        from llm_council.webhooks.types import WebhookConfig, WebhookPayload

        dispatcher = WebhookDispatcher()
        configs = [
            WebhookConfig(url="https://example1.com/webhook"),
            WebhookConfig(url="https://example2.com/webhook"),
        ]
        payload = WebhookPayload(
            event="council.complete", request_id="req-123", timestamp=datetime.now(), data={}
        )

        with patch("llm_council.webhooks.dispatcher.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock(status_code=200)
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            results = await dispatcher.dispatch_batch(configs, payload)

        assert len(results) == 2
        assert all(r.success for r in results)
