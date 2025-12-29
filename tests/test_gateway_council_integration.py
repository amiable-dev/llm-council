"""Tests for gateway layer integration with council (ADR-023 Issue #45).

TDD: Write these tests first, then implement the integration.

ADR-032: Updated to use gateway_adapter.USE_GATEWAY_LAYER instead of config.py.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestGatewayConfig:
    """Test gateway configuration options."""

    def test_gateway_enabled_config_exists(self):
        """Config should have USE_GATEWAY_LAYER option."""
        from llm_council.gateway_adapter import USE_GATEWAY_LAYER

        # Should be a boolean (default False for backward compatibility)
        assert isinstance(USE_GATEWAY_LAYER, bool)

    def test_gateway_enabled_default_false(self):
        """Gateway should be disabled by default for backward compatibility."""
        from llm_council.gateway_adapter import USE_GATEWAY_LAYER

        # Default should be False for backward compatibility
        # (unless explicitly enabled via config)
        assert USE_GATEWAY_LAYER is False


class TestGatewayAdapter:
    """Test gateway adapter module."""

    def test_adapter_provides_query_model_interface(self):
        """Adapter should provide query_model function."""
        from llm_council.gateway_adapter import query_model

        assert callable(query_model)

    def test_adapter_provides_query_models_parallel_interface(self):
        """Adapter should provide query_models_parallel function."""
        from llm_council.gateway_adapter import query_models_parallel

        assert callable(query_models_parallel)

    def test_adapter_provides_query_models_with_progress_interface(self):
        """Adapter should provide query_models_with_progress function."""
        from llm_council.gateway_adapter import query_models_with_progress

        assert callable(query_models_with_progress)

    def test_adapter_provides_status_constants(self):
        """Adapter should provide status constants."""
        from llm_council.gateway_adapter import (
            STATUS_OK,
            STATUS_TIMEOUT,
            STATUS_RATE_LIMITED,
            STATUS_AUTH_ERROR,
            STATUS_ERROR,
        )

        assert STATUS_OK == "ok"
        assert STATUS_TIMEOUT == "timeout"
        assert STATUS_RATE_LIMITED == "rate_limited"
        assert STATUS_AUTH_ERROR == "auth_error"
        assert STATUS_ERROR == "error"


class TestAdapterGatewayEnabled:
    """Test adapter behavior when gateway is enabled."""

    @pytest.mark.asyncio
    async def test_query_model_uses_gateway_when_enabled(self):
        """query_model should use gateway layer when enabled."""
        from llm_council.gateway.types import GatewayResponse

        with patch("llm_council.gateway_adapter.USE_GATEWAY_LAYER", True):
            with patch("llm_council.gateway_adapter._gateway_router") as mock_router:
                mock_response = GatewayResponse(
                    content="Hello from gateway",
                    model="openai/gpt-4o",
                    status="ok",
                    latency_ms=100,
                )
                mock_router.complete = AsyncMock(return_value=mock_response)

                from llm_council.gateway_adapter import query_model

                result = await query_model("openai/gpt-4o", [{"role": "user", "content": "Hello"}])

                assert result is not None
                assert result["content"] == "Hello from gateway"


class TestAdapterGatewayDisabled:
    """Test adapter behavior when gateway is disabled (default)."""

    @pytest.mark.asyncio
    async def test_query_model_uses_openrouter_when_disabled(self):
        """query_model should use direct openrouter when disabled."""
        with patch("llm_council.gateway_adapter.USE_GATEWAY_LAYER", False):
            with patch("llm_council.gateway_adapter._direct_query_model") as mock_direct:
                mock_direct.return_value = {"content": "Hello from openrouter"}

                from llm_council.gateway_adapter import query_model

                result = await query_model("openai/gpt-4o", [{"role": "user", "content": "Hello"}])

                mock_direct.assert_called_once()


class TestCouncilGatewayIntegration:
    """Test council using gateway adapter."""

    def test_council_imports_from_adapter(self):
        """Council should be able to import from gateway_adapter."""
        # This just verifies the adapter module is importable
        from llm_council.gateway_adapter import (
            query_model,
            query_models_parallel,
            query_models_with_progress,
            STATUS_OK,
        )

        # All should be callable or strings
        assert callable(query_model)
        assert callable(query_models_parallel)
        assert callable(query_models_with_progress)
        assert STATUS_OK == "ok"
