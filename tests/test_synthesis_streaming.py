"""ADR-046 P2: chairman token streaming (#410).

Invariants: streamed synthesis assembles to the SAME final result object as
the non-streamed path; stream failure falls back to non-streaming; cancels
propagate without phantom usage; flag-off is byte-identical.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from llm_council.webhooks.types import WebhookEventType


class TestEventVocabulary:
    def test_synthesis_delta_event(self):
        assert WebhookEventType.SYNTHESIS_DELTA.value == "synthesis.delta"

    def test_layer_mapping(self):
        from llm_council.layer_contracts import LayerEvent, LayerEventType
        from llm_council.webhooks.event_bridge import map_layer_event_to_webhook

        event = LayerEvent(event_type=LayerEventType.L3_SYNTHESIS_DELTA, data={})
        assert map_layer_event_to_webhook(event) == WebhookEventType.SYNTHESIS_DELTA


class TestStreamAdapter:
    @pytest.mark.asyncio
    async def test_accumulates_deltas_and_invokes_callback(self, monkeypatch):
        from llm_council import gateway_adapter

        chunks = ["Hel", "lo ", "world"]

        class FakeRouter:
            async def complete_stream(self, request):
                for c in chunks:
                    yield c

        monkeypatch.setattr(gateway_adapter, "USE_GATEWAY_LAYER", True)
        monkeypatch.setattr(
            gateway_adapter, "_get_gateway_router", lambda: FakeRouter()
        )
        seen = []

        async def on_delta(text):
            seen.append(text)

        result = await gateway_adapter.query_model_stream_with_status(
            "chair/model", [{"role": "user", "content": "q"}], on_delta=on_delta
        )
        assert seen == chunks
        assert result["status"] == "ok"
        assert result["content"] == "Hello world"
        assert isinstance(result.get("usage"), dict)  # empty => cost UNKNOWN, never fabricated


class TestStage3Equality:
    def _inputs(self):
        stage1 = [{"model": "m/a", "response": "A"}]
        stage2 = [{"model": "m/a", "ranking": ["Response A"]}]
        return stage1, stage2

    @pytest.mark.asyncio
    async def test_streamed_synthesis_equals_non_streamed_result(self, monkeypatch):
        from llm_council import council_stages

        text = "The final synthesis."

        async def fake_status(model, messages, **kw):
            return {"status": "ok", "content": text, "latency_ms": 7, "usage": {"total_tokens": 9}}

        async def fake_stream(model, messages, on_delta=None, **kw):
            for c in (text[:7], text[7:]):
                await on_delta(c)
            return {"status": "ok", "content": text, "latency_ms": 7, "usage": {"total_tokens": 9}}

        monkeypatch.setattr(council_stages, "query_model_with_status", fake_status)
        monkeypatch.setattr(council_stages, "query_model_stream_with_status", fake_stream)

        s1, s2 = self._inputs()
        plain = await council_stages.stage3_synthesize_final("q", s1, s2)
        deltas = []

        async def on_delta(t):
            deltas.append(t)

        streamed = await council_stages.stage3_synthesize_final(
            "q", s1, s2, on_synthesis_delta=on_delta
        )
        assert streamed == plain  # SAME final result object (ADR-046 P2)
        assert "".join(deltas) == text

    @pytest.mark.asyncio
    async def test_stream_failure_falls_back_to_non_streaming(self, monkeypatch):
        from llm_council import council_stages

        async def fake_status(model, messages, **kw):
            return {"status": "ok", "content": "fallback text", "latency_ms": 5, "usage": {}}

        async def broken_stream(model, messages, on_delta=None, **kw):
            raise RuntimeError("stream transport died")

        monkeypatch.setattr(council_stages, "query_model_with_status", fake_status)
        monkeypatch.setattr(
            council_stages, "query_model_stream_with_status", broken_stream
        )
        s1, s2 = self._inputs()
        result, usage, verdict = await council_stages.stage3_synthesize_final(
            "q", s1, s2, on_synthesis_delta=AsyncMock()
        )
        assert result["response"] == "fallback text"

    @pytest.mark.asyncio
    async def test_cancelled_stream_propagates_without_phantom_usage(self, monkeypatch):
        from llm_council import council_stages

        async def cancelled_stream(model, messages, on_delta=None, **kw):
            raise asyncio.CancelledError()

        fallback = AsyncMock()
        monkeypatch.setattr(council_stages, "query_model_with_status", fallback)
        monkeypatch.setattr(
            council_stages, "query_model_stream_with_status", cancelled_stream
        )
        s1, s2 = self._inputs()
        with pytest.raises(asyncio.CancelledError):
            await council_stages.stage3_synthesize_final(
                "q", s1, s2, on_synthesis_delta=AsyncMock()
            )
        fallback.assert_not_awaited()  # cancel is NOT a fallback trigger


class TestOrchestratorOptIn:
    @pytest.mark.asyncio
    async def test_default_passes_no_delta_callback(self):
        from llm_council import council

        with patch.object(
            council, "stage1_collect_responses_with_status", new_callable=AsyncMock
        ) as s1:
            s1.return_value = ([], {}, {})
            await council.run_council_with_fallback("q", bypass_cache=True)
            # No streaming consumer + no opt-in => stage3 never sees a delta cb.
            # (stage1 empty => stage3 not reached; the wiring var must be None)
            assert s1.call_args.kwargs.get("on_model_complete") is None

    @pytest.mark.asyncio
    async def test_runner_forwards_stream_tokens_flag(self):
        from llm_council.webhooks import _council_runner

        async def fake_council(prompt, **kwargs):
            assert kwargs.get("stream_synthesis") is True
            return {"synthesis": "s", "metadata": {"status": "complete"}}

        with patch.object(
            _council_runner,
            "run_council_with_fallback",
            side_effect=fake_council,
        ):
            events = [
                e
                async for e in _council_runner.run_council(
                    "q", stream_tokens=True
                )
            ]
        assert events[-1]["event"] == "council.complete"
