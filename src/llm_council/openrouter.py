"""OpenRouter API client for parallel LLM queries.

ADR-026 Phase 2: Added reasoning_params support for reasoning models.
"""

import httpx
import asyncio
import logging
import math
import time
from typing import TYPE_CHECKING, List, Dict, Any, Optional, Callable, Awaitable

# ADR-032: Migrated to unified_config
from llm_council.log_safety import safe_log
from llm_council.unified_config import get_api_key

from llm_council.gateway.resolver import resolve_endpoint, resolve_model_name

logger = logging.getLogger(__name__)

# Default OpenRouter API URL (can be overridden via gateways config)
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"


def _get_openrouter_api_key() -> str:
    """Get OpenRouter API key from unified config resolution."""
    return get_api_key("openrouter") or ""


# Module-level alias for backwards compatibility with tests
OPENROUTER_API_KEY = _get_openrouter_api_key()


# Sanity bounds. A value beyond these is a malformed payload, not a very large
# call: clamping a count and rejecting a cost is safer than letting an unbounded
# integer reach float() and raise where the failure destroys a paid-for answer.
_MAX_TOKENS = 1_000_000_000
_MAX_COST = 1_000_000.0


def _as_token_count(value: Any) -> int:
    """A provider-supplied count as a non-negative int, or 0.

    ONE coercion for every count that reaches arithmetic. Provider payloads are
    untrusted, and a raise here is worse than a zero: it is swallowed by a
    caller's soft-fail and silently disables cost resolution entirely.

    #694 gate round 2: there were three near-identical validators with
    different behaviour. Three validators is three chances to guard the wrong
    branch — which is exactly what happened, see `_extract_cached_tokens`.
    """
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, int):
        # No isfinite() on an int: a gigantic JSON integer overflows on the
        # int->float conversion, and that OverflowError would be caught by the
        # caller's broad handler and destroy a successful completion.
        return max(min(value, _MAX_TOKENS), 0)
    if isinstance(value, float) and math.isfinite(value):
        # Clamped like the int branch. The docstring calls `_MAX_TOKENS` a bound
        # for every count, and then only one of the two numeric branches applied
        # it — so 1e300 passed straight through into cost arithmetic.
        return max(min(int(value), _MAX_TOKENS), 0)
    # Deliberately NOT parsing numeric strings. `tests/test_cache_telemetry.py`
    # pins `"800"` degrading to 0, and that contract is right: a string where a
    # number was specified is a malformed payload, and silently coercing it
    # makes "the provider sent a string" indistinguishable from "the provider
    # sent a number". The round-2 finding was that FLOATS were being discarded;
    # widening to strings was scope creep that broke a deliberate invariant.
    return 0


def _as_mapping(value: Any) -> Dict[str, Any]:
    """A nested provider container as a dict, or empty.

    #694 gate round 2: `(x or {})` rescues only FALSY values. A truthy non-dict
    — a JSON string or list where an object was expected — reached `.get(...)`
    and raised inside result construction, where the broad handler turned an
    already-billed successful completion into STATUS_ERROR and threw the content
    away. Losing a paid-for answer to a malformed telemetry field is the worst
    trade in this file.
    """
    return value if isinstance(value, dict) else {}


def _as_reported_cost(value: Any) -> Optional[float]:
    """A provider-reported cost, or None if it is not a usable number.

    #694 gate round 2: the provider figure was copied through unchecked and then
    stamped `cost_source="provider"` — so a bool, a negative, a NaN or a string
    became authoritative billing data, in the change whose entire purpose is
    cost-accounting integrity. Ground truth still wins over an estimate, but it
    has to be a number first. A rejected value falls through to the registry
    estimate, which is labelled, rather than poisoning a total that reads as a
    bill. Mirrors `CostResolver.resolve`'s own validation of the same field.
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return float(value) if 0 <= value <= _MAX_COST else None
    if isinstance(value, float) and math.isfinite(value) and 0 <= value <= _MAX_COST:
        return float(value)
    return None


def _extract_cached_tokens(usage: Dict[str, Any]) -> int:
    """Cached prompt tokens from an OpenRouter usage object (0 if absent).

    Explicit None-check so a genuine reported 0 isn't discarded by a truthiness
    short-circuit (#365 review).
    """
    # #694 gate: validate, do not trust — on BOTH branches. Round 1 of the gate
    # validated only the `cached_tokens` top-level field and left the nested
    # fallback returning the raw provider value, which is the branch OpenRouter
    # actually populates. A guard over the path that was not the problem.
    direct = usage.get("cached_tokens")
    if direct is not None:
        return _as_token_count(direct)
    nested = _as_mapping(usage.get("prompt_tokens_details")).get("cached_tokens")
    return _as_token_count(nested)


def _extract_cache_write_tokens(usage: Dict[str, Any]) -> int:
    """Cache-WRITE tokens from a provider usage object (ADR-049 D4; 0 if absent).

    Checked in precedence order — a missing field degrades to 0 (full-price
    accounting), never a crash or a fabricated figure:

    1. Anthropic direct top-level ``cache_creation_input_tokens`` (vendor-
       documented total; authoritative when present).
    2. Anthropic per-TTL sub-object ``cache_creation.ephemeral_{5m,1h}_input_
       tokens`` (summed).
    3. OpenRouter ``prompt_tokens_details.cache_write_tokens`` (empirically
       observed 2026-07-04, not vendor-documented — ADR-049 §Compliance
       drift guard re-probes quarterly).
    """

    # #694 gate round 2: one shared coercion, not a third local variant.
    _count = _as_token_count

    top_level = usage.get("cache_creation_input_tokens")
    if top_level is not None:
        return _count(top_level)
    sub = _as_mapping(usage.get("cache_creation"))
    if isinstance(sub, dict) and sub:
        return sum(_count(v) for k, v in sub.items() if k.endswith("_input_tokens"))
    return _count(_as_mapping(usage.get("prompt_tokens_details")).get("cache_write_tokens"))


if TYPE_CHECKING:
    from llm_council.gateway.types import ReasoningParams


# Status constants for structured results (ADR-012)
STATUS_OK = "ok"
STATUS_TIMEOUT = "timeout"
STATUS_RATE_LIMITED = "rate_limited"
STATUS_AUTH_ERROR = "auth_error"
STATUS_ERROR = "error"


async def query_model(
    model: str,
    messages: List[Dict[str, str]],
    timeout: float = 120.0,
    disable_tools: bool = False,
    reasoning_params: Optional["ReasoningParams"] = None,
) -> Optional[Dict[str, Any]]:
    """
    Query a single model via OpenRouter API.

    Args:
        model: OpenRouter model identifier (e.g., "openai/gpt-4o")
        messages: List of message dicts with 'role' and 'content'
        timeout: Request timeout in seconds
        disable_tools: If True, explicitly disable tool/function calling
        reasoning_params: Optional reasoning parameters for reasoning models (ADR-026)

    Returns:
        Response dict with 'content', optional 'reasoning_details', and 'usage', or None if failed
    """
    result = await query_model_with_status(
        model, messages, timeout, disable_tools, reasoning_params
    )
    if result["status"] == STATUS_OK:
        return {
            "content": result.get("content"),
            "reasoning_details": result.get("reasoning_details"),
            "usage": result.get("usage", {}),
            # ADR-049 D4: route/session attribution rides along.
            "route": result.get("route"),
            "session_id": result.get("session_id"),
        }
    return None



def resolve_missing_cost(
    usage: Dict[str, Any],
    model: Optional[str],
    gateway: str = "openrouter",
) -> None:
    """#694: fill an unreported cost from the registry, labelled as an estimate.

    Cost capture worked only because OpenRouter volunteers `usage.cost`. It
    always will — per OpenRouter's usage-accounting docs the old
    `usage: {include: true}` request flag is "deprecated and has no effect…
    usage details are now always included automatically" — so there is nothing
    to ask for and no flag is sent. The exposure is the OTHER routes: Requesty,
    the direct provider APIs, anything that does not volunteer a figure. There,
    a missing cost meant `cost_known` was never set and every model in the
    session landed null.

    `CostResolver` already knows how to price a call from `registry.yaml`, but
    it was only ever constructed on the gateway path, which is off by default.
    This makes that fallback reachable from the default path.

    `model` must be the CANONICAL id, not one already rewritten by
    `resolve_model_name` for a gateway's dialect: `registry.yaml` is keyed by
    the canonical id, so a rewritten one (Requesty stripping a `:free` suffix,
    say) silently misses and the fallback does nothing.

    Mutates `usage` in place, adding `cost` and `cost_source`. A
    provider-reported figure always wins, including a reported 0.0 — that is
    ground truth about a free or fully cached call, not a missing value. When
    nothing can be resolved, `cost` stays None and no source is claimed:
    inventing a number here would be the exact failure this guards against.

    Never raises. It runs inside the per-model call path, and a pricing lookup
    must not fail a call that has already been made and billed.
    """
    try:
        # Set once, up front, so EVERY exit below leaves the key present. The
        # gateway path always emits `cost_source`; this function had three
        # exits that omitted it, which is the asymmetry a comment two functions
        # away calls "a KeyError waiting for a consumer". Nothing in this
        # codebase reads it without `.get`, so the practical risk is low — but
        # a stated invariant that the neighbouring code breaks is how the last
        # four review rounds went.
        usage.setdefault("cost_source", None)

        reported = _as_reported_cost(usage.get("cost"))
        if reported is not None:
            usage["cost"] = reported
            usage["cost_source"] = "provider"
            return
        # A present-but-unusable figure is discarded rather than trusted, and
        # falls through to the labelled registry estimate below.
        if usage.get("cost") is not None:
            usage["cost"] = None
            # Reset rather than delete: an unresolved cost keeping a
            # `provider` label is the confusion `cost_source` exists to
            # prevent, but popping the key would re-open the presence gap
            # closed above.
            usage["cost_source"] = None
        if not model:
            return

        from .gateway.cost_resolver import CostResolver

        cost, source = CostResolver().resolve(
            model_id=model,
            # #694 gate: the ROUTE, not a hardcoded "openrouter". The whole
            # point of this fallback is the non-OpenRouter routes, and
            # `CostResolver` branches on gateway — `local_zero` for Ollama, and
            # the registry estimate for the direct provider APIs. Hardcoding
            # the one route that does not need the fallback mislabelled the
            # provenance of exactly the routes that do.
            gateway=gateway,
            prompt_tokens=_as_token_count(usage.get("prompt_tokens")),
            completion_tokens=_as_token_count(usage.get("completion_tokens")),
            # Coerce here too, not only in the extractors: this reads the
            # dict, which may carry a raw provider value that never went
            # through them. `int("lots")` raised, the soft-fail below swallowed
            # it, and the whole fallback silently stopped working.
            cache_read_tokens=_as_token_count(usage.get("cached_tokens")),
            provider_cost_usd=None,
        )
        # `local_zero` counts: an Ollama call really did cost nothing, and that
        # is a measurement, not an estimate. Accepting only `registry_estimate`
        # discarded it and left local runs reporting an unknown cost forever.
        if cost is not None and source in ("registry_estimate", "local_zero"):
            usage["cost"] = cost
            usage["cost_source"] = source
    except Exception:  # pragma: no cover - defensive
        logger.debug("cost fallback failed; leaving cost unknown", exc_info=True)


async def query_model_with_status(
    model: str,
    messages: List[Dict[str, str]],
    timeout: float = 120.0,
    disable_tools: bool = False,
    reasoning_params: Optional["ReasoningParams"] = None,
) -> Dict[str, Any]:
    """
    Query a single model via OpenRouter API with structured status (ADR-012).

    Args:
        model: OpenRouter model identifier (e.g., "openai/gpt-4o")
        messages: List of message dicts with 'role' and 'content'
        timeout: Request timeout in seconds
        disable_tools: If True, explicitly disable tool/function calling
        reasoning_params: Optional reasoning parameters for reasoning models (ADR-026)

    Returns:
        Response dict with 'status', 'content', 'latency_ms', 'usage', and optional 'error'
    """
    api_url, api_key, route = resolve_endpoint()
    # #694 gate: keep the canonical id. `registry.yaml` is keyed by it, and the
    # rewritten form is only for the wire.
    canonical_model = model
    model = resolve_model_name(model, route)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # Build payload using gateway function for reasoning injection (ADR-026)
    from llm_council.gateway.openrouter import build_openrouter_payload

    payload = build_openrouter_payload(
        model=model,
        messages=messages,
        reasoning_params=reasoning_params,
        disable_tools=disable_tools,
    )

    start_time = time.time()

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            # Issue #545: httpx's `timeout=` sets four SEPARATE per-operation
            # timeouts (connect/read/write/pool); `read` is the maximum gap
            # BETWEEN chunks, not total elapsed, and httpx offers no
            # total-wall-clock option. A provider that keeps the socket fed
            # (streamed tokens, processing heartbeats) therefore ran unbounded,
            # so ADR-040's per-stage waterfall budget never held. asyncio.wait_for
            # is the actual elapsed-time bound. An OUTER cancellation (the ADR-040
            # global deadline) still propagates: wait_for re-raises CancelledError,
            # which derives from BaseException and is not caught below.
            response = await asyncio.wait_for(
                client.post(api_url, headers=headers, json=payload), timeout=timeout
            )
            latency_ms = int((time.time() - start_time) * 1000)

            # Handle specific HTTP status codes (ADR-012 failure taxonomy)
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After", "60")
                return {
                    "status": STATUS_RATE_LIMITED,
                    "latency_ms": latency_ms,
                    "error": f"Rate limited by {model}",
                    "retry_after": int(retry_after) if retry_after.isdigit() else 60,
                }

            if response.status_code in (401, 403):
                return {
                    "status": STATUS_AUTH_ERROR,
                    "latency_ms": latency_ms,
                    "error": f"Authentication failed for {model}: {response.status_code}",
                }

            if response.status_code == 400:
                return {
                    "status": STATUS_ERROR,
                    "latency_ms": latency_ms,
                    "error": f"Bad request for {model}: {response.text[:200]}",
                }

            response.raise_for_status()

            data = _as_mapping(response.json())
            # Three assumptions in one subscript — that `choices` exists, that
            # it is non-empty, and that its first entry is an object — in the
            # one function whose thesis is that a malformed payload must never
            # cost you an answer you have already paid for. The guards added
            # for the `usage` containers left this line, its sibling, alone.
            #
            # A throw here lands in the broad handler below, which reports
            # STATUS_ERROR and discards the content: the call is billed and the
            # answer is gone. Degrading to an empty message keeps whatever else
            # the response carried (usage, cost) and lets the caller see an
            # empty completion rather than a failure it cannot diagnose.
            choices = data.get("choices")
            first = _as_mapping(choices[0] if isinstance(choices, list) and choices else None)
            message = _as_mapping(first.get("message"))
            # #694 gate round 3: `.get(k, {})` defaults only when the key is
            # ABSENT. `"usage": null`, or a truthy non-object, yields a
            # non-dict and every `.get` below raises — inside result
            # construction, where the broad handler turns an already-billed
            # success into STATUS_ERROR and throws the content away. Round 2
            # added `_as_mapping` for the NESTED containers and left the
            # outermost one, which is the one every field goes through.
            usage = _as_mapping(data.get("usage"))

            # ADR-049 D4: route + session attribution per call, so hit-rate
            # is reconstructable from logs alone. Lazy import (house pattern
            # from the gateway payload builder) keeps startup order safe.
            from .cache_context import get_cache_context

            cache_ctx = get_cache_context()

            result: Dict[str, Any] = {
                "status": STATUS_OK,
                "content": message.get("content"),
                "reasoning_details": message.get("reasoning_details"),
                "latency_ms": latency_ms,
                "route": route,
                "session_id": cache_ctx.session_id if cache_ctx else None,
                "usage": {
                    # #694 gate round 3: through the coercion, like every
                    # other count. `_as_token_count`'s own docstring says "ONE
                    # coercion for every count that reaches arithmetic" and then
                    # these three — the primary ones — were copied raw. An
                    # invariant stated and not applied, in the same commit.
                    "prompt_tokens": _as_token_count(usage.get("prompt_tokens")),
                    "completion_tokens": _as_token_count(usage.get("completion_tokens")),
                    "total_tokens": _as_token_count(usage.get("total_tokens")),
                    # ADR-011: OpenRouter returns the authoritative billed cost
                    # inline; capture it (previously discarded) so the council
                    # can account cost, not just tokens.
                    # #694 gate round 2: validated, not copied. An unchecked
                    # bool/NaN/negative/string was being stamped as authoritative
                    # billing data by `resolve_missing_cost`.
                    "cost": _as_reported_cost(usage.get("cost")),
                    "cached_tokens": _extract_cached_tokens(usage),
                    # ADR-049 D4: cache writes (0 when the route reports none).
                    "cache_write_tokens": _extract_cache_write_tokens(usage),
                },
            }
            # #694: label the provenance, and fall back to a registry estimate
            # when the provider reported nothing.
            resolve_missing_cost(result["usage"], canonical_model, gateway=route)
            return result

    except (httpx.TimeoutException, asyncio.TimeoutError):
        # #545: asyncio.TimeoutError is the wall-clock bound above; httpx's is a
        # per-operation one. Both mean "this model did not answer in time".
        latency_ms = int((time.time() - start_time) * 1000)
        return {
            "status": STATUS_TIMEOUT,
            "latency_ms": latency_ms,
            "error": f"Timeout after {timeout}s",
        }

    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        # #594: `str(e)` is "" for any exception constructed without a message
        # (e.g. a bare IndexError from an unexpected response shape), and that
        # empty string travelled all the way to the operator as
        # "Unable to generate final synthesis (error: )" during the 2026-07-16
        # chairman outage — undiagnosable. Always name the type, so the detail
        # is non-empty by construction. This is the same goal as #397 (don't
        # collapse failures to None) and #403 (distinguish infra from defect);
        # an empty detail defeats both.
        detail = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
        logger.warning("Error querying model %s: %s", safe_log(model), safe_log(detail))
        return {
            "status": STATUS_ERROR,
            "latency_ms": latency_ms,
            "error": detail,
        }


async def query_models_parallel(
    models: List[str],
    messages: List[Dict[str, str]],
    disable_tools: bool = False,
    timeout: float = 120.0,
    reasoning_params: Optional["ReasoningParams"] = None,
) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    Query multiple models in parallel.

    Args:
        models: List of OpenRouter model identifiers
        messages: List of message dicts to send to each model
        disable_tools: If True, disable tool/function calling for all queries
        timeout: Per-model timeout in seconds
        reasoning_params: Optional reasoning parameters for reasoning models (ADR-026)

    Returns:
        Dict mapping model identifier to response dict (or None if failed)
    """
    # Create tasks for all models
    tasks = [
        query_model(
            model,
            messages,
            timeout=timeout,
            disable_tools=disable_tools,
            reasoning_params=reasoning_params,
        )
        for model in models
    ]

    # Wait for all to complete
    responses = await asyncio.gather(*tasks)

    # Map models to their responses
    return {model: response for model, response in zip(models, responses)}


# Progress callback type for ADR-012
ProgressCallback = Callable[[int, int, str], Awaitable[None]]


async def query_models_with_progress(
    models: List[str],
    messages: List[Dict[str, str]],
    on_progress: Optional[ProgressCallback] = None,
    timeout: float = 25.0,
    disable_tools: bool = False,
    reasoning_params: Optional["ReasoningParams"] = None,
    shared_results: Optional[Dict[str, Dict[str, Any]]] = None,
    on_model_complete: Optional[Callable[[str, Dict[str, Any]], Awaitable[None]]] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Query multiple models with progress callbacks and structured status (ADR-012).

    Args:
        models: List of OpenRouter model identifiers
        messages: List of message dicts to send to each model
        on_progress: Async callback(completed, total, message) for progress updates
        timeout: Per-model timeout in seconds (default 25s per ADR-012)
        disable_tools: If True, disable tool/function calling for all queries
        reasoning_params: Optional reasoning parameters for reasoning models
            (ADR-026) — previously dropped on this path (#365)
        shared_results: Optional dict to populate incrementally. If provided, results
            are written here as each model completes, preserving state even if the
            function is cancelled by an outer timeout. This fixes ADR-012 diagnostic
            loss on global timeout.

    Returns:
        Dict mapping model identifier to structured result with status
    """
    # Use shared_results if provided, otherwise create local dict
    results: Dict[str, Dict[str, Any]] = shared_results if shared_results is not None else {}
    total = len(models)
    completed = 0

    # Report initial progress
    if on_progress:
        await on_progress(0, total, f"Querying {total} models...")

    # Create tasks with model tracking
    async def query_with_tracking(model: str) -> tuple[str, Dict[str, Any]]:
        result = await query_model_with_status(
            model,
            messages,
            timeout=timeout,
            disable_tools=disable_tools,
            reasoning_params=reasoning_params,
        )
        return model, result

    tasks = [query_with_tracking(model) for model in models]

    # Process as they complete for real-time progress
    for coro in asyncio.as_completed(tasks):
        model, result = await coro
        results[model] = result  # Write to shared dict immediately
        completed += 1

        # ADR-046 P1: per-model completion hook (soft-fail, streaming only)
        if on_model_complete is not None:
            try:
                await on_model_complete(model, result)
            except Exception:
                pass

        if on_progress:
            status_emoji = "✓" if result["status"] == STATUS_OK else "✗"
            model_short = model.split("/")[-1]  # e.g., "gpt-4" from "openai/gpt-4"
            # Show which models are still pending
            pending = [m.split("/")[-1] for m in models if m not in results]
            if pending and completed < total:
                pending_str = f" | waiting: {', '.join(pending[:3])}"
                if len(pending) > 3:
                    pending_str += f" +{len(pending)-3}"
            else:
                pending_str = ""
            await on_progress(
                completed, total, f"{status_emoji} {model_short} ({completed}/{total}){pending_str}"
            )

    return results
