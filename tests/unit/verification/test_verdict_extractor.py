"""Regression tests for verdict extraction robustness (ADR-034).

A reasoning-only model returning null content, or a partial/timed-out stage 3,
yields a synthesis whose ``response`` is ``None`` (the key is present with a
None value, so ``.get("response", "")`` returns None — not ""). The verdict
extractors must degrade to an "unclear"/empty result instead of raising
``AttributeError: 'NoneType' object has no attribute ...``.
"""

import pytest

from llm_council.verification.verdict_extractor import (
    extract_blocking_issues,
    extract_verdict_from_synthesis,
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
