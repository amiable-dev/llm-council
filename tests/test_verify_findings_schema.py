"""ADR-051 C1 (#485): flag + additive findings/diagnostics schema (foundation).

The whole ADR-051 epic ships behind LLM_COUNCIL_STRUCTURED_FINDINGS (default
off). C1 adds only the schema + flag — no emission yet (C2) — so it is purely
additive and non-breaking: the new response fields default empty and no
existing field changes.
"""

import pytest

from llm_council.verification.findings import structured_findings_enabled
from llm_council.verification.schemas import (
    Finding,
    VerifyDiagnostics,
    VerifyResponse,
)


class TestFlag:
    def test_default_off(self, monkeypatch):
        monkeypatch.delenv("LLM_COUNCIL_STRUCTURED_FINDINGS", raising=False)
        assert structured_findings_enabled() is False

    def test_on(self, monkeypatch):
        monkeypatch.setenv("LLM_COUNCIL_STRUCTURED_FINDINGS", "true")
        assert structured_findings_enabled() is True

    def test_falsey_values_off(self, monkeypatch):
        for v in ("false", "0", "no", ""):
            monkeypatch.setenv("LLM_COUNCIL_STRUCTURED_FINDINGS", v)
            assert structured_findings_enabled() is False


class TestFindingModel:
    def test_minimal(self):
        f = Finding(severity="critical", description="null deref at line 42")
        assert f.severity == "critical"
        assert f.location is None and f.dimension is None

    def test_full(self):
        f = Finding(severity="major", description="d", location="x.py:10",
                    dimension="correctness")
        assert f.location == "x.py:10"

    def test_severity_is_constrained(self):
        with pytest.raises(Exception):
            Finding(severity="blocker", description="d")  # not in the enum

    def test_all_severities_valid(self):
        for s in ("critical", "major", "minor", "info"):
            assert Finding(severity=s, description="d").severity == s


class TestDiagnosticsModel:
    def test_defaults(self):
        d = VerifyDiagnostics()
        assert d.inner_verdict is None
        assert d.findings_source == "fallback"
        assert d.verdict_source == "legacy"
        assert d.verdict_evidence_mismatch is None


class TestVerifyResponseAdditive:
    def _base(self, **kw):
        base = dict(
            verification_id="v1", verdict="pass", confidence=0.9, exit_code=0,
            rationale="ok", transcript_location="/tmp/t",
        )
        base.update(kw)
        return VerifyResponse(**base)

    def test_new_fields_default_empty(self):
        # Additive + non-breaking: absent findings/diagnostics ⇒ empty defaults,
        # existing fields untouched.
        r = self._base()
        assert r.findings == []
        assert isinstance(r.diagnostics, VerifyDiagnostics)
        assert r.blocking_issues == []  # unchanged
        assert r.verdict == "pass"

    def test_accepts_populated_findings(self):
        r = self._base(findings=[Finding(severity="critical", description="d")])
        assert r.findings[0].severity == "critical"

    def test_existing_contract_unchanged(self):
        # A pre-C1 payload (no findings/diagnostics keys) still validates.
        r = self._base(verdict="fail", exit_code=1,
                       blocking_issues=[{"severity": "critical", "description": "x"}])
        assert r.verdict == "fail"
        assert r.blocking_issues[0].severity == "critical"
