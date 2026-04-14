import asyncio
import uuid
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from llm_council.council import run_council_with_fallback, stage1_collect_responses_with_status


@pytest.mark.asyncio
async def test_stage1_collect_responses_with_status_handles_timeout():
    """Verify that Stage 1 correctly captures timeouts without crashing."""
    mock_responses = {
        "m-a": {"status": "ok", "content": "A", "latency_ms": 100},
        "m-b": {"status": "timeout", "latency_ms": 25000},
    }
    with (
        patch("llm_council.stages.stage1._get_council_models", return_value=["m-a", "m-b"]),
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
            "llm_council.stages.stage1.stage1_5_normalize_styles",
            AsyncMock(return_value=([{"model": "m", "response": "R"}], {})),
        ),
        patch(
            "llm_council.stages.stage2.stage2_collect_rankings",
            AsyncMock(return_value=([], {}, {})),
        ),
        patch(
            "llm_council.stages.stage3.stage3_synthesize_final",
            AsyncMock(return_value=({"response": "C"}, {}, None)),
        ),
    ):
        result = await run_council_with_fallback("test")
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
                return_value=(
                    [{"model": "a", "response": "A"}],
                    {},
                    {"a": {"status": "ok"}, "b": {"status": "timeout"}},
                )
            ),
        ),
        patch(
            "llm_council.stages.stage1.stage1_5_normalize_styles",
            AsyncMock(return_value=([{"model": "a", "response": "A"}], {})),
        ),
        patch("llm_council.stages.stage2.stage2_collect_rankings", side_effect=slow_s2),
        patch("llm_council.stages.stage1._get_council_models", return_value=["a", "b"]),
        patch("llm_council.council._get_council_models", return_value=["a", "b"]),
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
        patch("llm_council.stages.stage1._get_council_models", return_value=["a", "b"]),
        patch("llm_council.council._get_council_models", return_value=["a", "b"]),
    ):
        result = await run_council_with_fallback("test")
        assert result["model_statuses"]["b"]["status"] == "timeout"


@pytest.mark.asyncio
async def test_run_council_with_fallback_timeout_in_stage1_total_failure():
    from llm_council.council import run_council_with_fallback

    with (
        patch(
            "llm_council.stages.stage1.stage1_collect_responses_with_status",
            AsyncMock(
                return_value=([], {}, {"a": {"status": "timeout"}, "b": {"status": "timeout"}})
            ),
        ),
        patch(
            "llm_council.stages.stage1.stage1_5_normalize_styles", AsyncMock(return_value=([], {}))
        ),
        patch("llm_council.stages.stage1._get_council_models", return_value=["a", "b"]),
        patch("llm_council.council._get_council_models", return_value=["a", "b"]),
    ):
        result = await run_council_with_fallback("test")
        assert result["metadata"]["status"] == "failed"


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
            "llm_council.stages.stage1.stage1_5_normalize_styles",
            AsyncMock(return_value=([{"model": "a", "response": "A"}], {})),
        ),
        patch("llm_council.stages.stage2.stage2_collect_rankings", side_effect=slow_s2),
        patch("llm_council.stages.stage1._get_council_models", return_value=["a", "b"]),
        patch("llm_council.council._get_council_models", return_value=["a", "b"]),
    ):
        result = await run_council_with_fallback("test", synthesis_deadline=0.05)
        assert result["metadata"]["status"] == "partial"


@pytest.mark.asyncio
async def test_full_council_returns_complete_on_success():
    from llm_council.council import run_council_with_fallback

    with (
        patch(
            "llm_council.stages.stage1.stage1_collect_responses_with_status",
            AsyncMock(
                return_value=([{"model": "m", "response": "R"}], {}, {"m": {"status": "ok"}})
            ),
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
        patch("llm_council.stages.stage1._get_council_models", return_value=["m"]),
        patch("llm_council.council._get_council_models", return_value=["m"]),
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
        patch(
            "llm_council.stages.stage1.stage1_5_normalize_styles", AsyncMock(return_value=([], {}))
        ),
        patch("llm_council.stages.stage1._get_council_models", return_value=["a"]),
        patch("llm_council.council._get_council_models", return_value=["a"]),
    ):
        result = await run_council_with_fallback("test")
        assert result["metadata"]["status"] == "failed"


@pytest.mark.asyncio
async def test_council_reliability_progress_tracking():
    from llm_council.council import run_council_with_fallback

    progress = []

    async def track(s, t, m):
        progress.append(m)

    async def slow_s2(*args, **kwargs):
        await asyncio.sleep(100)
        return [], {}, {}

    with (
        patch(
            "llm_council.stages.stage1.stage1_collect_responses_with_status",
            AsyncMock(
                return_value=([{"model": "a", "response": "R"}], {}, {"a": {"status": "ok"}})
            ),
        ),
        patch(
            "llm_council.stages.stage1.stage1_5_normalize_styles",
            AsyncMock(return_value=([{"model": "a", "response": "R"}], {})),
        ),
        patch(
            "llm_council.stages.stage2.stage2_collect_rankings",
            AsyncMock(return_value=([], {}, {})),
        ),
        patch(
            "llm_council.stages.stage3.stage3_synthesize_final",
            AsyncMock(return_value=({"response": "S"}, {}, None)),
        ),
        patch("llm_council.stages.stage1._get_council_models", return_value=["a"]),
        patch("llm_council.council._get_council_models", return_value=["a"]),
    ):
        await run_council_with_fallback("test", on_progress=track)
        assert len(progress) >= 2
