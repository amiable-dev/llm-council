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

    def test_chairman_disabled_beats_low_confidence(self):
        # PR #519: chairman_disabled is a deliberate skip, not an incidental
        # low-confidence deliberation — must be distinguishable from both.
        stage3 = {"model": "m1", "response": "some peer answer", "chairman_disabled": True}
        assert derive_unclear_reason("unclear", stage3) == "chairman_disabled"

    def test_chairman_disabled_loses_to_timeout(self):
        # A starved chairman is a scheduling problem even if it happened to
        # also be configured with chairman_disabled — timeout is checked first.
        stage3 = {"chairman_disabled": True}
        assert derive_unclear_reason("unclear", stage3, timeout_fired=True) == "timeout"


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


class TestCouncilRound1:
    def test_build_verification_result_survives_none_stage3(self):
        # #434 r1: rationale extraction used a bare .get on stage3_result —
        # None (chairman never produced a dict) raised AttributeError while
        # every sibling extractor already None-coalesces.
        from llm_council.verification.verdict_extractor import (
            build_verification_result,
        )

        out = build_verification_result([], [], None, confidence_threshold=0.7)
        assert out["verdict"] == "unclear"
        assert isinstance(out["rationale"], str)


class TestChairmanDisabledVerdict:
    """PR #519 review: chairman_disabled must not silently produce a
    fabricated pass/fail on the BINARY verdict path (council-verify /
    council-gate). A raw peer answer to the original query is not a verdict
    and must never be scraped by the legacy regex extractor or the
    structured-findings parser as if it were one."""

    def _chairman_disabled_stage3(self, response="The answer to your question is 42."):
        return {"model": "peer-model", "response": response, "chairman_disabled": True}

    def test_verdict_is_unclear_not_scraped(self):
        from llm_council.verification.verdict_extractor import build_verification_result

        # A response containing approval-sounding language would flip a
        # naive regex scrape to "pass" — must not happen here.
        stage3 = self._chairman_disabled_stage3(
            "Yes, this looks correct and approved, no issues found."
        )
        out = build_verification_result([], [], stage3, confidence_threshold=0.7)

        assert out["verdict"] == "unclear"
        assert out["blocking_issues"] == []
        assert out["diagnostics"]["verdict_source"] == "chairman_disabled"
        assert out["diagnostics"]["findings_source"] == "skipped"

    def test_ignores_verdict_result_when_chairman_disabled(self):
        # Belt-and-suspenders: even if a caller mistakenly passes a stale
        # verdict_result alongside a chairman_disabled stage3_result, the
        # explicit chairman_disabled marker on stage3_result wins.
        from llm_council.verification.verdict_extractor import build_verification_result

        out = build_verification_result(
            [],
            [],
            self._chairman_disabled_stage3(),
            confidence_threshold=0.7,
            verdict_result="not-a-real-verdict-result",
        )
        assert out["verdict"] == "unclear"
        assert out["diagnostics"]["verdict_source"] == "chairman_disabled"

    def test_rubric_scores_still_computed(self):
        # Rubric scores come from stage2 peer review, which still ran —
        # only the chairman step was skipped, so this data remains useful.
        from llm_council.verification.verdict_extractor import build_verification_result

        stage2 = [
            {
                "model": "m1",
                "ranking": "1. Response A",
                "parsed_ranking": {"ranking": ["Response A"]},
                "rubric_scores": {"accuracy": 8.0, "relevance": 9.0},
            }
        ]
        out = build_verification_result([], stage2, self._chairman_disabled_stage3())
        assert out["rubric_scores"]["accuracy"] == 8.0
        assert out["rubric_scores"]["relevance"] == 9.0

    def test_end_to_end_unclear_reason_via_api_helper(self):
        # derive_unclear_reason is fed the verdict this function returns —
        # confirm the two compose to the documented "chairman_disabled" reason.
        from llm_council.verification.verdict_extractor import (
            build_verification_result,
            derive_unclear_reason,
        )

        out = build_verification_result([], [], self._chairman_disabled_stage3())
        reason = derive_unclear_reason(out["verdict"], self._chairman_disabled_stage3())
        assert reason == "chairman_disabled"
