import pytest
import json
from unittest.mock import patch, MagicMock
from llm_council.mcp_server import council_health_check

@pytest.mark.asyncio
async def test_health_check_dual_403_warning():
    """Verify that a double 403 Forbidden returns a critical warning (Refs #44)."""
    
    # Mock status_ok and status_auth_error correctly based on provider return types
    # Our internal provider returns a dict with "status": "auth_error" for 403
    
    mock_response = {
        "status": "auth_error",
        "error": "Authentication failed for model: 403",
        "latency_ms": 100
    }
    
    with patch("llm_council.mcp_server.query_model_with_status", return_value=mock_response), \
         patch("llm_council.mcp_server._get_openrouter_api_key", return_value="fake-key"), \
         patch("httpx.AsyncClient.get") as mock_get:
        
        # Mock the credits API to also return 403
        mock_get.return_value = MagicMock(status_code=403)
        
        result_json = await council_health_check()
        result = json.loads(result_json)
        
        # 1. Ready should be False
        assert result["ready"] is False
        
        # 2. Ready warning should contain the Critical message
        assert "Critical: Both chairman" in result["ready_warning"]
        assert "returned 403" in result["ready_warning"]
        
        # 3. Credits should show the error code
        assert result["account_credits"] == "Error: 403"

@pytest.mark.asyncio
async def test_health_check_success_with_credits():
    """Verify that a successful check displays credits (Refs #44)."""
    
    mock_success = {
        "status": "ok",
        "content": "pong",
        "latency_ms": 100
    }
    
    with patch("llm_council.mcp_server.query_model_with_status", return_value=mock_success), \
         patch("llm_council.mcp_server._get_openrouter_api_key", return_value="fake-key"), \
         patch("httpx.AsyncClient.get") as mock_get:
        
        # Mock the credits API to return success
        mock_data = {"data": {"total_credits": 25.50}}
        mock_get.return_value = MagicMock(status_code=200, json=lambda: mock_data)
        
        result_json = await council_health_check()
        result = json.loads(result_json)
        
        assert result["ready"] is True
        assert result["account_credits"] == "$25.50"
