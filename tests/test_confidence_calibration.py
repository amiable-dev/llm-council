"""ADR-047 P2: confidence calibration (#414).

Reproducible corpus analysis, monotonic PAV fit, both confidences surfaced,
flag-off byte-identical.
"""

import json

import pytest

from llm_council.verification.calibration import (
    CalibrationMapping,
    CalibrationRecord,
    analyze_corpus,
    calibrated_confidence_enabled,
    fit_from_dispositions,
    load_corpus,
    load_mapping,
    pav_fit,
)


def _write_result(tmp_path, vid, verdict, confidence, blocking=0):
    d = tmp_path / vid
    d.mkdir()
    (d / "result.json").write_text(
        json.dumps(
            {
                "verification_id": vid,
                "verdict": verdict,
                "confidence": confidence,
                "blocking_issues": [{"severity": "major", "description": "x"}] * blocking,
            }
        )
    )


class TestCorpus:
    def test_load_and_analyze(self, tmp_path):
        _write_result(tmp_path, "a1", "fail", 0.95, blocking=0)
        _write_result(tmp_path, "a2", "fail", 1.0, blocking=0)
        _write_result(tmp_path, "a3", "pass", 0.9)
        _write_result(tmp_path, "a4", "unclear", 0.4)
        records = load_corpus(tmp_path)
        assert len(records) == 4
        summary = analyze_corpus(records)
        assert summary["n"] == 4
        assert summary["verdicts"]["fail"] == 2
        # THE anomaly: FAILs with zero blocking issues
        assert summary["zero_blocking_fail_rate"] == 1.0

    def test_unreadable_files_skipped(self, tmp_path):
        d = tmp_path / "bad"
        d.mkdir()
        (d / "result.json").write_text("{not json")
        assert load_corpus(tmp_path) == []


class TestPav:
    def test_monotonic_output(self):
        # Violating sequence gets pooled: outcomes dip in the middle.
        pairs = [(0.2, 0.0), (0.4, 1.0), (0.6, 0.0), (0.8, 1.0)]
        points = pav_fit(pairs)
        ys = [y for _, y in points]
        assert ys == sorted(ys)

    def test_already_monotonic_preserved(self):
        pairs = [(0.2, 0.0), (0.5, 0.5), (0.9, 1.0)]
        assert pav_fit(pairs) == [(0.2, 0.0), (0.5, 0.5), (0.9, 1.0)]

    def test_empty(self):
        assert pav_fit([]) == []


class TestMapping:
    def test_identity_when_no_points(self):
        m = CalibrationMapping.identity()
        assert m.is_identity
        assert m.calibrate(0.73) == 0.73

    def test_interpolation_and_clamping(self):
        m = CalibrationMapping(points=[(0.5, 0.2), (1.0, 0.8)])
        assert m.calibrate(0.3) == 0.2  # below range clamps to first y
        assert m.calibrate(1.0) == 0.8
        assert m.calibrate(0.75) == 0.5  # linear midpoint

    def test_json_round_trip(self):
        m = CalibrationMapping(points=[(0.5, 0.2), (1.0, 0.8)])
        m2 = CalibrationMapping.from_json(m.to_json())
        assert m2.points == m.points

    def test_corrupt_non_monotonic_rejected(self):
        with pytest.raises(ValueError):
            CalibrationMapping.from_json(
                json.dumps({"version": 1, "points": [[0.5, 0.9], [1.0, 0.1]]})
            )

    def test_load_mapping_identity_fallback(self, tmp_path):
        assert load_mapping(tmp_path / "missing.json").is_identity


class TestFit:
    def test_fit_from_dispositions(self):
        records = [
            CalibrationRecord("v1", "fail", 0.95, 0, False),
            CalibrationRecord("v2", "fail", 1.0, 0, False),
            CalibrationRecord("v3", "pass", 0.9, 0, False),
            CalibrationRecord("v4", "fail", 0.6, 1, False),
        ]
        # High-confidence FAILs overridden by humans; others upheld.
        dispositions = {"v1": False, "v2": False, "v3": True, "v4": True}
        m = fit_from_dispositions(records, dispositions)
        assert not m.is_identity
        # Outcomes anti-correlate with confidence here, so the isotonic
        # (non-decreasing) fit pools everything to the global uphold rate —
        # a raw 1.0 is deflated to 0.5, exactly the honest calibration.
        assert m.calibrate(1.0) == 0.5

    def test_records_without_disposition_ignored(self):
        records = [CalibrationRecord("v1", "fail", 0.9, 0, False)]
        assert fit_from_dispositions(records, {}).is_identity


class TestFlagGate:
    def test_default_off(self, monkeypatch):
        monkeypatch.delenv("LLM_COUNCIL_CALIBRATED_CONFIDENCE", raising=False)
        assert calibrated_confidence_enabled() is False

    def test_flag_off_verdict_byte_identical(self):
        # build_verification_result without a calibrator: threshold uses raw.
        from llm_council.verification.verdict_extractor import (
            build_verification_result,
        )

        stage3 = {"response": "VERDICT: PASS — looks good."}
        out = build_verification_result([], [], stage3, confidence_threshold=0.7)
        out2 = build_verification_result(
            [], [], stage3, confidence_threshold=0.7, calibrate=None
        )
        assert out == out2

    def test_flag_on_threshold_uses_calibrated(self):
        # A pass at raw 0.75 with a deflating calibrator (0.75 -> 0.5) must
        # soften to unclear when the calibrator is applied.
        from llm_council.verification.verdict_extractor import (
            build_verification_result,
        )

        mapping = CalibrationMapping(points=[(0.0, 0.0), (1.0, 0.65)])

        class FakeVerdict:
            verdict_type = None

        # Use the legacy path: synthesis says pass; agreement confidence 0.5
        # (no stage2) blended with base => compute raw first.
        stage3 = {"response": "VERDICT: PASS — approved."}
        raw = build_verification_result([], [], stage3, confidence_threshold=0.7)
        calibrated = build_verification_result(
            [], [], stage3, confidence_threshold=0.7, calibrate=mapping.calibrate
        )
        if raw["verdict"] == "pass":
            # Deflated below 0.7 => softened.
            assert calibrated["verdict"] == "unclear"
        else:
            # Raw already below threshold: calibrator can't resurrect it.
            assert calibrated["verdict"] == raw["verdict"]
        assert calibrated["confidence_calibrated"] == mapping.calibrate(
            raw["confidence"]
        )


class TestSchemaField:
    def test_verify_response_carries_calibrated(self):
        from llm_council.verification.schemas import VerifyResponse

        resp = VerifyResponse(
            verification_id="v1",
            verdict="pass",
            confidence=0.9,
            exit_code=0,
            rationale="r",
            transcript_location="/tmp/t",
            confidence_calibrated=0.62,
        )
        assert resp.confidence_calibrated == 0.62


class TestCouncilRound1:
    def test_string_false_disposition_not_coerced_to_true(self, tmp_path):
        # #435 r1: bool("false") is True — a string disposition would be
        # silently INVERTED. Non-boolean values must be skipped, not coerced.
        from llm_council.verification.calibration import load_dispositions

        p = tmp_path / "d.jsonl"
        p.write_text(
            '{"verification_id": "v1", "upheld": "false"}\n'
            '{"verification_id": "v2", "upheld": false}\n'
            '{"verification_id": "v3", "upheld": true}\n'
        )
        d = load_dispositions(p)
        assert "v1" not in d  # string skipped, never inverted
        assert d == {"v2": False, "v3": True}

    def test_verdict_counts_include_confidence_less_records(self):
        # #435 r1: the verdict histogram counted only records WITH a
        # confidence — a null-confidence result vanished from the counts.
        rec = [
            CalibrationRecord("v1", "unclear", None, 0, True),
            CalibrationRecord("v2", "fail", 0.9, 1, False),
        ]
        summary = analyze_corpus(rec)
        assert summary["verdicts"] == {"unclear": 1, "fail": 1}


class TestCouncilRound2:
    def test_tied_confidence_values_pool_to_mean(self):
        # #435 r2: sorted() orders ties by y ascending, so the >-only merge
        # never pooled tied x values — calibrate(0.9) returned the FIRST tied
        # y (0.0) instead of the mean. Real corpora cluster at 0.95/1.0.
        points = pav_fit([(0.9, 0.0), (0.9, 1.0)])
        assert points == [(0.9, 0.5)]

    def test_ties_then_monotonic_sequence(self):
        points = pav_fit([(0.5, 0.0), (0.9, 1.0), (0.9, 0.0), (1.0, 1.0)])
        xs = [x for x, _ in points]
        ys = [y for _, y in points]
        assert xs == sorted(xs) and len(set(xs)) == len(xs)  # unique x
        assert ys == sorted(ys)  # monotonic

    def test_unparseable_disposition_lines_logged(self, tmp_path, caplog):
        import logging

        from llm_council.verification.calibration import load_dispositions

        p = tmp_path / "d.jsonl"
        p.write_text('{broken\n{"verification_id": "v1", "upheld": true}\n')
        with caplog.at_level(logging.WARNING, logger="llm_council.verification.calibration"):
            d = load_dispositions(p)
        assert d == {"v1": True}
        assert any("disposition" in r.message for r in caplog.records)
