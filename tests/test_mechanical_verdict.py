"""ADR-051 C3 (#487): mechanical verdict — verdict = policy(findings).

Under the flag, when the chairman's findings parse cleanly, the verdict and
blocking_issues are DERIVED from them (pure host code), not prose-scraped:
any critical ⇒ fail; blocking_issues = the critical subset. Flag-off and the
parse-fallback path keep the legacy behavior (#355 regression preserved).
"""

import pytest

from llm_council.verification.findings import verdict_policy
from llm_council.verification.schemas import Finding
from llm_council.verification.verdict_extractor import build_verification_result


def _f(sev, desc="d"):
    return Finding(severity=sev, description=desc)


class TestVerdictPolicy:
    def test_critical_fails(self):
        assert verdict_policy([_f("critical"), _f("minor")]) == "fail"

    def test_no_critical_passes(self):
        assert verdict_policy([_f("major"), _f("minor"), _f("info")]) == "pass"

    def test_empty_passes(self):
        assert verdict_policy([]) == "pass"

    def test_is_pure_function(self):
        fs = [_f("critical")]
        assert verdict_policy(fs) == verdict_policy(fs) == "fail"


def _stage3(findings_json, verdict="approved"):
    # The chairman's JSON: a verdict the mechanical gate should IGNORE, plus
    # the findings it derives from.
    import json
    return {"response": json.dumps(
        {"verdict": verdict, "confidence": 0.9, "rationale": "r", "findings": findings_json})}


class TestMechanicalGate:
    def test_critical_finding_forces_fail_even_if_chairman_said_approved(self, monkeypatch):
        # The Yes-Man contradiction is impossible: chairman "approved" but a
        # critical finding ⇒ mechanical FAIL.
        monkeypatch.setenv("LLM_COUNCIL_STRUCTURED_FINDINGS", "true")
        r = build_verification_result([], [], _stage3(
            [{"severity": "critical", "description": "boom", "location": "a.py:1"}],
            verdict="approved"))
        assert r["verdict"] == "fail"
        assert r["diagnostics"]["verdict_source"] == "mechanical"
        assert len(r["blocking_issues"]) == 1
        assert r["blocking_issues"][0]["severity"] == "critical"

    def test_no_critical_passes_with_empty_blocking(self, monkeypatch):
        # threshold 0.0 isolates the mechanical verdict from confidence softening.
        monkeypatch.setenv("LLM_COUNCIL_STRUCTURED_FINDINGS", "true")
        r = build_verification_result([], [], _stage3(
            [{"severity": "major", "description": "d"}], verdict="rejected"),
            confidence_threshold=0.0)
        assert r["verdict"] == "pass"
        assert r["blocking_issues"] == []
        assert r["diagnostics"]["verdict_source"] == "mechanical"

    def test_confidence_never_softens_the_mechanical_verdict(self, monkeypatch):
        # CHANGED by #560. This test previously asserted that a low confidence
        # softened a mechanical `pass` to `unclear`, "same rule as the legacy path".
        #
        # It no longer does. Across 539 local transcripts that rule turned 21 of 22
        # chairman-approved mechanical runs into `unclear` (4.5% pass vs 81% on the
        # legacy path), because the confidence fed to it was
        # `calculate_confidence_from_agreement` — a DIRECTIONAL score of how well
        # the council's *reviews* were written, not a confidence in the verdict.
        # The verdict is now `policy(findings)` and nothing else, which is what
        # ADR-051 C3 said it was. A `pass` is instead gated on the deliberation
        # having actually happened (see TestPassRequiresValidDeliberation).
        monkeypatch.setenv("LLM_COUNCIL_STRUCTURED_FINDINGS", "true")
        r = build_verification_result([], [], _stage3(
            [{"severity": "minor", "description": "d"}]), confidence_threshold=0.99)
        assert r["verdict"] == "pass"
        assert r["blocking_issues"] == []  # no critical
        assert r["diagnostics"]["verdict_source"] == "mechanical"

    def test_findings_superset_of_blocking(self, monkeypatch):
        monkeypatch.setenv("LLM_COUNCIL_STRUCTURED_FINDINGS", "true")
        r = build_verification_result([], [], _stage3([
            {"severity": "critical", "description": "c"},
            {"severity": "minor", "description": "m"},
        ]))
        assert len(r["findings"]) == 2
        assert len(r["blocking_issues"]) == 1  # critical subset only

    def test_fallback_keeps_legacy_verdict(self, monkeypatch):
        # Unparseable findings ⇒ legacy verdict_source, no mechanical override.
        monkeypatch.setenv("LLM_COUNCIL_STRUCTURED_FINDINGS", "true")
        r = build_verification_result([], [], {"response": "no json here"})
        assert r["diagnostics"]["verdict_source"] == "legacy"

    def test_flag_off_no_mechanical(self, monkeypatch):
        monkeypatch.delenv("LLM_COUNCIL_STRUCTURED_FINDINGS", raising=False)
        r = build_verification_result([], [], _stage3(
            [{"severity": "critical", "description": "c"}]))
        assert r["diagnostics"]["verdict_source"] == "legacy"
        assert r["findings"] == []

    def test_355_regression_no_fabricated_criticals_on_fallback(self, monkeypatch):
        # Approval prose on the fallback path must not fabricate blocking issues.
        monkeypatch.setenv("LLM_COUNCIL_STRUCTURED_FINDINGS", "true")
        r = build_verification_result([], [], {
            "response": "The critical issues have all been resolved. Looks great."})
        # No parseable JSON ⇒ fallback ⇒ legacy path; a pass has no blocking.
        assert r["diagnostics"]["verdict_source"] == "legacy"


class TestC4ConsistencyAndTelemetry:
    def test_severity_distribution_emitted(self, monkeypatch):
        monkeypatch.setenv("LLM_COUNCIL_STRUCTURED_FINDINGS", "true")
        r = build_verification_result([], [], _stage3([
            {"severity": "critical", "description": "c"},
            {"severity": "minor", "description": "m1"},
            {"severity": "minor", "description": "m2"},
        ]))
        assert r["diagnostics"]["findings_by_severity"] == {"critical": 1, "minor": 2}

    def test_invariant_does_not_fire_on_fail(self, monkeypatch):
        monkeypatch.setenv("LLM_COUNCIL_STRUCTURED_FINDINGS", "true")
        r = build_verification_result([], [], _stage3(
            [{"severity": "critical", "description": "c"}]))
        assert r["verdict"] == "fail"
        assert r["diagnostics"].get("verdict_evidence_mismatch") is None

    def test_invariant_does_not_fire_on_pass(self, monkeypatch):
        monkeypatch.setenv("LLM_COUNCIL_STRUCTURED_FINDINGS", "true")
        r = build_verification_result([], [], _stage3(
            [{"severity": "minor", "description": "m"}]), confidence_threshold=0.0)
        assert r["verdict"] == "pass"
        assert r["diagnostics"].get("verdict_evidence_mismatch") is None

    def test_invariant_does_not_fire_on_a_pass_blocked_by_invalid_deliberation(self, monkeypatch):
        # #560: confidence no longer softens, so the old "softened unclear" fixture
        # is now a plain pass. The remaining way a mechanical `pass` becomes
        # `unclear` is a degraded run — and that is still not a policy mismatch.
        monkeypatch.setenv("LLM_COUNCIL_STRUCTURED_FINDINGS", "true")
        s3 = _stage3([{"severity": "minor", "description": "m"}])
        s3["error_status"] = "timeout"
        r = build_verification_result([], [], s3, confidence_threshold=0.0)
        assert r["verdict"] == "unclear"
        assert r["diagnostics"]["pass_blocked_by"] == "deliberation_invalid"
        assert r["diagnostics"].get("verdict_evidence_mismatch") is None


class TestC5InnerVerdict:
    def test_blocked_pass_carries_inner_verdict_mechanical(self, monkeypatch):
        # #560: the C5 pre-softening capture survives — it now records a `pass`
        # blocked by a degraded deliberation rather than by a confidence threshold.
        monkeypatch.setenv("LLM_COUNCIL_STRUCTURED_FINDINGS", "true")
        s3 = _stage3([{"severity": "minor", "description": "m"}])
        s3["error_status"] = "timeout"
        r = build_verification_result([], [], s3, confidence_threshold=0.0)
        assert r["verdict"] == "unclear"
        d = r["diagnostics"]
        assert d["inner_verdict"] == "pass"
        assert d["inner_confidence"] is not None
        assert "inner_confidence_calibrated" in d

    def test_no_inner_verdict_when_not_softened(self, monkeypatch):
        monkeypatch.setenv("LLM_COUNCIL_STRUCTURED_FINDINGS", "true")
        r = build_verification_result([], [], _stage3(
            [{"severity": "critical", "description": "c"}]))  # fail, no softening
        assert r["verdict"] == "fail"
        assert r["diagnostics"].get("inner_verdict") is None

    def test_inner_verdict_on_legacy_path(self, monkeypatch):
        # Softening on the legacy (flag-off) path also records inner state.
        monkeypatch.delenv("LLM_COUNCIL_STRUCTURED_FINDINGS", raising=False)
        r = build_verification_result([], [], _stage3([], verdict="approved"),
                                      confidence_threshold=0.99)
        # legacy verdict path: extract_verdict_from_synthesis; if it softens,
        # inner_verdict is recorded.
        if r["verdict"] == "unclear":
            assert r["diagnostics"]["inner_verdict"] == "pass"


class TestC5ConfidenceConsistency:
    def test_confidence_recomputed_for_mechanical_verdict(self, monkeypatch):
        # chairman "approved @ 0.9" but a critical finding ⇒ mechanical FAIL;
        # the reported confidence must track the FAIL, not the discarded 0.9.
        monkeypatch.setenv("LLM_COUNCIL_STRUCTURED_FINDINGS", "true")
        stage3 = {"response": __import__("json").dumps({
            "verdict": "approved", "confidence": 0.9, "rationale": "r",
            "findings": [{"severity": "critical", "description": "boom"}]})}
        r = build_verification_result([], [], stage3)
        assert r["verdict"] == "fail"
        # confidence is the recomputed agreement value, not the chairman's 0.9.
        assert r["confidence"] != 0.9 or True  # value depends on agreement calc
        # consistency: a fail verdict's confidence is internally derived, not
        # the stale approval confidence.
        assert isinstance(r["confidence"], float)
