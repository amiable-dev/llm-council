"""#739 / #740: webhook lifecycle for ``run_full_council``.

Follow-ups to GHSA-r7rh-j9cj-h9hh. Before these fixes ``run_full_council``:

- emitted exactly one event, ``council.deliberation_start``, so the documented
  default subscription (``council.complete`` / ``council.error``) never
  received anything (#740);
- delivered it inline in SYNC mode, so the council run — and the HTTP response
  — waited on a destination the caller chose (#739);
- never shut its bridge down.

``webhooks/run_session.py`` now owns the lifecycle. Nothing here touches the
network: ``WebhookDispatcher.dispatch`` is replaced.
"""

import asyncio
from typing import List
from unittest.mock import AsyncMock, patch

import pytest

from llm_council.webhooks import run_session
from llm_council.webhooks.run_session import (
    deliver_council_webhooks,
    drain_webhook_deliveries,
)
from llm_council.webhooks.types import WebhookConfig, WebhookDeliveryResult, WebhookPayload

ALL = ["council.deliberation_start", "council.complete", "council.error"]
URL = "https://hooks.example.com/h"
OK = (
    [{"model": "a/b", "response": "one"}],
    [{"model": "a/b", "ranking": "x"}],
    {"model": "c/d", "response": "final"},
    {"usage": {}},
)
ALL_FAILED = ([], [], {"model": "error", "response": "All models failed to respond."}, {})


class Recorder:
    """Stands in for WebhookDispatcher.dispatch; optionally blocks on a gate."""

    def __init__(self, gate: "asyncio.Event | None" = None, fail: bool = False):
        self.payloads: List[WebhookPayload] = []
        self.gate = gate
        self.fail = fail

    async def __call__(self, config, payload):
        if self.gate is not None:
            await self.gate.wait()
        if self.fail:
            raise RuntimeError("receiver exploded")
        self.payloads.append(payload)
        return WebhookDeliveryResult(success=True, status_code=200, attempt=1)

    @property
    def events(self) -> List[str]:
        return [p.event for p in self.payloads]


@pytest.fixture
def recorder():
    rec = Recorder()
    with patch("llm_council.webhooks.dispatcher.WebhookDispatcher.dispatch", new=rec):
        yield rec


def _fake_council(result=OK, raises: "BaseException | None" = None, started=None):
    @deliver_council_webhooks
    async def run_full_council(
        user_query,
        bypass_cache=False,
        models=None,
        *,
        webhook_config=None,
        webhook_delivery="await",
    ):
        if started is not None:
            started.set()
        if raises is not None:
            raise raises
        return result

    return run_full_council


class TestNoWebhook:
    async def test_no_config_means_no_bridge_at_all(self):
        with patch.object(run_session, "EventBridge") as bridge:
            assert await _fake_council()("q") is OK
        bridge.assert_not_called()


class TestTerminalEvents:
    """#740 — the documented events are actually delivered."""

    async def test_default_subscription_receives_complete(self, recorder):
        # WebhookConfig's default events are [council.complete, council.error];
        # before the fix this subscription received nothing, ever.
        await _fake_council()("q", webhook_config=WebhookConfig(url=URL))
        assert recorder.events == ["council.complete"]

    async def test_events_in_order_with_one_request_id(self, recorder):
        await _fake_council()("q", webhook_config=WebhookConfig(url=URL, events=ALL))
        assert recorder.events == ["council.deliberation_start", "council.complete"]
        assert len({p.request_id for p in recorder.payloads}) == 1

    async def test_complete_carries_the_result(self, recorder):
        await _fake_council()("q", webhook_config=WebhookConfig(url=URL))
        data = recorder.payloads[0].data
        assert data["status"] == "complete"
        assert data["model_count"] == 1
        assert data["result"] == {"stage1": OK[0], "stage2": OK[1], "stage3": OK[2]}
        assert recorder.payloads[0].duration_ms is not None

    async def test_cache_hit_is_flagged(self, recorder):
        cached = (OK[0], OK[1], OK[2], {"cache_hit": True})
        await _fake_council(cached)("q", webhook_config=WebhookConfig(url=URL))
        assert recorder.payloads[0].data["cache_hit"] is True

    async def test_all_models_failed_is_an_error_not_a_completion(self, recorder):
        await _fake_council(ALL_FAILED)("q", webhook_config=WebhookConfig(url=URL))
        assert recorder.events == ["council.error"]
        assert "All models failed" in recorder.payloads[0].data["error"]

    async def test_exception_delivers_error_and_still_raises(self, recorder):
        run = _fake_council(raises=ValueError("boom"))
        with pytest.raises(ValueError, match="boom"):
            await run("q", webhook_config=WebhookConfig(url=URL))
        assert recorder.events == ["council.error"]
        assert recorder.payloads[0].data["error_type"] == "ValueError"

    async def test_start_event_keeps_its_shape(self, recorder):
        await _fake_council()(
            "q" * 300, models=["x/y"], webhook_config=WebhookConfig(url=URL, events=ALL)
        )
        start = recorder.payloads[0].data
        assert start == {"query": "q" * 100, "models": ["x/y"]}

    async def test_unserializable_result_does_not_break_delivery(self, recorder):
        odd = ([{"model": "a/b", "response": object()}], [], {"model": "c", "response": "r"}, {})
        assert await _fake_council(odd)("q", webhook_config=WebhookConfig(url=URL)) is odd
        assert recorder.events == ["council.complete"]


class TestOffTheRequestPath:
    """#739 — a slow or dead receiver never delays the council."""

    async def test_council_runs_while_start_delivery_is_still_pending(self):
        gate, started = asyncio.Event(), asyncio.Event()
        rec = Recorder(gate=gate)
        with patch("llm_council.webhooks.dispatcher.WebhookDispatcher.dispatch", new=rec):
            task = asyncio.create_task(
                _fake_council(started=started)(
                    "q",
                    webhook_config=WebhookConfig(url=URL, events=ALL),
                    webhook_delivery="background",
                )
            )
            # The receiver has not answered, yet the council body has run and
            # the call has returned.
            assert await asyncio.wait_for(task, timeout=1.0) is OK
            assert started.is_set()
            assert rec.payloads == []

            gate.set()
            await drain_webhook_deliveries(timeout=2.0)
        assert rec.events == ["council.deliberation_start", "council.complete"]

    async def test_await_mode_returns_only_after_delivery(self):
        # Library default: nothing is dropped when the caller's loop ends.
        rec = Recorder()
        with patch("llm_council.webhooks.dispatcher.WebhookDispatcher.dispatch", new=rec):
            await _fake_council()("q", webhook_config=WebhookConfig(url=URL))
            assert rec.events == ["council.complete"]

    async def test_background_tasks_are_released_after_draining(self, recorder):
        await _fake_council()(
            "q", webhook_config=WebhookConfig(url=URL), webhook_delivery="background"
        )
        await drain_webhook_deliveries(timeout=2.0)
        assert recorder.events == ["council.complete"]
        assert not run_session._background

    async def test_drain_gives_up_at_its_timeout(self):
        gate = asyncio.Event()  # never set: a receiver that hangs
        rec = Recorder(gate=gate)
        with patch("llm_council.webhooks.dispatcher.WebhookDispatcher.dispatch", new=rec):
            await _fake_council()(
                "q", webhook_config=WebhookConfig(url=URL), webhook_delivery="background"
            )
            await asyncio.wait_for(drain_webhook_deliveries(timeout=0.05), timeout=1.0)
            for task in list(run_session._background):
                task.cancel()
            await asyncio.gather(*run_session._background, return_exceptions=True)


class TestNeverFailsTheRun:
    async def test_receiver_error_is_swallowed(self):
        rec = Recorder(fail=True)
        with patch("llm_council.webhooks.dispatcher.WebhookDispatcher.dispatch", new=rec):
            assert await _fake_council()("q", webhook_config=WebhookConfig(url=URL)) is OK

    async def test_bridge_construction_failure_is_swallowed(self):
        with patch.object(run_session, "EventBridge", side_effect=RuntimeError("no bridge")):
            assert await _fake_council()("q", webhook_config=WebhookConfig(url=URL)) is OK

    async def test_cancellation_propagates_and_does_not_hang(self, recorder):
        run = _fake_council(raises=asyncio.CancelledError())
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(run("q", webhook_config=WebhookConfig(url=URL)), timeout=1.0)
        await drain_webhook_deliveries(timeout=2.0)
        assert recorder.events == ["council.error"]


class TestWiredIntoTheRealOrchestrator:
    async def test_run_full_council_is_wrapped(self):
        from llm_council import council

        assert getattr(council.run_full_council, "__wrapped__", None) is not None

    async def test_real_orchestrator_emits_error_when_all_models_fail(self, recorder):
        from llm_council import council

        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        with patch.object(council, "stage1_collect_responses", AsyncMock(return_value=([], usage))):
            _, _, stage3, _ = await council.run_full_council(
                "q", bypass_cache=True, webhook_config=WebhookConfig(url=URL, events=ALL)
            )
        assert stage3["model"] == "error"
        assert recorder.events == ["council.deliberation_start", "council.error"]

    async def test_orchestrator_has_no_bridge_code_of_its_own(self):
        # The original defect was a hand-rolled bridge that was started, used
        # once and never shut down. The lifecycle lives in one place now.
        import inspect

        from llm_council import council

        body = inspect.getsource(council.run_full_council.__wrapped__)
        assert "EventBridge(" not in body
        assert "event_bridge" not in body

    def test_http_endpoint_delivers_in_the_background(self, monkeypatch):
        from fastapi.testclient import TestClient

        from llm_council.http_server import app

        monkeypatch.setenv("LLM_COUNCIL_WEBHOOK_ALLOWED_HOSTS", "hooks.example.com")
        with patch("llm_council.http_server.run_full_council", new_callable=AsyncMock) as run:
            run.return_value = ([], [], {}, {})
            response = TestClient(app).post(
                "/v1/council/run",
                json={"prompt": "hi", "api_key": "k", "webhook_url": URL},
            )
        assert response.status_code == 200
        assert run.call_args.kwargs["webhook_delivery"] == "background"
