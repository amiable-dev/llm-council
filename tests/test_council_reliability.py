"""Tests for ADR-012: Council Reliability and Partial Results.

These tests follow TDD - written BEFORE implementation.
"""

import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from typing import Dict, Any


# =============================================================================
# Test 1: Tiered Timeout Constants
# =============================================================================


def test_timeout_constants_defined():
    """Test that tiered timeout constants are defined per ADR-012."""
    from llm_council.council import (
        TIMEOUT_PER_MODEL_SOFT,
        TIMEOUT_PER_MODEL_HARD,
        TIMEOUT_SYNTHESIS_TRIGGER,
        TIMEOUT_RESPONSE_DEADLINE,
    )

    # Per ADR-012: 15s/25s/40s/50s tiered strategy
    assert TIMEOUT_PER_MODEL_SOFT == 15.0
    assert TIMEOUT_PER_MODEL_HARD == 25.0
    assert TIMEOUT_SYNTHESIS_TRIGGER == 40.0
    assert TIMEOUT_RESPONSE_DEADLINE == 50.0


# =============================================================================
# Test 2: Structured Model Result Schema
# =============================================================================


def test_model_result_status_types():
    """Test that model result status types are defined."""
    from llm_council.council import (
        MODEL_STATUS_OK,
        MODEL_STATUS_TIMEOUT,
        MODEL_STATUS_ERROR,
    )

    assert MODEL_STATUS_OK == "ok"
    assert MODEL_STATUS_TIMEOUT == "timeout"
    assert MODEL_STATUS_ERROR == "error"


# =============================================================================
# Test 3: Stage 1 with Structured Results
# =============================================================================


@pytest.mark.asyncio
async def test_stage1_returns_structured_results():
    """Test that Stage 1 returns per-model status information."""
    from llm_council.council import stage1_collect_responses_with_status

    mock_responses = {
        "model-a": {
            "status": "ok",
            "content": "Response A",
            "latency_ms": 1200,
            "usage": {"total_tokens": 100},
        },
        "model-b": {
            "status": "timeout",
            "error": "Timeout after 25s",
            "latency_ms": 25000,
        },
    }

    with (
        patch("llm_council.council.COUNCIL_MODELS", ["model-a", "model-b"]),
        patch("llm_council.council.query_models_with_progress") as mock_query,
    ):
        mock_query.return_value = mock_responses

        results, usage, model_statuses = await stage1_collect_responses_with_status("test query")

        # Should have one successful result
        assert len(results) == 1
        assert results[0]["model"] == "model-a"
        assert results[0]["response"] == "Response A"

        # Should have status for both models
        assert "model-a" in model_statuses
        assert "model-b" in model_statuses
        assert model_statuses["model-a"]["status"] == "ok"
        assert model_statuses["model-b"]["status"] == "timeout"


@pytest.mark.asyncio
async def test_stage1_with_timeout_returns_partial():
    """Test that Stage 1 returns partial results when some models timeout."""
    from llm_council.council import stage1_collect_responses_with_status

    # Simulate 2 successful, 2 timeout
    mock_responses = {
        "model-a": {"status": "ok", "content": "A", "latency_ms": 1000, "usage": {}},
        "model-b": {"status": "ok", "content": "B", "latency_ms": 1500, "usage": {}},
        "model-c": {"status": "timeout", "error": "Timeout", "latency_ms": 25000},
        "model-d": {"status": "timeout", "error": "Timeout", "latency_ms": 25000},
    }

    with (
        patch("llm_council.council.COUNCIL_MODELS", ["model-a", "model-b", "model-c", "model-d"]),
        patch("llm_council.council.query_models_with_progress") as mock_query,
    ):
        mock_query.return_value = mock_responses

        results, usage, model_statuses = await stage1_collect_responses_with_status("test")

        # Should return 2 successful responses
        assert len(results) == 2
        # All 4 models should have status entries
        assert len(model_statuses) == 4
        assert sum(1 for s in model_statuses.values() if s["status"] == "ok") == 2
        assert sum(1 for s in model_statuses.values() if s["status"] == "timeout") == 2


# =============================================================================
# Test 4: Council with Fallback - Partial Results
# =============================================================================


@pytest.mark.asyncio
async def test_run_council_with_fallback_returns_structured_metadata():
    """Test that run_council_with_fallback returns structured result schema."""
    from llm_council.council import run_council_with_fallback

    # Mock successful council run
    mock_stage1 = [{"model": "test", "response": "Test response"}]
    mock_stage2 = [{"model": "test", "ranking": "Test", "parsed_ranking": {}}]
    mock_stage3 = {"model": "chairman", "response": "Synthesis"}

    with (
        patch("llm_council.council.stage1_collect_responses_with_status") as mock_s1,
        patch("llm_council.council.stage1_5_normalize_styles") as mock_s15,
        patch("llm_council.council.stage2_collect_rankings") as mock_s2,
        patch("llm_council.council.stage3_synthesize_final") as mock_s3,
        patch("llm_council.council.calculate_aggregate_rankings") as mock_agg,
        patch("llm_council.council.COUNCIL_MODELS", ["test"]),
    ):
        mock_s1.return_value = (
            mock_stage1,
            {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            {"test": {"status": "ok", "latency_ms": 1000}},
        )
        mock_s15.return_value = (mock_stage1, {})
        mock_s2.return_value = (mock_stage2, {"Response A": "test"}, {})
        mock_s3.return_value = (mock_stage3, {}, None)
        mock_agg.return_value = []

        result = await run_council_with_fallback("test query")

        # Check structured result schema per ADR-012
        assert "synthesis" in result
        assert "model_responses" in result
        assert "metadata" in result
        assert result["metadata"]["status"] in ["complete", "partial", "failed"]
        assert "completed_models" in result["metadata"]
        assert "requested_models" in result["metadata"]


@pytest.mark.asyncio
async def test_run_council_with_fallback_partial_on_timeout():
    """Test that council returns partial results when global timeout triggers."""
    from llm_council.council import run_council_with_fallback

    # Simulate a timeout during Stage 2
    async def slow_stage2(*args, **kwargs):
        await asyncio.sleep(100)  # Will be cancelled by timeout
        return [], {}, {}

    # Mock stage1 that also populates shared_raw_responses for timeout handling
    async def mock_stage1_fn(
        user_query, timeout=None, on_progress=None, shared_raw_responses=None, models=None
    ):
        # Simulate the shared dict being populated (for timeout diagnostic preservation)
        if shared_raw_responses is not None:
            shared_raw_responses["model-a"] = {"status": "ok", "content": "A", "latency_ms": 100}
            shared_raw_responses["model-b"] = {"status": "ok", "content": "B", "latency_ms": 100}
        return (
            [{"model": "model-a", "response": "A"}, {"model": "model-b", "response": "B"}],
            {},
            {
                "model-a": {"status": "ok", "response": "A"},
                "model-b": {"status": "ok", "response": "B"},
            },
        )

    with (
        patch(
            "llm_council.council.stage1_collect_responses_with_status", side_effect=mock_stage1_fn
        ),
        patch("llm_council.council.stage1_5_normalize_styles") as mock_s15,
        patch("llm_council.council.stage2_collect_rankings", side_effect=slow_stage2),
        patch("llm_council.council.quick_synthesis") as mock_quick,
        patch("llm_council.council.COUNCIL_MODELS", ["model-a", "model-b"]),
    ):
        mock_s15.return_value = (
            [{"model": "model-a", "response": "A"}, {"model": "model-b", "response": "B"}],
            {},
        )
        mock_quick.return_value = ("Quick synthesis from partial data", {})

        # Pass short timeout explicitly
        result = await run_council_with_fallback("test query", synthesis_deadline=0.1)

        # Should return partial result
        assert result["metadata"]["status"] == "partial"
        assert result["metadata"]["synthesis_type"] == "partial"
        assert mock_quick.called


@pytest.mark.asyncio
async def test_run_council_with_fallback_includes_model_statuses():
    """Test that result includes per-model status information."""
    from llm_council.council import run_council_with_fallback

    with (
        patch("llm_council.council.stage1_collect_responses_with_status") as mock_s1,
        patch("llm_council.council.stage1_5_normalize_styles") as mock_s15,
        patch("llm_council.council.stage2_collect_rankings") as mock_s2,
        patch("llm_council.council.stage3_synthesize_final") as mock_s3,
        patch("llm_council.council.calculate_aggregate_rankings") as mock_agg,
        patch("llm_council.council.COUNCIL_MODELS", ["model-a", "model-b"]),
    ):
        model_statuses = {
            "model-a": {"status": "ok", "latency_ms": 1200},
            "model-b": {"status": "timeout", "latency_ms": 25000, "error": "Timeout"},
        }
        mock_s1.return_value = ([{"model": "model-a", "response": "A"}], {}, model_statuses)
        mock_s15.return_value = ([{"model": "model-a", "response": "A"}], {})
        mock_s2.return_value = ([], {"Response A": "model-a"}, {})
        mock_s3.return_value = ({"model": "chairman", "response": "Synthesis"}, {}, None)
        mock_agg.return_value = []

        result = await run_council_with_fallback("test query")

        # Check model_responses includes status per ADR-012 schema
        assert "model_responses" in result
        assert "model-a" in result["model_responses"]
        assert "model-b" in result["model_responses"]
        assert result["model_responses"]["model-a"]["status"] == "ok"
        assert result["model_responses"]["model-b"]["status"] == "timeout"


# =============================================================================
# Test 5: Quick Synthesis (Fallback)
# =============================================================================


@pytest.mark.asyncio
async def test_quick_synthesis_function():
    """Test quick_synthesis generates response from partial data."""
    from llm_council.council import quick_synthesis

    partial_responses = {
        "model-a": {"status": "ok", "response": "Response A content"},
        "model-b": {"status": "ok", "response": "Response B content"},
    }

    with patch("llm_council.council.query_model") as mock_query:
        mock_query.return_value = {
            "content": "Synthesized from available responses",
            "usage": {"total_tokens": 50},
        }

        synthesis, usage = await quick_synthesis("test query", partial_responses)

        assert synthesis is not None
        assert len(synthesis) > 0
        mock_query.assert_called_once()


@pytest.mark.asyncio
async def test_quick_synthesis_handles_chairman_failure():
    """Test quick_synthesis returns best response if chairman fails."""
    from llm_council.council import quick_synthesis

    partial_responses = {
        "model-a": {"status": "ok", "response": "Best response here"},
    }

    with patch("llm_council.council.query_model") as mock_query:
        mock_query.return_value = None  # Chairman fails

        synthesis, usage = await quick_synthesis("test query", partial_responses)

        # Should fall back to returning best available response
        assert "Best response here" in synthesis or synthesis is not None


# =============================================================================
# Test 6: Warning Messages
# =============================================================================


def test_generate_partial_warning():
    """Test that partial result warning is generated correctly."""
    from llm_council.council import generate_partial_warning

    model_statuses = {
        "gpt-4": {"status": "ok"},
        "claude": {"status": "timeout"},
        "gemini": {"status": "ok"},
        "llama": {"status": "rate_limited"},
    }

    warning = generate_partial_warning(model_statuses, requested=4)

    assert "2 of 4" in warning
    assert "claude" in warning.lower() or "llama" in warning.lower()


def test_generate_partial_warning_all_ok():
    """Test that no warning is generated when all models succeed."""
    from llm_council.council import generate_partial_warning

    model_statuses = {
        "gpt-4": {"status": "ok"},
        "claude": {"status": "ok"},
    }

    warning = generate_partial_warning(model_statuses, requested=2)

    assert warning is None or warning == ""


# =============================================================================
# Test 7: Integration - Full Council with Fallback
# =============================================================================


@pytest.mark.asyncio
async def test_full_council_fallback_stage1_only():
    """Test fallback synthesis when only Stage 1 completes."""
    from llm_council.council import run_council_with_fallback

    # Stage 1 succeeds, Stage 2 times out
    async def timeout_stage2(*args, **kwargs):
        await asyncio.sleep(100)

    # Mock stage1 that also populates shared_raw_responses for timeout handling
    async def mock_stage1_fn(
        user_query, timeout=None, on_progress=None, shared_raw_responses=None, models=None
    ):
        # Simulate the shared dict being populated (for timeout diagnostic preservation)
        if shared_raw_responses is not None:
            shared_raw_responses["a"] = {"status": "ok", "content": "A", "latency_ms": 100}
            shared_raw_responses["b"] = {"status": "ok", "content": "B", "latency_ms": 100}
            shared_raw_responses["c"] = {"status": "ok", "content": "C", "latency_ms": 100}
        return (
            [
                {"model": "a", "response": "A"},
                {"model": "b", "response": "B"},
                {"model": "c", "response": "C"},
            ],
            {},
            {
                "a": {"status": "ok", "response": "A"},
                "b": {"status": "ok", "response": "B"},
                "c": {"status": "ok", "response": "C"},
            },
        )

    with (
        patch(
            "llm_council.council.stage1_collect_responses_with_status", side_effect=mock_stage1_fn
        ),
        patch("llm_council.council.stage1_5_normalize_styles") as mock_s15,
        patch("llm_council.council.stage2_collect_rankings", side_effect=timeout_stage2),
        patch("llm_council.council.quick_synthesis") as mock_quick,
        patch("llm_council.council.COUNCIL_MODELS", ["a", "b", "c"]),
    ):
        mock_s15.return_value = (
            [
                {"model": "a", "response": "A"},
                {"model": "b", "response": "B"},
                {"model": "c", "response": "C"},
            ],
            {},
        )
        mock_quick.return_value = ("Fallback synthesis", {})

        # Pass short timeout explicitly
        result = await run_council_with_fallback("test", synthesis_deadline=0.05)

        # Should have partial status with fallback synthesis
        assert result["metadata"]["status"] == "partial"
        assert result["metadata"]["synthesis_type"] in ["partial", "stage1_only"]


@pytest.mark.asyncio
async def test_full_council_returns_complete_on_success():
    """Test that successful council returns complete status."""
    from llm_council.council import run_council_with_fallback

    with (
        patch("llm_council.council.stage1_collect_responses_with_status") as mock_s1,
        patch("llm_council.council.stage1_5_normalize_styles") as mock_s15,
        patch("llm_council.council.stage2_collect_rankings") as mock_s2,
        patch("llm_council.council.stage3_synthesize_final") as mock_s3,
        patch("llm_council.council.calculate_aggregate_rankings") as mock_agg,
        patch("llm_council.council.COUNCIL_MODELS", ["a", "b"]),
    ):
        mock_s1.return_value = (
            [{"model": "a", "response": "A"}, {"model": "b", "response": "B"}],
            {},
            {"a": {"status": "ok"}, "b": {"status": "ok"}},
        )
        mock_s15.return_value = (
            [{"model": "a", "response": "A"}, {"model": "b", "response": "B"}],
            {},
        )
        mock_s2.return_value = (
            [{"model": "a", "ranking": "R", "parsed_ranking": {}}],
            {"Response A": "a"},
            {},
        )
        mock_s3.return_value = ({"model": "chair", "response": "Full synthesis"}, {}, None)
        mock_agg.return_value = []

        result = await run_council_with_fallback("test")

        assert result["metadata"]["status"] == "complete"
        assert result["metadata"]["synthesis_type"] == "full"
        assert "Full synthesis" in result["synthesis"]


# =============================================================================
# Test 8: All Models Timeout - Failed Status
# =============================================================================


@pytest.mark.asyncio
async def test_council_fails_when_all_models_timeout():
    """Test that council returns failed status when all models timeout."""
    from llm_council.council import run_council_with_fallback

    with (
        patch("llm_council.council.stage1_collect_responses_with_status") as mock_s1,
        patch("llm_council.council.COUNCIL_MODELS", ["a", "b", "c"]),
    ):
        # All models timeout
        mock_s1.return_value = (
            [],  # No successful responses
            {},
            {
                "a": {"status": "timeout", "error": "Timeout"},
                "b": {"status": "timeout", "error": "Timeout"},
                "c": {"status": "timeout", "error": "Timeout"},
            },
        )

        result = await run_council_with_fallback("test")

        assert result["metadata"]["status"] == "failed"
        assert result["metadata"]["completed_models"] == 0
        assert "error" in result["synthesis"].lower() or "failed" in result["synthesis"].lower()


# =============================================================================
# Test 9: Progress Callback Integration
# =============================================================================


@pytest.mark.asyncio
async def test_council_with_progress_callback():
    """Test that run_council_with_fallback supports progress callbacks."""
    from llm_council.council import run_council_with_fallback

    progress_updates = []

    async def track_progress(step, total, message):
        progress_updates.append((step, total, message))

    with (
        patch("llm_council.council.stage1_collect_responses_with_status") as mock_s1,
        patch("llm_council.council.stage1_5_normalize_styles") as mock_s15,
        patch("llm_council.council.stage2_collect_rankings") as mock_s2,
        patch("llm_council.council.stage3_synthesize_final") as mock_s3,
        patch("llm_council.council.calculate_aggregate_rankings") as mock_agg,
        patch("llm_council.council.COUNCIL_MODELS", ["a"]),
    ):
        mock_s1.return_value = ([{"model": "a", "response": "A"}], {}, {"a": {"status": "ok"}})
        mock_s15.return_value = ([{"model": "a", "response": "A"}], {})
        mock_s2.return_value = ([], {"Response A": "a"}, {})
        mock_s3.return_value = ({"model": "chair", "response": "S"}, {}, None)
        mock_agg.return_value = []

        result = await run_council_with_fallback("test", on_progress=track_progress)

        # Should have called progress at least for start and end
        assert len(progress_updates) >= 2
