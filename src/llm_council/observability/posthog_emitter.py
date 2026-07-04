"""Opt-in PostHog LLM Analytics emitter foundation (ADR-050 Part 5 + transport).

Off by default: with no ``POSTHOG_API_KEY`` the emitter is disabled and every
entry point is a no-op — byte-identical to pre-ADR-050 behavior, and the
optional ``posthog`` SDK is never imported. Emission is **soft-fail**: any
failure (missing SDK, bad key, network down) is logged at debug and never
raises into or delays a verification (ADR-011/024 convention).

This module is only the foundation (config + transport). The actual
``$ai_generation`` property mapping lands in ADR-050 D2 (#474).
"""

from __future__ import annotations

import atexit
import logging
import os
import threading
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# EU ingestion endpoint (ADR-050 Part 5). Note the `.i.` host — `eu.posthog.com`
# is the app/private host and is wrong for capture. The SDK maps app hosts to
# ingestion hosts, but we default explicitly.
DEFAULT_HOST = "https://eu.i.posthog.com"

# Bounded flush: dropped events are acceptable (soft-fail), a hung process is
# not. shutdown() joins the flush thread for at most this many seconds.
_FLUSH_TIMEOUT_S = 3.0

_lock = threading.Lock()
_client: Optional[Any] = None
_init_attempted = False
_atexit_registered = False


def posthog_emission_enabled() -> bool:
    """True iff a PostHog project key is configured (opt-in, off by default)."""
    return bool(os.getenv("POSTHOG_API_KEY"))


def scrub_exception(exc: BaseException) -> str:
    """Return the exception TYPE name only (ADR-050 Part 2 residual-leakage rule).

    Provider/gateway errors sometimes echo the prompt in their message; the
    soft-fail paths log this scrubbed form so customer code can never leak into
    a debug log (and never into a property).
    """
    return type(exc).__name__


def _get_client() -> Optional[Any]:
    """Lazily build the PostHog client; ``None`` if disabled or unavailable.

    Import-guarded: the optional ``posthog`` SDK is imported only when a key is
    configured, so an unconfigured install pays nothing and never needs the
    dependency. Initialization is attempted at most once; a failure caches
    ``None`` (soft-fail) rather than retrying on every emit.
    """
    global _client, _init_attempted, _atexit_registered
    if not posthog_emission_enabled():
        return None
    with _lock:
        if _init_attempted:
            return _client
        _init_attempted = True
        # Re-read the key under the lock via getenv (consistent with
        # posthog_emission_enabled) — never os.environ[...], which would
        # KeyError if the env was cleared between the enabled-check and here.
        key = os.getenv("POSTHOG_API_KEY")
        if not key:
            _client = None
            return None
        try:
            from posthog import Posthog  # optional dependency — [posthog] extra

            _client = Posthog(
                project_api_key=key,
                host=os.getenv("POSTHOG_HOST", DEFAULT_HOST),
            )
            if not _atexit_registered:
                atexit.register(shutdown)
                _atexit_registered = True
        except Exception as exc:  # missing SDK, bad config — soft-fail
            logger.debug("posthog emitter init failed (disabled): %s", scrub_exception(exc))
            _client = None
        return _client


def emit(event: str, properties: Dict[str, Any], distinct_id: str) -> None:
    """Emit one event via the SDK's non-blocking batched ``capture()``.

    Soft-fail: never raises and never blocks the caller on network I/O (the
    SDK buffers to a background consumer). A no-op when emission is disabled.
    """
    try:
        client = _get_client()
        if client is None:
            return
        client.capture(distinct_id=distinct_id, event=event, properties=properties)
    except Exception as exc:  # emission must never break a run
        logger.debug("posthog emit failed for %s (ignored): %s", event, scrub_exception(exc))


def shutdown(timeout: float = _FLUSH_TIMEOUT_S) -> None:
    """Flush the buffer on exit, bounded so a stuck flush never hangs the process.

    The flush runs on a daemon thread joined for ``timeout`` seconds; if it
    hasn't returned, we drop the remaining buffer and move on (the daemon dies
    with the process). Registered via ``atexit`` on client init; also safe to
    call explicitly from a CLI/gate teardown.
    """
    with _lock:  # snapshot under the lock — a concurrent reset must not race
        client = _client
    if client is None:
        return

    def _flush() -> None:
        try:
            fn = getattr(client, "shutdown", None) or getattr(client, "flush", None)
            if fn is not None:
                fn()
        except Exception as exc:  # flush failure is non-fatal
            logger.debug("posthog shutdown failed (ignored): %s", scrub_exception(exc))

    t = threading.Thread(target=_flush, name="posthog-flush", daemon=True)
    t.start()
    t.join(timeout)


def reset_for_testing() -> None:
    """Test hook: clear the client singleton so env changes take effect.

    Deliberately does NOT clear ``_atexit_registered``: the atexit handler is
    process-global and idempotent (None-guarded), so it must be registered at
    most once for the process, never re-registered per test.
    """
    global _client, _init_attempted
    with _lock:
        _client = None
        _init_attempted = False
