"""Tests for Direct API gateway implementation (ADR-023 Phase 3, Issue #67).

TDD: Write these tests first, then implement the DirectGateway.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime


class TestDirectGateway:
    """Test DirectGateway implements BaseRouter protocol."""

    def test_direct_gateway_is_base_router(self):
        """DirectGateway should implement BaseRouter protocol."""
        from llm_council.gateway.direct import DirectGateway
        from llm_council.gateway.base import BaseRouter

        gateway = DirectGateway()
        assert isinstance(gateway, BaseRouter)

    def test_direct_gateway_has_capabilities(self):
        """DirectGateway should report correct capabilities."""
        from llm_council.gateway.direct import DirectGateway
        from llm_council.gateway.base import RouterCapabilities

        gateway = DirectGateway()
        caps = gateway.capabilities

        assert isinstance(caps, RouterCapabilities)
        assert caps.supports_streaming is True
        assert caps.supports_tools is True
        assert caps.supports_vision is True
        assert caps.requires_byok is True  # Direct requires provider keys

    def test_direct_gateway_has_router_id(self):
        """DirectGateway should have router_id property."""
        from llm_council.gateway.direct import DirectGateway

        gateway = DirectGateway()
        assert gateway.router_id == "direct"


class TestDirectProviderDetection:
    """Test provider detection from model identifiers."""

    def test_detect_anthropic_provider(self):
        """Should detect Anthropic models."""
        from llm_council.gateway.direct import DirectGateway

        gateway = DirectGateway()

        assert gateway._get_provider("anthropic/claude-3-5-sonnet-20241022") == "anthropic"
        assert gateway._get_provider("anthropic/claude-3-opus-20240229") == "anthropic"

    def test_detect_openai_provider(self):
        """Should detect OpenAI models."""
        from llm_council.gateway.direct import DirectGateway

        gateway = DirectGateway()

        assert gateway._get_provider("openai/gpt-4o") == "openai"
        assert gateway._get_provider("openai/gpt-4-turbo") == "openai"

    def test_detect_google_provider(self):
        """Should detect Google models."""
        from llm_council.gateway.direct import DirectGateway

        gateway = DirectGateway()

        assert gateway._get_provider("google/gemini-1.5-pro") == "google"
        assert gateway._get_provider("google/gemini-2.0-flash-001") == "google"

    def test_unknown_provider_raises(self):
        """Should handle unknown providers gracefully."""
        from llm_council.gateway.direct import DirectGateway

        gateway = DirectGateway()

        # Unknown provider should return None or raise
        provider = gateway._get_provider("unknown/some-model")
        assert provider == "unknown"


class TestDirectProviderKeys:
    """Test provider API key configuration."""

    def test_anthropic_key_from_env(self):
        """Should use ANTHROPIC_API_KEY from environment."""
        from llm_council.gateway.direct import DirectGateway

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test"}):
            gateway = DirectGateway()
            assert gateway._get_api_key("anthropic") == "sk-ant-test"

    def test_openai_key_from_env(self):
        """Should use OPENAI_API_KEY from environment."""
        from llm_council.gateway.direct import DirectGateway

        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-openai-test"}):
            gateway = DirectGateway()
            assert gateway._get_api_key("openai") == "sk-openai-test"

    def test_google_key_from_env(self):
        """Should use GOOGLE_API_KEY from environment."""
        from llm_council.gateway.direct import DirectGateway

        with patch.dict("os.environ", {"GOOGLE_API_KEY": "google-test-key"}):
            gateway = DirectGateway()
            assert gateway._get_api_key("google") == "google-test-key"

    def test_custom_provider_keys(self):
        """Should accept custom provider keys in constructor."""
        from llm_council.gateway.direct import DirectGateway

        gateway = DirectGateway(
            provider_keys={
                "anthropic": "custom-ant-key",
                "openai": "custom-openai-key",
            }
        )

        assert gateway._get_api_key("anthropic") == "custom-ant-key"
        assert gateway._get_api_key("openai") == "custom-openai-key"


class TestDirectMessageConversion:
    """Test message format conversion for different providers."""

    def test_convert_to_anthropic_format(self):
        """Should convert CanonicalMessage to Anthropic format."""
        from llm_council.gateway.direct import DirectGateway
        from llm_council.gateway.types import CanonicalMessage, ContentBlock

        gateway = DirectGateway()
        msg = CanonicalMessage(role="user", content=[ContentBlock(type="text", text="Hello!")])

        result = gateway._convert_message_for_provider(msg, "anthropic")

        assert result["role"] == "user"
        # Anthropic uses content blocks
        assert isinstance(result["content"], (str, list))

    def test_convert_to_openai_format(self):
        """Should convert CanonicalMessage to OpenAI format."""
        from llm_council.gateway.direct import DirectGateway
        from llm_council.gateway.types import CanonicalMessage, ContentBlock

        gateway = DirectGateway()
        msg = CanonicalMessage(role="user", content=[ContentBlock(type="text", text="Hello!")])

        result = gateway._convert_message_for_provider(msg, "openai")

        assert result["role"] == "user"
        assert "content" in result

    def test_convert_system_message(self):
        """Should handle system messages for all providers."""
        from llm_council.gateway.direct import DirectGateway
        from llm_council.gateway.types import CanonicalMessage, ContentBlock

        gateway = DirectGateway()
        msg = CanonicalMessage(
            role="system", content=[ContentBlock(type="text", text="You are helpful.")]
        )

        # System message handling varies by provider
        result = gateway._convert_message_for_provider(msg, "openai")
        assert result["role"] == "system"


class TestDirectComplete:
    """Test DirectGateway.complete() method."""

    @pytest.mark.asyncio
    async def test_complete_returns_gateway_response(self):
        """complete() should return GatewayResponse."""
        from llm_council.gateway.direct import DirectGateway
        from llm_council.gateway.types import (
            GatewayRequest,
            GatewayResponse,
            CanonicalMessage,
            ContentBlock,
        )

        gateway = DirectGateway(provider_keys={"openai": "test-key"})
        request = GatewayRequest(
            model="openai/gpt-4o",
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

        with patch.object(gateway, "_query_provider", new_callable=AsyncMock) as mock_query:
            mock_query.return_value = mock_response
            response = await gateway.complete(request)

        assert isinstance(response, GatewayResponse)
        assert response.content == "Hi there!"
        assert response.model == "openai/gpt-4o"
        assert response.status == "ok"

    @pytest.mark.asyncio
    async def test_complete_routes_to_correct_provider(self):
        """complete() should route to the correct provider based on model."""
        from llm_council.gateway.direct import DirectGateway
        from llm_council.gateway.types import GatewayRequest, CanonicalMessage, ContentBlock

        gateway = DirectGateway(provider_keys={"anthropic": "ant-key"})
        request = GatewayRequest(
            model="anthropic/claude-3-5-sonnet-20241022",
            messages=[
                CanonicalMessage(role="user", content=[ContentBlock(type="text", text="Hello")])
            ],
        )

        mock_response = {"status": "ok", "content": "Hi!", "latency_ms": 100, "usage": {}}

        with patch.object(gateway, "_query_provider", new_callable=AsyncMock) as mock_query:
            mock_query.return_value = mock_response
            response = await gateway.complete(request)

            # Verify correct provider was used
            call_args = mock_query.call_args
            assert call_args[1]["provider"] == "anthropic"

        assert response.status == "ok"

    @pytest.mark.asyncio
    async def test_complete_handles_timeout(self):
        """complete() should handle timeout properly."""
        from llm_council.gateway.direct import DirectGateway
        from llm_council.gateway.types import GatewayRequest, CanonicalMessage, ContentBlock

        gateway = DirectGateway(provider_keys={"openai": "test-key"})
        request = GatewayRequest(
            model="openai/gpt-4o",
            messages=[
                CanonicalMessage(role="user", content=[ContentBlock(type="text", text="Hello")])
            ],
            timeout=30.0,
        )

        mock_response = {"status": "timeout", "latency_ms": 30000, "error": "Timeout after 30s"}

        with patch.object(gateway, "_query_provider", new_callable=AsyncMock) as mock_query:
            mock_query.return_value = mock_response
            response = await gateway.complete(request)

        assert response.status == "timeout"
        assert response.error == "Timeout after 30s"

    @pytest.mark.asyncio
    async def test_complete_handles_missing_api_key(self):
        """complete() should handle missing API key gracefully."""
        from llm_council.gateway.direct import DirectGateway
        from llm_council.gateway.types import GatewayRequest, CanonicalMessage, ContentBlock

        # No keys provided
        gateway = DirectGateway()
        request = GatewayRequest(
            model="openai/gpt-4o",
            messages=[
                CanonicalMessage(role="user", content=[ContentBlock(type="text", text="Hello")])
            ],
        )

        response = await gateway.complete(request)

        # Should return auth error
        assert response.status == "auth_error"


class TestDirectHealthCheck:
    """Test DirectGateway.health_check() method."""

    @pytest.mark.asyncio
    async def test_health_check_returns_router_health(self):
        """health_check() should return RouterHealth."""
        from llm_council.gateway.direct import DirectGateway
        from llm_council.gateway.base import RouterHealth, HealthStatus

        gateway = DirectGateway(provider_keys={"openai": "test-key"})

        mock_response = {"status": "ok", "content": "pong", "latency_ms": 50, "usage": {}}

        with patch.object(gateway, "_query_provider", new_callable=AsyncMock) as mock_query:
            mock_query.return_value = mock_response
            health = await gateway.health_check()

        assert isinstance(health, RouterHealth)
        assert health.router_id == "direct"
        assert health.status == HealthStatus.HEALTHY


class TestDirectIntegrationWithRouter:
    """Test DirectGateway integration with GatewayRouter."""

    def test_gateway_can_be_registered(self):
        """DirectGateway should be registrable with GatewayRouter."""
        from llm_council.gateway.direct import DirectGateway
        from llm_council.gateway.router import GatewayRouter

        direct = DirectGateway(provider_keys={"openai": "test-key"})
        router = GatewayRouter(gateways={"direct": direct})

        assert "direct" in router.gateways

    def test_gateway_in_fallback_chain(self):
        """DirectGateway should work in fallback chain."""
        from llm_council.gateway.direct import DirectGateway
        from llm_council.gateway.openrouter import OpenRouterGateway
        from llm_council.gateway.router import GatewayRouter

        openrouter = OpenRouterGateway(api_key="or-key")
        direct = DirectGateway(provider_keys={"openai": "test-key"})

        router = GatewayRouter(
            gateways={"openrouter": openrouter, "direct": direct},
            default_gateway="openrouter",
            fallback_chains={"openrouter": ["direct"]},
        )

        assert router._fallback_chains.get("openrouter") == ["direct"]


class TestDirectProviderEndpoints:
    """Test provider-specific API endpoints."""

    def test_anthropic_endpoint(self):
        """Should use correct Anthropic API endpoint."""
        from llm_council.gateway.direct import DirectGateway

        gateway = DirectGateway()
        endpoint = gateway._get_provider_endpoint("anthropic")

        assert (
            "anthropic" in endpoint.lower()
            or "claude" in endpoint.lower()
            or "messages" in endpoint
        )

    def test_openai_endpoint(self):
        """Should use correct OpenAI API endpoint."""
        from llm_council.gateway.direct import DirectGateway

        gateway = DirectGateway()
        endpoint = gateway._get_provider_endpoint("openai")

        assert "openai" in endpoint.lower() or "chat/completions" in endpoint

    def test_google_endpoint(self):
        """Should use correct Google API endpoint."""
        from llm_council.gateway.direct import DirectGateway

        gateway = DirectGateway()
        endpoint = gateway._get_provider_endpoint("google")

        assert "google" in endpoint.lower() or "generativelanguage" in endpoint.lower()
