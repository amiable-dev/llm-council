"""Webhook lifecycle for a whole council run (#739, #740).

``run_full_council`` used to build its own ``EventBridge``, emit one event
(``council.deliberation_start``) in SYNC mode and never shut the bridge down.
Two defects followed, both follow-ups to GHSA-r7rh-j9cj-h9hh:

- #740 — ``council.complete`` / ``council.error`` (the DEFAULT subscription)
  were never delivered from that orchestrator.
- #739 — delivery ran inline, so the run and its HTTP response waited on a
  destination the caller chose.

``deliver_council_webhooks`` wraps the orchestrator and owns the bridge:

    start ─ council.deliberation_start
    run   ─ the wrapped coroutine; webhooks are delivered by a queue worker,
            so the run never waits on a receiver
    end   ─ council.complete, or council.error (exception, or the
            "all models failed" result), then the bridge is shut down

``webhook_delivery`` decides who waits for the queue to drain at the end:

- ``"await"`` (default): the call returns once every event has been delivered
  or has exhausted its retries. Right for library callers — an
  ``asyncio.run()`` loop that ends would otherwise drop pending deliveries.
- ``"background"``: the call returns immediately and the drain continues on
  the running loop. Right for a long-lived server (the HTTP endpoint), which
  calls ``drain_webhook_deliveries()`` on shutdown.

Everything here is soft-fail: a webhook problem never fails or delays a run.
With no ``webhook_config`` the wrapper is a plain passthrough.
"""

import asyncio
import functools
import inspect
import json
import logging
import time
from typing import Any, Awaitable, Callable, Dict, Optional, ParamSpec, Set, TypeVar

from .event_bridge import DispatchMode, EventBridge
from .types import WebhookConfig, WebhookEventType

logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")

# Strong references to in-flight background drains (the loop only keeps weak
# ones); each task removes itself when done.
_background: Set["asyncio.Task[None]"] = set()


def _jsonable(value: Any) -> Any:
    """A copy of ``value`` that always serialises (unknown objects → str)."""
    return json.loads(json.dumps(value, default=str))


class _Session:
    """One run's bridge. Every method swallows its own failures."""

    def __init__(self) -> None:
        self._bridge: Optional[EventBridge] = None
        self._t0 = time.monotonic()

    async def start(self, config: WebhookConfig, query: Any, models: Any) -> None:
        try:
            bridge = EventBridge(webhook_config=config, mode=DispatchMode.ASYNC)
            await bridge.start()
            self._bridge = bridge
        except Exception as e:
            logger.warning("Webhook session not started: %s", type(e).__name__)
            return
        if not models:
            try:
                from llm_council import council  # call-time: honours test patches

                models = council._get_council_models()
            except Exception:
                models = []
        await self._emit(
            WebhookEventType.DELIBERATION_START,
            {"query": str(query)[:100], "models": models},
            with_duration=False,
        )

    async def _emit(
        self, event: WebhookEventType, data: Dict[str, Any], with_duration: bool = True
    ) -> None:
        if self._bridge is None:
            return
        try:
            duration = int((time.monotonic() - self._t0) * 1000) if with_duration else None
            await self._bridge.emit_webhook(event, _jsonable(data), duration)
        except Exception as e:
            logger.warning("Webhook event %s not queued: %s", event.value, type(e).__name__)

    async def finish(self, result: Any) -> None:
        """Emit the terminal event for a returned result."""
        try:
            stage1, stage2, stage3, metadata = result
            failed = isinstance(stage3, dict) and stage3.get("model") == "error"
        except Exception:
            await self._emit(WebhookEventType.COMPLETE, {"status": "complete"})
            return
        if failed:
            await self._emit(
                WebhookEventType.ERROR,
                {"status": "failed", "error": str(stage3.get("response", ""))[:500]},
            )
            return
        await self._emit(
            WebhookEventType.COMPLETE,
            {
                "status": "complete",
                "model_count": len(stage1) if hasattr(stage1, "__len__") else None,
                "cache_hit": bool(isinstance(metadata, dict) and metadata.get("cache_hit")),
                "result": {"stage1": stage1, "stage2": stage2, "stage3": stage3},
            },
        )

    async def fail(self, error: BaseException) -> None:
        await self._emit(
            WebhookEventType.ERROR,
            {"status": "failed", "error_type": type(error).__name__, "error": str(error)[:500]},
        )

    async def _shutdown(self) -> None:
        try:
            if self._bridge is not None:
                await self._bridge.shutdown()
        except Exception as e:
            logger.warning("Webhook session shutdown failed: %s", type(e).__name__)

    async def close(self, background: bool) -> None:
        if self._bridge is None:
            return
        if background:
            task = asyncio.create_task(self._shutdown())
            _background.add(task)
            task.add_done_callback(_background.discard)
        else:
            await self._shutdown()


def deliver_council_webhooks(fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    """Give a council orchestrator the webhook lifecycle described above.

    The wrapped coroutine must accept ``webhook_config`` and
    ``webhook_delivery``; it does not need to act on either.
    """
    signature = inspect.signature(fn)

    @functools.wraps(fn)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        bound: Dict[str, Any] = {}
        try:
            bound = dict(signature.bind_partial(*args, **kwargs).arguments)
        except TypeError:
            pass
        config = bound.get("webhook_config")
        if not config:
            return await fn(*args, **kwargs)

        background = bound.get("webhook_delivery", "await") == "background"
        session = _Session()
        await session.start(config, bound.get("user_query", ""), bound.get("models"))
        try:
            result = await fn(*args, **kwargs)
        except Exception as e:
            await session.fail(e)
            await session.close(background)
            raise
        except BaseException as e:
            # Cancellation / shutdown: never await a drain on the way out.
            await session.fail(e)
            await session.close(background=True)
            raise
        await session.finish(result)
        await session.close(background)
        return result

    return wrapper


async def drain_webhook_deliveries(timeout: float = 10.0) -> None:
    """Wait (up to ``timeout`` seconds) for background deliveries to finish.

    For server shutdown hooks. Tasks still running at the timeout are left
    alone — the caller's loop teardown cancels them.
    """
    pending = set(_background)
    if pending:
        await asyncio.wait(pending, timeout=timeout)


__all__ = ["deliver_council_webhooks", "drain_webhook_deliveries"]
