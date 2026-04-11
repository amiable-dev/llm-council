import pytest
import asyncio
from unittest.mock import patch, AsyncMock
from llm_council.council import run_full_council

@pytest.mark.asyncio
async def test_run_full_council_legacy_signature_parity():
    """BUG-023: Verify that run_full_council respects legacy parameter 'models' and return structure."""
    
    # Mock stage functions to return dummy data in the new modular format
    mock_stage1 = {
        "stage1_results": [{"model": "test-model", "response": "ok"}],
        "usage": {},
        "session_id": "test-session",
        "requested_models": 1,
        "total_steps": 5
    }
    mock_stage2 = {
        "stage2_results": [],
        "label_to_model": {"Response A": "test-model"},
        "aggregate_rankings": [],
        "usage": {}
    }
    mock_stage3 = {
        "chairman_result": {"model": "chairman", "response": "final synthesis"},
        "usage": {}
    }

    with patch("llm_council.council.run_stage1", new_callable=AsyncMock, return_value=mock_stage1), \
         patch("llm_council.council.run_stage2", new_callable=AsyncMock, return_value=mock_stage2), \
         patch("llm_council.council.run_stage3", new_callable=AsyncMock, return_value=mock_stage3):
        
        # This call SHOULD fail in the current broken state due to 'models' parameter rename
        # AND the unpacking should fail if it doesn't return a 4-tuple of (List, List, Dict, Dict)
        try:
            results = await run_full_council(
                "Is the moon cheese?",
                models=["test-model"]  # Legacy parameter name
            )
            
            # If it reaches here, we check the return types (current code returns (str, dict, dict, list))
            # Legacy expects (List, List, Dict, Dict)
            stage1, stage2, stage3, metadata = results
            
            assert isinstance(stage1, list), f"Stage 1 should be a list, got {type(stage1)}"
            assert isinstance(stage2, list), f"Stage 2 should be a list, got {type(stage2)}"
            assert isinstance(stage3, dict), f"Stage 3 should be a dict, got {type(stage3)}"
            assert isinstance(metadata, dict), f"Metadata should be a dict, got {type(metadata)}"
            
        except TypeError as e:
            pytest.fail(f"API Signature Regression: run_full_council failed with {e}")
        except ValueError as e:
            pytest.fail(f"API Return Structure Regression: Unpacking failed with {e}")

if __name__ == "__main__":
    asyncio.run(test_run_full_council_legacy_signature_parity())
