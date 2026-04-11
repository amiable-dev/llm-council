import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from llm_council.council import run_council_with_fallback, VerdictType, MODEL_STATUS_OK, STATUS_OK


@pytest.mark.asyncio
async def test_adversarial_mode_logic_split():
    """Test that adversarial mode correctly splits models and runs DA sequentially."""

    council_models = ["model1", "model2", "model3", "model4"]
    user_query = "What is 2+2?"

    # Mock Stage 1 results
    mock_stage1_results = [
        {"model": "model1", "response": "It is 4."},
        {"model": "model2", "response": "4."},
        {"model": "model3", "response": "Four."},
    ]
    mock_stage1_usage = {
        "total_cost": 0.01,
        "total_tokens": 100,
        "prompt_tokens": 50,
        "completion_tokens": 50,
    }
    mock_model_statuses = {
        "model1": {"status": MODEL_STATUS_OK, "response": "It is 4."},
        "model2": {"status": MODEL_STATUS_OK, "response": "4."},
        "model3": {"status": MODEL_STATUS_OK, "response": "Four."},
    }

    # Mock DA response
    mock_da_response = {
        "status": STATUS_OK,
        "content": "This is a dissent report.",
        "usage": {
            "total_cost": 0.005,
            "total_tokens": 50,
            "prompt_tokens": 25,
            "completion_tokens": 25,
        },
        "latency_ms": 100,
    }

    with (
        patch("llm_council.stages.stage1._get_adversarial_mode", return_value=True),
        patch("llm_council.stages.stage1._get_adversarial_model", return_value="model4"),
        patch(
            "llm_council.stages.stage1.stage1_collect_responses_with_status", new_callable=AsyncMock
        ) as mock_collector_s1,
        patch(
            "llm_council.stages.stage1.query_model_with_status", new_callable=AsyncMock
        ) as mock_query,
        patch(
            "llm_council.stages.stage1.stage1_5_normalize_styles", new_callable=AsyncMock
        ) as mock_norm,
        patch("llm_council.council.run_stage2", new_callable=AsyncMock) as mock_stage2,
        patch("llm_council.council.run_stage3", new_callable=AsyncMock) as mock_stage3,
    ):
        mock_collector_s1.return_value = (
            mock_stage1_results,
            mock_stage1_usage,
            mock_model_statuses,
        )
        mock_query.return_value = mock_da_response
        mock_norm.return_value = (mock_stage1_results, {})
        mock_stage2.return_value = {
            "stage2_results": [],
            "label_to_model": {},
            "aggregate_rankings": [],
            "usage": {},
            "consensus_winner": None,
            "constructive_dissent": None,
        }
        mock_stage3.return_value = {
            "chairman_result": {"response": "Final synth"},
            "verdict_result": None,
            "usage": {},
        }

        # Run council
        result = await run_council_with_fallback(user_query, models=council_models)

        # 1. Verify Stage 1 was called with only first 3 models
        mock_collector_s1.assert_called_once()
        sent_models = mock_collector_s1.call_args[1].get("models")
        assert len(sent_models) == 3
        assert "model4" not in sent_models

        # 2. Verify DA (model4) was called sequentially
        mock_query.assert_called_once()
        assert mock_query.call_args[0][0] == "model4"
        da_prompt = mock_query.call_args[0][1][0]["content"]
        assert "It is 4." in da_prompt
        assert "ADVERSARIAL CRITIQUE" in da_prompt

        # 3. Verify dissent_report was passed to Stage 2 and Stage 3
        # In the modular refactor, stage1_data and stage2_data are passed as packets.
        stage1_data_sent = mock_stage3.call_args[0][1]
        assert stage1_data_sent["dissent_report"] == "This is a dissent report."

        # Stage 2 call check
        stage1_data_to_s2 = mock_stage2.call_args[0][1]
        assert stage1_data_to_s2["dissent_report"] == "This is a dissent report."

        # 4. Verify usage was aggregated
        total_usage = result["metadata"]["usage"]
        assert total_usage["total_cost"] == 0.01 + 0.005
        assert total_usage["total_tokens"] == 150


@pytest.mark.asyncio
async def test_adversarial_mode_skipped_for_small_councils():
    """Test that adversarial mode is bypassed if there are fewer than 3 models."""
    council_models = ["model1", "model2"]
    user_query = "2+2?"

    with (
        patch("llm_council.stages.stage1._get_adversarial_mode", return_value=True),
        patch(
            "llm_council.stages.stage1.stage1_collect_responses_with_status", new_callable=AsyncMock
        ) as mock_collector,
    ):
        mock_collector.return_value = ([], {}, {})

        await run_council_with_fallback(user_query, models=council_models)

        # Verify all models were sent to Stage 1 (no DA split)
        sent_models = mock_collector.call_args[1].get("models")
        assert len(sent_models) == 2
