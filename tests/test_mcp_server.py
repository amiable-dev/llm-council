"""Tests for llm_council_mcp MCP server."""
from unittest.mock import AsyncMock, patch
import pytest


def test_mcp_server_imports():
    """Test that MCP server can be imported."""
    from llm_council_mcp import mcp_server
    assert hasattr(mcp_server, 'mcp')
    assert hasattr(mcp_server, 'consult_council')
    assert hasattr(mcp_server, 'main')


def test_main_entry_point_exists():
    """Test that main() entry point is defined."""
    from llm_council_mcp.mcp_server import main
    assert callable(main)


@pytest.mark.asyncio
async def test_consult_council_tool():
    """Test that consult_council tool is properly defined."""
    from llm_council_mcp.mcp_server import consult_council
    
    # Mock the run_full_council function
    mock_stage1 = [{"model": "test-model", "response": "Test response"}]
    mock_stage2 = [{"model": "test-model", "ranking": "Test ranking", "parsed_ranking": []}]
    mock_stage3 = {"model": "chairman", "response": "Synthesized response"}
    mock_metadata = {"label_to_model": {}, "aggregate_rankings": []}
    
    with patch('llm_council_mcp.mcp_server.run_full_council') as mock_council:
        mock_council.return_value = (mock_stage1, mock_stage2, mock_stage3, mock_metadata)
        
        result = await consult_council("test query", include_details=False)
        
        assert "Synthesized response" in result
        assert "### Chairman's Synthesis" in result


@pytest.mark.asyncio
async def test_consult_council_with_details():
    """Test consult_council with include_details=True."""
    from llm_council_mcp.mcp_server import consult_council
    
    mock_stage1 = [{"model": "test-model", "response": "Test response"}]
    mock_stage2 = [{"model": "test-model", "ranking": "Test ranking", "parsed_ranking": []}]
    mock_stage3 = {"model": "chairman", "response": "Synthesized response"}
    mock_metadata = {"label_to_model": {}, "aggregate_rankings": []}
    
    with patch('llm_council_mcp.mcp_server.run_full_council') as mock_council:
        mock_council.return_value = (mock_stage1, mock_stage2, mock_stage3, mock_metadata)
        
        result = await consult_council("test query", include_details=True)
        
        assert "### Chairman's Synthesis" in result
        assert "### Council Details" in result
        assert "Stage 1: Individual Opinions" in result
        assert "Stage 2: Peer Review" in result
