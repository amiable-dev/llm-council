"""Map the ADR-011 usage summary to PostHog ``$ai_generation`` events (ADR-050 Part 1).

Emits one ``$ai_generation`` per council-member model from ``usage.by_model``.
Off by default (gated on ``posthog_emission_enabled``) and soft-fail — never
raises into or delays a verification.

The load-bearing mapping rule is the cache subtraction: PostHog's cost engine
and the cache-hit-rate tile (``cache_read / (cache_read + input)``) assume
**exclusive** token counting, so ``$ai_input_tokens`` MUST be the non-cached
input count. We clamp with ``max(0, prompt - cache_read)`` so an
already-exclusive route or a ``cached > prompt`` reporting anomaly never
produces a negative count.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from .posthog_emitter import emit, posthog_emission_enabled, scrub_exception

logger = logging.getLogger(__name__)

# Consumers post evaluations against this actor when none is supplied.
DEFAULT_DISTINCT_ID = "llm-council"


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    """Coerce a cost to a finite float, else 0.0 — a junk value must never drop
    the whole event via an unguarded ``float()`` raise."""
    try:
        import math

        f = float(value or 0.0)
        return f if math.isfinite(f) else 0.0
    except (TypeError, ValueError):
        return 0.0


def build_generation_properties(
    model: str,
    model_usage: Dict[str, Any],
    *,
    verification_id: str,
    tier: Optional[str] = None,
    route: Optional[str] = None,
    round_index: Optional[int] = None,
    subject_sha: Optional[str] = None,
    consumer: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the ``$ai_generation`` properties for one ``by_model`` entry.

    ``$ai_total_cost_usd`` is our ADR-011 ground-truth cost (overrides PostHog's
    auto-calc) — emitted only when ``cost_known`` so an estimate is never
    presented as a bill. ``$ai_cache_creation_input_tokens`` is Anthropic-
    specific and omitted when zero.
    """
    prompt = _int(model_usage.get("prompt_tokens"))
    completion = _int(model_usage.get("completion_tokens"))
    cache_read = _int(model_usage.get("cached_tokens"))
    cache_write = _int(model_usage.get("cache_write_tokens"))

    props: Dict[str, Any] = {
        "$ai_trace_id": verification_id,
        "$ai_model": model,
        "$ai_provider": model.split("/", 1)[0] if "/" in model else "unknown",
        # Cache-subtraction clamp (ADR-050 Part 1): non-cached input only.
        "$ai_input_tokens": max(0, prompt - cache_read),
        "$ai_output_tokens": completion,
        "$ai_cache_read_input_tokens": cache_read,
    }
    if cache_write:
        props["$ai_cache_creation_input_tokens"] = cache_write
    if model_usage.get("cost_known"):
        props["$ai_total_cost_usd"] = _float(model_usage.get("cost_usd"))
    for key, value in (
        ("tier", tier),
        ("route", route),
        ("round", round_index),
        ("subject_sha", subject_sha),
        ("consumer", consumer),
    ):
        if value is not None:
            props[key] = value
    return props


def emit_generation_events(
    usage: Optional[Dict[str, Any]],
    *,
    verification_id: str,
    tier: Optional[str] = None,
    route: Optional[str] = None,
    round_index: Optional[int] = None,
    subject_sha: Optional[str] = None,
    consumer: Optional[str] = None,
) -> None:
    """Emit one ``$ai_generation`` per council-member model. Soft-fail, opt-in.

    ``$ai_trace_id`` is the ``verification_id`` (the cross-repo contract);
    ``distinct_id`` is the opaque ``consumer`` (or ``llm-council``).
    """
    if not posthog_emission_enabled() or not usage or not verification_id:
        return
    try:
        distinct_id = consumer or DEFAULT_DISTINCT_ID
        for model, model_usage in (usage.get("by_model") or {}).items():
            if not isinstance(model_usage, dict):
                continue
            props = build_generation_properties(
                str(model),
                model_usage,
                verification_id=verification_id,
                tier=tier,
                route=route,
                round_index=round_index,
                subject_sha=subject_sha,
                consumer=consumer,
            )
            emit("$ai_generation", props, distinct_id=distinct_id)
    except Exception as exc:  # emission must never break a run
        logger.debug("emit_generation_events failed (ignored): %s", scrub_exception(exc))
