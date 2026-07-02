"""ADR-044 Phase 2: early consensus termination (#391)."""

import asyncio
from itertools import permutations

import pytest

from llm_council.early_consensus import (
    borda_update,
    early_consensus_enabled,
    estimate_reviewers_cost,
    unassailable_leader,
)


class TestFlag:
    def test_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("LLM_COUNCIL_EARLY_CONSENSUS", raising=False)
        assert early_consensus_enabled() is False


class TestUnassailabilityMath:
    def test_decided_case(self):
        # 3 candidates, 5 reviewers, 4 voted A>B>C: A=8, B=4, C=0, 1 remaining.
        points = {"Response A": 8.0, "Response B": 4.0, "Response C": 0.0}
        assert unassailable_leader(points, remaining_votes=1, num_candidates=3) == "Response A"

    def test_not_decided_when_reachable(self):
        # A=6, B=3, 2 remaining, max swing 2*2=4: B could reach 7 > 6.
        points = {"Response A": 6.0, "Response B": 3.0, "Response C": 0.0}
        assert unassailable_leader(points, remaining_votes=2, num_candidates=3) is None

    def test_tie_never_decided(self):
        points = {"Response A": 4.0, "Response B": 4.0}
        assert unassailable_leader(points, remaining_votes=0, num_candidates=2) is None

    def test_exhaustive_soundness_small(self):
        # Property check: whenever the checker says "decided" mid-count, no
        # completion of the remaining votes may change the winner.
        n = 3
        labels = [f"Response {c}" for c in "ABC"]
        all_votes = list(permutations(labels))
        for v1 in all_votes:
            for v2 in all_votes:
                points: dict = {}
                borda_update(points, list(v1), n)
                borda_update(points, list(v2), n)
                leader = unassailable_leader(points, remaining_votes=1, num_candidates=n)
                if leader is None:
                    continue
                for v3 in all_votes:
                    final = dict(points)
                    borda_update(final, list(v3), n)
                    winner = max(final.items(), key=lambda kv: kv[1])
                    # strict: decided leader must remain the unique max
                    others = [p for lbl, p in final.items() if lbl != leader]
                    assert final[leader] > max(others), (v1, v2, v3, final)


class TestCostEstimate:
    def test_sums_known_costs_and_never_raises(self, monkeypatch):
        class _T:
            def get_model_index(self, m):
                from types import SimpleNamespace

                return SimpleNamespace(mean_cost_usd={"a": 0.01, "b": None}.get(m))

        import llm_council.performance.integration as integ

        monkeypatch.setattr(integ, "get_tracker", lambda: _T())
        assert estimate_reviewers_cost(["a", "b"]) == 0.01


# ---------------------------------------------------------------------------
# stage2 integration
# ---------------------------------------------------------------------------

_STAGE1 = [
    {"model": "m1", "response": "answer one"},
    {"model": "m2", "response": "answer two"},
    {"model": "m3", "response": "answer three"},
]

_RANKING_TEXT = "FINAL RANKING:\n1. Response A\n2. Response B\n3. Response C"


def _mock_query_model(delays, calls, cancelled):
    async def fake(model, messages, disable_tools=False, timeout=120.0, **kw):
        try:
            await asyncio.sleep(delays.get(model, 0.0))
        except asyncio.CancelledError:
            cancelled.append(model)
            raise
        calls.append(model)
        return {
            "content": _RANKING_TEXT,
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }

    return fake


@pytest.mark.asyncio
async def test_active_mode_cancels_unneeded_reviewers(monkeypatch):
    from llm_council import council as council_mod
    from llm_council import layer_contracts

    monkeypatch.setenv("LLM_COUNCIL_EARLY_CONSENSUS", "true")
    # Anonymization shuffles; pin it so 'Response A' is deterministic.
    monkeypatch.setattr(council_mod.random, "shuffle", lambda x: None)
    reviewers = [f"r{i}" for i in range(1, 6)]
    delays = {f"r{i}": 0.01 * i for i in range(1, 5)}
    delays["r5"] = 30.0  # would dominate wall-clock if not cancelled
    calls, cancelled = [], []
    monkeypatch.setattr(council_mod, "query_model", _mock_query_model(delays, calls, cancelled))

    before = len(getattr(layer_contracts, "_layer_events", []))
    results, label_to_model, usage = await asyncio.wait_for(
        council_mod.stage2_collect_rankings(
            "q", _STAGE1, timeout=5.0, models=reviewers, on_progress=None
        ),
        timeout=10.0,  # far below r5's 30s: proves cancellation, not waiting
    )
    # After 4 unanimous A>B>C votes: A=8, B=4, remaining=1*2 → decided; r5 cancelled.
    assert "r5" in cancelled
    assert len(results) == 4
    # usage aggregated for the completed four only
    assert usage["prompt_tokens"] == 40
    events = getattr(layer_contracts, "_layer_events", [])
    new = [
        e
        for e in events[before:]
        if "early_consensus" in str(getattr(e.event_type, "value", e.event_type))
    ]
    assert new and new[-1].data["votes_saved"] == 1


@pytest.mark.asyncio
async def test_shadow_mode_runs_everything_and_emits_nothing(monkeypatch):
    from llm_council import council as council_mod
    from llm_council import layer_contracts

    monkeypatch.delenv("LLM_COUNCIL_EARLY_CONSENSUS", raising=False)
    monkeypatch.setattr(council_mod.random, "shuffle", lambda x: None)
    reviewers = [f"r{i}" for i in range(1, 6)]
    calls, cancelled = [], []
    monkeypatch.setattr(
        council_mod, "query_model", _mock_query_model({}, calls, cancelled)
    )

    async def _noop_progress(done, total, msg):
        return None

    before = len(getattr(layer_contracts, "_layer_events", []))
    results, _, usage = await council_mod.stage2_collect_rankings(
        "q", _STAGE1, timeout=5.0, models=reviewers, on_progress=_noop_progress
    )
    assert cancelled == []
    assert len(results) == 5  # every reviewer ran
    assert usage["prompt_tokens"] == 50
    events = getattr(layer_contracts, "_layer_events", [])
    new = [
        e
        for e in events[before:]
        if "early_consensus" in str(getattr(e.event_type, "value", e.event_type))
    ]
    assert not new  # shadow mode: log only, no event
