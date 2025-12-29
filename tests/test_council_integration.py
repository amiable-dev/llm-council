import asyncio
import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from llm_council.council import run_council_with_fallback, MODEL_STATUS_OK


@pytest.fixture
def temp_bias_store():
    """Create a temporary bias store file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store_path = Path(tmpdir) / "bias_metrics.jsonl"
        yield store_path


@pytest.mark.asyncio
async def test_integration_persistence_enabled(temp_bias_store):
    """Verify that council execution writes to bias store when enabled."""

    # Mock responses for all stages

    # Stage 1: mock 2 models responding
    mock_stage1_responses = {
        "model1": {
            "status": MODEL_STATUS_OK,
            "content": "Response 1",
            "latency_ms": 100,
            "usage": {},
        },
        "model2": {
            "status": MODEL_STATUS_OK,
            "content": "Response 2",
            "latency_ms": 100,
            "usage": {},
        },
    }

    # Stage 2: mock rankings
    # Model 1 ranks A and B
    mock_ranking1 = {
        "ranking": ["Response A", "Response B"],
        "scores": {"Response A": 8, "Response B": 7},
    }
    mock_stage2_responses = {
        "model1": {"content": json.dumps(mock_ranking1), "usage": {}},
        "model2": {"content": json.dumps(mock_ranking1), "usage": {}},
    }

    # Stage 3: mock synthesis
    mock_synthesis_response = {"content": "Synthesized answer", "usage": {}}

    # Mock normalizer (should check if called, but for now just mock return)
    mock_normalize_response = {"content": "Normalized", "usage": {}}

    with patch(
        "llm_council.council.query_models_with_progress", new_callable=AsyncMock
    ) as mock_query_all:
        mock_query_all.return_value = mock_stage1_responses

        with patch(
            "llm_council.council.query_models_parallel", new_callable=AsyncMock
        ) as mock_query_parallel:
            # Stage 2 uses query_models_parallel
            # It returns a dict {model: response_dict}
            mock_query_parallel.return_value = {
                "model1": {
                    "status": MODEL_STATUS_OK,
                    "content": json.dumps(mock_ranking1),
                    "usage": {},
                },
                "model2": {
                    "status": MODEL_STATUS_OK,
                    "content": json.dumps(mock_ranking1),
                    "usage": {},
                },
            }

            with patch(
                "llm_council.council.query_model", new_callable=AsyncMock
            ) as mock_query_single:
                # Side effect for query_model to handle different calls
                async def side_effect(model, messages, **kwargs):
                    # If checking normalizer
                    if "neutral, consistent style" in messages[0]["content"]:
                        return mock_normalize_response
                    # If stage 3 synthesis
                    if "synthesizing multiple AI responses" in messages[0]["content"]:
                        return mock_synthesis_response
                    # If stage 2 peer review
                    return mock_stage2_responses.get(model, {"content": "{}"})

                mock_query_single.side_effect = side_effect

                with patch(
                    "llm_council.bias_persistence._get_bias_persistence_enabled", return_value=True
                ):
                    with patch(
                        "llm_council.bias_persistence._get_bias_store_path",
                        return_value=temp_bias_store,
                    ):
                        with patch("llm_council.council.COUNCIL_MODELS", ["model1", "model2"]):
                            # Run council
                            result = await run_council_with_fallback("Test query")

                            # Assert success
                            assert result["metadata"]["status"] == "complete"

                            # Check if file exists and has content
                            assert temp_bias_store.exists()

                            with open(temp_bias_store, "r") as f:
                                lines = f.readlines()
                                assert len(lines) > 0
                                # Check content of first record
                                record = json.loads(lines[0])
                                assert record["schema_version"] == "1.1.0"
                                assert "session_id" in record
                                assert record["consent_level"] == 1  # Default LOCAL_ONLY


@pytest.mark.asyncio
async def test_integration_persistence_disabled(temp_bias_store):
    """Verify that council execution does NOT write when disabled."""
    # Mock stage 1
    mock_stage1_responses = {
        "model1": {
            "status": MODEL_STATUS_OK,
            "content": "Response 1",
            "latency_ms": 100,
            "usage": {},
        },
    }
    # Mock stage 2
    mock_stage2_responses = {
        "model1": {
            "content": json.dumps({"ranking": ["Response A"], "scores": {"Response A": 8}}),
            "usage": {},
        },
    }

    with patch(
        "llm_council.council.query_models_with_progress", new_callable=AsyncMock
    ) as mock_query_all:
        mock_query_all.return_value = mock_stage1_responses
        with patch(
            "llm_council.council.query_models_parallel", new_callable=AsyncMock
        ) as mock_query_parallel:
            mock_query_parallel.return_value = {
                "model1": {
                    "status": MODEL_STATUS_OK,
                    "content": json.dumps({"ranking": ["Response A"], "scores": {"Response A": 8}}),
                    "usage": {},
                },
            }
            with patch(
                "llm_council.council.query_model", new_callable=AsyncMock
            ) as mock_query_single:
                mock_query_single.return_value = {"content": "Synthesis", "usage": {}}

                with patch(
                    "llm_council.bias_persistence._get_bias_persistence_enabled", return_value=False
                ):
                    with patch(
                        "llm_council.bias_persistence._get_bias_store_path",
                        return_value=temp_bias_store,
                    ):
                        with patch("llm_council.council.COUNCIL_MODELS", ["model1"]):
                            await run_council_with_fallback("Test query")

                            # File should NOT exist (or be empty if created but not written)
                            if temp_bias_store.exists():
                                assert temp_bias_store.stat().st_size == 0
