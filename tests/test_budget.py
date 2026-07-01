"""Tests for opt-in budget estimation & enforcement (ADR-011 Phase 4, #363)."""

from types import SimpleNamespace

from llm_council.budget import (
    BudgetDecision,
    BudgetEnforcer,
    BudgetMode,
    CostEstimate,
    CostEstimator,
    budget_enforcement_enabled,
    configured_budget_mode,
)


class _FakeTracker:
    def __init__(self, costs):
        self._costs = costs

    def get_model_index(self, model_id):
        return SimpleNamespace(mean_cost_usd=self._costs.get(model_id))


class TestEstimator:
    def test_sums_known_model_costs(self):
        est = CostEstimator(tracker=_FakeTracker({"a": 0.01, "b": 0.02}))
        e = est.estimate(["a", "b"])
        assert e.expected == 0.03
        assert e.low == 0.018  # 0.03 * 0.6
        assert e.high == 0.045  # 0.03 * 1.5

    def test_unknown_cost_models_add_nothing(self):
        est = CostEstimator(tracker=_FakeTracker({"a": 0.01, "b": None}))
        assert est.estimate(["a", "b"]).expected == 0.01

    def test_cold_start_is_zero(self):
        est = CostEstimator(tracker=_FakeTracker({}))
        assert est.estimate(["a"]).expected == 0.0

    def test_known_zero_cost_model_included(self):
        # A genuine $0 model is "known" (contributes 0), not dropped as unknown.
        est = CostEstimator(tracker=_FakeTracker({"free": 0.0, "paid": 0.02}))
        assert est.estimate(["free", "paid"]).expected == 0.02

    def test_negative_cost_clamped(self):
        est = CostEstimator(tracker=_FakeTracker({"a": -0.5, "b": 0.02}))
        assert est.estimate(["a", "b"]).expected == 0.02  # negative clamped to 0

    def test_tracker_failure_is_tolerated(self):
        class _Boom:
            def get_model_index(self, _):
                raise RuntimeError("store unavailable")

        assert CostEstimator(tracker=_Boom()).estimate(["a"]).expected == 0.0


_EST = CostEstimate(low=0.6, expected=1.0, high=1.5)


class TestEnforcerModes:
    def test_no_budget_always_allows(self):
        r = BudgetEnforcer(BudgetMode.STRICT).pre_query_check(_EST, None)
        assert r.decision == BudgetDecision.ALLOW

    def test_strict_rejects_when_high_exceeds(self):
        # budget between expected and high -> STRICT rejects (high 1.5 > 1.2)
        r = BudgetEnforcer(BudgetMode.STRICT).pre_query_check(_EST, 1.2)
        assert r.decision == BudgetDecision.REJECT

    def test_balanced_warns_when_only_high_exceeds(self):
        r = BudgetEnforcer(BudgetMode.BALANCED).pre_query_check(_EST, 1.2)
        assert r.decision == BudgetDecision.WARN

    def test_balanced_rejects_when_expected_exceeds(self):
        r = BudgetEnforcer(BudgetMode.BALANCED).pre_query_check(_EST, 0.5)
        assert r.decision == BudgetDecision.REJECT

    def test_permissive_only_warns(self):
        r = BudgetEnforcer(BudgetMode.PERMISSIVE).pre_query_check(_EST, 0.5)
        assert r.decision == BudgetDecision.WARN

    def test_within_budget_allows(self):
        r = BudgetEnforcer(BudgetMode.STRICT).pre_query_check(_EST, 2.0)
        assert r.decision == BudgetDecision.ALLOW


class TestMidQuery:
    def test_aborts_gracefully_when_over(self):
        r = BudgetEnforcer().mid_query_check(spent_so_far=2.0, budget_remaining=1.0)
        assert r.decision == BudgetDecision.ABORT_GRACEFULLY

    def test_continues_when_within(self):
        r = BudgetEnforcer().mid_query_check(spent_so_far=0.5, budget_remaining=1.0)
        assert r.decision == BudgetDecision.CONTINUE

    def test_no_budget_continues(self):
        r = BudgetEnforcer().mid_query_check(spent_so_far=9.9, budget_remaining=None)
        assert r.decision == BudgetDecision.CONTINUE


class TestConfig:
    def test_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("LLM_COUNCIL_BUDGET_ENFORCEMENT", raising=False)
        assert budget_enforcement_enabled() is False

    def test_enabled_via_env(self, monkeypatch):
        monkeypatch.setenv("LLM_COUNCIL_BUDGET_ENFORCEMENT", "true")
        assert budget_enforcement_enabled() is True

    def test_default_mode_balanced(self, monkeypatch):
        monkeypatch.delenv("LLM_COUNCIL_BUDGET_MODE", raising=False)
        assert configured_budget_mode() == BudgetMode.BALANCED

    def test_unknown_mode_falls_back(self, monkeypatch):
        monkeypatch.setenv("LLM_COUNCIL_BUDGET_MODE", "bogus")
        assert configured_budget_mode() == BudgetMode.BALANCED


class TestAuditEvent:
    def test_reject_emits_layer_event(self):
        # A reject must emit an auditable L1_BUDGET_DECISION and not raise.
        from llm_council import layer_contracts

        before = len(getattr(layer_contracts, "_layer_events", []))
        r = BudgetEnforcer(BudgetMode.BALANCED).pre_query_check(_EST, 0.5)
        assert r.decision == BudgetDecision.REJECT
        after = len(getattr(layer_contracts, "_layer_events", []))
        assert after > before
