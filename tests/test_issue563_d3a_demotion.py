"""#563 / ADR-054 D3a: confidence demoted to labelled telemetry.

The maintainer decision (2026-08-21): `confidence` stays reported, documented
as a reviewer-agreement-derived heuristic — NOT a calibrated probability — and
`LLM_COUNCIL_CALIBRATED_CONFIDENCE` is removed as a PASS gate. The
`calibrate` parameter machinery in `build_verification_result` remains (it is
how `confidence_calibrated` is computed for REPORTING), but no production
path wires it into verdict thresholds any more.
"""

import pathlib

import pytest


class TestFlagRemoved:
    def test_flag_function_is_gone(self):
        with pytest.raises(ImportError):
            from llm_council.verification.calibration import (  # noqa: F401
                calibrated_confidence_enabled,
            )

    def test_env_flag_has_no_code_references(self):
        src = pathlib.Path("src/llm_council")
        hits = [
            p
            for p in src.rglob("*.py")
            if "LLM_COUNCIL_CALIBRATED_CONFIDENCE" in p.read_text()
        ]
        assert hits == [], f"flag still referenced in: {hits}"

    def test_api_no_longer_wires_calibrate_into_the_gate(self):
        api_src = pathlib.Path("src/llm_council/verification/api.py").read_text()
        assert "calibrated_confidence_enabled" not in api_src
        # the reporting fill (confidence_calibrated from the persisted mapping)
        # must survive the demotion — reporting is kept, gating is removed
        assert "confidence_calibrated" in api_src


class TestDocsRelabelled:
    def test_env_reference_no_longer_documents_the_flag(self):
        ref = pathlib.Path("docs/reference/environment-variables.md").read_text()
        assert "LLM_COUNCIL_CALIBRATED_CONFIDENCE" not in ref

    def test_verify_guide_labels_confidence_as_uncalibrated(self):
        guide = pathlib.Path("docs/guides/verify.md").read_text()
        assert "not a calibrated probability" in guide.lower()


class TestReportingSurvives:
    def test_calibrate_param_still_computes_reported_value(self):
        """The calibrate mechanism stays for REPORTING (confidence_calibrated);
        only the production gate wiring was removed."""
        from llm_council.verification.verdict_extractor import (
            build_verification_result,
        )

        stage3 = {"response": "VERDICT: PASS — approved."}
        out = build_verification_result(
            [], [], stage3, confidence_threshold=0.7, calibrate=lambda c: 0.42
        )
        assert out["confidence_calibrated"] == 0.42
