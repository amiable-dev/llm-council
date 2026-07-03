"""ADR-046 P1: rich SSE stage events (#409).

Covers: new event vocabulary, versioned envelope (v/session_id/ts/seq),
per-model stage-1 events, per-reviewer stage-2 events, stage3.start,
ordering invariants, and the byte-identical non-stream guarantee.
"""

import asyncio
from unittest import mock
from unittest.mock import AsyncMock, patch

import pytest

from llm_council.webhooks.types import WebhookEventType


class TestEventVocabulary:
    def test_new_event_types_exist_with_adr_names(self):
        assert WebhookEventType.STAGE1_RESPONSE.value == "stage1.response"
        assert WebhookEventType.STAGE2_REVIEW.value == "stage2.review"
        assert (
            WebhookEventType.CONSENSUS_EARLY_TERMINATION.value
            == "consensus.early_termination"
        )
        assert WebhookEventType.STAGE3_START.value == "stage3.start"

    def test_layer_mapping_covers_new_events(self):
        from llm_council.layer_contracts import LayerEvent, LayerEventType
        from llm_council.webhooks.event_bridge import map_layer_event_to_webhook

        cases = {
            LayerEventType.L3_STAGE1_RESPONSE: WebhookEventType.STAGE1_RESPONSE,
            LayerEventType.L3_STAGE2_REVIEW: WebhookEventType.STAGE2_REVIEW,
            LayerEventType.L3_STAGE3_START: WebhookEventType.STAGE3_START,
            LayerEventType.L3_EARLY_CONSENSUS_TERMINATION: (
                WebhookEventType.CONSENSUS_EARLY_TERMINATION
            ),
        }
        for layer_type, webhook_type in cases.items():
            event = LayerEvent(event_type=layer_type, data={})
            assert map_layer_event_to_webhook(event) == webhook_type


class TestStage1PerModelCallback:
    @pytest.mark.asyncio
    async def test_gateway_invokes_on_model_complete_per_model(self):
        from llm_council.gateway_adapter import query_models_with_progress

        seen = []

        async def on_model_complete(model, result):
            seen.append((model, result.get("status")))

        async def fake_query(model, messages, **kwargs):
            return {"status": "ok", "content": f"resp-{model}", "latency_ms": 5}

        with patch(
            "llm_council.gateway_adapter.USE_GATEWAY_LAYER", False
        ), patch(
            "llm_council.gateway_adapter._direct_query_models_with_progress",
            new_callable=AsyncMock,
        ) as direct:
            await query_models_with_progress(
                ["m/a", "m/b"], [{"role": "user", "content": "q"}],
                on_model_complete=on_model_complete,
            )
            # Direct path receives the callback (its own unit covers invocation).
            assert direct.call_args.kwargs.get("on_model_complete") is on_model_complete

    @pytest.mark.asyncio
    async def test_stage1_threads_callback_through(self):
        from llm_council import council_stages

        cb = AsyncMock()
        with patch(
            "llm_council.council_stages.query_models_with_progress",
            new_callable=AsyncMock,
            return_value={},
        ) as qmp:
            await council_stages.stage1_collect_responses_with_status(
                "q", models=["m/a"], on_model_complete=cb
            )
            assert qmp.call_args.kwargs.get("on_model_complete") is cb


class TestStage2ReviewCallback:
    def _stage1_results(self):
        return [
            {"model": "m/a", "response": "answer a"},
            {"model": "m/b", "response": "answer b"},
        ]

    @pytest.mark.asyncio
    async def test_on_review_event_fires_per_reviewer_with_parse_ok(self, monkeypatch):
        from llm_council import council_stages

        events = []

        async def on_review_event(kind, data):
            events.append((kind, data))

        async def fake_query_model(model, messages, **kwargs):
            return {
                "content": "FINAL RANKING:\n1. Response A\n2. Response B",
                "usage": {"total_tokens": 5},
            }

        monkeypatch.setattr(council_stages, "query_model", fake_query_model)
        monkeypatch.setattr(council_stages.random, "shuffle", lambda x: None)
        await council_stages.stage2_collect_rankings(
            "q",
            self._stage1_results(),
            models=["m/a", "m/b"],
            on_review_event=on_review_event,
        )
        reviews = [e for e in events if e[0] == "review"]
        assert len(reviews) == 2
        for _, data in reviews:
            assert data["parse_ok"] is True
            assert data["ranking"] == ["Response A", "Response B"]
            assert data["reviewer"] in ("m/a", "m/b")

    @pytest.mark.asyncio
    async def test_batch_path_when_no_consumers(self, monkeypatch):
        # Byte-identical non-stream guarantee: without on_progress /
        # on_review_event / early-consensus flag, stage2 must take the batch
        # (gather) path, not the incremental as_completed path.
        from llm_council import council_stages

        monkeypatch.delenv("LLM_COUNCIL_EARLY_CONSENSUS", raising=False)
        monkeypatch.setattr(council_stages.random, "shuffle", lambda x: None)

        async def fake_query_models_parallel(models, messages, **kwargs):
            return {
                m: {"content": "FINAL RANKING:\n1. Response A\n2. Response B"}
                for m in models
            }

        parallel = AsyncMock(side_effect=fake_query_models_parallel)
        monkeypatch.setattr(council_stages, "query_models_parallel", parallel)
        query_model_spy = AsyncMock()
        monkeypatch.setattr(council_stages, "query_model", query_model_spy)

        await council_stages.stage2_collect_rankings("q", self._stage1_results())
        parallel.assert_awaited()  # batch path
        query_model_spy.assert_not_awaited()  # incremental path untouched


class TestEnvelope:
    @pytest.mark.asyncio
    async def test_runner_events_carry_versioned_envelope(self):
        from llm_council.webhooks import _council_runner

        async def fake_council(prompt, **kwargs):
            on_event = kwargs.get("on_event")
            # Simulate bridge callbacks arriving in stage order.
            for name in ("stage1.response", "stage2.review", "stage3.start"):
                on_event(
                    mock.Mock(event=name, data={"payload": name})
                )
            await asyncio.sleep(0)
            return {"synthesis": "s", "metadata": {"status": "complete"}}

        with patch.object(
            _council_runner, "run_council_with_fallback", side_effect=fake_council
        ):
            events = [e async for e in _council_runner.run_council("q")]

        assert all(e.get("v") == 1 for e in events)
        session_ids = {e.get("session_id") for e in events}
        assert len(session_ids) == 1 and None not in session_ids
        seqs = [e["seq"] for e in events]
        assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)
        assert all("ts" in e for e in events)

    @pytest.mark.asyncio
    async def test_ordering_invariant_stage_events_before_terminal(self):
        from llm_council.webhooks import _council_runner

        async def fake_council(prompt, **kwargs):
            on_event = kwargs.get("on_event")
            for name in (
                "stage1.response",
                "stage1.response",
                "council.stage1.complete",
                "stage2.review",
                "council.stage2.complete",
                "stage3.start",
            ):
                on_event(mock.Mock(event=name, data={}))
            await asyncio.sleep(0)
            return {"synthesis": "s", "metadata": {"status": "complete"}}

        with patch.object(
            _council_runner, "run_council_with_fallback", side_effect=fake_council
        ):
            names = [e["event"] async for e in _council_runner.run_council("q")]

        # Terminal event is last; rich stage events preserve emission order.
        assert names[-1] == "council.complete"
        assert names.index("stage3.start") > names.index("stage2.review")
        assert names.index("stage2.review") > names.index("stage1.response")


class TestOrchestratorWiring:
    @pytest.mark.asyncio
    async def test_no_stream_consumer_passes_none_callbacks(self):
        # Byte-identical guarantee at the orchestrator: without on_event or
        # webhook_config, stage functions receive None callbacks.
        from llm_council import council

        with patch.object(
            council, "stage1_collect_responses_with_status", new_callable=AsyncMock
        ) as s1:
            s1.return_value = ([], {}, {})
            result = await council.run_council_with_fallback("q", bypass_cache=True)
            assert result["metadata"]["status"] == "failed"  # no responses
            assert s1.call_args.kwargs.get("on_model_complete") is None

    @pytest.mark.asyncio
    async def test_rich_events_reach_on_event_in_stage_order(self, monkeypatch):
        from llm_council import council, council_stages
        from llm_council.webhooks.types import WebhookConfig

        # Mirror the SSE runner: subscription via an internal webhook config
        # (an on_event-only bridge has an empty subscription set).
        webhook_config = WebhookConfig(
            url="internal://sse-capture",
            events=[
                WebhookEventType.STAGE1_RESPONSE.value,
                WebhookEventType.STAGE2_REVIEW.value,
                WebhookEventType.STAGE3_START.value,
            ],
        )
        captured = []

        def on_event(payload):
            captured.append(payload.event)

        async def fake_query_model(model, messages, **kwargs):
            return {
                "content": "FINAL RANKING:\n1. Response A\n2. Response B",
                "usage": {"total_tokens": 3},
            }

        async def fake_qmwp(models, messages, on_model_complete=None, **kwargs):
            out = {}
            for m in models:
                r = {
                    "status": "ok",
                    "content": f"answer from {m}",
                    "latency_ms": 3,
                    "usage": {"total_tokens": 2},
                }
                out[m] = r
                if on_model_complete is not None:
                    await on_model_complete(m, r)
            return out

        async def fake_stage3(*a, **kw):
            return "synthesis", {"total_tokens": 1}, None

        monkeypatch.setattr(
            council_stages, "query_models_with_progress", fake_qmwp
        )
        monkeypatch.setattr(council_stages, "query_model", fake_query_model)
        monkeypatch.setattr(council_stages.random, "shuffle", lambda x: None)
        monkeypatch.setattr(council, "stage3_synthesize_final", fake_stage3)
        monkeypatch.setattr(
            council, "_get_council_models", lambda: ["m/a", "m/b"]
        )

        await council.run_council_with_fallback(
            "q", bypass_cache=True, on_event=on_event, webhook_config=webhook_config
        )

        s1 = [i for i, e in enumerate(captured) if e == "stage1.response"]
        s2 = [i for i, e in enumerate(captured) if e == "stage2.review"]
        s3 = [i for i, e in enumerate(captured) if e == "stage3.start"]
        assert len(s1) == 2, captured
        assert len(s2) == 2, captured
        assert len(s3) == 1, captured
        assert max(s1) < min(s2) < max(s2) < s3[0]
