"""Shared council constants and ADR-011 usage accounting (ADR-046 P0, #408).

Verbatim moves from council.py; council.py re-exports these names.
"""

import logging
import math
from typing import Any, Awaitable, Callable, Dict, Optional

from llm_council.gateway_adapter import (
    STATUS_AUTH_ERROR,
    STATUS_ERROR,
    STATUS_OK,
    STATUS_RATE_LIMITED,
    STATUS_TIMEOUT,
)
from llm_council.log_safety import safe_log

logger = logging.getLogger(__name__)

# ADR-012: Tiered Timeout Strategy Constants
TIMEOUT_PER_MODEL_SOFT = 15.0
TIMEOUT_PER_MODEL_HARD = 25.0
TIMEOUT_SYNTHESIS_TRIGGER = 40.0
TIMEOUT_RESPONSE_DEADLINE = 50.0

# #660: default budget for the fallback chairman call in `quick_synthesis`,
# preserved at its historical hard-coded value so direct callers that pass no
# tier context behave as before. Callers WITH a tier budget must pass it
# explicitly — 15s is far below any tier's per-model budget, and this is the
# only synthesis attempt on the global-timeout path.
TIMEOUT_QUICK_SYNTHESIS = 15.0

# #648: floor for the Stage 2 / Stage 3 budgets on the consult path, in SECONDS.
# Equal to the historical hard-coded default in stage2_collect_rankings /
# stage3_synthesize_final. Every call site converted in #648 previously OMITTED
# the argument and so inherited exactly this value, which is what makes the
# "can only ever RAISE a budget" claim hold — it is a statement about those
# specific call sites, not a general property of the helper.
TIMEOUT_STAGE_FLOOR = 120.0

# #648: sanity ceiling for a stage budget, in seconds. The largest value any
# supported configuration can produce is reasoning's 300s per-model budget at
# the maximum LLM_COUNCIL_TIMEOUT_MULTIPLIER of 10.0 = 3000s, so anything above
# this is a unit slip (a raw `_ms` field) rather than an intent. Rejections are
# logged, never silent.
_MAX_STAGE_TIMEOUT = 3600.0


def resolve_stage_timeout(per_model_timeout: Optional[float]) -> float:
    """#648: derive the Stage 2 / Stage 3 budget from the tier's per-model one.

    Both consult orchestrators used to call ``stage2_collect_rankings`` and
    ``stage3_synthesize_final`` without a ``timeout``, so each ran at its own
    hard-coded 120s default no matter the tier — and
    ``LLM_COUNCIL_TIMEOUT_MULTIPLIER`` never reached them. ADR-040 fixed the
    same class of bug on the verify path (#545).

    The tier value raises the budget; ``TIMEOUT_STAGE_FLOOR`` guarantees it can
    never SHRINK the converted call sites below the historical default. That
    floor is load-bearing: high tier's per-model budget is 90s and balanced's is
    45s, so capping at ``per_model_timeout`` — the literal ADR-040 waterfall —
    would have created fresh instances of the very timeout this fixes.

    Args:
        per_model_timeout: The per-model budget **in SECONDS**, matching
            ``run_council_with_fallback``'s parameter of the same name.
            ``TierContract`` stores this figure in MILLISECONDS as
            ``per_model_timeout_ms``; callers holding a contract must divide by
            1000, as ``facade.py`` and ``http_server.py`` do. Passing the raw
            ``_ms`` field would produce a 300,000-second budget — i.e. silently
            disable the stage timeout — so anything non-finite or beyond
            ``_MAX_STAGE_TIMEOUT`` is rejected back to the floor rather than
            trusted (a unit slip is always a bug, never a 3.5-day budget).

    Returns:
        A finite, positive budget in seconds, never below ``TIMEOUT_STAGE_FLOOR``.

    Note:
        This is a NOMINAL stage budget, not guaranteed wall-clock. The outer
        bound stays ``synthesis_deadline``, whose global ``wait_for`` fires
        first when it is the tighter of the two and degrades to
        ``quick_synthesis`` rather than to a stage error string.
    """
    if per_model_timeout is None:
        return TIMEOUT_STAGE_FLOOR
    try:
        value = float(per_model_timeout)
    except (TypeError, ValueError, OverflowError):
        # OverflowError: float(10**400) and friends. The docstring promises a
        # fallback for anything unusable, so the tuple must cover it (#650 gate).
        # CWE-117 (#651): the rejected value is arbitrary by definition here,
        # so it is CR/LF-collapsed before it reaches the log line.
        logger.warning(
            "non-numeric per_model_timeout %s; using the %ss stage floor",
            safe_log(repr(per_model_timeout)),
            TIMEOUT_STAGE_FLOOR,
        )
        return TIMEOUT_STAGE_FLOOR
    # Explicit rather than incidental: NaN would propagate through max() (it
    # compares False against everything), and a millisecond value passed by
    # mistake would read as a multi-day budget. Both land on the floor, so the
    # documented contract is load-bearing instead of a side effect of max().
    if not math.isfinite(value) or value <= 0.0 or value > _MAX_STAGE_TIMEOUT:
        # Already proven finite-or-not by float(), so no CR/LF risk here.
        logger.warning(
            "implausible per_model_timeout %s seconds (expected 0 < t <= %s; "
            "a value near 1000x the tier budget means a TierContract "
            "per_model_timeout_ms was passed without dividing by 1000); "
            "using the %ss stage floor",
            value,
            _MAX_STAGE_TIMEOUT,
            TIMEOUT_STAGE_FLOOR,
        )
        return TIMEOUT_STAGE_FLOOR
    return max(value, TIMEOUT_STAGE_FLOOR)


# ADR-012: Model Status Types (mirrors openrouter status types)
MODEL_STATUS_OK = STATUS_OK
MODEL_STATUS_TIMEOUT = STATUS_TIMEOUT
MODEL_STATUS_ERROR = STATUS_ERROR
MODEL_STATUS_RATE_LIMITED = STATUS_RATE_LIMITED
MODEL_STATUS_AUTH_ERROR = STATUS_AUTH_ERROR

# Progress callback type
ProgressCallback = Callable[[int, int, str], Awaitable[None]]


def _merge_cost_source(bucket: Dict[str, Any], source: Optional[str]) -> None:
    """Accumulate cost provenance across calls.

    #694: a model's stage-1 call might be provider-reported and its stage-2
    call registry-estimated. Claiming either label for the sum would be false,
    so disagreeing sources collapse to ``"mixed"`` and the estimated portion
    stays separately visible in ``cost_estimated_usd``. A call with no source
    contributes nothing rather than overwriting a known one.
    """
    if not source:
        return
    existing = bucket.get("cost_source")
    if existing is None:
        bucket["cost_source"] = source
    elif existing != source:
        bucket["cost_source"] = "mixed"


def _as_number(value: Any) -> float:
    """Coerce a provider-supplied count to a number, or 0.

    #692 gate: token aggregation runs on the deliberation path, OUTSIDE the
    soft-fail wrapper around persistence. A provider returning `null` or a
    string for a token count would raise a TypeError and fail a consult that
    had already completed and already been billed.
    """
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, (int, float)):
        return value if math.isfinite(value) else 0
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0
    return parsed if math.isfinite(parsed) else 0


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
    cost = _as_number(raw_cost)
    # #694: provenance rides with the figure. An estimate that cannot be told
    # apart from a measurement is worse than no figure, because it WILL be
    # summed with real ones.
    source = usage.get("cost_source")
    estimated = cost if source == "registry_estimate" else 0.0
    cached = usage.get("cached_tokens", 0) or 0
    # ADR-049 D4: cache-write tokens ride the same aggregation; absent => 0.
    cache_write = usage.get("cache_write_tokens", 0) or 0
    total_usage["cost_usd"] = total_usage.get("cost_usd", 0.0) + cost
    total_usage["cost_estimated_usd"] = (
        total_usage.get("cost_estimated_usd", 0.0) + estimated
    )
    _merge_cost_source(total_usage, source)
    total_usage["cached_tokens"] = total_usage.get("cached_tokens", 0) + cached
    total_usage["cache_write_tokens"] = (
        total_usage.get("cache_write_tokens", 0) + cache_write
    )
    # Track whether ANY cost was reported so the summary can tell a genuine
    # $0 (free/local) from unknown cost (None) — a present cost, even 0.0, is
    # "known".
    if raw_cost is not None:
        total_usage["cost_known"] = True
    else:
        # #692 gate: `cost_known` means "at least one call reported a cost", so
        # a session mixing reported and unreported calls records a PARTIAL sum
        # that reads as a measurement. That is a lower bound presented as a
        # total — the exact failure invoice reconciliation must not have.
        # `cost_complete` is the flag a total can be trusted on.
        total_usage["cost_incomplete"] = True
    if model is not None:
        bucket = total_usage.setdefault("by_model", {}).setdefault(
            model,
            {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "cost_usd": 0.0,
                "cached_tokens": 0,
                "cache_write_tokens": 0,
            },
        )
        bucket["prompt_tokens"] += _as_number(usage.get("prompt_tokens"))
        bucket["completion_tokens"] += _as_number(usage.get("completion_tokens"))
        bucket["total_tokens"] += _as_number(usage.get("total_tokens"))
        bucket["cost_usd"] += cost
        bucket["cost_estimated_usd"] = bucket.get("cost_estimated_usd", 0.0) + estimated
        _merge_cost_source(bucket, source)
        bucket["cached_tokens"] += cached
        bucket["cache_write_tokens"] = bucket.get("cache_write_tokens", 0) + cache_write
        if raw_cost is not None:
            bucket["cost_known"] = True
        else:
            bucket["cost_incomplete"] = True


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
        "cache_write_tokens": sum(
            s.get("cache_write_tokens", 0) for s in by_stage.values()
        ),
        "cost_known": any(s.get("cost_known", False) for s in by_stage.values()),
    }
    numeric_keys = (
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "cost_usd",
        "cached_tokens",
        "cache_write_tokens",
    )
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
                    "cache_write_tokens": 0,
                    "cost_known": False,
                },
            )
            for key in numeric_keys:  # never iterate the bool cost_known
                agg[key] += _as_number(model_usage.get(key))
            agg["cost_estimated_usd"] = agg.get("cost_estimated_usd", 0.0) + _as_number(
                model_usage.get("cost_estimated_usd")
            )
            _merge_cost_source(agg, model_usage.get("cost_source"))
            if model_usage.get("cost_known"):
                agg["cost_known"] = True
            if model_usage.get("cost_incomplete"):
                agg["cost_incomplete"] = True
    return {"by_stage": by_stage, "by_model": by_model, "total": grand_total}


def persist_council_performance(
    session_id: str,
    model_statuses: Any,
    aggregate_rankings: Any,
    stage2_results: Any,
    usage_summary: Any,
) -> int:
    """ADR-011 / #692: write one performance record per model for a consult.

    Before this, `performance_metrics.jsonl` had exactly one writer — the
    verify path. Every `consult`, the path an operator is actually billed for,
    left no local trace at all, so a recorded total could not be compared with
    a provider invoice and nobody could tell "cheap" from "unrecorded".

    Both consult orchestrators route through here rather than calling
    `persist_session_performance_data` directly, so the two cannot drift in
    what they record, and so the council's list-shaped `aggregate_rankings` is
    normalised in one place instead of at each call site.

    Soft-fail by contract: telemetry must never fail a deliberation that has
    already completed and already cost money. Returns the number of records
    written, 0 on any failure.
    """
    try:
        # The council carries rankings as a list of {"model": ..., ...};
        # `persist_session_performance_data` wants them keyed by model.
        if isinstance(aggregate_rankings, dict):
            rankings = aggregate_rankings
        elif isinstance(aggregate_rankings, list):
            rankings = {
                r["model"]: r
                for r in aggregate_rankings
                if isinstance(r, dict) and isinstance(r.get("model"), str)
            }
        else:
            rankings = {}

        from llm_council.performance.integration import persist_session_performance_data

        return persist_session_performance_data(
            session_id=session_id,
            model_statuses=model_statuses or {},
            aggregate_rankings=rankings,
            stage2_results=stage2_results,
            usage_by_model=(usage_summary or {}).get("by_model"),
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("performance persistence failed (ignored): %s", exc, exc_info=True)
        return 0
