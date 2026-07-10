"""OpenRouter API client for parallel LLM queries.

ADR-026 Phase 2: Added reasoning_params support for reasoning models.
"""

import httpx
import asyncio
import time
from typing import TYPE_CHECKING, List, Dict, Any, Optional, Callable, Awaitable

# ADR-032: Migrated to unified_config
from llm_council.unified_config import get_api_key

from llm_council.gateway.resolver import resolve_endpoint, resolve_model_name

# Default OpenRouter API URL (can be overridden via gateways config)
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"


def _get_openrouter_api_key() -> str:
    """Get OpenRouter API key from unified config resolution."""
    return get_api_key("openrouter") or ""


# Module-level alias for backwards compatibility with tests
OPENROUTER_API_KEY = _get_openrouter_api_key()


def _extract_cached_tokens(usage: Dict[str, Any]) -> int:
    """Cached prompt tokens from an OpenRouter usage object (0 if absent).

    Explicit None-check so a genuine reported 0 isn't discarded by a truthiness
    short-circuit (#365 review).
    """
    direct = usage.get("cached_tokens")
    if direct is not None:
        return direct
    return (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0


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

    def _count(value: Any) -> int:
        # Provider payloads are untrusted: a non-numeric value degrades to 0
        # rather than crashing usage capture (same posture as missing).
        return value if isinstance(value, int) and not isinstance(value, bool) else 0

    top_level = usage.get("cache_creation_input_tokens")
    if top_level is not None:
        return _count(top_level)
    sub = usage.get("cache_creation")
    if isinstance(sub, dict) and sub:
        return sum(_count(v) for k, v in sub.items() if k.endswith("_input_tokens"))
    return _count((usage.get("prompt_tokens_details") or {}).get("cache_write_tokens"))


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

            data = response.json()
            message = data["choices"][0]["message"]
            usage = data.get("usage", {})

            # ADR-049 D4: route + session attribution per call, so hit-rate
            # is reconstructable from logs alone. Lazy import (house pattern
            # from the gateway payload builder) keeps startup order safe.
            from .cache_context import get_cache_context

            cache_ctx = get_cache_context()

            return {
                "status": STATUS_OK,
                "content": message.get("content"),
                "reasoning_details": message.get("reasoning_details"),
                "latency_ms": latency_ms,
                "route": route,
                "session_id": cache_ctx.session_id if cache_ctx else None,
                "usage": {
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                    # ADR-011: OpenRouter returns the authoritative billed cost
                    # inline; capture it (previously discarded) so the council
                    # can account cost, not just tokens.
                    "cost": usage.get("cost"),
                    "cached_tokens": _extract_cached_tokens(usage),
                    # ADR-049 D4: cache writes (0 when the route reports none).
                    "cache_write_tokens": _extract_cache_write_tokens(usage),
                },
            }

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
        print(f"Error querying model {model}: {e}")
        return {
            "status": STATUS_ERROR,
            "latency_ms": latency_ms,
            "error": str(e),
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
