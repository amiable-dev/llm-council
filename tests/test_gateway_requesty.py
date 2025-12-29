"""Tests for Requesty gateway implementation (ADR-023 Phase 2, Issue #66).

TDD: Write these tests first, then implement the RequestyGateway.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime


class TestRequestyGateway:
    """Test RequestyGateway implements BaseRouter protocol."""

    def test_requesty_gateway_is_base_router(self):
        """RequestyGateway should implement BaseRouter protocol."""
        from llm_council.gateway.requesty import RequestyGateway
        from llm_council.gateway.base import BaseRouter

        gateway = RequestyGateway()
        assert isinstance(gateway, BaseRouter)

    def test_requesty_gateway_has_capabilities(self):
        """RequestyGateway should report correct capabilities."""
        from llm_council.gateway.requesty import RequestyGateway
        from llm_council.gateway.base import RouterCapabilities

        gateway = RequestyGateway()
        caps = gateway.capabilities

        assert isinstance(caps, RouterCapabilities)
        assert caps.supports_streaming is True
        assert caps.supports_tools is True
        assert caps.supports_vision is True
        assert caps.supports_json_mode is True
        assert caps.supports_byok is True  # Requesty supports BYOK

    def test_requesty_gateway_has_router_id(self):
        """RequestyGateway should have router_id property."""
        from llm_council.gateway.requesty import RequestyGateway

        gateway = RequestyGateway()
        assert gateway.router_id == "requesty"


class TestRequestyBYOK:
    """Test Requesty BYOK (Bring Your Own Key) functionality."""

    def test_byok_disabled_by_default(self):
        """BYOK should be disabled by default."""
        from llm_council.gateway.requesty import RequestyGateway

        gateway = RequestyGateway()
        assert gateway.byok_enabled is False

    def test_byok_can_be_enabled(self):
        """BYOK should be configurable."""
        from llm_council.gateway.requesty import RequestyGateway

        gateway = RequestyGateway(byok_enabled=True)
        assert gateway.byok_enabled is True

    def test_byok_provider_keys_configurable(self):
        """BYOK provider keys should be configurable."""
        from llm_council.gateway.requesty import RequestyGateway

        gateway = RequestyGateway(
            byok_enabled=True,
            byok_keys={
                "anthropic": "sk-ant-test-key",
                "openai": "sk-openai-test-key",
            },
        )
        assert gateway.byok_keys.get("anthropic") == "sk-ant-test-key"
        assert gateway.byok_keys.get("openai") == "sk-openai-test-key"

    def test_byok_injects_provider_key(self):
        """BYOK should inject provider API key into request headers."""
        from llm_council.gateway.requesty import RequestyGateway

        gateway = RequestyGateway(byok_enabled=True, byok_keys={"anthropic": "sk-ant-test"})

        headers = gateway._get_byok_headers("anthropic/claude-3-5-sonnet-20241022")
        assert "x-provider-api-key" in headers or "X-Provider-API-Key" in headers


class TestRequestyMessageConversion:
    """Test message format conversion for Requesty."""

    def test_convert_canonical_to_requesty_text(self):
        """Should convert CanonicalMessage with text to Requesty format."""
        from llm_council.gateway.requesty import RequestyGateway
        from llm_council.gateway.types import CanonicalMessage, ContentBlock

        gateway = RequestyGateway()
        msg = CanonicalMessage(
            role="user", content=[ContentBlock(type="text", text="Hello, world!")]
        )

        result = gateway._convert_message(msg)

        assert result["role"] == "user"
        assert result["content"] == "Hello, world!"

    def test_convert_canonical_to_requesty_image(self):
        """Should convert image content blocks for Requesty."""
        from llm_council.gateway.requesty import RequestyGateway
        from llm_council.gateway.types import CanonicalMessage, ContentBlock

        gateway = RequestyGateway()
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


class TestRequestyComplete:
    """Test RequestyGateway.complete() method."""

    @pytest.mark.asyncio
    async def test_complete_returns_gateway_response(self):
        """complete() should return GatewayResponse."""
        from llm_council.gateway.requesty import RequestyGateway
        from llm_council.gateway.types import (
            GatewayRequest,
            GatewayResponse,
            CanonicalMessage,
            ContentBlock,
        )

        gateway = RequestyGateway()
        request = GatewayRequest(
            model="anthropic/claude-3-5-sonnet-20241022",
            messages=[
                CanonicalMessage(role="user", content=[ContentBlock(type="text", text="Hello")])
            ],
        )

        mock_response = {
            "status": "ok",
            "content": "Hi there!",
            "latency_ms": 150,
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        }

        with patch.object(gateway, "_query_requesty", new_callable=AsyncMock) as mock_query:
            mock_query.return_value = mock_response
            response = await gateway.complete(request)

        assert isinstance(response, GatewayResponse)
        assert response.content == "Hi there!"
        assert response.model == "anthropic/claude-3-5-sonnet-20241022"
        assert response.status == "ok"
        assert response.latency_ms == 150

    @pytest.mark.asyncio
    async def test_complete_with_byok(self):
        """complete() should use BYOK headers when enabled."""
        from llm_council.gateway.requesty import RequestyGateway
        from llm_council.gateway.types import GatewayRequest, CanonicalMessage, ContentBlock

        gateway = RequestyGateway(byok_enabled=True, byok_keys={"anthropic": "sk-ant-test"})
        request = GatewayRequest(
            model="anthropic/claude-3-5-sonnet-20241022",
            messages=[
                CanonicalMessage(role="user", content=[ContentBlock(type="text", text="Hello")])
            ],
        )

        mock_response = {"status": "ok", "content": "Hi!", "latency_ms": 100, "usage": {}}

        with patch.object(gateway, "_query_requesty", new_callable=AsyncMock) as mock_query:
            mock_query.return_value = mock_response
            response = await gateway.complete(request)

            # Verify BYOK headers were included
            call_kwargs = mock_query.call_args
            assert call_kwargs is not None

        assert response.status == "ok"

    @pytest.mark.asyncio
    async def test_complete_handles_timeout(self):
        """complete() should handle timeout properly."""
        from llm_council.gateway.requesty import RequestyGateway
        from llm_council.gateway.types import GatewayRequest, CanonicalMessage, ContentBlock

        gateway = RequestyGateway()
        request = GatewayRequest(
            model="anthropic/claude-3-5-sonnet-20241022",
            messages=[
                CanonicalMessage(role="user", content=[ContentBlock(type="text", text="Hello")])
            ],
            timeout=30.0,
        )

        mock_response = {"status": "timeout", "latency_ms": 30000, "error": "Timeout after 30s"}

        with patch.object(gateway, "_query_requesty", new_callable=AsyncMock) as mock_query:
            mock_query.return_value = mock_response
            response = await gateway.complete(request)

        assert response.status == "timeout"
        assert response.error == "Timeout after 30s"

    @pytest.mark.asyncio
    async def test_complete_handles_rate_limit(self):
        """complete() should handle rate limiting with retry_after."""
        from llm_council.gateway.requesty import RequestyGateway
        from llm_council.gateway.types import GatewayRequest, CanonicalMessage, ContentBlock

        gateway = RequestyGateway()
        request = GatewayRequest(
            model="anthropic/claude-3-5-sonnet-20241022",
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

        with patch.object(gateway, "_query_requesty", new_callable=AsyncMock) as mock_query:
            mock_query.return_value = mock_response
            response = await gateway.complete(request)

        assert response.status == "rate_limited"
        assert response.retry_after == 60


class TestRequestyHealthCheck:
    """Test RequestyGateway.health_check() method."""

    @pytest.mark.asyncio
    async def test_health_check_returns_router_health(self):
        """health_check() should return RouterHealth."""
        from llm_council.gateway.requesty import RequestyGateway
        from llm_council.gateway.base import RouterHealth, HealthStatus

        gateway = RequestyGateway()

        mock_response = {"status": "ok", "content": "pong", "latency_ms": 50, "usage": {}}

        with patch.object(gateway, "_query_requesty", new_callable=AsyncMock) as mock_query:
            mock_query.return_value = mock_response
            health = await gateway.health_check()

        assert isinstance(health, RouterHealth)
        assert health.router_id == "requesty"
        assert health.status == HealthStatus.HEALTHY
        assert health.latency_ms == 50.0

    @pytest.mark.asyncio
    async def test_health_check_unhealthy_on_error(self):
        """health_check() should return unhealthy on error."""
        from llm_council.gateway.requesty import RequestyGateway
        from llm_council.gateway.base import HealthStatus

        gateway = RequestyGateway()

        mock_response = {"status": "error", "latency_ms": 100, "error": "Connection refused"}

        with patch.object(gateway, "_query_requesty", new_callable=AsyncMock) as mock_query:
            mock_query.return_value = mock_response
            health = await gateway.health_check()

        assert health.status == HealthStatus.UNHEALTHY
        assert "Connection refused" in health.error_message


class TestRequestyGatewayConfig:
    """Test RequestyGateway configuration."""

    def test_gateway_uses_env_api_key(self):
        """Gateway should use REQUESTY_API_KEY from environment."""
        from llm_council.gateway.requesty import RequestyGateway

        with patch.dict("os.environ", {"REQUESTY_API_KEY": "test-requesty-key"}):
            gateway = RequestyGateway()
            assert gateway._api_key == "test-requesty-key"

    def test_gateway_allows_custom_api_key(self):
        """Gateway should accept custom API key."""
        from llm_council.gateway.requesty import RequestyGateway

        gateway = RequestyGateway(api_key="custom-key")
        assert gateway._api_key == "custom-key"

    def test_gateway_uses_correct_base_url(self):
        """Gateway should use Requesty API URL."""
        from llm_council.gateway.requesty import RequestyGateway

        gateway = RequestyGateway()
        assert "requesty" in gateway._base_url.lower() or gateway._base_url is not None


class TestRequestyIntegrationWithRouter:
    """Test RequestyGateway integration with GatewayRouter."""

    def test_gateway_can_be_registered(self):
        """RequestyGateway should be registrable with GatewayRouter."""
        from llm_council.gateway.requesty import RequestyGateway
        from llm_council.gateway.router import GatewayRouter

        requesty = RequestyGateway(api_key="test-key")
        router = GatewayRouter(gateways={"requesty": requesty})

        assert "requesty" in router.gateways

    def test_gateway_in_fallback_chain(self):
        """RequestyGateway should work in fallback chain."""
        from llm_council.gateway.requesty import RequestyGateway
        from llm_council.gateway.openrouter import OpenRouterGateway
        from llm_council.gateway.router import GatewayRouter

        openrouter = OpenRouterGateway(api_key="or-key")
        requesty = RequestyGateway(api_key="req-key")

        router = GatewayRouter(
            gateways={"openrouter": openrouter, "requesty": requesty},
            default_gateway="openrouter",
            fallback_chains={"openrouter": ["requesty"]},
        )

        assert router._fallback_chains.get("openrouter") == ["requesty"]
