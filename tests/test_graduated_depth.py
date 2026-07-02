"""ADR-044 Phase 3: graduated deliberation depth (#392)."""

from types import SimpleNamespace

import pytest

from llm_council.graduated_depth import (
    DepthRung,
    graduated_depth_enabled,
    merge_usage_summaries,
    models_for_rung,
    next_rung,
    plan_escalation,
    should_escalate,
)


class TestFlag:
    def test_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("LLM_COUNCIL_GRADUATED_DEPTH", raising=False)
        assert graduated_depth_enabled() is False


class TestLadder:
    def test_rung_progression(self):
        assert next_rung(DepthRung.SINGLE) == DepthRung.MINI
        assert next_rung(DepthRung.MINI) == DepthRung.FULL
        assert next_rung(DepthRung.FULL) is None

    def test_models_for_rung_are_prefix_subsets(self):
        pool = ["a", "b", "c", "d", "e"]
        single = models_for_rung(pool, DepthRung.SINGLE)
        mini = models_for_rung(pool, DepthRung.MINI)
        full = models_for_rung(pool, DepthRung.FULL)
        assert single == ["a"]
        assert mini == ["a", "b", "c"]
        assert full == pool
        # Deeper rungs are supersets -> shallow responses are always reusable.
        assert set(single) <= set(mini) <= set(full)


class TestEscalationSignal:
    def test_low_css_escalates(self):
        assert should_escalate(css=0.4, confidence=0.9) is True

    def test_low_confidence_escalates(self):
        assert should_escalate(css=0.9, confidence=0.5) is True

    def test_strong_signals_do_not_escalate(self):
        assert should_escalate(css=0.9, confidence=0.9) is False

    def test_missing_signals_do_not_escalate(self):
        # Unknown signals can't justify extra spend (documented choice).
        assert should_escalate(css=None, confidence=None) is False


class _FixedEstimator:
    def __init__(self, expected=0.05):
        from llm_council.budget import CostEstimate

        self._e = CostEstimate(low=expected * 0.6, expected=expected, high=expected * 1.5)

    def estimate(self, models):
        return self._e


class TestPlanEscalation:
    def _plan(self, monkeypatch, enabled=True, css=0.4, confidence=0.5, **kw):
        if enabled:
            monkeypatch.setenv("LLM_COUNCIL_GRADUATED_DEPTH", "true")
        else:
            monkeypatch.delenv("LLM_COUNCIL_GRADUATED_DEPTH", raising=False)
        return plan_escalation(
            all_models=["a", "b", "c", "d"],
            current_rung=DepthRung.SINGLE,
            css=css,
            confidence=confidence,
            **kw,
        )

    def test_disabled_stops(self, monkeypatch):
        plan = self._plan(monkeypatch, enabled=False)
        assert plan.decision == "stop" and plan.reason == "disabled"

    def test_sufficient_consensus_stops(self, monkeypatch):
        plan = self._plan(monkeypatch, css=0.95, confidence=0.95)
        assert plan.decision == "stop" and plan.reason == "consensus_sufficient"

    def test_full_depth_stops(self, monkeypatch):
        monkeypatch.setenv("LLM_COUNCIL_GRADUATED_DEPTH", "true")
        plan = plan_escalation(
            all_models=["a", "b"], current_rung=DepthRung.FULL, css=0.1, confidence=0.1
        )
        assert plan.decision == "stop" and plan.reason == "at_full_depth"

    def test_escalates_with_added_models_only_and_emits_event(self, monkeypatch):
        from llm_council import layer_contracts

        before = len(getattr(layer_contracts, "_layer_events", []))
        plan = self._plan(monkeypatch, estimator=_FixedEstimator())
        assert plan.decision == "escalate"
        assert plan.next_rung == DepthRung.MINI
        assert plan.added_models == ["b", "c"]  # 'a' reused, never re-called
        events = getattr(layer_contracts, "_layer_events", [])
        new = [
            e
            for e in events[before:]
            if "deliberation_escalation" in str(getattr(e.event_type, "value", e.event_type))
        ]
        assert new and new[-1].data["added_models"] == ["b", "c"]

    def test_budget_veto_is_auditable_never_silent(self, monkeypatch):
        from llm_council.budget import BudgetEnforcer, BudgetMode

        monkeypatch.setenv("LLM_COUNCIL_BUDGET_ENFORCEMENT", "true")
        plan = self._plan(
            monkeypatch,
            estimator=_FixedEstimator(expected=5.0),
            enforcer=BudgetEnforcer(BudgetMode.BALANCED),
            budget_remaining=1.0,
        )
        assert plan.decision == "vetoed"
        assert "budget" in plan.reason
        assert plan.next_rung is None  # veto means: stay at current depth

    def test_no_budget_set_escalates(self, monkeypatch):
        from llm_council.budget import BudgetEnforcer

        monkeypatch.setenv("LLM_COUNCIL_BUDGET_ENFORCEMENT", "true")
        plan = self._plan(
            monkeypatch,
            estimator=_FixedEstimator(expected=5.0),
            enforcer=BudgetEnforcer(),
            budget_remaining=None,  # no budget configured -> allow
        )
        assert plan.decision == "escalate"


class TestUsageMerge:
    def test_merges_totals_stages_and_models(self):
        a = {
            "by_stage": {"stage1": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "cost_usd": 0.01, "cached_tokens": 0}},
            "by_model": {"a": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "cost_usd": 0.01, "cached_tokens": 0}},
            "total": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "cost_usd": 0.01, "cached_tokens": 0, "cost_known": True},
        }
        b = {
            "by_stage": {"stage1": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30, "cost_usd": 0.02, "cached_tokens": 2}},
            "by_model": {"b": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30, "cost_usd": 0.02, "cached_tokens": 2}},
            "total": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30, "cost_usd": 0.02, "cached_tokens": 2, "cost_known": False},
        }
        merged = merge_usage_summaries(a, b)
        assert merged["total"]["total_tokens"] == 45
        assert merged["total"]["cost_usd"] == pytest.approx(0.03)
        assert merged["total"]["cost_known"] is True  # OR-semantics
        assert merged["by_stage"]["stage1"]["prompt_tokens"] == 30
        assert set(merged["by_model"]) == {"a", "b"}

    def test_handles_missing_sections(self):
        merged = merge_usage_summaries({}, {"total": {"total_tokens": 5}})
        assert merged["total"]["total_tokens"] == 5
