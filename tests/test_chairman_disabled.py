"""PR #519: chairman_disabled skips Stage 3 synthesis for cost/latency.

Covers the council_stages.py short-circuits in stage3_synthesize_final and
quick_synthesis. The verify/gate-path interaction (build_verification_result
must not scrape the returned peer response as a verdict) is covered
separately in tests/test_unclear_reason.py::TestChairmanDisabledVerdict.
"""

import pytest

from llm_council import council_stages as council_mod


def _stage1():
    return [
        {"model": "model-a", "response": "Response from A"},
        {"model": "model-b", "response": "Response from B"},
    ]


def _agg(top_model="model-b"):
    return [
        {"model": top_model, "borda_score": 2.0, "rank": 1, "vote_count": 1},
        {"model": "model-a", "borda_score": 1.0, "rank": 2, "vote_count": 1},
    ]


class TestStage3ChairmanDisabled:
    @pytest.mark.asyncio
    async def test_returns_top_ranked_response_without_llm_call(self, monkeypatch):
        monkeypatch.setattr(council_mod, "_get_chairman_disabled", lambda: True)
        # Any call to query_model_with_status would mean synthesis wasn't
        # actually skipped — fail loudly instead of silently succeeding.
        monkeypatch.setattr(
            council_mod,
            "query_model_with_status",
            lambda *a, **kw: (_ for _ in ()).throw(
                AssertionError("chairman_disabled must not call the model")
            ),
        )

        result, usage, verdict = await council_mod.stage3_synthesize_final(
            "q", _stage1(), [], aggregate_rankings=_agg(top_model="model-b")
        )

        assert result["model"] == "model-b"
        assert result["response"] == "Response from B"
        assert result["chairman_disabled"] is True
        assert verdict is None
        assert usage == {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    @pytest.mark.asyncio
    async def test_falls_back_to_first_stage1_result_when_ranking_unmatched(self, monkeypatch):
        # aggregate_rankings names a model that isn't in stage1_results —
        # must not raise or return "No response available" when a real
        # response is available.
        monkeypatch.setattr(council_mod, "_get_chairman_disabled", lambda: True)

        result, _, verdict = await council_mod.stage3_synthesize_final(
            "q", _stage1(), [], aggregate_rankings=_agg(top_model="model-not-in-stage1")
        )

        assert result["model"] == "model-a"
        assert result["response"] == "Response from A"
        assert verdict is None

    @pytest.mark.asyncio
    async def test_falls_back_to_first_stage1_result_when_no_rankings(self, monkeypatch):
        monkeypatch.setattr(council_mod, "_get_chairman_disabled", lambda: True)

        result, _, verdict = await council_mod.stage3_synthesize_final(
            "q", _stage1(), [], aggregate_rankings=None
        )

        assert result["model"] == "model-a"
        assert result["response"] == "Response from A"

    @pytest.mark.asyncio
    async def test_no_response_available_when_nothing_to_return(self, monkeypatch):
        monkeypatch.setattr(council_mod, "_get_chairman_disabled", lambda: True)

        result, _, verdict = await council_mod.stage3_synthesize_final(
            "q", [], [], aggregate_rankings=None
        )

        assert result["response"] == "No response available"
        assert result["chairman_disabled"] is True


class TestQuickSynthesisChairmanDisabled:
    @pytest.mark.asyncio
    async def test_returns_first_successful_response_directly(self, monkeypatch):
        monkeypatch.setattr(council_mod, "_get_chairman_disabled", lambda: True)

        model_responses = {
            "model-a": {"status": council_mod.STATUS_OK, "response": "A's answer"},
            "model-b": {"status": council_mod.STATUS_OK, "response": "B's answer"},
        }

        text, usage = await council_mod.quick_synthesis("q", model_responses)

        assert text in ("A's answer", "B's answer")  # dict order is insertion order (A)
        assert text == "A's answer"
        assert usage == {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    @pytest.mark.asyncio
    async def test_still_reports_error_when_nothing_succeeded(self, monkeypatch):
        # chairman_disabled must not mask the "no responses at all" case.
        monkeypatch.setattr(council_mod, "_get_chairman_disabled", lambda: True)

        model_responses = {"model-a": {"status": "error", "response": None}}
        text, usage = await council_mod.quick_synthesis("q", model_responses)

        assert text == "Error: No model responses available for synthesis."
        assert usage == {}

    @pytest.mark.asyncio
    async def test_disabled_false_is_unaffected(self, monkeypatch):
        # Regression guard: default (disabled=False) must still attempt the
        # normal LLM-backed synthesis path (via query_model), not the
        # chairman_disabled short-circuit.
        monkeypatch.setattr(council_mod, "_get_chairman_disabled", lambda: False)

        called = {}

        async def fake_query(model, messages, timeout=120.0, disable_tools=False, **kw):
            called["hit"] = True
            return {
                "content": "synthesized",
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }

        monkeypatch.setattr(council_mod, "query_model", fake_query)

        model_responses = {"model-a": {"status": council_mod.STATUS_OK, "response": "A's answer"}}
        text, usage = await council_mod.quick_synthesis("q", model_responses)

        assert called.get("hit") is True
        assert text == "synthesized"
