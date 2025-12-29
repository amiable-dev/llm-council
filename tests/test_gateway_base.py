"""Tests for gateway base types and protocol (ADR-023).

TDD: Write these tests first, then implement the gateway package.
"""

import pytest
from dataclasses import FrozenInstanceError


class TestCanonicalMessage:
    """Test CanonicalMessage dataclass."""

    def test_canonical_message_has_required_fields(self):
        """CanonicalMessage must have role and content."""
        from llm_council.gateway.types import CanonicalMessage, ContentBlock

        msg = CanonicalMessage(role="user", content=[ContentBlock(type="text", text="Hello")])

        assert msg.role == "user"
        assert len(msg.content) == 1
        assert msg.content[0].type == "text"
        assert msg.content[0].text == "Hello"

    def test_canonical_message_supports_system_role(self):
        """CanonicalMessage should support system role."""
        from llm_council.gateway.types import CanonicalMessage, ContentBlock

        msg = CanonicalMessage(
            role="system", content=[ContentBlock(type="text", text="You are helpful")]
        )

        assert msg.role == "system"

    def test_canonical_message_supports_assistant_role(self):
        """CanonicalMessage should support assistant role."""
        from llm_council.gateway.types import CanonicalMessage, ContentBlock

        msg = CanonicalMessage(
            role="assistant", content=[ContentBlock(type="text", text="I can help")]
        )

        assert msg.role == "assistant"

    def test_canonical_message_optional_tool_fields(self):
        """CanonicalMessage should have optional tool fields."""
        from llm_council.gateway.types import CanonicalMessage, ContentBlock

        msg = CanonicalMessage(role="user", content=[ContentBlock(type="text", text="Hello")])

        # Tool fields should have defaults
        assert msg.tool_calls == []
        assert msg.tool_call_id is None


class TestContentBlock:
    """Test ContentBlock dataclass."""

    def test_content_block_text_type(self):
        """ContentBlock should support text type."""
        from llm_council.gateway.types import ContentBlock

        block = ContentBlock(type="text", text="Hello world")

        assert block.type == "text"
        assert block.text == "Hello world"

    def test_content_block_image_type(self):
        """ContentBlock should support image type."""
        from llm_council.gateway.types import ContentBlock

        block = ContentBlock(type="image", image_url="https://example.com/img.png")

        assert block.type == "image"
        assert block.image_url == "https://example.com/img.png"

    def test_content_block_optional_fields(self):
        """ContentBlock fields should have None defaults."""
        from llm_council.gateway.types import ContentBlock

        block = ContentBlock(type="text")

        assert block.text is None
        assert block.image_url is None
        assert block.tool_use is None


class TestGatewayRequest:
    """Test GatewayRequest dataclass."""

    def test_gateway_request_has_required_fields(self):
        """GatewayRequest must have model and messages."""
        from llm_council.gateway.types import GatewayRequest, CanonicalMessage, ContentBlock

        request = GatewayRequest(
            model="openai/gpt-4o",
            messages=[
                CanonicalMessage(role="user", content=[ContentBlock(type="text", text="Hello")])
            ],
        )

        assert request.model == "openai/gpt-4o"
        assert len(request.messages) == 1

    def test_gateway_request_optional_params(self):
        """GatewayRequest should have optional generation params."""
        from llm_council.gateway.types import GatewayRequest, CanonicalMessage, ContentBlock

        request = GatewayRequest(
            model="openai/gpt-4o",
            messages=[
                CanonicalMessage(role="user", content=[ContentBlock(type="text", text="Hello")])
            ],
            max_tokens=1000,
            temperature=0.7,
            timeout=30.0,
        )

        assert request.max_tokens == 1000
        assert request.temperature == 0.7
        assert request.timeout == 30.0


class TestGatewayResponse:
    """Test GatewayResponse dataclass."""

    def test_gateway_response_has_required_fields(self):
        """GatewayResponse must have content and model fields."""
        from llm_council.gateway.types import GatewayResponse

        response = GatewayResponse(
            content="Hello, how can I help?",
            model="openai/gpt-4o",
            status="ok",
        )

        assert response.content == "Hello, how can I help?"
        assert response.model == "openai/gpt-4o"
        assert response.status == "ok"

    def test_gateway_response_optional_usage(self):
        """GatewayResponse should have optional usage info."""
        from llm_council.gateway.types import GatewayResponse, UsageInfo

        usage = UsageInfo(prompt_tokens=10, completion_tokens=20, total_tokens=30)
        response = GatewayResponse(
            content="Hello",
            model="openai/gpt-4o",
            status="ok",
            usage=usage,
            latency_ms=150,
        )

        assert response.usage.prompt_tokens == 10
        assert response.usage.completion_tokens == 20
        assert response.latency_ms == 150


class TestUsageInfo:
    """Test UsageInfo dataclass."""

    def test_usage_info_fields(self):
        """UsageInfo should have token counts."""
        from llm_council.gateway.types import UsageInfo

        usage = UsageInfo(prompt_tokens=100, completion_tokens=50, total_tokens=150)

        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 50
        assert usage.total_tokens == 150


class TestRouterCapabilities:
    """Test RouterCapabilities dataclass."""

    def test_router_capabilities_defaults(self):
        """RouterCapabilities should have sensible defaults."""
        from llm_council.gateway.base import RouterCapabilities

        caps = RouterCapabilities()

        assert caps.supports_streaming is True
        assert caps.supports_tools is True
        assert caps.supports_vision is True
        assert caps.supports_json_mode is True
        assert caps.supports_byok is False
        assert caps.requires_byok is False

    def test_router_capabilities_customizable(self):
        """RouterCapabilities should be customizable."""
        from llm_council.gateway.base import RouterCapabilities

        caps = RouterCapabilities(
            supports_streaming=False,
            supports_byok=True,
            max_context_window=128000,
        )

        assert caps.supports_streaming is False
        assert caps.supports_byok is True
        assert caps.max_context_window == 128000


class TestRouterConfig:
    """Test RouterConfig dataclass."""

    def test_router_config_required_fields(self):
        """RouterConfig must have name, base_url, api_key_env."""
        from llm_council.gateway.base import RouterConfig

        config = RouterConfig(
            name="openrouter",
            base_url="https://openrouter.ai/api/v1/chat/completions",
            api_key_env="OPENROUTER_API_KEY",
        )

        assert config.name == "openrouter"
        assert config.base_url == "https://openrouter.ai/api/v1/chat/completions"
        assert config.api_key_env == "OPENROUTER_API_KEY"

    def test_router_config_defaults(self):
        """RouterConfig should have timeout and retry defaults."""
        from llm_council.gateway.base import RouterConfig

        config = RouterConfig(
            name="test",
            base_url="https://example.com",
            api_key_env="TEST_KEY",
        )

        assert config.timeout == 120.0
        assert config.retry_policy is None
        assert config.extra_headers is None


class TestBaseRouterProtocol:
    """Test that BaseRouter defines required abstract methods."""

    def test_base_router_is_abstract(self):
        """BaseRouter should not be instantiable directly."""
        from llm_council.gateway.base import BaseRouter

        with pytest.raises(TypeError):
            BaseRouter()  # type: ignore

    def test_base_router_has_required_methods(self):
        """BaseRouter should define required abstract methods."""
        from llm_council.gateway.base import BaseRouter
        import inspect

        # Check abstract methods exist
        abstract_methods = {
            name
            for name, method in inspect.getmembers(BaseRouter)
            if getattr(method, "__isabstractmethod__", False)
        }

        assert "complete" in abstract_methods
        assert "complete_stream" in abstract_methods
        assert "health_check" in abstract_methods

    def test_base_router_has_capabilities_property(self):
        """BaseRouter should have capabilities property."""
        from llm_council.gateway.base import BaseRouter
        import inspect

        # Check capabilities is defined
        assert hasattr(BaseRouter, "capabilities")


class TestGatewayErrors:
    """Test gateway error types."""

    def test_transport_failure_error(self):
        """TransportFailure should have message and router_id."""
        from llm_council.gateway.errors import TransportFailure

        error = TransportFailure("Connection timeout", router_id="openrouter")

        assert str(error) == "Connection timeout"
        assert error.router_id == "openrouter"

    def test_rate_limit_error(self):
        """RateLimitError should have retry_after."""
        from llm_council.gateway.errors import RateLimitError

        error = RateLimitError("Rate limited", retry_after=30)

        assert "Rate limited" in str(error)
        assert error.retry_after == 30

    def test_auth_error(self):
        """AuthenticationError should have message."""
        from llm_council.gateway.errors import AuthenticationError

        error = AuthenticationError("Invalid API key")

        assert "Invalid API key" in str(error)

    def test_model_not_found_error(self):
        """ModelNotFoundError should have model_id."""
        from llm_council.gateway.errors import ModelNotFoundError

        error = ModelNotFoundError("Model not found", model_id="invalid/model")

        assert error.model_id == "invalid/model"

    def test_circuit_open_error(self):
        """CircuitOpenError for circuit breaker."""
        from llm_council.gateway.errors import CircuitOpenError

        error = CircuitOpenError("Circuit is open", router_id="openrouter")

        assert error.router_id == "openrouter"


class TestRouterHealth:
    """Test RouterHealth dataclass."""

    def test_router_health_fields(self):
        """RouterHealth should have status and timing info."""
        from llm_council.gateway.base import RouterHealth, HealthStatus
        from datetime import datetime

        health = RouterHealth(
            router_id="openrouter",
            status=HealthStatus.HEALTHY,
            latency_ms=50.0,
            last_check=datetime.now(),
        )

        assert health.router_id == "openrouter"
        assert health.status == HealthStatus.HEALTHY
        assert health.latency_ms == 50.0
        assert health.circuit_open is False
        assert health.consecutive_failures == 0


class TestHealthStatus:
    """Test HealthStatus enum."""

    def test_health_status_values(self):
        """HealthStatus should have healthy, degraded, unhealthy."""
        from llm_council.gateway.base import HealthStatus

        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.DEGRADED.value == "degraded"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"
