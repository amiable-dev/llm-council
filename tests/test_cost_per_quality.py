"""Cost-per-quality signal in the performance index (ADR-011 Phase 3, #362)."""

from datetime import datetime, timezone

import pytest

from llm_council.performance.tracker import InternalPerformanceTracker
from llm_council.performance.types import ModelPerformanceIndex, ModelSessionMetric


def _now():
    return datetime.now(timezone.utc).isoformat()


def _metric(model_id, borda, cost, sid):
    return ModelSessionMetric(
        session_id=sid,
        model_id=model_id,
        timestamp=_now(),
        latency_ms=100,
        borda_score=borda,
        parse_success=True,
        cost_usd=cost,
    )


class TestSerialization:
    def test_cost_usd_round_trips(self):
        m = ModelSessionMetric(model_id="m", borda_score=0.8, cost_usd=0.0123)
        restored = ModelSessionMetric.from_jsonl_line(m.to_jsonl_line())
        assert restored.cost_usd == 0.0123

    def test_old_record_without_cost_defaults_none(self):
        # A pre-Phase-3 JSONL line has no cost_usd key.
        line = '{"model_id": "m", "borda_score": 0.5}'
        assert ModelSessionMetric.from_jsonl_line(line).cost_usd is None


class TestQualityPerCost:
    def test_ratio(self):
        idx = ModelPerformanceIndex(
            model_id="m", sample_size=5, mean_borda_score=0.8,
            p50_latency_ms=1, p95_latency_ms=1, parse_success_rate=1.0,
            confidence_level="PRELIMINARY", mean_cost_usd=0.02,
        )
        assert idx.quality_per_cost == 0.8 / 0.02

    def test_none_when_cost_unknown_or_zero(self):
        base = dict(
            model_id="m", sample_size=5, mean_borda_score=0.8,
            p50_latency_ms=1, p95_latency_ms=1, parse_success_rate=1.0,
            confidence_level="PRELIMINARY",
        )
        assert ModelPerformanceIndex(**base, mean_cost_usd=None).quality_per_cost is None
        assert ModelPerformanceIndex(**base, mean_cost_usd=0.0).quality_per_cost is None


class TestTrackerCostAggregation:
    def test_mean_cost_excludes_none(self, tmp_path):
        t = InternalPerformanceTracker(store_path=tmp_path / "perf.jsonl")
        t.record_session("s1", [_metric("m", 0.8, 0.02, "s1")])
        t.record_session("s2", [_metric("m", 0.6, None, "s2")])  # unknown cost
        idx = t.get_model_index("m")
        assert idx.mean_cost_usd == 0.02  # None excluded, not averaged as 0
        # (decay weights recompute per call; compare approximately)
        assert t.get_cost_per_quality("m") == pytest.approx(idx.mean_borda_score / 0.02, rel=1e-3)

    def test_mean_cost_none_when_no_costs(self, tmp_path):
        t = InternalPerformanceTracker(store_path=tmp_path / "perf.jsonl")
        t.record_session("s1", [_metric("m", 0.8, None, "s1")])
        assert t.get_model_index("m").mean_cost_usd is None
        assert t.get_cost_per_quality("m") is None


class TestCostAwareScores:
    def _seed(self, tmp_path):
        t = InternalPerformanceTracker(store_path=tmp_path / "perf.jsonl")
        # >=10 samples each so get_all_model_scores includes them.
        for i in range(12):
            # cheap model: lower quality but far cheaper -> better value
            t.record_session(f"a{i}", [_metric("cheap/m", 0.6, 0.001, f"a{i}")])
            t.record_session(f"b{i}", [_metric("pricey/m", 0.7, 0.05, f"b{i}")])
        return t

    def test_disabled_by_default_is_plain_quality(self, tmp_path, monkeypatch):
        monkeypatch.delenv("LLM_COUNCIL_COST_AWARE_SELECTION", raising=False)
        t = self._seed(tmp_path)
        aware = t.get_all_cost_aware_scores()
        plain = t.get_all_model_scores()
        assert aware.keys() == plain.keys()
        for model_id in plain:  # decay recomputes per call; approx equality
            assert aware[model_id] == pytest.approx(plain[model_id], rel=1e-3)

    def test_enabled_rewards_better_value(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LLM_COUNCIL_COST_AWARE_SELECTION", "true")
        t = self._seed(tmp_path)
        scores = t.get_all_cost_aware_scores()
        # cheap/m has higher quality-per-cost (0.6/0.001 >> 0.7/0.05) -> ranks above.
        assert scores["cheap/m"] > scores["pricey/m"]


class TestPersistWiring:
    def test_persist_records_cost_from_usage_by_model(self, tmp_path, monkeypatch):
        import llm_council.performance.integration as integ

        monkeypatch.setattr(integ, "PERFORMANCE_TRACKING_ENABLED", True)
        monkeypatch.setattr(integ, "PERFORMANCE_STORE_PATH", tmp_path / "perf.jsonl")
        integ.persist_session_performance_data(
            session_id="s1",
            model_statuses={"openai/gpt-4o": {"latency_ms": 100}},
            aggregate_rankings={"openai/gpt-4o": {"borda_score": 0.8}},
            usage_by_model={"openai/gpt-4o": {"cost_usd": 0.03, "cost_known": True}},
        )
        t = InternalPerformanceTracker(store_path=tmp_path / "perf.jsonl")
        assert t.get_model_index("openai/gpt-4o").mean_cost_usd == 0.03

    def test_persist_leaves_cost_none_when_unknown(self, tmp_path, monkeypatch):
        import llm_council.performance.integration as integ

        monkeypatch.setattr(integ, "PERFORMANCE_TRACKING_ENABLED", True)
        monkeypatch.setattr(integ, "PERFORMANCE_STORE_PATH", tmp_path / "perf.jsonl")
        integ.persist_session_performance_data(
            session_id="s1",
            model_statuses={"m": {"latency_ms": 100}},
            aggregate_rankings={"m": {"borda_score": 0.8}},
            usage_by_model={"m": {"cost_usd": 0.0}},  # no cost_known -> unknown
        )
        t = InternalPerformanceTracker(store_path=tmp_path / "perf.jsonl")
        assert t.get_model_index("m").mean_cost_usd is None
