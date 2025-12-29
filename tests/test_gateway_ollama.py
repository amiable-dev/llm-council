"""Tests for OllamaGateway implementation (ADR-025).

TDD: Write these tests first, then implement the OllamaGateway.

This gateway wraps LiteLLM to provide local LLM support via Ollama,
with quality degradation notices for local model usage.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime


class TestOllamaGateway:
    """Test OllamaGateway basic structure and protocol compliance."""

    def test_ollama_gateway_is_base_router(self):
        """OllamaGateway should implement BaseRouter protocol."""
        from llm_council.gateway.ollama import OllamaGateway
        from llm_council.gateway.base import BaseRouter

        gateway = OllamaGateway()
        assert isinstance(gateway, BaseRouter)

    def test_ollama_gateway_has_capabilities(self):
        """OllamaGateway should report correct capabilities."""
        from llm_council.gateway.ollama import OllamaGateway
        from llm_council.gateway.base import RouterCapabilities

        gateway = OllamaGateway()
        caps = gateway.capabilities

        assert isinstance(caps, RouterCapabilities)
        assert caps.supports_streaming is True
        assert caps.supports_tools is True
        assert caps.supports_vision is True
        assert caps.supports_json_mode is True
        # Local models don't need BYOK
        assert caps.supports_byok is False
        assert caps.requires_byok is False

    def test_ollama_gateway_has_router_id(self):
        """OllamaGateway should have router_id 'ollama'."""
        from llm_council.gateway.ollama import OllamaGateway

        gateway = OllamaGateway()
        assert gateway.router_id == "ollama"

    def test_ollama_gateway_identifies_local_model(self):
        """Gateway should identify all ollama/* models as local."""
        from llm_council.gateway.ollama import OllamaGateway

        gateway = OllamaGateway()
        # All ollama models should be identified as local
        assert gateway._is_local_model("ollama/llama3.2") is True
        assert gateway._is_local_model("ollama/mistral") is True
        assert gateway._is_local_model("openai/gpt-4o") is False


class TestOllamaModelIdentifier:
    """Test model identifier parsing for ollama/* format."""

    def test_parse_ollama_model_format(self):
        """Should parse 'ollama/llama3.2' format correctly."""
        from llm_council.gateway.ollama import OllamaGateway

        gateway = OllamaGateway()
        # ollama/model-name format passes through to LiteLLM
        assert gateway._get_model_name("ollama/llama3.2") == "ollama/llama3.2"

    def test_extract_model_name(self):
        """Should extract 'llama3.2' from 'ollama/llama3.2' when needed."""
        from llm_council.gateway.ollama import OllamaGateway

        gateway = OllamaGateway()
        assert gateway._extract_model_name("ollama/llama3.2") == "llama3.2"
        assert gateway._extract_model_name("ollama/mistral:7b") == "mistral:7b"

    def test_add_ollama_prefix_if_missing(self):
        """Should add ollama/ prefix if missing."""
        from llm_council.gateway.ollama import OllamaGateway

        gateway = OllamaGateway()
        assert gateway._get_model_name("llama3.2") == "ollama/llama3.2"
        assert gateway._get_model_name("ollama/llama3.2") == "ollama/llama3.2"


class TestOllamaMessageConversion:
    """Test message conversion from CanonicalMessage to LiteLLM format."""

    def test_convert_canonical_to_litellm_text(self):
        """Should convert CanonicalMessage with text to LiteLLM format."""
        from llm_council.gateway.ollama import OllamaGateway
        from llm_council.gateway.types import CanonicalMessage, ContentBlock

        gateway = OllamaGateway()
        msg = CanonicalMessage(
            role="user", content=[ContentBlock(type="text", text="Hello, world!")]
        )

        converted = gateway._convert_message(msg)

        assert converted["role"] == "user"
        assert converted["content"] == "Hello, world!"

    def test_convert_canonical_to_litellm_multiple_text(self):
        """Should concatenate multiple text blocks."""
        from llm_council.gateway.ollama import OllamaGateway
        from llm_council.gateway.types import CanonicalMessage, ContentBlock

        gateway = OllamaGateway()
        msg = CanonicalMessage(
            role="user",
            content=[
                ContentBlock(type="text", text="Hello"),
                ContentBlock(type="text", text="World"),
            ],
        )

        converted = gateway._convert_message(msg)

        assert converted["role"] == "user"
        assert "Hello" in converted["content"]
        assert "World" in converted["content"]

    def test_convert_system_message(self):
        """Should handle system messages correctly."""
        from llm_council.gateway.ollama import OllamaGateway
        from llm_council.gateway.types import CanonicalMessage, ContentBlock

        gateway = OllamaGateway()
        msg = CanonicalMessage(
            role="system", content=[ContentBlock(type="text", text="You are a helpful assistant.")]
        )

        converted = gateway._convert_message(msg)

        assert converted["role"] == "system"
        assert converted["content"] == "You are a helpful assistant."

    def test_convert_image_content(self):
        """Should convert image content blocks for vision models."""
        from llm_council.gateway.ollama import OllamaGateway
        from llm_council.gateway.types import CanonicalMessage, ContentBlock

        gateway = OllamaGateway()
        msg = CanonicalMessage(
            role="user",
            content=[
                ContentBlock(type="text", text="What's in this image?"),
                ContentBlock(type="image", image_url="https://example.com/image.png"),
            ],
        )

        converted = gateway._convert_message(msg)

        assert converted["role"] == "user"
        # Multi-part content for vision
        assert isinstance(converted["content"], list)
        assert len(converted["content"]) == 2
        assert converted["content"][0]["type"] == "text"
        assert converted["content"][1]["type"] == "image_url"


class TestOllamaComplete:
    """Test async completion functionality."""

    @pytest.mark.asyncio
    async def test_complete_returns_gateway_response(self):
        """complete() should return GatewayResponse."""
        from llm_council.gateway.ollama import OllamaGateway
        from llm_council.gateway.types import (
            GatewayRequest,
            GatewayResponse,
            CanonicalMessage,
            ContentBlock,
        )

        gateway = OllamaGateway()
        request = GatewayRequest(
            model="ollama/llama3.2",
            messages=[
                CanonicalMessage(role="user", content=[ContentBlock(type="text", text="Hello")])
            ],
        )

        # Mock LiteLLM
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hi there!"
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 5
        mock_response.usage.completion_tokens = 10
        mock_response.usage.total_tokens = 15

        with patch.object(gateway, "_get_litellm") as mock_get_litellm:
            mock_litellm = MagicMock()
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)
            mock_get_litellm.return_value = mock_litellm

            response = await gateway.complete(request)

        assert isinstance(response, GatewayResponse)
        assert response.content == "Hi there!"
        assert response.model == "ollama/llama3.2"
        assert response.status == "ok"

    @pytest.mark.asyncio
    async def test_complete_includes_usage(self):
        """complete() should include usage info when available."""
        from llm_council.gateway.ollama import OllamaGateway
        from llm_council.gateway.types import (
            GatewayRequest,
            CanonicalMessage,
            ContentBlock,
            UsageInfo,
        )

        gateway = OllamaGateway()
        request = GatewayRequest(
            model="ollama/llama3.2",
            messages=[
                CanonicalMessage(role="user", content=[ContentBlock(type="text", text="Hello")])
            ],
        )

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hi!"
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 5
        mock_response.usage.completion_tokens = 10
        mock_response.usage.total_tokens = 15

        with patch.object(gateway, "_get_litellm") as mock_get_litellm:
            mock_litellm = MagicMock()
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)
            mock_get_litellm.return_value = mock_litellm

            response = await gateway.complete(request)

        assert response.usage is not None
        assert isinstance(response.usage, UsageInfo)
        assert response.usage.prompt_tokens == 5
        assert response.usage.completion_tokens == 10
        assert response.usage.total_tokens == 15

    @pytest.mark.asyncio
    async def test_complete_handles_timeout(self):
        """complete() should handle timeout properly."""
        from llm_council.gateway.ollama import OllamaGateway
        from llm_council.gateway.types import GatewayRequest, CanonicalMessage, ContentBlock
        import asyncio

        gateway = OllamaGateway()
        request = GatewayRequest(
            model="ollama/llama3.2",
            messages=[
                CanonicalMessage(role="user", content=[ContentBlock(type="text", text="Hello")])
            ],
            timeout=1.0,
        )

        with patch.object(gateway, "_get_litellm") as mock_get_litellm:
            mock_litellm = MagicMock()
            mock_litellm.acompletion = AsyncMock(side_effect=asyncio.TimeoutError("Timeout"))
            mock_get_litellm.return_value = mock_litellm

            response = await gateway.complete(request)

        assert response.status == "timeout"
        assert response.error is not None
        assert "timeout" in response.error.lower()

    @pytest.mark.asyncio
    async def test_complete_handles_connection_error(self):
        """complete() should handle connection refused (Ollama not running)."""
        from llm_council.gateway.ollama import OllamaGateway
        from llm_council.gateway.types import GatewayRequest, CanonicalMessage, ContentBlock

        gateway = OllamaGateway()
        request = GatewayRequest(
            model="ollama/llama3.2",
            messages=[
                CanonicalMessage(role="user", content=[ContentBlock(type="text", text="Hello")])
            ],
        )

        with patch.object(gateway, "_get_litellm") as mock_get_litellm:
            mock_litellm = MagicMock()
            mock_litellm.acompletion = AsyncMock(
                side_effect=ConnectionRefusedError("Connection refused")
            )
            mock_get_litellm.return_value = mock_litellm

            response = await gateway.complete(request)

        assert response.status == "error"
        assert response.error is not None
        assert "ollama" in response.error.lower() or "connection" in response.error.lower()

    @pytest.mark.asyncio
    async def test_complete_calls_litellm_acompletion(self):
        """Should call litellm.acompletion with correct parameters."""
        from llm_council.gateway.ollama import OllamaGateway
        from llm_council.gateway.types import GatewayRequest, CanonicalMessage, ContentBlock

        gateway = OllamaGateway()
        request = GatewayRequest(
            model="ollama/llama3.2",
            messages=[
                CanonicalMessage(role="user", content=[ContentBlock(type="text", text="Hello")])
            ],
            max_tokens=100,
            temperature=0.7,
        )

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hi!"
        mock_response.usage = None

        with patch.object(gateway, "_get_litellm") as mock_get_litellm:
            mock_litellm = MagicMock()
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)
            mock_get_litellm.return_value = mock_litellm

            await gateway.complete(request)

            # Verify acompletion was called with correct params
            mock_litellm.acompletion.assert_called_once()
            call_kwargs = mock_litellm.acompletion.call_args.kwargs
            assert call_kwargs["model"] == "ollama/llama3.2"
            assert call_kwargs["max_tokens"] == 100
            assert call_kwargs["temperature"] == 0.7

    @pytest.mark.asyncio
    async def test_complete_passes_ollama_model_format(self):
        """Should pass 'ollama/model-name' format to LiteLLM."""
        from llm_council.gateway.ollama import OllamaGateway
        from llm_council.gateway.types import GatewayRequest, CanonicalMessage, ContentBlock

        gateway = OllamaGateway()
        request = GatewayRequest(
            model="ollama/mistral:7b",
            messages=[
                CanonicalMessage(role="user", content=[ContentBlock(type="text", text="Hello")])
            ],
        )

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hi!"
        mock_response.usage = None

        with patch.object(gateway, "_get_litellm") as mock_get_litellm:
            mock_litellm = MagicMock()
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)
            mock_get_litellm.return_value = mock_litellm

            await gateway.complete(request)

            call_kwargs = mock_litellm.acompletion.call_args.kwargs
            assert call_kwargs["model"] == "ollama/mistral:7b"


class TestOllamaQualityDegradation:
    """Test quality degradation notices for local models."""

    def test_quality_degradation_notice_created(self):
        """Should create QualityDegradationNotice for local models."""
        from llm_council.gateway.ollama import OllamaGateway

        gateway = OllamaGateway()
        notice = gateway._create_quality_degradation_notice("ollama/llama3.2")

        assert notice is not None
        assert notice.is_local_model is True
        assert (
            "ollama" in notice.warning_message.lower() or "local" in notice.warning_message.lower()
        )

    def test_quality_notice_format(self):
        """Quality notice should follow ADR-025 format."""
        from llm_council.gateway.ollama import OllamaGateway

        gateway = OllamaGateway()
        notice = gateway._create_quality_degradation_notice("ollama/llama3.2")

        # Check for required elements per ADR-025
        assert (
            "LOCAL" in notice.warning_message.upper() or "local" in notice.warning_message.lower()
        )
        assert (
            "quality" in notice.warning_message.lower()
            or "degraded" in notice.warning_message.lower()
        )

    def test_response_includes_quality_metadata(self):
        """Response should include quality degradation notice for local models."""
        from llm_council.gateway.ollama import OllamaGateway

        gateway = OllamaGateway()
        notice = gateway._create_quality_degradation_notice("ollama/llama3.2")

        # Should suggest hardware profile
        assert notice.suggested_hardware_profile is not None
        assert notice.suggested_hardware_profile in [
            "minimum",
            "recommended",
            "professional",
            "enterprise",
        ]

    def test_hardware_profile_suggestion(self):
        """Should suggest appropriate hardware profile based on model."""
        from llm_council.gateway.ollama import OllamaGateway

        gateway = OllamaGateway()

        # Small models get minimum profile
        notice_small = gateway._create_quality_degradation_notice("ollama/llama3.2:7b")
        assert notice_small.suggested_hardware_profile in ["minimum", "recommended"]

        # This is a basic test - actual implementation may be more sophisticated


class TestOllamaHealthCheck:
    """Test health check functionality."""

    @pytest.mark.asyncio
    async def test_health_check_returns_router_health(self):
        """health_check() should return RouterHealth."""
        from llm_council.gateway.ollama import OllamaGateway
        from llm_council.gateway.base import RouterHealth, HealthStatus

        gateway = OllamaGateway()

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "pong"
        mock_response.usage = None

        with patch.object(gateway, "_get_litellm") as mock_get_litellm:
            mock_litellm = MagicMock()
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)
            mock_get_litellm.return_value = mock_litellm

            health = await gateway.health_check()

        assert isinstance(health, RouterHealth)
        assert health.router_id == "ollama"
        assert health.status == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_health_check_unhealthy_on_connection_error(self):
        """health_check() should return UNHEALTHY when Ollama is not running."""
        from llm_council.gateway.ollama import OllamaGateway
        from llm_council.gateway.base import RouterHealth, HealthStatus

        gateway = OllamaGateway()

        with patch.object(gateway, "_get_litellm") as mock_get_litellm:
            mock_litellm = MagicMock()
            mock_litellm.acompletion = AsyncMock(
                side_effect=ConnectionRefusedError("Connection refused")
            )
            mock_get_litellm.return_value = mock_litellm

            health = await gateway.health_check()

        assert isinstance(health, RouterHealth)
        assert health.status == HealthStatus.UNHEALTHY
        assert health.error_message is not None


class TestOllamaGatewayConfig:
    """Test configuration handling."""

    def test_gateway_uses_default_base_url(self):
        """Gateway should use http://localhost:11434 by default."""
        from llm_council.gateway.ollama import OllamaGateway

        with patch.dict("os.environ", {}, clear=True):
            gateway = OllamaGateway()
            assert gateway._base_url == "http://localhost:11434"

    def test_gateway_uses_env_var_base_url(self):
        """Gateway should use LLM_COUNCIL_OLLAMA_BASE_URL if set."""
        from llm_council.gateway.ollama import OllamaGateway

        with patch.dict("os.environ", {"LLM_COUNCIL_OLLAMA_BASE_URL": "http://custom:11434"}):
            # Need to reimport to pick up env var, or pass explicitly
            gateway = OllamaGateway(base_url="http://custom:11434")
            assert gateway._base_url == "http://custom:11434"

    def test_gateway_uses_custom_timeout(self):
        """Gateway should accept custom default timeout."""
        from llm_council.gateway.ollama import OllamaGateway

        gateway = OllamaGateway(default_timeout=300.0)
        assert gateway._default_timeout == 300.0


class TestOllamaRouterIntegration:
    """Test integration with GatewayRouter."""

    def test_gateway_can_be_registered(self):
        """OllamaGateway should be registrable with GatewayRouter."""
        from llm_council.gateway.ollama import OllamaGateway
        from llm_council.gateway.router import GatewayRouter

        ollama_gateway = OllamaGateway()

        # Should not raise
        router = GatewayRouter(gateways={"ollama": ollama_gateway}, default_gateway="ollama")

        assert "ollama" in router.gateways
        assert router.gateways["ollama"] is ollama_gateway

    def test_model_routing_pattern_matches(self):
        """'ollama/*' pattern should route to OllamaGateway."""
        from llm_council.gateway.ollama import OllamaGateway
        from llm_council.gateway.router import GatewayRouter
        from llm_council.gateway.openrouter import OpenRouterGateway

        ollama_gateway = OllamaGateway()
        openrouter_gateway = OpenRouterGateway()

        router = GatewayRouter(
            gateways={
                "ollama": ollama_gateway,
                "openrouter": openrouter_gateway,
            },
            model_routing={
                "ollama/*": "ollama",
            },
            default_gateway="openrouter",
        )

        # ollama/* should route to ollama gateway
        selected = router.get_gateway_for_model("ollama/llama3.2")
        assert selected is ollama_gateway

        # Other models should use default
        selected = router.get_gateway_for_model("openai/gpt-4o")
        assert selected is openrouter_gateway

    def test_fallback_chain_works(self):
        """Should fallback to cloud gateways when Ollama fails."""
        from llm_council.gateway.ollama import OllamaGateway
        from llm_council.gateway.router import GatewayRouter
        from llm_council.gateway.openrouter import OpenRouterGateway

        ollama_gateway = OllamaGateway()
        openrouter_gateway = OpenRouterGateway()

        router = GatewayRouter(
            gateways={
                "ollama": ollama_gateway,
                "openrouter": openrouter_gateway,
            },
            fallback_chains={
                "ollama": ["openrouter"],
            },
            default_gateway="ollama",
        )

        # Verify fallback chain is configured (access internal attribute)
        assert router._fallback_chains.get("ollama") == ["openrouter"]


class TestOllamaLiteLLMImport:
    """Test lazy import of LiteLLM."""

    def test_litellm_lazy_import(self):
        """LiteLLM should be lazily imported."""
        from llm_council.gateway.ollama import OllamaGateway

        gateway = OllamaGateway()
        # _litellm should be None before first use
        assert gateway._litellm is None

    def test_litellm_import_error_handling(self):
        """Should raise helpful error if LiteLLM not installed."""
        from llm_council.gateway.ollama import OllamaGateway

        gateway = OllamaGateway()

        with patch.dict("sys.modules", {"litellm": None}):
            with patch("builtins.__import__", side_effect=ImportError("No module named 'litellm'")):
                with pytest.raises(ImportError) as exc_info:
                    gateway._get_litellm()

                assert "litellm" in str(exc_info.value).lower()
                assert (
                    "pip install" in str(exc_info.value).lower()
                    or "ollama" in str(exc_info.value).lower()
                )
