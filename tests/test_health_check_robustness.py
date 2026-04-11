"""Tests for council_health_check robustness and fallback logic (ADR-039)."""

import json
import pytest
from unittest.mock import AsyncMock, patch
from llm_council.mcp_server import council_health_check
from llm_council.openrouter import STATUS_OK, STATUS_AUTH_ERROR
from llm_council.council import CHAIRMAN_MODEL

@pytest.mark.asyncio
async def test_council_health_check_403_fallback_success():
    """Test health check when chairman fails with 403 but fallback succeeds (ADR-039)."""
    
    async def mock_query_with_status(model, *args, **kwargs):
        if model == CHAIRMAN_MODEL:
            return {
                "status": STATUS_AUTH_ERROR,
                "error": "Authentication failed for model: 403",
                "latency_ms": 50,
            }
        elif model == "openai/gpt-4o-mini":
            return {
                "status": STATUS_OK,
                "latency_ms": 100,
            }
        return {"status": "error", "error": f"Unexpected model: {model}"}

    with (
        patch("llm_council.mcp_server.get_api_key", return_value="test-key"),
        patch("llm_council.mcp_server.query_model_with_status", side_effect=mock_query_with_status),
    ):
        result = await council_health_check()
        data = json.loads(result)

        assert data["ready"] is True
        assert "ready_warning" in data
        assert CHAIRMAN_MODEL in data["ready_warning"]
        assert "403" in data["ready_warning"]
        assert data["api_connectivity"]["test_model"] == "openai/gpt-4o-mini"
        assert "API Key Valid" in data["message"]

@pytest.mark.asyncio
async def test_council_health_check_403_fallback_failure():
    """Test health check when both chairman and fallback fail with 403."""
    
    mock_response = {
        "status": STATUS_AUTH_ERROR,
        "error": "Authentication failed for model: 403",
        "latency_ms": 50,
    }

    with (
        patch("llm_council.mcp_server.get_api_key", return_value="test-key"),
        patch("llm_council.mcp_server.query_model_with_status", return_value=mock_response),
    ):
        result = await council_health_check()
        data = json.loads(result)

        assert data["ready"] is False
        assert data["api_connectivity"]["status"] == STATUS_AUTH_ERROR
        assert "connectivity issue" in data["message"].lower()

@pytest.mark.asyncio
async def test_council_health_check_direct_success():
    """Test health check when chairman succeeds directly."""
    
    mock_response = {
        "status": STATUS_OK,
        "latency_ms": 150,
    }

    with (
        patch("llm_council.mcp_server.get_api_key", return_value="test-key"),
        patch("llm_council.mcp_server.query_model_with_status", return_value=mock_response),
    ):
        result = await council_health_check()
        data = json.loads(result)

        assert data["ready"] is True
        assert data["api_connectivity"]["test_model"] == CHAIRMAN_MODEL
        assert "ready_warning" not in data
        assert "Council is ready" in data["message"]
