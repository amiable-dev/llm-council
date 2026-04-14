"""Tests for dissent metadata population in the unified council orchestrator."""

import pytest
from unittest.mock import patch, AsyncMock
from llm_council.council import run_full_council


@pytest.mark.asyncio
async def test_dissent_metadata_integration():
    """Verify that include_dissent correctly populates metadata['dissent']."""

    user_query = "Test query"

    # Mock data for the 3 stages
    mock_stage1_data = {
        "stage1_results": [
            {"model": "m1", "response": "resp1"},
            {"model": "m2", "response": "resp2"},
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        "model_statuses": {"m1": {"status": "ok"}, "m2": {"status": "ok"}},
        "dissent_report": "This is a minority opinion.",
    }

    mock_stage2_data = {
        "stage2_results": [{"model": "m2", "ranking": "..."}],
        "label_to_model": {"Response B": {"model": "m2"}},
        "aggregate_rankings": [{"model": "m2", "borda_score": 1.0}],
        "usage": {"prompt_tokens": 50, "completion_tokens": 25, "total_tokens": 75},
        "constructive_dissent": "Additional context.",
    }

    mock_stage3_data = {
        "chairman_result": {"model": "chairman/model", "response": "Final synthesis"},
        "verdict_result": None,
        "usage": {"prompt_tokens": 100, "completion_tokens": 100, "total_tokens": 200},
    }

    with (
        patch("llm_council.council.run_stage1", new_callable=AsyncMock) as m1,
        patch("llm_council.council.run_stage2", new_callable=AsyncMock) as m2,
        patch("llm_council.council.run_stage3", new_callable=AsyncMock) as m3,
    ):
        m1.return_value = mock_stage1_data
        m2.return_value = mock_stage2_data
        m3.return_value = mock_stage3_data

        # Final Verify: Unpacking (stage1, rankings, usage, metadata)
        _, _, _, metadata = await run_full_council(
            user_query, include_dissent=True, models=["m1", "m2"]
        )

        # Assertions
        assert metadata.get("dissent") == "This is a minority opinion."
        assert metadata.get("constructive_dissent") == "Additional context."
        assert metadata.get("status") == "complete"
