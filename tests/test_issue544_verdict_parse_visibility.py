"""Regression tests for #544 — a binary-verdict parse failure must leave a trace.

`council_stages.stage3_synthesize_final` parses the chairman's ADR-025b BINARY
`VerdictResult`. When that JSON is malformed — most commonly a missing `verdict`
key — the `except ValueError` logs a warning and leaves `verdict_result = None`.
Nothing about that reaches the response.

`build_verification_result` then takes the legacy prose-regex branch.
`diagnostics.fallback_reason` is set only by the *findings* parser (behind
`LLM_COUNCIL_STRUCTURED_FINDINGS`), never by the *verdict* parser, so:

- With the flag OFF (the default), `verdict_source` reads `"legacy"` — which is
  indistinguishable from "structured findings are simply disabled". A caller
  cannot tell a clean legacy run from one where the chairman's verdict JSON was
  malformed and the verdict was scraped out of prose.
- With the flag ON, the mechanical gate overrides the verdict anyway, so the
  parse failure has no effect on the verdict — but it is still the only signal
  that the chairman's structured output is degrading, and it is discarded.

Observed on two real runs (`bff6de55`, `dc7acb57`), chairman
`google/gemini-3.1-pro-preview`, stderr `Failed to parse binary verdict: Missing
required field: verdict`, while `diagnostics` carried no `fallback_reason` at all.

NOTE on scope: these runs also reported confidence ~0.27. That is **not** caused
by the parse failure — on the mechanical path confidence is always recomputed by
`calculate_confidence_from_agreement(stage2_results, mechanical)`. See the
separate issue on the mechanical path inheriting the legacy agreement heuristic.
"""

from typing import Any, Dict, List

import pytest

from llm_council.verification.verdict_extractor import build_verification_result


def _stage2(scores: List[float]) -> List[Dict[str, Any]]:
    return [
        {"parsed_ranking": {"ranking": ["Response A", "Response B"], "scores": {"overall": s}}}
        for s in scores
    ]


class _StructuredVerdict:
    """Minimal stand-in for a parsed ADR-025b BINARY VerdictResult."""

    def __init__(self, verdict: str = "pass", confidence: float = 0.9):
        self.verdict = verdict
        self.confidence = confidence
        self.approved = verdict == "pass"


class TestVerdictParseIsVisible:
    def test_parse_error_is_surfaced_in_diagnostics(self):
        """A malformed verdict block must be recorded, not merely logged."""
        stage3 = {
            "model": "chairman",
            "response": "The work looks acceptable overall.",
            # what stage3_synthesize_final records when parse_binary_verdict raises
            "verdict_parse_error": "ValueError: Missing required field: verdict",
        }

        result = build_verification_result(
            stage1_results=[],
            stage2_results=_stage2([8, 8, 8]),
            stage3_result=stage3,
            verdict_result=None,  # parse failed
        )

        diagnostics = result.get("diagnostics") or {}
        assert diagnostics.get("verdict_parse") == "error", (
            "a binary-verdict parse failure leaves no trace in the response; "
            "verdict_source='legacy' is indistinguishable from 'flag is off'"
        )
        assert "Missing required field" in (diagnostics.get("verdict_parse_error") or "")

    def test_successful_parse_is_recorded_as_ok(self):
        result = build_verification_result(
            stage1_results=[],
            stage2_results=_stage2([9, 9, 9]),
            stage3_result={"model": "chairman", "response": "Approved."},
            verdict_result=_StructuredVerdict("pass", 0.9),
        )
        diagnostics = result.get("diagnostics") or {}
        assert diagnostics.get("verdict_parse") == "ok"
        assert "verdict_parse_error" not in diagnostics

    def test_absent_verdict_without_error_is_distinguishable(self):
        """No verdict_result and no parse error (e.g. non-BINARY mode) != a parse failure."""
        result = build_verification_result(
            stage1_results=[],
            stage2_results=_stage2([8, 8, 8]),
            stage3_result={"model": "chairman", "response": "Approved."},
            verdict_result=None,
        )
        diagnostics = result.get("diagnostics") or {}
        assert diagnostics.get("verdict_parse") == "absent"
        assert "verdict_parse_error" not in diagnostics


class TestStage3RecordsTheParseError:
    def test_stage3_stores_parse_error_on_the_result_dict(self):
        """The `except ValueError` in stage3 must persist the reason, not just log it."""
        import llm_council.council_stages as cs

        # Exercise the narrow contract: a malformed BINARY payload must leave
        # `verdict_parse_error` on the returned stage-3 dict.
        response: Dict[str, Any] = {"content": "no json here", "usage": {}}
        cs._record_verdict_parse_error(response, ValueError("Missing required field: verdict"))

        assert response["verdict_parse_error"] == "ValueError: Missing required field: verdict"

    def test_helper_is_idempotent_and_never_raises(self):
        import llm_council.council_stages as cs

        response: Dict[str, Any] = {}
        cs._record_verdict_parse_error(response, ValueError("x"))
        cs._record_verdict_parse_error(response, ValueError("y"))
        # last writer wins; telemetry must never raise
        assert response["verdict_parse_error"].endswith("y")
