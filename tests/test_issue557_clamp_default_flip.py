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

import pathlib

import pytest

from llm_council.verification import coverage

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _hermetic_env(monkeypatch):
    """#681 gate: the clamp tests cleared the policy var but not the ack list,
    so an ambient LLM_COUNCIL_COVERAGE_ACK_REASONS could reverse both the
    `not_found` (clamps) and `binary` (does not clamp) expectations."""
    monkeypatch.delenv("LLM_COUNCIL_COVERAGE_ACK_REASONS", raising=False)


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
    """The notice promised a flip; once flipped it must not still say 'will'.

    #681 gate: the first cut asserted only `"clamp" in guide`, which any row
    merely listing `warn|clamp|fail` as allowed values satisfies — the docs
    could still have called `warn` the default and passed. Pinned properly now.
    """

    def test_guide_no_longer_promises_a_future_flip(self):
        guide = (REPO_ROOT / "docs/guides/verify.md").read_text()
        assert "Upcoming default change" not in guide
        assert "will flip" not in guide
        assert "The clamp is the default" in guide

    def test_env_reference_documents_clamp_as_the_default(self):
        ref = (REPO_ROOT / "docs/reference/environment-variables.md").read_text()
        row = next(
            (ln for ln in ref.splitlines() if "LLM_COUNCIL_COVERAGE_POLICY" in ln), None
        )
        assert row, "coverage policy row missing"
        # the Default column is the last cell of the table row
        default_cell = [c.strip() for c in row.strip().strip("|").split("|")][-1]
        assert default_cell == "clamp", f"documented default is {default_cell!r}"
        assert "default `warn`" not in row


class TestExplicitOriginClampsUnconditionally:
    """#681 gate (major): an explicitly-named path clamps regardless of reason,
    and post-flip `gate` refuses the only workaround (`warn`). That is the
    documented contract — a caller who NAMES a path is owed a review of it —
    but it is newly reachable by default, so it is pinned and release-noted
    rather than left implicit."""

    def test_named_path_clamps_even_for_an_acknowledged_reason(self, monkeypatch):
        monkeypatch.delenv("LLM_COUNCIL_COVERAGE_POLICY", raising=False)
        cov = {
            "requested": ["logo.png"],
            "reviewed": [],
            "omitted": [
                {"path": "logo.png", "reason": "binary", "origin": "explicit"}
            ],
            "explicit_omitted": True,
            "truncated": False,
            "conservation_ok": True,
        }
        clampers = coverage.coverage_clamp_decision(
            "pass", cov, coverage.coverage_policy(), coverage.coverage_ack_reasons()
        )
        assert clampers and clampers[0]["origin"] == "explicit", (
            "`binary` is acknowledged, but naming the path is a caller contract"
        )


class TestRobustness:
    def test_ack_reasons_are_case_insensitive(self, monkeypatch):
        """#681 gate: coverage_policy() lowercased but this did not, so
        ACK_REASONS="Binary" silently failed to acknowledge `binary`."""
        monkeypatch.setenv("LLM_COUNCIL_COVERAGE_ACK_REASONS", "Binary, NOT_FOUND")
        assert coverage.coverage_ack_reasons() == frozenset({"binary", "not_found"})

    def test_malformed_receipt_degrades_instead_of_raising(self, monkeypatch):
        monkeypatch.delenv("LLM_COUNCIL_COVERAGE_POLICY", raising=False)
        for cov in (
            {"omitted": None, "reviewed": []},
            {"omitted": ["not-a-dict", None], "reviewed": []},
        ):
            coverage.coverage_clamp_decision(
                "pass", cov, coverage.coverage_policy(), coverage.coverage_ack_reasons()
            )
