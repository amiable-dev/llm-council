"""Tests for ADR-012: Council Reliability and Partial Results."""

import pytest
import asyncio
from unittest.mock import patch, AsyncMock
from typing import Dict, Any


def test_timeout_constants_defined():
    from llm_council.council import TIMEOUT_PER_MODEL_SOFT

    assert TIMEOUT_PER_MODEL_SOFT == 15.0


def test_model_result_status_types():
    from llm_council.council import MODEL_STATUS_OK

    assert MODEL_STATUS_OK == "ok"


@pytest.mark.asyncio
async def test_stage1_returns_structured_results():
    from llm_council.council import stage1_collect_responses_with_status

    mock_responses = {
        "model-a": {
            "status": "ok",
            "content": "Response A",
            "latency_ms": 1200,
            "usage": {"total_tokens": 100},
        }
    }
    with (
        patch("llm_council.council.COUNCIL_MODELS", ["model-a"]),
        patch(
            "llm_council.stages.stage1.query_models_with_progress",
            AsyncMock(return_value=mock_responses),
        ),
    ):
        results, usage, model_statuses = await stage1_collect_responses_with_status("test")
        assert len(results) == 1
        assert model_statuses["model-a"]["status"] == "ok"


@pytest.mark.asyncio
async def test_stage1_with_timeout_returns_partial():
    from llm_council.council import stage1_collect_responses_with_status

    mock_responses = {
        "m-a": {"status": "ok", "content": "A", "latency_ms": 100},
        "m-b": {"status": "timeout", "latency_ms": 25000},
    }
    with (
        patch("llm_council.council.COUNCIL_MODELS", ["m-a", "m-b"]),
        patch(
            "llm_council.stages.stage1.query_models_with_progress",
            AsyncMock(return_value=mock_responses),
        ),
    ):
        results, usage, model_statuses = await stage1_collect_responses_with_status("test")
        assert len(results) == 1
        assert model_statuses["m-b"]["status"] == "timeout"


@pytest.mark.asyncio
async def test_run_council_with_fallback_returns_structured_metadata():
    from llm_council.council import run_council_with_fallback

    with (
        patch(
            "llm_council.stages.stage1.stage1_collect_responses_with_status",
            AsyncMock(return_value=([], {}, {"m": {"status": "ok"}})),
        ),
        patch(
            "llm_council.stages.stage1.stage1_5_normalize_styles", AsyncMock(return_value=([], {}))
        ),
        patch(
            "llm_council.stages.stage2.stage2_collect_rankings",
            AsyncMock(return_value=([], {}, {})),
        ),
        patch(
            "llm_council.stages.stage3.stage3_synthesize_final",
            AsyncMock(return_value=({"response": "S"}, {}, None)),
        ),
        patch("llm_council.stages.stage2.calculate_aggregate_rankings", return_value=[]),
        patch("llm_council.council.COUNCIL_MODELS", ["m"]),
    ):
        result = await run_council_with_fallback("test")
        assert "synthesis" in result
        assert "metadata" in result


@pytest.mark.asyncio
async def test_run_council_with_fallback_partial_on_timeout():
    from llm_council.council import run_council_with_fallback

    async def slow_s2(*args, **kwargs):
        await asyncio.sleep(100)
        return [], {}, {}

    with (
        patch(
            "llm_council.stages.stage1.stage1_collect_responses_with_status",
            AsyncMock(
                return_value=([{"model": "a", "response": "A"}], {}, {"a": {"status": "ok"}})
            ),
        ),
        patch(
            "llm_council.stages.stage1.stage1_5_normalize_styles", AsyncMock(return_value=([], {}))
        ),
        patch("llm_council.stages.stage2.stage2_collect_rankings", side_effect=slow_s2),
        patch("llm_council.council.quick_synthesis", AsyncMock(return_value=("Quick", {}))),
        patch("llm_council.council.COUNCIL_MODELS", ["a"]),
    ):
        result = await run_council_with_fallback("test", synthesis_deadline=0.1)
        assert result["metadata"]["status"] == "partial"


@pytest.mark.asyncio
async def test_run_council_with_fallback_includes_model_statuses():
    from llm_council.council import run_council_with_fallback

    model_statuses = {"a": {"status": "ok"}, "b": {"status": "timeout"}}
    with (
        patch(
            "llm_council.stages.stage1.stage1_collect_responses_with_status",
            AsyncMock(return_value=([], {}, model_statuses)),
        ),
        patch(
            "llm_council.stages.stage1.stage1_5_normalize_styles",
            AsyncMock(
                return_value=(
                    [{"model": "a", "response": "A"}, {"model": "b", "response": "B"}],
                    {"total_cost": 0.0},
                )
            ),
        ),
        patch(
            "llm_council.stages.stage2.stage2_collect_rankings",
            AsyncMock(return_value=([], {}, {})),
        ),
        patch(
            "llm_council.stages.stage3.stage3_synthesize_final",
            AsyncMock(return_value=({"response": "S"}, {}, None)),
        ),
        patch("llm_council.stages.stage2.calculate_aggregate_rankings", return_value=[]),
        patch("llm_council.council.COUNCIL_MODELS", ["a", "b"]),
    ):
        result = await run_council_with_fallback("test")
        assert result["model_responses"]["b"]["status"] == "timeout"


@pytest.mark.asyncio
async def test_quick_synthesis_function():
    from llm_council.council import quick_synthesis

    with patch(
        "llm_council.council.query_model", AsyncMock(return_value={"content": "S", "usage": {}})
    ):
        synthesis, usage = await quick_synthesis("test", {"a": {"status": "ok", "response": "R"}})
        assert synthesis == "S"


@pytest.mark.asyncio
async def test_quick_synthesis_handles_chairman_failure():
    from llm_council.council import quick_synthesis

    with patch("llm_council.council.query_model", AsyncMock(return_value=None)):
        synthesis, usage = await quick_synthesis(
            "test", {"a": {"status": "ok", "response": "Best"}}
        )
        assert "Best" in synthesis


def test_generate_partial_warning():
    from llm_council.council import generate_partial_warning

    warning = generate_partial_warning({"a": {"status": "ok"}, "b": {"status": "timeout"}}, 2)
    assert "1 of 2" in warning


def test_generate_partial_warning_all_ok():
    from llm_council.council import generate_partial_warning

    assert generate_partial_warning({"a": {"status": "ok"}}, 1) is None


@pytest.mark.asyncio
async def test_full_council_fallback_stage1_only():
    from llm_council.council import run_council_with_fallback

    async def slow_s2(*args, **kwargs):
        await asyncio.sleep(100)
        return [], {}, {}

    with (
        patch(
            "llm_council.stages.stage1.stage1_collect_responses_with_status",
            AsyncMock(
                return_value=([{"model": "a", "response": "A"}], {}, {"a": {"status": "ok"}})
            ),
        ),
        patch(
            "llm_council.stages.stage1.stage1_5_normalize_styles", AsyncMock(return_value=([], {}))
        ),
        patch("llm_council.stages.stage2.stage2_collect_rankings", side_effect=slow_s2),
        patch("llm_council.council.quick_synthesis", AsyncMock(return_value=("Fallback", {}))),
        patch("llm_council.council.COUNCIL_MODELS", ["a"]),
    ):
        result = await run_council_with_fallback("test", synthesis_deadline=0.05)
        assert result["metadata"]["status"] == "partial"


@pytest.mark.asyncio
async def test_full_council_returns_complete_on_success():
    from llm_council.council import run_council_with_fallback

    with (
        patch(
            "llm_council.stages.stage1.stage1_collect_responses_with_status",
            AsyncMock(return_value=([{"m": "a"}], {}, {"m": {"status": "ok"}})),
        ),
        patch(
            "llm_council.stages.stage1.stage1_5_normalize_styles",
            AsyncMock(return_value=([{"model": "m", "response": "R"}], {"total_cost": 0.0})),
        ),
        patch(
            "llm_council.stages.stage2.stage2_collect_rankings",
            AsyncMock(return_value=([], {}, {})),
        ),
        patch(
            "llm_council.stages.stage3.stage3_synthesize_final",
            AsyncMock(return_value=({"response": "Full"}, {}, None)),
        ),
        patch("llm_council.stages.stage2.calculate_aggregate_rankings", return_value=[]),
        patch("llm_council.council.COUNCIL_MODELS", ["m"]),
    ):
        result = await run_council_with_fallback("test")
        assert result["metadata"]["status"] == "complete"


@pytest.mark.asyncio
async def test_council_fails_when_all_models_timeout():
    from llm_council.council import run_council_with_fallback

    with (
        patch(
            "llm_council.stages.stage1.stage1_collect_responses_with_status",
            AsyncMock(return_value=([], {}, {"a": {"status": "timeout"}})),
        ),
        patch("llm_council.council.COUNCIL_MODELS", ["a"]),
    ):
        result = await run_council_with_fallback("test")
        assert result["metadata"]["status"] == "failed"


@pytest.mark.asyncio
async def test_council_with_progress_callback():
    from llm_council.council import run_council_with_fallback

    progress = []

    async def track(s, t, m):
        progress.append(m)

    with (
        patch(
            "llm_council.stages.stage1.stage1_collect_responses_with_status",
            AsyncMock(return_value=([], {}, {"a": {"status": "ok"}})),
        ),
        patch(
            "llm_council.stages.stage1.stage1_5_normalize_styles", AsyncMock(return_value=([], {}))
        ),
        patch(
            "llm_council.stages.stage2.stage2_collect_rankings",
            AsyncMock(return_value=([], {}, {})),
        ),
        patch(
            "llm_council.stages.stage3.stage3_synthesize_final",
            AsyncMock(return_value=({"response": "S"}, {}, None)),
        ),
        patch("llm_council.stages.stage2.calculate_aggregate_rankings", return_value=[]),
        patch("llm_council.council.COUNCIL_MODELS", ["a"]),
    ):
        await run_council_with_fallback("test", on_progress=track)
        assert len(progress) >= 2
