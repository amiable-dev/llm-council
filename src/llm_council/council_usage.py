"""Shared council constants and ADR-011 usage accounting (ADR-046 P0, #408).

Verbatim moves from council.py; council.py re-exports these names.
"""

from typing import Any, Awaitable, Callable, Dict, Optional

from llm_council.gateway_adapter import (
    STATUS_AUTH_ERROR,
    STATUS_ERROR,
    STATUS_OK,
    STATUS_RATE_LIMITED,
    STATUS_TIMEOUT,
)

# ADR-012: Tiered Timeout Strategy Constants
TIMEOUT_PER_MODEL_SOFT = 15.0
TIMEOUT_PER_MODEL_HARD = 25.0
TIMEOUT_SYNTHESIS_TRIGGER = 40.0
TIMEOUT_RESPONSE_DEADLINE = 50.0

# ADR-012: Model Status Types (mirrors openrouter status types)
MODEL_STATUS_OK = STATUS_OK
MODEL_STATUS_TIMEOUT = STATUS_TIMEOUT
MODEL_STATUS_ERROR = STATUS_ERROR
MODEL_STATUS_RATE_LIMITED = STATUS_RATE_LIMITED
MODEL_STATUS_AUTH_ERROR = STATUS_AUTH_ERROR

# Progress callback type
ProgressCallback = Callable[[int, int, str], Awaitable[None]]


def _add_cost_to_usage(
    total_usage: Dict[str, Any], usage: Dict[str, Any], model: Optional[str] = None
) -> None:
    """ADR-011: accumulate cost_usd, cached_tokens, and optional per-model spend.

    Additive to the existing token aggregation. ``usage["cost"]`` may be None
    (provider didn't report it) and is treated as a 0 contribution. When
    ``model`` is given, the same figures also accumulate under
    ``total_usage["by_model"][model]`` (reviewer-primary attribution).
    """
    raw_cost = usage.get("cost")
    cost = raw_cost or 0.0
    cached = usage.get("cached_tokens", 0) or 0
    total_usage["cost_usd"] = total_usage.get("cost_usd", 0.0) + cost
    total_usage["cached_tokens"] = total_usage.get("cached_tokens", 0) + cached
    # Track whether ANY cost was reported so the summary can tell a genuine
    # $0 (free/local) from unknown cost (None) — a present cost, even 0.0, is
    # "known".
    if raw_cost is not None:
        total_usage["cost_known"] = True
    if model is not None:
        bucket = total_usage.setdefault("by_model", {}).setdefault(
            model,
            {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "cost_usd": 0.0,
                "cached_tokens": 0,
            },
        )
        bucket["prompt_tokens"] += usage.get("prompt_tokens", 0)
        bucket["completion_tokens"] += usage.get("completion_tokens", 0)
        bucket["total_tokens"] += usage.get("total_tokens", 0)
        bucket["cost_usd"] += cost
        bucket["cached_tokens"] += cached
        if raw_cost is not None:
            bucket["cost_known"] = True


def _build_usage_summary(by_stage: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """ADR-011: assemble the ``metadata["usage"]`` block from per-stage buckets.

    Produces ``{"by_stage", "by_model", "total"}`` where ``total`` sums tokens +
    cost + cached across stages and ``by_model`` merges per-model spend. Shared
    by both council entry points so the HTTP and MCP paths report identically.
    """
    grand_total = {
        "prompt_tokens": sum(s.get("prompt_tokens", 0) for s in by_stage.values()),
        "completion_tokens": sum(s.get("completion_tokens", 0) for s in by_stage.values()),
        "total_tokens": sum(s.get("total_tokens", 0) for s in by_stage.values()),
        "cost_usd": sum(s.get("cost_usd", 0.0) for s in by_stage.values()),
        "cached_tokens": sum(s.get("cached_tokens", 0) for s in by_stage.values()),
        "cost_known": any(s.get("cost_known", False) for s in by_stage.values()),
    }
    numeric_keys = ("prompt_tokens", "completion_tokens", "total_tokens", "cost_usd", "cached_tokens")
    by_model: Dict[str, Dict[str, Any]] = {}
    for stage_usage in by_stage.values():
        for model_id, model_usage in stage_usage.get("by_model", {}).items():
            agg = by_model.setdefault(
                model_id,
                {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "cost_usd": 0.0,
                    "cached_tokens": 0,
                    "cost_known": False,
                },
            )
            for key in numeric_keys:  # never iterate the bool cost_known
                agg[key] += model_usage.get(key, 0)
            if model_usage.get("cost_known"):
                agg["cost_known"] = True
    return {"by_stage": by_stage, "by_model": by_model, "total": grand_total}


