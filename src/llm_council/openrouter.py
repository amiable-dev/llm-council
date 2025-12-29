"""OpenRouter API client for parallel LLM queries.

ADR-026 Phase 2: Added reasoning_params support for reasoning models.
"""

import httpx
import asyncio
import time
from typing import TYPE_CHECKING, List, Dict, Any, Optional, Callable, Awaitable

# ADR-032: Migrated to unified_config
from llm_council.unified_config import get_api_key, get_config

# Default OpenRouter API URL (can be overridden via gateways config)
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"


def _get_openrouter_api_key() -> str:
    """Get OpenRouter API key from unified config resolution."""
    return get_api_key("openrouter") or ""


# Module-level alias for backwards compatibility with tests
OPENROUTER_API_KEY = _get_openrouter_api_key()

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
    headers = {
        "Authorization": f"Bearer {_get_openrouter_api_key()}",
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
            response = await client.post(OPENROUTER_API_URL, headers=headers, json=payload)
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

            response.raise_for_status()

            data = response.json()
            message = data["choices"][0]["message"]
            usage = data.get("usage", {})

            return {
                "status": STATUS_OK,
                "content": message.get("content"),
                "reasoning_details": message.get("reasoning_details"),
                "latency_ms": latency_ms,
                "usage": {
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                },
            }

    except httpx.TimeoutException:
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
    shared_results: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Query multiple models with progress callbacks and structured status (ADR-012).

    Args:
        models: List of OpenRouter model identifiers
        messages: List of message dicts to send to each model
        on_progress: Async callback(completed, total, message) for progress updates
        timeout: Per-model timeout in seconds (default 25s per ADR-012)
        disable_tools: If True, disable tool/function calling for all queries
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
            model, messages, timeout=timeout, disable_tools=disable_tools
        )
        return model, result

    tasks = [query_with_tracking(model) for model in models]

    # Process as they complete for real-time progress
    for coro in asyncio.as_completed(tasks):
        model, result = await coro
        results[model] = result  # Write to shared dict immediately
        completed += 1

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
