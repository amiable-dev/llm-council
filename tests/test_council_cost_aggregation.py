import pytest
from unittest.mock import patch, AsyncMock


@pytest.mark.asyncio
async def test_council_aggregates_total_cost(anyio_backend):
    if anyio_backend == "trio":
        pytest.xfail("run_council_with_fallback uses asyncio.wait_for")
    from llm_council.council import run_council_with_fallback

    # Mock helpers with specific costs (Tuples)
    mock_s1 = (
        [{"model": "m1", "response": "r1"}],
        {"total_cost": 0.1, "total_tokens": 100},
        {"m1": {"status": "ok"}},
    )
    mock_s15 = ([{"model": "m1", "response": "r1_n"}], {"total_cost": 0.05, "total_tokens": 50})
    mock_s2 = ([], {}, {"total_cost": 0.2, "total_tokens": 200})
    mock_s3 = ({"response": "f"}, {"total_cost": 0.15, "total_tokens": 150}, None)

    with (
        patch(
            "llm_council.stages.stage1.stage1_collect_responses_with_status",
            AsyncMock(return_value=mock_s1),
        ),
        patch(
            "llm_council.stages.stage1.stage1_5_normalize_styles", AsyncMock(return_value=mock_s15)
        ),
        patch("llm_council.stages.stage2.stage2_collect_rankings", AsyncMock(return_value=mock_s2)),
        patch("llm_council.stages.stage3.stage3_synthesize_final", AsyncMock(return_value=mock_s3)),
        patch("llm_council.stages.stage2.persist_session_bias_data"),
        patch("llm_council.council._get_council_models", return_value=["m1"]),
        patch("llm_council.council.COUNCIL_MODELS", ["m1"]),
    ):
        result = await run_council_with_fallback("test")

        # 0.1 + 0.05 + 0.2 + 0.15 = 0.5
        assert result["metadata"]["usage"]["total_cost"] == pytest.approx(0.5)
        # Stage 1 now consolidates 1.5: 0.1 + 0.05 = 0.15
        assert result["metadata"]["usage"]["stages"]["stage1"]["total_cost"] == pytest.approx(0.15)
