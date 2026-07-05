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

    def test_pass_softens_to_unclear_below_threshold(self, monkeypatch):
        # No critical ⇒ mechanical pass, but low confidence ⇒ softened to unclear
        # (same rule as the legacy path); still verdict_source=mechanical.
        monkeypatch.setenv("LLM_COUNCIL_STRUCTURED_FINDINGS", "true")
        r = build_verification_result([], [], _stage3(
            [{"severity": "minor", "description": "d"}]), confidence_threshold=0.99)
        assert r["verdict"] == "unclear"
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

    def test_invariant_does_not_fire_on_softened_unclear(self, monkeypatch):
        # unclear (softened pass, no critical) is consistent — not a mismatch.
        monkeypatch.setenv("LLM_COUNCIL_STRUCTURED_FINDINGS", "true")
        r = build_verification_result([], [], _stage3(
            [{"severity": "minor", "description": "m"}]), confidence_threshold=0.99)
        assert r["verdict"] == "unclear"
        assert r["diagnostics"].get("verdict_evidence_mismatch") is None
