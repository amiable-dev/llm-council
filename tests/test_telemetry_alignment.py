import asyncio
import uuid
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from llm_council.council import run_council_with_fallback
from llm_council.telemetry import TelemetryProtocol


class TestTelemetryUnification:
    """Verify session_id alignment between bias persistence and telemetry."""

    @pytest.mark.asyncio
    async def test_session_id_aligned(self):
        """Telemetry and bias persistence should receive the same session_id."""

        # Mocks
        mock_persist = MagicMock()
        mock_telemetry_client = MagicMock()
        mock_telemetry_client.is_enabled.return_value = True
        mock_telemetry_client.send_event = AsyncMock()

        # Mock LLM interactions
        with (
            patch("llm_council.council.run_stage1", new_callable=AsyncMock) as mock_stage1,
            patch("llm_council.council.run_stage2", new_callable=AsyncMock) as mock_stage2,
            patch("llm_council.council.run_stage3", new_callable=AsyncMock) as mock_stage3,
            patch("llm_council.council.persist_session_bias_data", mock_persist),
            patch("llm_council.council.get_telemetry", return_value=mock_telemetry_client),
            patch("llm_council.council._get_council_models", return_value=["m"]),
        ):
            # Setup minimal working mocks
            mock_stage1.return_value = {
                "stage1_results": [{"model": "m", "response": "r"}],
                "usage": {},
                "model_statuses": {"m": {"status": "ok"}},
            }
            mock_stage2.return_value = {
                "stage2_results": [],
                "aggregate_rankings": [],
                "label_to_model": {},
                "usage": {},
            }
            mock_stage3.return_value = {
                "chairman_result": {
                    "response": "synthesis",
                    "bias_analysis": {"bias_detected": False},
                },
                "usage": {},
            }

            # Run the council
            await run_council_with_fallback("test query")

            # 1. Verify bias persistence was called with A session_id
            assert mock_persist.called
            bias_call_args = mock_persist.call_args[1]
            bias_session_id = bias_call_args["session_id"]
            assert bias_session_id is not None
            assert len(bias_session_id) > 0

            # 2. Verify telemetry event was sent
            assert mock_telemetry_client.send_event.called
            telemetry_call_args = mock_telemetry_client.send_event.call_args[0][0]

            # 3. Verify IDs match
            assert telemetry_call_args["type"] == "council_completed"
            assert telemetry_call_args["session_id"] == bias_session_id

            # 4. Verify telemetry excluded PII (optional but good sanity check)
            # Ensure "response" key is NOT present (payload should be metadata only)
            assert "response" not in telemetry_call_args
            assert "query" not in telemetry_call_args
