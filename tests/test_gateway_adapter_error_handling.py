"""Tests for gateway adapter error handling (grok-4 HTTP 400 bug fix).

Verifies that one model's failure does not cancel other model queries,
and that error results are properly returned instead of exceptions propagating.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestQueryWithTrackingExceptionHandling:
    """Test that query_with_tracking handles exceptions gracefully."""

    @pytest.mark.asyncio
    async def test_one_model_failure_does_not_cancel_others(self):
        """When one model raises an exception, other models should still complete."""
        from llm_council.gateway_adapter import query_models_with_progress, STATUS_OK, STATUS_ERROR
        from llm_council.gateway.types import GatewayResponse

        success_response = GatewayResponse(
            content="Hello!",
            model="openai/gpt-5.1",
            status="ok",
            latency_ms=100,
        )

        mock_router = MagicMock()

        async def mock_complete(request):
            if request.model == "x-ai/grok-4":
                raise Exception("Gateway openrouter error: Bad request for x-ai/grok-4")
            return success_response

        mock_router.complete = mock_complete

        with (
            patch("llm_council.gateway_adapter._use_gateway_layer", return_value=True),
            patch("llm_council.gateway_adapter.USE_GATEWAY_LAYER", True),
            patch("llm_council.gateway_adapter._get_gateway_router", return_value=mock_router),
        ):
            results = await query_models_with_progress(
                models=["openai/gpt-5.1", "x-ai/grok-4", "google/gemini-3-pro"],
                messages=[{"role": "user", "content": "Hello"}],
            )

        # All 3 models should have results
        assert len(results) == 3

        # Successful models should have OK status
        assert results["openai/gpt-5.1"]["status"] == STATUS_OK
        assert results["google/gemini-3-pro"]["status"] == STATUS_OK

        # Failed model should have error status, not crash
        assert results["x-ai/grok-4"]["status"] == STATUS_ERROR
        assert "Bad request" in results["x-ai/grok-4"]["error"]

    @pytest.mark.asyncio
    async def test_all_models_fail_returns_all_errors(self):
        """When all models fail, should return error results for each."""
        from llm_council.gateway_adapter import query_models_with_progress, STATUS_ERROR

        mock_router = MagicMock()
        mock_router.complete = AsyncMock(side_effect=Exception("All gateways in chain failed"))

        with (
            patch("llm_council.gateway_adapter._use_gateway_layer", return_value=True),
            patch("llm_council.gateway_adapter.USE_GATEWAY_LAYER", True),
            patch("llm_council.gateway_adapter._get_gateway_router", return_value=mock_router),
        ):
            results = await query_models_with_progress(
                models=["model-a", "model-b"],
                messages=[{"role": "user", "content": "Hello"}],
            )

        assert len(results) == 2
        assert results["model-a"]["status"] == STATUS_ERROR
        assert results["model-b"]["status"] == STATUS_ERROR

    @pytest.mark.asyncio
    async def test_progress_callback_reports_failures(self):
        """Progress callback should report failures with ✗ emoji."""
        from llm_council.gateway_adapter import query_models_with_progress

        mock_router = MagicMock()
        mock_router.complete = AsyncMock(side_effect=Exception("Gateway error"))

        progress_calls = []

        async def track_progress(completed, total, msg):
            progress_calls.append((completed, total, msg))

        with (
            patch("llm_council.gateway_adapter._use_gateway_layer", return_value=True),
            patch("llm_council.gateway_adapter.USE_GATEWAY_LAYER", True),
            patch("llm_council.gateway_adapter._get_gateway_router", return_value=mock_router),
        ):
            await query_models_with_progress(
                models=["x-ai/grok-4"],
                messages=[{"role": "user", "content": "Hello"}],
                on_progress=track_progress,
            )

        # Should have initial progress + completion
        assert len(progress_calls) >= 1
        # The failure progress should contain ✗
        failure_msg = [call for call in progress_calls if "grok-4" in call[2]]
        assert len(failure_msg) == 1
        assert "✗" in failure_msg[0][2]

    @pytest.mark.asyncio
    async def test_error_result_contains_required_fields(self):
        """Error results should have status, content, latency_ms, and error fields."""
        from llm_council.gateway_adapter import query_models_with_progress, STATUS_ERROR

        mock_router = MagicMock()
        mock_router.complete = AsyncMock(side_effect=Exception("HTTP 400: Bad Request"))

        with (
            patch("llm_council.gateway_adapter._use_gateway_layer", return_value=True),
            patch("llm_council.gateway_adapter.USE_GATEWAY_LAYER", True),
            patch("llm_council.gateway_adapter._get_gateway_router", return_value=mock_router),
        ):
            results = await query_models_with_progress(
                models=["x-ai/grok-4"],
                messages=[{"role": "user", "content": "Hello"}],
            )

        result = results["x-ai/grok-4"]
        assert result["status"] == STATUS_ERROR
        assert result["content"] is None
        assert result["latency_ms"] == 0
        assert "HTTP 400" in result["error"]


class TestOpenRouterHTTP400Handling:
    """Test explicit HTTP 400 handling in openrouter.py."""

    @pytest.mark.asyncio
    async def test_direct_openrouter_handles_400(self):
        """Direct openrouter module should return error dict for HTTP 400."""
        from llm_council.openrouter import query_model_with_status, STATUS_ERROR
        import httpx

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request: model not available"
        mock_response.headers = {}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await query_model_with_status(
                model="x-ai/grok-4",
                messages=[{"role": "user", "content": "Hello"}],
            )

        assert result["status"] == STATUS_ERROR
        assert "Bad request" in result["error"]
        assert "grok-4" in result["error"]

    @pytest.mark.asyncio
    async def test_gateway_openrouter_handles_400(self):
        """Gateway OpenRouter should return error dict for HTTP 400."""
        from llm_council.gateway.openrouter import OpenRouterGateway

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request: invalid model"
        mock_response.headers = {}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        gateway = OpenRouterGateway(api_key="test-key")

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await gateway._query_openrouter(
                model="x-ai/grok-4",
                messages=[{"role": "user", "content": "Hello"}],
                timeout=30.0,
            )

        assert result["status"] == "error"
        assert "Bad request" in result["error"]
        assert "grok-4" in result["error"]


class TestHTTPServerErrorBoundary:
    """Test HTTP server returns proper error responses."""

    @pytest.mark.asyncio
    async def test_council_run_returns_500_on_failure(self):
        """POST /v1/council/run should return 500 JSON on unhandled errors."""
        from llm_council.http_server import app
        from fastapi.testclient import TestClient

        with (
            patch(
                "llm_council.http_server.run_full_council", new_callable=AsyncMock
            ) as mock_council,
            patch("llm_council.http_server.get_api_key", return_value="test-key"),
        ):
            mock_council.side_effect = Exception("All models failed")

            client = TestClient(app)
            response = client.post(
                "/v1/council/run",
                json={"prompt": "test question"},
            )

        assert response.status_code == 500
        assert "Council deliberation failed" in response.json()["detail"]
