import pytest
from unittest.mock import patch, AsyncMock
from llm_council.council import run_full_council


@pytest.mark.asyncio
async def test_dissent_metadata_integration():
    """Verify that include_dissent correctly populates metadata['dissent']."""

    user_query = "Test query"
    mock_stage1 = [{"model": "m1", "response": "resp1"}, {"model": "m2", "response": "resp2"}]
    mock_stage2 = [{"model": "m2", "response": "resp2"}]
    mock_stage3 = {"response": "synthesis"}

    # We patch run_full_council because we want to test that query.py
    # would receive and display this metadata.
    # But since we're testing the integration in the engine first:

    mock_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "total_cost": 0.0}

    with (
        patch("llm_council.council.stage1_collect_responses", new_callable=AsyncMock) as m1,
        patch("llm_council.council.stage2_collect_rankings", new_callable=AsyncMock) as m2,
        patch("llm_council.council.stage3_synthesize_final", new_callable=AsyncMock) as m3,
        patch(
            "llm_council.council.extract_dissent_from_stage2",
            return_value="This is a minority opinion.",
        ),
    ):
        m1.return_value = (mock_stage1, mock_usage)
        m2.return_value = (mock_stage2, {}, mock_usage)
        m3.return_value = (mock_stage3, mock_usage, None)

        _, _, _, metadata = await run_full_council(user_query, include_dissent=True)

        assert metadata.get("dissent") == "This is a minority opinion."
