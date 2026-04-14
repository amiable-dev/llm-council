import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from llm_council.stages.stage3 import run_stage3
from llm_council.verdict import VerdictType
from llm_council.council import run_full_council


@pytest.mark.asyncio
async def test_stage3_timeout_propagation():
    """Verify that Stage 3 uses the provided per_model_timeout."""
    mock_stage1 = {"stage1_results": [], "usage": {}}
    mock_stage2 = {"stage2_results": [], "aggregate_rankings": [], "usage": {}}

    with patch(
        "llm_council.stages.stage3.stage3_synthesize_final", new_callable=AsyncMock
    ) as mock_synth:
        mock_synth.return_value = ({"response": "ok"}, {}, None)

        # Test with explicit timeout
        await run_stage3("query", mock_stage1, mock_stage2, per_model_timeout=45)

        # Check if the mock was called with the correct timeout
        args, kwargs = mock_synth.call_args
        assert kwargs["timeout"] == 45


@pytest.mark.asyncio
async def test_stage3_default_timeout_is_90():
    """Verify that Stage 3 default timeout is now 90s (Bug Fix #34)."""
    mock_stage1 = {"stage1_results": [], "usage": {}}
    mock_stage2 = {"stage2_results": [], "aggregate_rankings": [], "usage": {}}

    with patch(
        "llm_council.stages.stage3.stage3_synthesize_final", new_callable=AsyncMock
    ) as mock_synth:
        mock_synth.return_value = ({"response": "ok"}, {}, None)

        await run_stage3("query", mock_stage1, mock_stage2)

        args, kwargs = mock_synth.call_args
        assert kwargs["timeout"] == 90


@pytest.mark.asyncio
async def test_run_full_council_legacy_signature_parity():
    """BUG-023: Verify that run_full_council respects legacy parameter 'models' and return structure."""

    # Mock stage functions to return dummy data in the new modular format
    mock_stage1 = {
        "stage1_results": [{"model": "test-model", "response": "ok"}],
        "usage": {},
        "session_id": "test-session",
        "requested_models": 1,
        "total_steps": 5,
    }
    mock_stage2 = {
        "stage2_results": [],
        "label_to_model": {"Response A": "test-model"},
        "aggregate_rankings": [],
        "usage": {},
    }
    mock_stage3 = {
        "chairman_result": {"model": "chairman", "response": "final synthesis"},
        "usage": {},
    }

    with (
        patch("llm_council.council.run_stage1", new_callable=AsyncMock, return_value=mock_stage1),
        patch("llm_council.council.run_stage2", new_callable=AsyncMock, return_value=mock_stage2),
        patch("llm_council.council.run_stage3", new_callable=AsyncMock, return_value=mock_stage3),
    ):
        try:
            results = await run_full_council(
                "Is the moon cheese?",
                models=["test-model"],  # Legacy parameter name
            )

            # Orchestrator Return Signature: (List, List, Dict, Dict)
            # 1: stage1_data (List of results)
            # 2: rankings (List of strings)
            # 3: usage_stats (Dict)
            # 4: metadata (Dict)
            stage1, stage2, stage3, metadata = results

            assert isinstance(stage1, list), (
                f"Stage 1 should be a model results list, got {type(stage1)}"
            )
            assert isinstance(stage2, list), (
                f"Stage 2 (rankings) should be a list, got {type(stage2)}"
            )
            assert isinstance(stage3, dict), f"Stage 3 (usage) should be a dict, got {type(stage3)}"
            assert isinstance(metadata, dict), f"Metadata should be a dict, got {type(metadata)}"

        except TypeError as e:
            pytest.fail(f"API Signature Regression: run_full_council failed with {e}")
        except ValueError as e:
            pytest.fail(f"API Return Structure Regression: Unpacking failed with {e}")


if __name__ == "__main__":
    asyncio.run(test_run_full_council_legacy_signature_parity())
