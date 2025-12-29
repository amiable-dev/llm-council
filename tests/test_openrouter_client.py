"""TDD tests for ADR-026: OpenRouter API Client.

Tests for the OpenRouter Models API client that fetches model metadata.

VCR cassettes are used for happy-path tests that make real HTTP calls.
Mocks are retained for error handling tests (timeout, connection error, rate limit).
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


class TestOpenRouterClient:
    """Test OpenRouterClient API interactions."""

    @pytest.mark.asyncio
    @pytest.mark.vcr()
    async def test_fetch_models_returns_model_list(self):
        """fetch_models() should return list of ModelInfo."""
        from llm_council.metadata.openrouter_client import OpenRouterClient
        from llm_council.metadata.types import ModelInfo

        client = OpenRouterClient(api_key="test-key")
        models = await client.fetch_models()

        assert len(models) == 1
        assert isinstance(models[0], ModelInfo)
        assert models[0].id == "openai/gpt-4o"
        assert models[0].context_window == 128000

    @pytest.mark.asyncio
    @pytest.mark.vcr()
    async def test_fetch_models_extracts_pricing_correctly(self):
        """Pricing should be converted from string to float."""
        from llm_council.metadata.openrouter_client import OpenRouterClient

        client = OpenRouterClient(api_key="test-key")
        models = await client.fetch_models()

        assert models[0].pricing == {"prompt": 0.0025, "completion": 0.01}

    @pytest.mark.asyncio
    @pytest.mark.vcr()
    async def test_fetch_models_extracts_modalities(self):
        """Modalities should be extracted from architecture."""
        from llm_council.metadata.openrouter_client import OpenRouterClient

        client = OpenRouterClient(api_key="test-key")
        models = await client.fetch_models()

        assert "text" in models[0].modalities
        # Image should be normalized to vision
        assert "vision" in models[0].modalities

    @pytest.mark.asyncio
    async def test_fetch_models_handles_timeout(self):
        """Should return empty list on timeout."""
        from llm_council.metadata.openrouter_client import OpenRouterClient

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client_instance

            client = OpenRouterClient()
            models = await client.fetch_models()

            assert models == []

    @pytest.mark.asyncio
    async def test_fetch_models_handles_connection_error(self):
        """Should return empty list on connection error."""
        from llm_council.metadata.openrouter_client import OpenRouterClient

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(
                side_effect=httpx.ConnectError("Connection failed")
            )
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client_instance

            client = OpenRouterClient()
            models = await client.fetch_models()

            assert models == []

    @pytest.mark.asyncio
    async def test_fetch_models_handles_rate_limit(self):
        """Should return empty list on 429 rate limit."""
        from llm_council.metadata.openrouter_client import OpenRouterClient

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_instance = AsyncMock()
            mock_response_obj = MagicMock()
            mock_response_obj.status_code = 429
            mock_request = MagicMock()
            mock_response_obj.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Rate Limited", request=mock_request, response=mock_response_obj
            )
            mock_client_instance.get = AsyncMock(return_value=mock_response_obj)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client_instance

            client = OpenRouterClient()
            models = await client.fetch_models()

            assert models == []

    @pytest.mark.asyncio
    async def test_client_uses_api_key_when_provided(self):
        """Should include Authorization header when API key present."""
        from llm_council.metadata.openrouter_client import OpenRouterClient

        mock_response = {"data": []}

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_instance = AsyncMock()
            mock_response_obj = MagicMock()
            mock_response_obj.status_code = 200
            mock_response_obj.json.return_value = mock_response
            mock_response_obj.raise_for_status = MagicMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response_obj)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client_instance

            client = OpenRouterClient(api_key="test-api-key")
            await client.fetch_models()

            # Check that get was called with headers containing Authorization
            call_args = mock_client_instance.get.call_args
            headers = call_args.kwargs.get("headers", {})
            assert headers.get("Authorization") == "Bearer test-api-key"

    @pytest.mark.asyncio
    async def test_client_uses_correct_endpoint(self):
        """Should call the correct OpenRouter API endpoint."""
        from llm_council.metadata.openrouter_client import OpenRouterClient

        mock_response = {"data": []}

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_instance = AsyncMock()
            mock_response_obj = MagicMock()
            mock_response_obj.status_code = 200
            mock_response_obj.json.return_value = mock_response
            mock_response_obj.raise_for_status = MagicMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response_obj)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client_instance

            client = OpenRouterClient()
            await client.fetch_models()

            call_args = mock_client_instance.get.call_args
            assert call_args.args[0] == "https://openrouter.ai/api/v1/models"


class TestModelInfoTransform:
    """Test transformation from API response to ModelInfo."""

    def test_transform_detects_reasoning_from_parameters(self):
        """Reasoning support should be detected from supported_parameters."""
        from llm_council.metadata.openrouter_client import transform_api_model

        api_model = {
            "id": "openai/o1",
            "context_length": 200000,
            "supported_parameters": ["reasoning"],
        }

        info = transform_api_model(api_model)
        assert "reasoning" in info.supported_parameters

    def test_transform_assigns_quality_tier_frontier(self):
        """High-priced models should get frontier tier."""
        from llm_council.metadata.openrouter_client import transform_api_model
        from llm_council.metadata.types import QualityTier

        api_model = {
            "id": "openai/gpt-4o",
            "context_length": 128000,
            "pricing": {"prompt": "0.015", "completion": "0.075"},
        }

        info = transform_api_model(api_model)
        assert info.quality_tier == QualityTier.FRONTIER

    def test_transform_assigns_quality_tier_standard(self):
        """Medium-priced models should get standard tier."""
        from llm_council.metadata.openrouter_client import transform_api_model
        from llm_council.metadata.types import QualityTier

        api_model = {
            "id": "openai/gpt-4o",
            "context_length": 128000,
            "pricing": {"prompt": "0.002", "completion": "0.008"},
        }

        info = transform_api_model(api_model)
        assert info.quality_tier == QualityTier.STANDARD

    def test_transform_assigns_quality_tier_economy(self):
        """Low-priced models should get economy tier."""
        from llm_council.metadata.openrouter_client import transform_api_model
        from llm_council.metadata.types import QualityTier

        api_model = {
            "id": "openai/gpt-4o-mini",
            "context_length": 128000,
            "pricing": {"prompt": "0.00015", "completion": "0.0006"},
        }

        info = transform_api_model(api_model)
        assert info.quality_tier == QualityTier.ECONOMY

    def test_transform_handles_missing_fields_gracefully(self):
        """Should use defaults for missing optional fields."""
        from llm_council.metadata.openrouter_client import transform_api_model

        api_model = {
            "id": "test/model",
            "context_length": 4096,
            # No pricing, modalities, or parameters
        }

        info = transform_api_model(api_model)
        assert info.id == "test/model"
        assert info.context_window == 4096
        assert info.pricing == {}
        assert info.modalities == ["text"]

    def test_transform_normalizes_image_to_vision(self):
        """'image' modality should be normalized to 'vision'."""
        from llm_council.metadata.openrouter_client import transform_api_model

        api_model = {
            "id": "test/model",
            "context_length": 4096,
            "architecture": {"input_modalities": ["text", "image"]},
        }

        info = transform_api_model(api_model)
        assert "vision" in info.modalities
        assert "image" not in info.modalities

    def test_transform_handles_zero_pricing(self):
        """Zero pricing (free models) should work correctly."""
        from llm_council.metadata.openrouter_client import transform_api_model
        from llm_council.metadata.types import QualityTier

        api_model = {
            "id": "ollama/llama3.2",
            "context_length": 128000,
            "pricing": {"prompt": "0", "completion": "0"},
        }

        info = transform_api_model(api_model)
        assert info.pricing == {"prompt": 0.0, "completion": 0.0}
        # Free models get LOCAL tier
        assert info.quality_tier == QualityTier.LOCAL

    def test_transform_preserves_all_supported_parameters(self):
        """All supported_parameters should be preserved."""
        from llm_council.metadata.openrouter_client import transform_api_model

        api_model = {
            "id": "test/model",
            "context_length": 4096,
            "supported_parameters": ["temperature", "top_p", "tools", "reasoning"],
        }

        info = transform_api_model(api_model)
        assert info.supported_parameters == ["temperature", "top_p", "tools", "reasoning"]


class TestOpenRouterClientConfiguration:
    """Test client configuration options."""

    def test_client_has_default_timeout(self):
        """Client should have a default timeout."""
        from llm_council.metadata.openrouter_client import OpenRouterClient

        client = OpenRouterClient()
        assert client.timeout > 0

    def test_client_timeout_is_configurable(self):
        """Client timeout should be configurable."""
        from llm_council.metadata.openrouter_client import OpenRouterClient

        client = OpenRouterClient(timeout=60.0)
        assert client.timeout == 60.0

    def test_client_reads_api_key_from_env(self):
        """Client should read API key from environment if not provided."""
        from llm_council.metadata.openrouter_client import OpenRouterClient

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "env-api-key"}):
            client = OpenRouterClient()
            assert client.api_key == "env-api-key"

    def test_client_explicit_api_key_overrides_env(self):
        """Explicit API key should override environment variable."""
        from llm_council.metadata.openrouter_client import OpenRouterClient

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "env-api-key"}):
            client = OpenRouterClient(api_key="explicit-key")
            assert client.api_key == "explicit-key"
