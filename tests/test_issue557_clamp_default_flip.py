"""#557: the coverage-clamp default flips `warn` → `clamp`.

The final step of ADR-053's rollout. `warn` shipped as the default in v0.40.0
so the clamp could land byte-identical; the flip was gated on (a) ≥2 minor
releases' notice and (b) a shadow-telemetry review.

Evidence reviewed 2026-09-18 before flipping — 30 real verify transcripts
carrying a coverage receipt (11 of them `pass`): **zero omissions of any kind
were recorded, so the clamp would have changed 0 runs (0%)**. The flip is a
no-op on the observed corpus and buys the guarantee prospectively. Sequencing
per the maintainer decision on #557: this lands only after the
`LLM_COUNCIL_FILE_SELECTION=content` default shipped (v0.44.0), which removed
the clamp's main noise source (`non-text` omissions of unlisted-extension
source files).

`warn` remains available as an explicit opt-out — but `gate` now refuses it,
because after the flip an explicit `warn` means "make this gate ignore
coverage", which is a foot-gun rather than the status quo.
"""

import pytest

from llm_council.verification import coverage


class TestDefaultIsNowClamp:
    def test_unset_defaults_to_clamp(self, monkeypatch):
        monkeypatch.delenv("LLM_COUNCIL_COVERAGE_POLICY", raising=False)
        assert coverage.coverage_policy() == "clamp"

    def test_invalid_value_falls_back_to_the_clamp_default(self, monkeypatch):
        monkeypatch.setenv("LLM_COUNCIL_COVERAGE_POLICY", "nonsense")
        assert coverage.coverage_policy() == "clamp"

    @pytest.mark.parametrize("val", ["clamp", "fail", "warn"])
    def test_explicit_values_are_still_honoured(self, monkeypatch, val):
        monkeypatch.setenv("LLM_COUNCIL_COVERAGE_POLICY", val)
        assert coverage.coverage_policy() == val


class TestGateNowRefusesAnExplicitWarn:
    def test_explicit_warn_is_refused_by_gate(self, monkeypatch):
        """Post-flip, `warn` is a deliberate downgrade — the one case the
        design always said should be refused."""
        monkeypatch.setenv("LLM_COUNCIL_COVERAGE_POLICY", "warn")
        assert coverage.gate_rejects_warn() is True

    def test_default_clamp_is_not_refused(self, monkeypatch):
        monkeypatch.delenv("LLM_COUNCIL_COVERAGE_POLICY", raising=False)
        assert coverage.gate_rejects_warn() is False


class TestClampFiresByDefault:
    def _cov(self, reason):
        return {
            "requested": ["a.py", "b.bin"],
            "reviewed": ["a.py"],
            "omitted": [{"path": "b.bin", "reason": reason, "origin": "changed"}],
            "explicit_omitted": False,
            "truncated": False,
            "conservation_ok": True,
        }

    def test_surprising_omission_clamps_a_pass_under_the_default(self, monkeypatch):
        monkeypatch.delenv("LLM_COUNCIL_COVERAGE_POLICY", raising=False)
        clampers = coverage.coverage_clamp_decision(
            "pass",
            self._cov("not_found"),
            coverage.coverage_policy(),
            coverage.coverage_ack_reasons(),
        )
        assert clampers and clampers[0]["path"] == "b.bin"

    def test_acknowledged_omission_still_passes_under_the_default(self, monkeypatch):
        """The ack list is what keeps the flip quiet: expected omissions
        (binary, generated, vendored, too_large, ignored, noise) never clamp."""
        monkeypatch.delenv("LLM_COUNCIL_COVERAGE_POLICY", raising=False)
        assert not coverage.coverage_clamp_decision(
            "pass",
            self._cov("binary"),
            coverage.coverage_policy(),
            coverage.coverage_ack_reasons(),
        )

    def test_clean_coverage_is_unaffected(self, monkeypatch):
        """The measured case: 30/30 real receipts had no omissions at all."""
        monkeypatch.delenv("LLM_COUNCIL_COVERAGE_POLICY", raising=False)
        cov = {
            "requested": ["a.py"],
            "reviewed": ["a.py"],
            "omitted": [],
            "explicit_omitted": False,
            "truncated": False,
            "conservation_ok": True,
        }
        assert not coverage.coverage_clamp_decision(
            "pass", cov, coverage.coverage_policy(), coverage.coverage_ack_reasons()
        )

    def test_explicit_warn_still_disables_the_clamp(self, monkeypatch):
        monkeypatch.setenv("LLM_COUNCIL_COVERAGE_POLICY", "warn")
        assert not coverage.coverage_clamp_decision(
            "pass",
            self._cov("not_found"),
            coverage.coverage_policy(),
            coverage.coverage_ack_reasons(),
        )


class TestAdvanceNoticeRetired:
    """The notice promised a flip; once flipped it must not still say 'will'."""

    def test_guide_no_longer_promises_a_future_flip(self):
        import pathlib

        guide = pathlib.Path("docs/guides/verify.md").read_text()
        assert "Upcoming default change" not in guide
        assert "clamp" in guide

    def test_env_reference_documents_clamp_as_the_default(self):
        import pathlib

        ref = pathlib.Path("docs/reference/environment-variables.md").read_text()
        row = [ln for ln in ref.splitlines() if "LLM_COUNCIL_COVERAGE_POLICY" in ln]
        assert row, "coverage policy row missing"
        assert "clamp" in row[0]
