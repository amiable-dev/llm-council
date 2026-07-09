"""ADR-044 Phase 1: performance-aware selection blending (#390).

The live performance index blends into candidate quality scores — default OFF,
cold-start safe, soft-fail, and emitting an auditable LayerEvent only when
blending actually changes the selected set.
"""

from types import SimpleNamespace

import pytest

import llm_council.metadata.selection as sel
from llm_council.metadata.selection import (
    _blend_quality_with_performance,
    performance_selection_enabled,
)


def _fake_tracker(confidence="HIGH", borda=0.9, raises=False):
    class _T:
        def get_model_index(self, model_id):
            if raises:
                raise RuntimeError("store unavailable")
            return SimpleNamespace(confidence_level=confidence, mean_borda_score=borda)

    return _T()


class TestFlag:
    def test_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("LLM_COUNCIL_PERFORMANCE_SELECTION", raising=False)
        assert performance_selection_enabled() is False

    def test_enabled_via_env(self, monkeypatch):
        monkeypatch.setenv("LLM_COUNCIL_PERFORMANCE_SELECTION", "true")
        assert performance_selection_enabled() is True


class TestBlend:
    def test_insufficient_confidence_returns_static(self, monkeypatch):
        monkeypatch.setattr(sel, "_get_perf_tracker", lambda: _fake_tracker("INSUFFICIENT", 0.99))
        assert _blend_quality_with_performance("m", 0.70) == 0.70

    @pytest.mark.parametrize(
        "confidence,weight",
        [("PRELIMINARY", 0.3), ("MODERATE", 0.6), ("HIGH", 0.8)],
    )
    def test_blend_weight_steps_by_confidence(self, monkeypatch, confidence, weight):
        monkeypatch.setattr(sel, "_get_perf_tracker", lambda: _fake_tracker(confidence, 0.9))
        expected = weight * 0.9 + (1 - weight) * 0.5
        assert _blend_quality_with_performance("m", 0.5) == pytest.approx(expected)

    def test_weight_never_exceeds_cap(self, monkeypatch):
        # Even at HIGH confidence, static keeps >= 20% influence.
        monkeypatch.setattr(sel, "_get_perf_tracker", lambda: _fake_tracker("HIGH", 1.0))
        blended = _blend_quality_with_performance("m", 0.0)
        assert blended <= 0.8

    def test_tracker_error_soft_fails_to_static(self, monkeypatch):
        monkeypatch.setattr(sel, "_get_perf_tracker", lambda: _fake_tracker(raises=True))
        assert _blend_quality_with_performance("m", 0.42) == 0.42


class TestSelectionIntegration:
    def _run(self, monkeypatch, enabled, tracker):
        if enabled:
            monkeypatch.setenv("LLM_COUNCIL_PERFORMANCE_SELECTION", "true")
        else:
            monkeypatch.delenv("LLM_COUNCIL_PERFORMANCE_SELECTION", raising=False)
        monkeypatch.setattr(sel, "_get_perf_tracker", lambda: tracker)
        # Deterministic: score = quality only, so outcomes are fully decided by
        # the static heuristics (opus/gpt-4 0.95 > sonnet 0.85 > mini 0.65)
        # and by the blend — no dependence on latency/cost weight tuning.
        monkeypatch.setattr(
            sel, "calculate_model_score", lambda c, t: c.quality_score
        )
        pool = ["alpha/opus-1", "beta/gpt-4-z", "gamma/sonnet-y", "weak/mini-x"]
        monkeypatch.setattr(sel, "_get_tier_model_pools", lambda: {"balanced": pool})
        monkeypatch.setattr(sel, "_is_discovery_enabled", lambda: False)
        monkeypatch.setattr(sel, "_is_circuit_breaker_open", lambda m: False)
        monkeypatch.setattr(sel, "_filter_by_tier_intersection", lambda c, t, p: c)
        return sel.select_tier_models("balanced", count=2)

    class _BoostMini:
        def get_model_index(self, model_id):
            borda = 1.0 if model_id == "weak/mini-x" else 0.0
            return SimpleNamespace(confidence_level="HIGH", mean_borda_score=borda)

    def test_flag_off_is_byte_identical(self, monkeypatch):
        # Even with a tracker that would massively boost weak/mini-x, the
        # flag-off path never consults it: static top-2 by quality.
        baseline = self._run(monkeypatch, enabled=False, tracker=self._BoostMini())
        assert baseline == ["alpha/opus-1", "beta/gpt-4-z"]
        assert "weak/mini-x" not in baseline

    def test_flag_on_blending_can_change_selection_and_emits_event(self, monkeypatch):
        from llm_council import layer_contracts

        before = len(getattr(layer_contracts, "_layer_events", []))
        selected = self._run(monkeypatch, enabled=True, tracker=self._BoostMini())
        # Blended: mini = 0.8*1.0 + 0.2*0.65 = 0.93 (top); others crater to 0.2*static.
        assert "weak/mini-x" in selected  # live record flipped it in
        events = list(getattr(layer_contracts, "_layer_events", []))
        new = [e for e in events[before:] if "performance_selection" in str(getattr(e.event_type, "value", e.event_type))]
        assert new, "route receipt LayerEvent must be emitted when the set changed"
        payload = new[-1].data
        assert payload["static_selection"] != payload["blended_selection"]

    def test_flag_on_no_change_no_event(self, monkeypatch):
        from llm_council import layer_contracts

        class _Uniform:  # same live score for all -> order preserved -> no change
            def get_model_index(self, model_id):
                return SimpleNamespace(confidence_level="PRELIMINARY", mean_borda_score=0.7)

        before = len(getattr(layer_contracts, "_layer_events", []))
        selected = self._run(monkeypatch, enabled=True, tracker=_Uniform())
        assert selected == ["alpha/opus-1", "beta/gpt-4-z"]  # unchanged set
        events = list(getattr(layer_contracts, "_layer_events", []))
        new = [e for e in events[before:] if "performance_selection" in str(getattr(e.event_type, "value", e.event_type))]
        assert not new, "no event when blending did not change the selected set"
