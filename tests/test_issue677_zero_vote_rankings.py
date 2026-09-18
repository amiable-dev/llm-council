"""#677: a zero-vote model yields `average_position: None` — don't crash, don't go blind.

`calculate_aggregate_rankings` emits `average_position=None` AND `borda_score=None`
for any model that received no position votes (ADR-027 keeps 0-vote candidates in
the aggregate; `council.py`'s single-model degraded path does the same). Both
consumers coalesced it with `r.get("average_position", r.get("borda_score", 0.0))`
— which returns the STORED None, because `.get`'s default never fires for a
present-but-None key (the #594 bug class). CSS then did ordering math on None:

* `run_full_council` → `calculate_quality_metrics` → TypeError, unguarded, so a
  completed deliberation failed the whole request (HTTP path, metrics default ON).
* `graduated_depth._css_from` → same TypeError, swallowed by its try/except into
  `signals_unavailable` — 96% of #618's depth telemetry was unusable.

The fix drops non-numeric entries rather than defaulting them. Deliberately NO
`borda_score` fallback: it is the opposite polarity (higher-is-better) on a
different scale (0–1 vs 1–N), so mixing it into a position list corrupts the very
ordering CSS measures — and it is None in the same cases anyway.
"""

import ast
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

import pytest

from llm_council import graduated_depth as gd
from llm_council.council_rankings import rankings_to_position_tuples

STAGE2 = [{"model": "m1", "parsed_ranking": {"ranking": ["Response A", "Response B"]}}]


def _agg(*positions):
    """Aggregate entries; a None position models a zero-vote candidate."""
    out = []
    for i, pos in enumerate(positions):
        out.append(
            {
                "model": f"m{i + 1}",
                "average_position": pos,
                # real aggregates carry borda_score=None in exactly these cases
                "borda_score": None if pos is None else round(1.0 - i * 0.3, 3),
            }
        )
    return out


class TestPositionTuples:
    def test_numeric_entries_pass_through(self):
        assert rankings_to_position_tuples(_agg(1.5, 2.0, 3.0)) == [
            ("m1", 1.5),
            ("m2", 2.0),
            ("m3", 3.0),
        ]

    def test_zero_vote_entry_is_dropped_not_defaulted(self):
        tuples = rankings_to_position_tuples(_agg(1.5, 2.0, 3.0, None))
        assert [t[0] for t in tuples] == ["m1", "m2", "m3"]
        assert all(isinstance(t[1], float) for t in tuples)

    def test_no_borda_fallback_even_when_borda_is_present(self):
        """Opposite polarity + different scale: a borda value must never be
        smuggled into a position list."""
        agg = [
            {"model": "m1", "average_position": 1.0, "borda_score": 1.0},
            {"model": "m2", "average_position": None, "borda_score": 0.9},
        ]
        assert rankings_to_position_tuples(agg) == [("m1", 1.0)]

    def test_missing_key_and_non_numeric_are_dropped(self):
        agg = [
            {"model": "m1", "average_position": 1.0},
            {"model": "m2"},  # key absent entirely
            {"model": "m3", "average_position": "2.0"},  # string, not a number
            {"model": "m4", "average_position": True},  # bool is not a position
        ]
        assert rankings_to_position_tuples(agg) == [("m1", 1.0)]

    def test_malformed_entries_never_raise(self):
        assert rankings_to_position_tuples([{"no_model": 1}, None, "junk"]) == []
        assert rankings_to_position_tuples(None) == []


class TestCssNoLongerBlind:
    def test_css_computed_despite_a_zero_vote_model(self):
        """The 60% `signals_unavailable` bucket: this returned None before."""
        css = gd._css_from(STAGE2, _agg(1.5, 2.0, 3.0, None))
        assert css is not None
        assert 0.0 <= css <= 1.0

    def test_css_matches_the_equivalent_clean_aggregate(self):
        """Dropping the unranked model is the whole semantic — the score must
        equal what the same council produces without that candidate listed."""
        assert gd._css_from(STAGE2, _agg(1.5, 2.0, 3.0, None)) == gd._css_from(
            STAGE2, _agg(1.5, 2.0, 3.0)
        )

    def test_fewer_than_two_usable_entries_is_genuinely_unavailable(self):
        assert gd._css_from(STAGE2, _agg(1.5, None, None)) is None
        assert gd._css_from(STAGE2, []) is None


class TestUnavailableReasonIsRecorded:
    def _record(self, tmp_path, monkeypatch, agg, council_models, stage2=None, l2m=None):
        monkeypatch.setattr(
            gd, "DEFAULT_DEPTH_DECISIONS_PATH", tmp_path / "d" / "decisions.jsonl"
        )
        labels = ["Response A", "Response B", "Response C", "Response D"]
        return gd.evaluate_and_log_shadow_depth(
            entry_point="test",
            stage2_results=stage2 if stage2 is not None else STAGE2,
            label_to_model=l2m
            if l2m is not None
            else {
                lab: {"model": m, "display_index": i}
                for i, (lab, m) in enumerate(zip(labels, council_models))
            },
            aggregate_rankings=agg,
            council_models=council_models,
        )

    def test_unavailable_records_say_why(self, tmp_path, monkeypatch):
        """`signals_unavailable` was an undiagnosable bucket — 68 records deep
        before anyone could ask what was missing."""
        rec = self._record(tmp_path, monkeypatch, _agg(None, None), ["m1", "m2"])
        assert rec["decision"] in ("signals_unavailable", "ladder_inapplicable")
        assert rec.get("unavailable_reason")

    def test_usable_records_carry_no_reason(self, tmp_path, monkeypatch):
        """A real 4-model council: every mini reviewer ranks the mini responses,
        so both the full CSS and the counterfactual are computable."""
        labels = ["Response A", "Response B", "Response C", "Response D"]
        stage2 = [
            {"model": m, "ranking": "", "parsed_ranking": {"ranking": labels}}
            for m in ("m1", "m2", "m3")
        ]
        rec = self._record(
            tmp_path,
            monkeypatch,
            _agg(1.0, 2.0, 3.0, 4.0),
            ["m1", "m2", "m3", "m4"],
            stage2=stage2,
        )
        assert rec["css_full"] is not None
        assert rec["css_mini_counterfactual"] is not None
        assert rec.get("unavailable_reason") is None


class TestQualityMetricsCannotFailARun:
    """House convention: annotation never fails a deliberation (cf. cost
    accounting, PostHog emission, shadow depth). The ADR-036 block was the one
    telemetry path with no guard at either end."""

    def _quality_block(self):
        src = (REPO_ROOT / "src/llm_council/council.py").read_text()
        tree = ast.parse(src)
        for fn in ast.walk(tree):
            if isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef) and (
                fn.name == "run_full_council"
            ):
                for node in ast.walk(fn):
                    if isinstance(node, ast.Call):
                        name = getattr(node.func, "id", getattr(node.func, "attr", ""))
                        if name == "calculate_quality_metrics":
                            return fn, node
        pytest.fail("calculate_quality_metrics call not found in run_full_council")

    def test_call_is_inside_a_try_except(self):
        fn, call = self._quality_block()
        guarded = [
            t
            for t in ast.walk(fn)
            if isinstance(t, ast.Try)
            and any(call is c for c in ast.walk(t) if isinstance(c, ast.Call))
        ]
        assert guarded, "calculate_quality_metrics must be wrapped in try/except"
        # #678 gate: "a try structurally contains the call" is not enough — the
        # handler must catch the type that actually bit us (TypeError out of
        # CSS), i.e. a bare except or one naming Exception/BaseException.
        names = []
        for h in guarded[0].handlers:
            if h.type is None:
                names.append("bare")
            else:
                for n in ast.walk(h.type):
                    if isinstance(n, ast.Name):
                        names.append(n.id)
        assert {"bare", "Exception", "BaseException"} & set(names), (
            f"handler(s) {names} would not swallow a TypeError from CSS"
        )

    def test_call_site_uses_the_shared_helper_not_the_buggy_coalesce(self):
        src = (REPO_ROOT / "src/llm_council/council.py").read_text()
        assert 'r.get("average_position", r.get("borda_score"' not in src, (
            "the .get(...) coalesce returns a stored None; use "
            "rankings_to_position_tuples instead"
        )
        assert "rankings_to_position_tuples" in src
