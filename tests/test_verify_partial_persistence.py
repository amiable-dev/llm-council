"""Tests for partial-result persistence and the input-too-large signal.

#356: timeout and input-cap verifications must be written to the transcript
store (a ``result.json``) so the failures we most need to debug are not lost.

#357: an input-cap rejection must be distinguishable from a deliberated UNCLEAR
so automation does not mistake an unreviewed oversized input for a passed gate.
"""

import asyncio

import pytest

from llm_council.verification.formatting import format_verification_result


def _result_writes(mock_store):
    """Return the data dicts written with stage == 'result'."""
    out = []
    for call in mock_store.write_stage.call_args_list:
        args = call.args
        if len(args) >= 3 and args[1] == "result":
            out.append(args[2])
    return out


class TestInputCapPersistenceAndSignal:
    @pytest.mark.asyncio
    async def test_input_too_large_persists_result_and_sets_error(self):
        from unittest.mock import AsyncMock, MagicMock, patch

        from llm_council.verification.api import run_verification, VerifyRequest

        request = VerifyRequest(snapshot_id="abc1234", tier="quick")  # cap 15000

        oversized = "x" * 20000
        with (
            patch("llm_council.verification.api.VerificationContextManager") as mock_ctx_mgr,
            patch(
                "llm_council.verification.api._build_verification_prompt",
                new_callable=AsyncMock,
                return_value=(oversized, {"kept": [], "warnings": []}),
            ),
        ):
            mock_ctx = MagicMock()
            mock_ctx.context_id = "test-ctx"
            mock_ctx_mgr.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_ctx_mgr.return_value.__exit__ = MagicMock(return_value=False)

            mock_store = MagicMock()
            mock_store.create_verification_directory.return_value = "/tmp/test"

            result = await run_verification(request, mock_store)

        # #357: distinct, non-deliberated signal.
        assert result.get("error") == "input_too_large"
        assert result["partial"] is True
        # #356: persisted to the transcript store.
        writes = _result_writes(mock_store)
        assert len(writes) == 1
        assert writes[0].get("error") == "input_too_large"

    def test_formatter_flags_input_too_large_distinctly(self):
        result = {
            "verdict": "unclear",
            "exit_code": 2,
            "confidence": 0.0,
            "error": "input_too_large",
            "rationale": "Input size (20000 chars) exceeds quick tier limit (15000 chars).",
            "transcript_location": "/tmp/x",
        }
        out = format_verification_result(result)
        # Must NOT read like a deliberated verdict the caller can accept.
        assert "INPUT TOO LARGE" in out.upper()
        assert "did not run" in out.lower() or "not reviewed" in out.lower()

    def test_formatter_normal_result_unchanged(self):
        result = {
            "verdict": "pass",
            "exit_code": 0,
            "confidence": 0.9,
            "rubric_scores": {"accuracy": 9.0},
            "blocking_issues": [],
            "rationale": "Looks good.",
            "transcript_location": "/tmp/x",
        }
        out = format_verification_result(result)
        assert "INPUT TOO LARGE" not in out.upper()
        assert "PASS" in out.upper()


class TestTimeoutPersistence:
    @pytest.mark.asyncio
    async def test_timeout_persists_result_json(self):
        from unittest.mock import AsyncMock, MagicMock, patch

        from llm_council.verification.api import run_verification, VerifyRequest

        request = VerifyRequest(snapshot_id="abc1234", tier="quick")

        async def hanging_pipeline(*args, **kwargs):
            await asyncio.sleep(9999)

        with (
            patch("llm_council.verification.api.VerificationContextManager") as mock_ctx_mgr,
            patch(
                "llm_council.verification.api._build_verification_prompt",
                new_callable=AsyncMock,
                return_value=("short prompt", {"kept": [], "warnings": []}),
            ),
            patch(
                "llm_council.verification.api._run_verification_pipeline",
                side_effect=hanging_pipeline,
            ),
            patch(
                "llm_council.verification.api.asyncio.wait_for",
                side_effect=asyncio.TimeoutError(),
            ),
        ):
            mock_ctx = MagicMock()
            mock_ctx.context_id = "test-ctx"
            mock_ctx_mgr.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_ctx_mgr.return_value.__exit__ = MagicMock(return_value=False)

            mock_store = MagicMock()
            mock_store.create_verification_directory.return_value = "/tmp/test"

            result = await run_verification(request, mock_store)

        assert result["timeout_fired"] is True
        writes = _result_writes(mock_store)
        assert len(writes) == 1
        assert writes[0]["timeout_fired"] is True
        assert writes[0]["partial"] is True
