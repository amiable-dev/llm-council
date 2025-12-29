"""Tests for OpenRouter gateway implementation (ADR-023).

TDD: Write these tests first, then implement the OpenRouterGateway.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime


class TestOpenRouterGateway:
    """Test OpenRouterGateway implements BaseRouter protocol."""

    def test_openrouter_gateway_is_base_router(self):
        """OpenRouterGateway should implement BaseRouter protocol."""
        from llm_council.gateway.openrouter import OpenRouterGateway
        from llm_council.gateway.base import BaseRouter

        gateway = OpenRouterGateway()
        assert isinstance(gateway, BaseRouter)

    def test_openrouter_gateway_has_capabilities(self):
        """OpenRouterGateway should report correct capabilities."""
        from llm_council.gateway.openrouter import OpenRouterGateway
        from llm_council.gateway.base import RouterCapabilities

        gateway = OpenRouterGateway()
        caps = gateway.capabilities

        assert isinstance(caps, RouterCapabilities)
        assert caps.supports_streaming is True
        assert caps.supports_tools is True
        assert caps.supports_vision is True
        assert caps.supports_json_mode is True
        assert caps.supports_byok is False  # OpenRouter uses its own key

    def test_openrouter_gateway_has_router_id(self):
        """OpenRouterGateway should have router_id property."""
        from llm_council.gateway.openrouter import OpenRouterGateway

        gateway = OpenRouterGateway()
        assert gateway.router_id == "openrouter"


class TestOpenRouterMessageConversion:
    """Test message format conversion."""

    def test_convert_canonical_to_openrouter_text(self):
        """Should convert CanonicalMessage with text to OpenRouter format."""
        from llm_council.gateway.openrouter import OpenRouterGateway
        from llm_council.gateway.types import CanonicalMessage, ContentBlock

        gateway = OpenRouterGateway()
        msg = CanonicalMessage(
            role="user", content=[ContentBlock(type="text", text="Hello, world!")]
        )

        result = gateway._convert_message(msg)

        assert result["role"] == "user"
        assert result["content"] == "Hello, world!"

    def test_convert_canonical_to_openrouter_multiple_text(self):
        """Should concatenate multiple text blocks."""
        from llm_council.gateway.openrouter import OpenRouterGateway
        from llm_council.gateway.types import CanonicalMessage, ContentBlock

        gateway = OpenRouterGateway()
        msg = CanonicalMessage(
            role="user",
            content=[
                ContentBlock(type="text", text="Part 1."),
                ContentBlock(type="text", text="Part 2."),
            ],
        )

        result = gateway._convert_message(msg)

        assert result["role"] == "user"
        assert "Part 1." in result["content"]
        assert "Part 2." in result["content"]

    def test_convert_canonical_to_openrouter_image(self):
        """Should convert image content blocks."""
        from llm_council.gateway.openrouter import OpenRouterGateway
        from llm_council.gateway.types import CanonicalMessage, ContentBlock

        gateway = OpenRouterGateway()
        msg = CanonicalMessage(
            role="user",
            content=[
                ContentBlock(type="text", text="What's in this image?"),
                ContentBlock(type="image", image_url="https://example.com/img.png"),
            ],
        )

        result = gateway._convert_message(msg)

        assert result["role"] == "user"
        assert isinstance(result["content"], list)
        # Should have both text and image parts
        assert any(p.get("type") == "text" for p in result["content"])
        assert any(p.get("type") == "image_url" for p in result["content"])

    def test_convert_system_message(self):
        """Should handle system messages."""
        from llm_council.gateway.openrouter import OpenRouterGateway
        from llm_council.gateway.types import CanonicalMessage, ContentBlock

        gateway = OpenRouterGateway()
        msg = CanonicalMessage(
            role="system", content=[ContentBlock(type="text", text="You are helpful.")]
        )

        result = gateway._convert_message(msg)

        assert result["role"] == "system"
        assert result["content"] == "You are helpful."


class TestOpenRouterComplete:
    """Test OpenRouterGateway.complete() method."""

    @pytest.mark.asyncio
    async def test_complete_returns_gateway_response(self):
        """complete() should return GatewayResponse."""
        from llm_council.gateway.openrouter import OpenRouterGateway
        from llm_council.gateway.types import (
            GatewayRequest,
            GatewayResponse,
            CanonicalMessage,
            ContentBlock,
        )

        gateway = OpenRouterGateway()
        request = GatewayRequest(
            model="openai/gpt-4o",
            messages=[
                CanonicalMessage(role="user", content=[ContentBlock(type="text", text="Hello")])
            ],
        )

        # Mock the underlying HTTP call
        mock_response = {
            "status": "ok",
            "content": "Hi there!",
            "latency_ms": 150,
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        }

        with patch.object(gateway, "_query_openrouter", new_callable=AsyncMock) as mock_query:
            mock_query.return_value = mock_response
            response = await gateway.complete(request)

        assert isinstance(response, GatewayResponse)
        assert response.content == "Hi there!"
        assert response.model == "openai/gpt-4o"
        assert response.status == "ok"
        assert response.latency_ms == 150

    @pytest.mark.asyncio
    async def test_complete_includes_usage(self):
        """complete() should include usage info when available."""
        from llm_council.gateway.openrouter import OpenRouterGateway
        from llm_council.gateway.types import (
            GatewayRequest,
            CanonicalMessage,
            ContentBlock,
            UsageInfo,
        )

        gateway = OpenRouterGateway()
        request = GatewayRequest(
            model="openai/gpt-4o",
            messages=[
                CanonicalMessage(role="user", content=[ContentBlock(type="text", text="Hello")])
            ],
        )

        mock_response = {
            "status": "ok",
            "content": "Hi!",
            "latency_ms": 100,
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }

        with patch.object(gateway, "_query_openrouter", new_callable=AsyncMock) as mock_query:
            mock_query.return_value = mock_response
            response = await gateway.complete(request)

        assert response.usage is not None
        assert response.usage.prompt_tokens == 10
        assert response.usage.completion_tokens == 5
        assert response.usage.total_tokens == 15

    @pytest.mark.asyncio
    async def test_complete_handles_timeout(self):
        """complete() should handle timeout properly."""
        from llm_council.gateway.openrouter import OpenRouterGateway
        from llm_council.gateway.types import GatewayRequest, CanonicalMessage, ContentBlock

        gateway = OpenRouterGateway()
        request = GatewayRequest(
            model="openai/gpt-4o",
            messages=[
                CanonicalMessage(role="user", content=[ContentBlock(type="text", text="Hello")])
            ],
            timeout=30.0,
        )

        mock_response = {"status": "timeout", "latency_ms": 30000, "error": "Timeout after 30s"}

        with patch.object(gateway, "_query_openrouter", new_callable=AsyncMock) as mock_query:
            mock_query.return_value = mock_response
            response = await gateway.complete(request)

        assert response.status == "timeout"
        assert response.error == "Timeout after 30s"

    @pytest.mark.asyncio
    async def test_complete_handles_rate_limit(self):
        """complete() should handle rate limiting with retry_after."""
        from llm_council.gateway.openrouter import OpenRouterGateway
        from llm_council.gateway.types import GatewayRequest, CanonicalMessage, ContentBlock

        gateway = OpenRouterGateway()
        request = GatewayRequest(
            model="openai/gpt-4o",
            messages=[
                CanonicalMessage(role="user", content=[ContentBlock(type="text", text="Hello")])
            ],
        )

        mock_response = {
            "status": "rate_limited",
            "latency_ms": 50,
            "error": "Rate limited",
            "retry_after": 60,
        }

        with patch.object(gateway, "_query_openrouter", new_callable=AsyncMock) as mock_query:
            mock_query.return_value = mock_response
            response = await gateway.complete(request)

        assert response.status == "rate_limited"
        assert response.retry_after == 60


class TestOpenRouterHealthCheck:
    """Test OpenRouterGateway.health_check() method."""

    @pytest.mark.asyncio
    async def test_health_check_returns_router_health(self):
        """health_check() should return RouterHealth."""
        from llm_council.gateway.openrouter import OpenRouterGateway
        from llm_council.gateway.base import RouterHealth, HealthStatus

        gateway = OpenRouterGateway()

        mock_response = {"status": "ok", "content": "pong", "latency_ms": 50, "usage": {}}

        with patch.object(gateway, "_query_openrouter", new_callable=AsyncMock) as mock_query:
            mock_query.return_value = mock_response
            health = await gateway.health_check()

        assert isinstance(health, RouterHealth)
        assert health.router_id == "openrouter"
        assert health.status == HealthStatus.HEALTHY
        assert health.latency_ms == 50.0

    @pytest.mark.asyncio
    async def test_health_check_unhealthy_on_error(self):
        """health_check() should return unhealthy on error."""
        from llm_council.gateway.openrouter import OpenRouterGateway
        from llm_council.gateway.base import HealthStatus

        gateway = OpenRouterGateway()

        mock_response = {"status": "error", "latency_ms": 100, "error": "Connection refused"}

        with patch.object(gateway, "_query_openrouter", new_callable=AsyncMock) as mock_query:
            mock_query.return_value = mock_response
            health = await gateway.health_check()

        assert health.status == HealthStatus.UNHEALTHY
        assert "Connection refused" in health.error_message


class TestOpenRouterGatewayConfig:
    """Test OpenRouterGateway configuration."""

    def test_gateway_uses_config_api_key(self):
        """Gateway should use OPENROUTER_API_KEY from config."""
        from llm_council.gateway.openrouter import OpenRouterGateway

        with patch("llm_council.gateway.openrouter.OPENROUTER_API_KEY", "test-key"):
            gateway = OpenRouterGateway()
            assert gateway._api_key == "test-key"

    def test_gateway_allows_custom_api_key(self):
        """Gateway should accept custom API key."""
        from llm_council.gateway.openrouter import OpenRouterGateway

        gateway = OpenRouterGateway(api_key="custom-key")
        assert gateway._api_key == "custom-key"

    def test_gateway_allows_custom_base_url(self):
        """Gateway should accept custom base URL."""
        from llm_council.gateway.openrouter import OpenRouterGateway

        gateway = OpenRouterGateway(base_url="https://custom.api/v1")
        assert gateway._base_url == "https://custom.api/v1"


class TestBackwardCompatibility:
    """Test backward compatibility with existing openrouter module."""

    def test_existing_functions_still_work(self):
        """Existing query_model functions should still be importable."""
        from llm_council.openrouter import (
            query_model,
            query_model_with_status,
            query_models_parallel,
            query_models_with_progress,
            STATUS_OK,
            STATUS_TIMEOUT,
            STATUS_RATE_LIMITED,
            STATUS_AUTH_ERROR,
            STATUS_ERROR,
        )

        # Just verify imports work
        assert callable(query_model)
        assert callable(query_model_with_status)
        assert callable(query_models_parallel)
        assert callable(query_models_with_progress)
        assert STATUS_OK == "ok"

    def test_gateway_can_be_used_alongside_existing(self):
        """Gateway should not break existing openrouter usage."""
        from llm_council.gateway.openrouter import OpenRouterGateway
        from llm_council.openrouter import query_model_with_status

        # Both should be importable and work
        gateway = OpenRouterGateway()
        assert gateway is not None
        assert callable(query_model_with_status)
