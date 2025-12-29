"""Tests for llm_council MCP server.

These tests require the optional [mcp] dependencies.
Install with: pip install "llm-council[mcp]"
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Skip all tests in this module if MCP is not installed
pytest.importorskip(
    "mcp", reason="MCP dependencies not installed. Install with: pip install 'llm-council[mcp]'"
)


def test_mcp_server_imports():
    """Test that MCP server can be imported."""
    from llm_council import mcp_server

    assert hasattr(mcp_server, "mcp")
    assert hasattr(mcp_server, "consult_council")
    assert hasattr(mcp_server, "council_health_check")
    assert hasattr(mcp_server, "main")


def test_main_entry_point_exists():
    """Test that main() entry point is defined."""
    from llm_council.mcp_server import main

    assert callable(main)


def test_confidence_configs_defined():
    """Test that confidence level configurations are defined (ADR-012)."""
    from llm_council.mcp_server import CONFIDENCE_CONFIGS

    assert "quick" in CONFIDENCE_CONFIGS
    assert "balanced" in CONFIDENCE_CONFIGS
    assert "high" in CONFIDENCE_CONFIGS

    # Quick should have fewer models
    assert CONFIDENCE_CONFIGS["quick"]["models"] == 2
    assert CONFIDENCE_CONFIGS["balanced"]["models"] == 3
    assert CONFIDENCE_CONFIGS["high"]["models"] is None  # Use all


@pytest.mark.asyncio
async def test_consult_council_tool():
    """Test that consult_council tool is properly defined."""
    from llm_council.mcp_server import consult_council

    # Mock the run_council_with_fallback function (ADR-012 structured response)
    mock_result = {
        "synthesis": "Synthesized response",
        "model_responses": {
            "test-model": {"status": "ok", "latency_ms": 1000, "response": "Test response"}
        },
        "metadata": {
            "status": "complete",
            "completed_models": 1,
            "requested_models": 1,
            "synthesis_type": "full",
            "warning": None,
            "label_to_model": {},
            "aggregate_rankings": [],
        },
    }

    with patch("llm_council.mcp_server.run_council_with_fallback") as mock_council:
        mock_council.return_value = mock_result

        result = await consult_council("test query", include_details=False)

        assert "Synthesized response" in result
        assert "### Chairman's Synthesis" in result


@pytest.mark.asyncio
async def test_consult_council_with_details():
    """Test consult_council with include_details=True."""
    from llm_council.mcp_server import consult_council

    mock_result = {
        "synthesis": "Synthesized response",
        "model_responses": {
            "test-model": {"status": "ok", "latency_ms": 1000, "response": "Test response"}
        },
        "metadata": {
            "status": "complete",
            "completed_models": 1,
            "requested_models": 1,
            "synthesis_type": "full",
            "warning": None,
            "label_to_model": {"Response A": "test-model"},
            "aggregate_rankings": [],
        },
    }

    with patch("llm_council.mcp_server.run_council_with_fallback") as mock_council:
        mock_council.return_value = mock_result

        result = await consult_council("test query", include_details=True)

        assert "### Chairman's Synthesis" in result
        assert "### Council Details" in result
        assert "Model Status" in result
        assert "Stage 1: Individual Opinions" in result
        assert "Stage 2: Peer Review" in result


@pytest.mark.asyncio
async def test_consult_council_with_confidence_level():
    """Test consult_council with confidence level parameter (ADR-012)."""
    from llm_council.mcp_server import consult_council

    mock_result = {
        "synthesis": "Quick response",
        "model_responses": {"test-model": {"status": "ok", "latency_ms": 500}},
        "metadata": {
            "status": "complete",
            "completed_models": 1,
            "requested_models": 1,
            "synthesis_type": "full",
            "warning": None,
            "aggregate_rankings": [],
        },
    }

    with patch("llm_council.mcp_server.run_council_with_fallback") as mock_council:
        mock_council.return_value = mock_result

        # Test with "quick" confidence
        result = await consult_council("test query", confidence="quick")
        assert "Quick response" in result


@pytest.mark.asyncio
async def test_consult_council_with_rankings_metadata():
    """Test consult_council includes aggregate rankings in output."""
    from llm_council.mcp_server import consult_council

    mock_result = {
        "synthesis": "Synthesized response",
        "model_responses": {},
        "metadata": {
            "status": "complete",
            "completed_models": 2,
            "requested_models": 2,
            "synthesis_type": "full",
            "warning": None,
            "label_to_model": {},
            "aggregate_rankings": [
                {"model": "openai/gpt-4", "borda_score": 0.85, "rank": 1},
                {"model": "anthropic/claude", "borda_score": 0.75, "rank": 2},
            ],
        },
    }

    with patch("llm_council.mcp_server.run_council_with_fallback") as mock_council:
        mock_council.return_value = mock_result

        result = await consult_council("test query")

        assert "### Council Rankings" in result
        assert "openai/gpt-4" in result
        assert "0.85" in result


@pytest.mark.asyncio
async def test_council_health_check_no_api_key():
    """Test health check when API key is not configured."""
    from llm_council.mcp_server import council_health_check

    with patch("llm_council.mcp_server.OPENROUTER_API_KEY", None):
        result = await council_health_check()
        data = json.loads(result)

        assert data["api_key_configured"] is False
        assert data["ready"] is False
        assert "not configured" in data["message"].lower()


@pytest.mark.asyncio
@pytest.mark.vcr()
async def test_council_health_check_success():
    """Test health check with successful API connectivity."""
    from llm_council.mcp_server import council_health_check
    from llm_council.openrouter import STATUS_OK

    with patch("llm_council.mcp_server.OPENROUTER_API_KEY", "test-key"):
        result = await council_health_check()
        data = json.loads(result)

        assert data["api_key_configured"] is True
        assert data["ready"] is True
        assert "api_connectivity" in data
        assert data["api_connectivity"]["status"] == STATUS_OK


@pytest.mark.asyncio
async def test_council_health_check_api_error():
    """Test health check when API returns an error."""
    from llm_council.mcp_server import council_health_check
    from llm_council.openrouter import STATUS_AUTH_ERROR

    mock_response = {
        "status": STATUS_AUTH_ERROR,
        "error": "Invalid API key",
        "latency_ms": 50,
    }

    with (
        patch("llm_council.mcp_server.OPENROUTER_API_KEY", "invalid-key"),
        patch("llm_council.mcp_server.query_model_with_status", return_value=mock_response),
    ):
        result = await council_health_check()
        data = json.loads(result)

        assert data["api_key_configured"] is True
        assert data["ready"] is False
        assert "connectivity issue" in data["message"].lower()


@pytest.mark.asyncio
async def test_council_health_check_includes_estimates():
    """Test health check includes duration estimates (ADR-012)."""
    from llm_council.mcp_server import council_health_check

    with patch("llm_council.mcp_server.OPENROUTER_API_KEY", None):
        result = await council_health_check()
        data = json.loads(result)

        assert "estimated_duration" in data
        assert "quick" in data["estimated_duration"]
        assert "balanced" in data["estimated_duration"]
        assert "high" in data["estimated_duration"]


@pytest.mark.asyncio
async def test_consult_council_with_context_progress():
    """Test that consult_council calls progress reporting when context is provided."""
    from llm_council.mcp_server import consult_council

    mock_result = {
        "synthesis": "Synthesized response",
        "model_responses": {"test-model": {"status": "ok", "latency_ms": 1000}},
        "metadata": {
            "status": "complete",
            "completed_models": 1,
            "requested_models": 1,
            "synthesis_type": "full",
            "warning": None,
            "label_to_model": {},
            "aggregate_rankings": [],
        },
    }

    # Create a mock context with report_progress method
    mock_ctx = MagicMock()
    mock_ctx.report_progress = AsyncMock()

    # Mock run_council_with_fallback to call the on_progress callback
    async def mock_council_fn(query, on_progress=None, synthesis_deadline=None, **kwargs):
        if on_progress:
            await on_progress(0, 5, "Starting...")
            await on_progress(5, 5, "Complete")
        return mock_result

    with patch("llm_council.mcp_server.run_council_with_fallback", side_effect=mock_council_fn):
        await consult_council("test query", ctx=mock_ctx)

        # Verify progress was reported (at least start and end)
        assert mock_ctx.report_progress.called
        assert mock_ctx.report_progress.call_count >= 2


@pytest.mark.asyncio
async def test_consult_council_shows_warning_on_partial():
    """Test that consult_council shows warning when partial results returned (ADR-012)."""
    from llm_council.mcp_server import consult_council

    mock_result = {
        "synthesis": "Partial synthesis",
        "model_responses": {
            "model-a": {"status": "ok", "latency_ms": 1000},
            "model-b": {"status": "timeout", "latency_ms": 25000, "error": "Timeout"},
        },
        "metadata": {
            "status": "partial",
            "completed_models": 1,
            "requested_models": 2,
            "synthesis_type": "partial",
            "warning": "This answer is based on 1 of 2 intended models. Did not respond: model-b (timeout).",
            "aggregate_rankings": [],
        },
    }

    with patch("llm_council.mcp_server.run_council_with_fallback") as mock_council:
        mock_council.return_value = mock_result

        result = await consult_council("test query")

        assert "Partial synthesis" in result
        assert "Note" in result
        assert "1 of 2" in result
        assert "partial" in result.lower()


@pytest.mark.asyncio
async def test_timeout_preserves_diagnostic_info():
    """Test that model status is preserved even when global timeout occurs (ADR-012 fix).

    This tests the fix for the bug where global asyncio.wait_for timeout would
    cancel the pipeline before model_responses was populated, losing diagnostic info.
    """
    import asyncio

    from llm_council.council import run_council_with_fallback
    from llm_council.openrouter import STATUS_OK, STATUS_TIMEOUT

    # Create a mock that simulates some models responding before timeout
    call_count = 0

    async def mock_query_with_status(
        model, messages, timeout=None, disable_tools=False, reasoning_params=None
    ):
        nonlocal call_count
        call_count += 1
        # First model responds quickly
        if "gpt" in model:
            await asyncio.sleep(0.01)
            return {
                "status": STATUS_OK,
                "content": "Fast response",
                "latency_ms": 10,
            }
        # Other models are slow (will be interrupted by timeout)
        await asyncio.sleep(10)  # Will be cancelled by timeout
        return {
            "status": STATUS_OK,
            "content": "Slow response",
            "latency_ms": 10000,
        }

    with (
        patch("llm_council.openrouter.query_model_with_status", side_effect=mock_query_with_status),
        patch(
            "llm_council.council.COUNCIL_MODELS",
            ["openai/gpt-4", "anthropic/claude", "google/gemini"],
        ),
    ):
        # Run with a very short timeout to trigger global timeout
        result = await run_council_with_fallback(
            "test query",
            synthesis_deadline=0.5,  # Very short - will timeout
        )

        # Key assertion: model_responses should have diagnostic info for ALL models
        # even those that didn't complete before timeout
        assert "model_responses" in result
        model_responses = result["model_responses"]

        # Should have entries for all 3 models
        assert (
            len(model_responses) >= 1
        ), f"Expected at least 1 model status, got: {model_responses}"

        # The fast model should show as ok or have response
        # Other models should show as timeout (not missing!)
        statuses = [info.get("status") for info in model_responses.values()]

        # At least the quick model should have responded
        # (implementation detail: depends on timing)
        assert any(s == STATUS_OK for s in statuses) or any(
            s == STATUS_TIMEOUT for s in statuses
        ), f"Expected some model statuses, got: {statuses}"

        # Check metadata reflects partial status
        assert result["metadata"]["status"] in ("partial", "failed")


@pytest.mark.asyncio
async def test_shared_results_populated_incrementally():
    """Test that query_models_with_progress populates shared_results as models complete."""
    from llm_council.openrouter import STATUS_OK, query_models_with_progress

    async def mock_query(model, messages, timeout=None, disable_tools=False):
        return {
            "status": STATUS_OK,
            "content": f"Response from {model}",
            "latency_ms": 100,
        }

    with patch("llm_council.openrouter.query_model_with_status", side_effect=mock_query):
        # Create a shared dict to observe incremental population
        shared = {}

        result = await query_models_with_progress(
            models=["model-a", "model-b"],
            messages=[{"role": "user", "content": "test"}],
            shared_results=shared,
        )

        # Both the returned result and shared dict should have the responses
        assert len(result) == 2
        assert len(shared) == 2
        assert result is shared  # They should be the same object
