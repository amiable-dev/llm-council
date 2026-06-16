"""Regression tests for verdict extraction robustness (ADR-034).

A reasoning-only model returning null content, or a partial/timed-out stage 3,
yields a synthesis whose ``response`` is ``None`` (the key is present with a
None value, so ``.get("response", "")`` returns None — not ""). The verdict
extractors must degrade to an "unclear"/empty result instead of raising
``AttributeError: 'NoneType' object has no attribute ...``.
"""

import pytest

from llm_council.verdict import VerdictResult, VerdictType
from llm_council.verification.verdict_extractor import (
    build_verification_result,
    extract_blocking_issues,
    extract_verdict_from_synthesis,
)


def _binary(verdict: str, confidence: float, rationale: str = "ok") -> VerdictResult:
    return VerdictResult(
        verdict_type=VerdictType.BINARY,
        verdict=verdict,
        confidence=confidence,
        rationale=rationale,
    )


class TestExtractVerdictFromSynthesisHandlesNone:
    def test_response_is_none_returns_unclear(self):
        # Chairman returned null content (reasoning-only model / empty synthesis)
        verdict, confidence = extract_verdict_from_synthesis({"response": None})
        assert verdict == "unclear"
        assert 0.0 <= confidence <= 1.0

    def test_response_key_absent_returns_unclear(self):
        verdict, _ = extract_verdict_from_synthesis({})
        assert verdict == "unclear"

    def test_stage3_result_is_none_returns_unclear(self):
        # Whole synthesis failed/missing
        verdict, _ = extract_verdict_from_synthesis(None)
        assert verdict == "unclear"

    def test_normal_pass_still_works(self):
        verdict, _ = extract_verdict_from_synthesis(
            {"response": "The implementation is APPROVED and correct."}
        )
        assert verdict == "pass"


class TestExtractBlockingIssuesHandlesNone:
    @pytest.mark.parametrize("stage3", [{"response": None}, {}, None])
    def test_none_or_missing_synthesis_yields_no_issues(self, stage3):
        assert extract_blocking_issues(stage3) == []

    def test_issues_still_extracted_from_text(self):
        issues = extract_blocking_issues(
            {"response": "CRITICAL: null deref in foo.py:10"}
        )
        assert len(issues) == 1
        assert issues[0]["severity"] == "critical"


# ---------------------------------------------------------------------------
# #355: blocking-issue extraction must not turn approval/resolution prose into
# fabricated CRITICAL blockers.
# ---------------------------------------------------------------------------
class TestBlockingIssueMisparse:
    @pytest.mark.parametrize(
        "prose",
        [
            # Real strings observed in persisted result.json files.
            "The previously identified critical issues (double-tap race condition "
            "in advance() and modulo-zero crash) have been verifiably resolved.",
            "No blocking issues were identified.",
            "Both critical issues are fixed: advance() uses an answerRevealed guard.",
            "The council found no critical bugs and approved the change.",
            "This addresses a major refactor with minor cleanup throughout.",
        ],
    )
    def test_approval_prose_is_not_a_blocking_issue(self, prose):
        assert extract_blocking_issues({"response": prose}) == []

    def test_genuine_marked_issue_is_extracted(self):
        text = (
            "Summary of findings:\n"
            "- **CRITICAL**: SQL injection in handler.py:42\n"
            "MAJOR: missing auth check\n"
            "The critical issues above must be fixed."  # prose tail -> ignored
        )
        issues = extract_blocking_issues({"response": text})
        sevs = sorted(i["severity"] for i in issues)
        assert sevs == ["critical", "major"]


# ---------------------------------------------------------------------------
# #355: prefer the council's structured BINARY verdict over prose regex.
# ---------------------------------------------------------------------------
class TestStructuredVerdictPreferred:
    def test_approved_verdict_yields_pass_despite_negation_prose(self):
        # Prose mentions "failures"/"critical" which the legacy regex misreads
        # as rejection; the structured verdict is authoritative.
        stage3 = {
            "response": (
                "The council unanimously approved the change. The previously "
                "identified critical issues have been verifiably resolved and "
                "no failures remain."
            )
        }
        result = build_verification_result(
            [], [], stage3, confidence_threshold=0.7,
            verdict_result=_binary("approved", 0.95),
        )
        assert result["verdict"] == "pass"
        assert result["confidence"] == 0.95
        assert result["blocking_issues"] == []

    def test_rejected_verdict_yields_fail(self):
        stage3 = {"response": "Rejected.\n- **CRITICAL**: data loss in sync.py:9"}
        result = build_verification_result(
            [], [], stage3, verdict_result=_binary("rejected", 0.9),
        )
        assert result["verdict"] == "fail"
        assert any(i["severity"] == "critical" for i in result["blocking_issues"])

    def test_approved_low_confidence_downgrades_to_unclear(self):
        result = build_verification_result(
            [], [], {"response": "approved"}, confidence_threshold=0.7,
            verdict_result=_binary("approved", 0.5),
        )
        assert result["verdict"] == "unclear"

    def test_no_structured_verdict_falls_back_to_regex(self):
        # Backward compatibility: without verdict_result, the legacy regex path
        # drives the verdict (with realistic high-scoring reviews).
        stage2 = [
            {"rubric_scores": {"accuracy": 9, "completeness": 9, "clarity": 9}},
            {"rubric_scores": {"accuracy": 9, "completeness": 8, "clarity": 9}},
        ]
        result = build_verification_result(
            [], stage2, {"response": "The implementation is APPROVED."},
        )
        assert result["verdict"] == "pass"
