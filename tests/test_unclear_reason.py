"""ADR-047 P1: unclear_reason disambiguation (#413).

UNCLEAR conflated three unlike causes; callers need machine-readable
disambiguation: infra_failure (chairman errored, #403), low_confidence
(deliberated but below threshold), timeout (global deadline).
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llm_council.verification.verdict_extractor import derive_unclear_reason


class TestDeriveUnclearReason:
    def test_none_for_pass_and_fail(self):
        assert derive_unclear_reason("pass", {}) is None
        assert derive_unclear_reason("fail", {"error_status": "auth_error"}) is None

    def test_timeout_wins(self):
        assert derive_unclear_reason("unclear", {}, timeout_fired=True) == "timeout"

    def test_infra_failure_from_stage3_error_status(self):
        stage3 = {"response": "Error: ...", "error_status": "auth_error",
                  "error_detail": "Payment required (402)"}
        assert derive_unclear_reason("unclear", stage3) == "infra_failure"

    def test_low_confidence_otherwise(self):
        stage3 = {"response": "The verdict is unclear..."}
        assert derive_unclear_reason("unclear", stage3) == "low_confidence"

    def test_non_dict_stage3_is_low_confidence(self):
        assert derive_unclear_reason("unclear", None) == "low_confidence"


class TestSchemaField:
    def test_verify_response_carries_unclear_reason(self):
        from llm_council.verification.schemas import VerifyResponse

        resp = VerifyResponse(
            verification_id="v1",
            verdict="unclear",
            confidence=0.4,
            exit_code=2,
            rationale="r",
            transcript_location="/tmp/t",
            unclear_reason="low_confidence",
        )
        assert resp.unclear_reason == "low_confidence"
        # Default None (pass/fail results)
        resp2 = VerifyResponse(
            verification_id="v2",
            verdict="pass",
            confidence=0.9,
            exit_code=0,
            rationale="r",
            transcript_location="/tmp/t",
        )
        assert resp2.unclear_reason is None


class TestTimeoutPathSetsReason:
    @pytest.mark.asyncio
    async def test_timeout_result_carries_timeout_reason(self):
        from llm_council.verification.api import VerifyRequest, run_verification

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

        assert result["verdict"] == "unclear"
        assert result["unclear_reason"] == "timeout"
        assert result["exit_code"] == 2  # compat: exit code unchanged
