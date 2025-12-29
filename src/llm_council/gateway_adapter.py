"""Gateway adapter for LLM Council (ADR-023).

This module provides a unified interface for LLM requests that can use either:
- Direct openrouter module (default, backward compatible)
- Gateway layer (when USE_GATEWAY_LAYER is enabled)

Usage:
    from llm_council.gateway_adapter import query_model, query_models_parallel

    # Uses the configured backend (direct or gateway)
    response = await query_model("openai/gpt-4o", messages)
"""

import asyncio
from typing import List, Dict, Any, Optional, Callable, Awaitable

# ADR-032: Migrated to unified_config
from llm_council.unified_config import get_config


def _use_gateway_layer() -> bool:
    """Check if gateway layer is enabled from unified config."""
    config = get_config()
    return getattr(config.gateways, "enabled", False) if hasattr(config, "gateways") else False


USE_GATEWAY_LAYER = _use_gateway_layer()

# Import direct openrouter functions (always available as fallback)
from llm_council.openrouter import (
    query_model as _direct_query_model,
    query_model_with_status as _direct_query_model_with_status,
    query_models_parallel as _direct_query_models_parallel,
    query_models_with_progress as _direct_query_models_with_progress,
    STATUS_OK,
    STATUS_TIMEOUT,
    STATUS_RATE_LIMITED,
    STATUS_AUTH_ERROR,
    STATUS_ERROR,
)

# Re-export status constants
__all__ = [
    "query_model",
    "query_model_with_status",
    "query_models_parallel",
    "query_models_with_progress",
    "STATUS_OK",
    "STATUS_TIMEOUT",
    "STATUS_RATE_LIMITED",
    "STATUS_AUTH_ERROR",
    "STATUS_ERROR",
]


# Lazy-initialized gateway router (only created when needed)
_gateway_router = None


def _get_gateway_router():
    """Get or create the gateway router singleton."""
    global _gateway_router
    if _gateway_router is None:
        from llm_council.gateway.router import GatewayRouter

        _gateway_router = GatewayRouter()
    return _gateway_router


def _gateway_response_to_dict(response) -> Dict[str, Any]:
    """Convert GatewayResponse to the dict format expected by council."""
    result = {
        "status": response.status,
        "latency_ms": response.latency_ms or 0,
    }

    if response.status == STATUS_OK:
        result["content"] = response.content
        if response.usage:
            result["usage"] = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

    if response.error:
        result["error"] = response.error

    if response.retry_after:
        result["retry_after"] = response.retry_after

    return result


async def query_model(
    model: str, messages: List[Dict[str, str]], timeout: float = 120.0, disable_tools: bool = False
) -> Optional[Dict[str, Any]]:
    """
    Query a single model via OpenRouter API.

    Uses gateway layer if USE_GATEWAY_LAYER is enabled, otherwise uses direct
    openrouter module.

    Args:
        model: OpenRouter model identifier (e.g., "openai/gpt-4o")
        messages: List of message dicts with 'role' and 'content'
        timeout: Request timeout in seconds
        disable_tools: If True, explicitly disable tool/function calling

    Returns:
        Response dict with 'content', optional 'reasoning_details', and 'usage',
        or None if failed
    """
    if USE_GATEWAY_LAYER:
        from llm_council.gateway.types import GatewayRequest, CanonicalMessage, ContentBlock

        # Convert messages to canonical format
        canonical_messages = [
            CanonicalMessage(
                role=msg["role"], content=[ContentBlock(type="text", text=msg.get("content", ""))]
            )
            for msg in messages
        ]

        request = GatewayRequest(
            model=model,
            messages=canonical_messages,
            timeout=timeout,
        )

        router = _get_gateway_router()
        response = await router.complete(request)

        if response.status == STATUS_OK:
            return {
                "content": response.content,
                "reasoning_details": None,  # Not available via gateway yet
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                    "total_tokens": response.usage.total_tokens if response.usage else 0,
                },
            }
        return None
    else:
        return await _direct_query_model(model, messages, timeout, disable_tools)


async def query_model_with_status(
    model: str, messages: List[Dict[str, str]], timeout: float = 120.0, disable_tools: bool = False
) -> Dict[str, Any]:
    """
    Query a single model with structured status (ADR-012).

    Uses gateway layer if USE_GATEWAY_LAYER is enabled.

    Args:
        model: OpenRouter model identifier
        messages: List of message dicts
        timeout: Request timeout in seconds
        disable_tools: If True, disable tool/function calling

    Returns:
        Response dict with 'status', 'content', 'latency_ms', 'usage', and optional 'error'
    """
    if USE_GATEWAY_LAYER:
        from llm_council.gateway.types import GatewayRequest, CanonicalMessage, ContentBlock

        canonical_messages = [
            CanonicalMessage(
                role=msg["role"], content=[ContentBlock(type="text", text=msg.get("content", ""))]
            )
            for msg in messages
        ]

        request = GatewayRequest(
            model=model,
            messages=canonical_messages,
            timeout=timeout,
        )

        router = _get_gateway_router()
        response = await router.complete(request)
        return _gateway_response_to_dict(response)
    else:
        return await _direct_query_model_with_status(model, messages, timeout, disable_tools)


async def query_models_parallel(
    models: List[str],
    messages: List[Dict[str, str]],
    disable_tools: bool = False,
    timeout: float = 120.0,
) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    Query multiple models in parallel.

    Uses gateway layer if USE_GATEWAY_LAYER is enabled.

    Args:
        models: List of OpenRouter model identifiers
        messages: List of message dicts to send to each model
        disable_tools: If True, disable tool/function calling for all queries
        timeout: Per-model timeout in seconds

    Returns:
        Dict mapping model identifier to response dict (or None if failed)
    """
    if USE_GATEWAY_LAYER:
        from llm_council.gateway.types import GatewayRequest, CanonicalMessage, ContentBlock

        canonical_messages = [
            CanonicalMessage(
                role=msg["role"], content=[ContentBlock(type="text", text=msg.get("content", ""))]
            )
            for msg in messages
        ]

        requests = [
            GatewayRequest(
                model=model,
                messages=canonical_messages,
                timeout=timeout,
            )
            for model in models
        ]

        router = _get_gateway_router()
        responses = await router.complete_many(requests)

        result = {}
        for model, response in zip(models, responses):
            if response.status == STATUS_OK:
                result[model] = {
                    "content": response.content,
                    "reasoning_details": None,
                    "usage": {
                        "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                        "completion_tokens": response.usage.completion_tokens
                        if response.usage
                        else 0,
                        "total_tokens": response.usage.total_tokens if response.usage else 0,
                    },
                }
            else:
                result[model] = None

        return result
    else:
        return await _direct_query_models_parallel(models, messages, disable_tools, timeout)


# Progress callback type
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

    Uses gateway layer if USE_GATEWAY_LAYER is enabled.

    Args:
        models: List of OpenRouter model identifiers
        messages: List of message dicts to send to each model
        on_progress: Async callback(completed, total, message) for progress updates
        timeout: Per-model timeout in seconds (default 25s per ADR-012)
        disable_tools: If True, disable tool/function calling for all queries
        shared_results: Optional dict to populate incrementally

    Returns:
        Dict mapping model identifier to structured result with status
    """
    if USE_GATEWAY_LAYER:
        from llm_council.gateway.types import GatewayRequest, CanonicalMessage, ContentBlock

        results: Dict[str, Dict[str, Any]] = shared_results if shared_results is not None else {}
        total = len(models)
        completed = 0

        if on_progress:
            await on_progress(0, total, f"Querying {total} models...")

        canonical_messages = [
            CanonicalMessage(
                role=msg["role"], content=[ContentBlock(type="text", text=msg.get("content", ""))]
            )
            for msg in messages
        ]

        async def query_with_tracking(model: str):
            nonlocal completed

            request = GatewayRequest(
                model=model,
                messages=canonical_messages,
                timeout=timeout,
            )

            router = _get_gateway_router()
            response = await router.complete(request)
            result = _gateway_response_to_dict(response)

            results[model] = result
            completed += 1

            if on_progress:
                status_emoji = "✓" if result["status"] == STATUS_OK else "✗"
                model_short = model.split("/")[-1]
                await on_progress(
                    completed, total, f"{status_emoji} {model_short} ({completed}/{total})"
                )

            return model, result

        tasks = [query_with_tracking(model) for model in models]
        await asyncio.gather(*tasks)

        return results
    else:
        return await _direct_query_models_with_progress(
            models, messages, on_progress, timeout, disable_tools, shared_results
        )
