"""Regression tests for #560 / #561 — the mechanical gate must actually be mechanical.

Across 539 local verify transcripts, enabling `LLM_COUNCIL_STRUCTURED_FINDINGS`
collapsed the chairman-approved → `pass` rate from **81% (legacy) to 4.5%
(mechanical)**: 21 of 22 approvals were softened to `unclear`.

Cause: the mechanical block recomputed confidence with
`calculate_confidence_from_agreement`, which scores the **quality of the
council's reviews** ("I'll evaluate each response based on how well it *reviews*
this ADR") — and does so *directionally*:

    pass: (mean_score - 5) / 5          # good reviews  => confident PASS
    fail: (5 - mean_score) / 5 + 0.5    # bad reviews   => confident FAIL

so a well-argued FAIL was reported at the 0.3 floor, and a clean artifact
reviewed by articulate models was denied `pass`.

The chairman's own self-report cannot replace it either: across the corpus it
never drops below 0.85 (stdev 0.034), so `conf < 0.7` would be permanently inert.

Fix: the verdict is `policy(findings)` and nothing else (#560a). A `pass` is
instead gated only on the deliberation having actually happened -- a chairman
schema violation or a stage-3 error (#560b). Chairman/findings discordance is
RECORDED, not gated: overruling `policy(findings)` with the chairman's stated
verdict would restore the authority ADR-051 deliberately removed.
And `parse_binary_verdict` now shares the findings parser's extractor (#561).
"""

import json
import pathlib
from typing import Any, Dict, List

import pytest

from llm_council.verification.verdict_extractor import (
    build_verification_result,
    derive_unclear_reason,
)

pytestmark = pytest.mark.usefixtures("_structured_findings_on")


@pytest.fixture
def _structured_findings_on(monkeypatch):
    monkeypatch.setenv("LLM_COUNCIL_STRUCTURED_FINDINGS", "true")


def _stage2(scores: List[float]) -> List[Dict[str, Any]]:
    return [
        {"parsed_ranking": {"ranking": ["Response A", "Response B"], "scores": {"overall": s}}}
        for s in scores
    ]


def _stage1(n: int = 3) -> List[Dict[str, Any]]:
    return [{"model": f"m{i}", "response": "..."} for i in range(n)]


class _Chairman:
    def __init__(self, verdict: str, confidence: float = 0.95):
        self.verdict = verdict  # "approved" | "rejected"
        self.confidence = confidence


def _chairman_json(verdict: str, findings: List[Dict[str, str]], fenced: bool = True) -> str:
    payload = {
        "findings": findings,  # findings-first, as ADR-051 specifies
        "verdict": verdict,
        "confidence": 0.95,
        "rationale": "because",
    }
    body = json.dumps(payload)
    return f"```json\n{body}\n```" if fenced else body


CLEAN = []  # zero findings
MAJOR_ONLY = [{"severity": "major", "description": "d", "location": "f.py"}]
CRITICAL = [{"severity": "critical", "description": "d", "location": "f.py"}]


class TestPassIsNoLongerVetoedByReviewQuality:
    @pytest.mark.parametrize("scores", [[7, 7, 7, 7, 7], [6, 7, 6, 7, 6], [9, 9, 9, 9, 9]])
    def test_clean_findings_pass_regardless_of_reviewer_rubric(self, scores):
        """The exact regression: unanimous 7/10 reviews used to force unclear."""
        result = build_verification_result(
            stage1_results=_stage1(),
            stage2_results=_stage2(scores),
            stage3_result={"response": _chairman_json("approved", CLEAN)},
            verdict_result=_Chairman("approved"),
        )
        assert result["verdict"] == "pass", (
            f"reviewer rubric {scores} vetoed a mechanical pass with zero findings"
        )
        assert (result["diagnostics"] or {}).get("pass_blocked_by") is None

    def test_fail_confidence_is_not_floored_by_good_reviews(self):
        """A 95%-confident rejection backed by a critical finding was reported at 0.26."""
        result = build_verification_result(
            stage1_results=_stage1(),
            stage2_results=_stage2([10, 8, 7, 8, 7]),
            stage3_result={"response": _chairman_json("rejected", CRITICAL)},
            verdict_result=_Chairman("rejected", 0.95),
        )
        assert result["verdict"] == "fail"
        assert result["confidence"] >= 0.9, (
            f"confidence {result['confidence']} — the agreement heuristic is still "
            "punishing a well-reviewed FAIL"
        )

    def test_agreement_figure_is_still_published_under_its_real_name(self):
        result = build_verification_result(
            stage1_results=_stage1(),
            stage2_results=_stage2([7, 7, 7]),
            stage3_result={"response": _chairman_json("approved", CLEAN)},
            verdict_result=_Chairman("approved"),
        )
        d = result["diagnostics"]
        assert isinstance(d.get("deliberation_agreement"), float)
        assert d["deliberation_agreement"] != result["confidence"]


class TestPassRequiresAValidDeliberation:
    def test_pass_blocked_when_chairman_verdict_did_not_parse(self):
        """#544's verdict_parse becomes the validity precondition."""
        result = build_verification_result(
            stage1_results=_stage1(),
            stage2_results=_stage2([9, 9, 9]),
            stage3_result={
                "response": _chairman_json("approved", CLEAN),
                "verdict_parse_error": "ValueError: Missing required field: verdict",
            },
            verdict_result=None,
        )
        d = result["diagnostics"]
        assert result["verdict"] == "unclear"
        assert d["pass_blocked_by"] == "deliberation_invalid"
        assert derive_unclear_reason("unclear", {}, diagnostics=d) == "infra_failure"

    def test_absent_chairman_verdict_does_not_block_pass(self):
        """`absent` != `error`. ADR-051 made the verdict channel non-authoritative."""
        result = build_verification_result(
            stage1_results=_stage1(),
            stage2_results=_stage2([9, 9, 9]),
            stage3_result={"response": _chairman_json("approved", CLEAN)},
            verdict_result=None,  # no parse error, just no structured verdict
        )
        assert result["verdict"] == "pass"
        assert (result["diagnostics"] or {}).get("pass_blocked_by") is None

    def test_pass_blocked_when_stage3_errored(self):
        result = build_verification_result(
            stage1_results=_stage1(),
            stage2_results=_stage2([9, 9, 9]),
            stage3_result={
                "response": _chairman_json("approved", CLEAN),
                "error_status": "timeout",
            },
            verdict_result=_Chairman("approved"),
        )
        assert result["verdict"] == "unclear"
        assert result["diagnostics"]["pass_blocked_by"] == "deliberation_invalid"

    def test_inner_verdict_records_the_blocked_pass(self):
        """ADR-051 C5's pre-softening capture must survive the new gate."""
        result = build_verification_result(
            stage1_results=_stage1(),
            stage2_results=_stage2([9, 9, 9]),
            stage3_result={
                "response": _chairman_json("approved", CLEAN),
                "verdict_parse_error": "ValueError: Missing required field: rationale",
            },
            verdict_result=None,
        )
        assert result["diagnostics"]["inner_verdict"] == "pass"


class TestChairmanFindingsConcordance:
    def test_chairman_rejected_but_no_critical_finding_is_marked_not_gated(self):
        """4 of 76 real mechanical runs, previously flagged 0 times.

        The verdict still comes from policy(findings) — ADR-051's central decision,
        pinned by test_mechanical_verdict::test_no_critical_passes_with_empty_blocking.
        Gating on the chairman's stated verdict would restore the authority ADR-051
        deliberately removed. We surface it; we do not act on it.
        """
        result = build_verification_result(
            stage1_results=_stage1(),
            stage2_results=_stage2([8, 8, 8]),
            stage3_result={"response": _chairman_json("rejected", MAJOR_ONLY)},
            verdict_result=_Chairman("rejected"),
        )
        d = result["diagnostics"]
        assert result["verdict"] == "pass"  # findings win
        assert d["verdict_evidence_mismatch"] == "chairman_contradicts_findings"
        assert d.get("pass_blocked_by") is None

    def test_concordant_rejection_is_a_clean_fail(self):
        result = build_verification_result(
            stage1_results=_stage1(),
            stage2_results=_stage2([8, 8, 8]),
            stage3_result={"response": _chairman_json("rejected", CRITICAL)},
            verdict_result=_Chairman("rejected"),
        )
        assert result["verdict"] == "fail"
        assert (result["diagnostics"] or {}).get("verdict_evidence_mismatch") is None


class TestIssue561ExtractorUnification:
    def test_findings_first_unfenced_payload_parses(self):
        """The real bff6de55 shape: bare JSON, findings first, no code fence."""
        from llm_council.verdict import parse_binary_verdict

        v = parse_binary_verdict(_chairman_json("rejected", CRITICAL, fenced=False))
        assert v.verdict == "rejected" and v.confidence == 0.95

    def test_findings_first_fenced_payload_parses(self):
        from llm_council.verdict import parse_binary_verdict

        v = parse_binary_verdict(_chairman_json("approved", CLEAN, fenced=True))
        assert v.verdict == "approved"

    def test_verdict_and_findings_parsers_share_one_extractor(self):
        from llm_council.json_extract import extract_json_object
        from llm_council.verification.findings import _extract_json_object

        assert _extract_json_object is extract_json_object


REAL = pathlib.Path(".council/logs")


@pytest.mark.skipif(not REAL.is_dir(), reason="no local transcripts")
class TestReplayRealTranscripts:
    def test_real_chairman_payloads_now_parse(self):
        """Replay the two transcripts that motivated #544/#560/#561."""
        from llm_council.verdict import parse_binary_verdict

        seen = 0
        for d in REAL.glob("*/stage3.json"):
            raw = json.loads(d.read_text()).get("synthesis", {}).get("response")
            if not raw or '"findings"' not in raw:
                continue
            v = parse_binary_verdict(raw)  # must not raise
            assert v.verdict in ("approved", "rejected")
            assert 0.0 <= v.confidence <= 1.0
            seen += 1
        assert seen > 0, "no findings-bearing transcripts replayed"
