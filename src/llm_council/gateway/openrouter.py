"""OpenRouter gateway implementation for LLM Council (ADR-023).

This module provides an OpenRouter-specific implementation of the BaseRouter
protocol, enabling unified access to 100+ models via OpenRouter's API.

The gateway wraps the existing openrouter module functionality while
conforming to the BaseRouter interface.
"""

import json
import logging
import time
from datetime import datetime
from typing import AsyncIterator, Dict, Any, List, Optional

import httpx

# ADR-032: Migrated to unified_config
from llm_council.unified_config import get_api_key

# ADR-011: per-gateway cost resolution. OpenRouter returns authoritative cost,
# so no pricing lookup is needed here (provider path).
from .cost_resolver import CostResolver

_COST_RESOLVER = CostResolver()

# Default constants
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"


def _get_openrouter_api_key() -> str:
    """Get OpenRouter API key via ADR-013 resolution chain."""
    return get_api_key("openrouter") or ""


OPENROUTER_API_KEY = _get_openrouter_api_key()

from .base import (
    CachingCapability,
    DEFAULT_HEALTH_CHECK_MODEL,
    BaseRouter,
    HealthStatus,
    RouterCapabilities,
    RouterHealth,
)
from .types import (
    CanonicalMessage,
    ContentBlock,
    GatewayRequest,
    GatewayResponse,
    ReasoningParams,
    UsageInfo,
)


def _apply_cache_breakpoints(
    messages: List[Dict[str, Any]],
    model: str,
    cache_ctx: "Any",
) -> List[Dict[str, Any]]:
    """Split the matching prompt into content parts with cache_control.

    Only the message whose string content matches the published segment map
    is transformed; everything else passes through untouched. Reassembly of
    the parts is byte-identical to the original prompt. Breakpoints honor
    the per-model minimum cacheable prefix (below-minimum marks are silently
    useless AND we skip them) and the ≤4-breakpoint hard limit.
    """
    out: List[Dict[str, Any]] = []
    for msg in messages:
        content = msg.get("content")
        if not isinstance(content, str) or not cache_ctx.matches(content):
            out.append(msg)
            continue
        # Sorted, deduped, strictly inside the content: a zero-width segment
        # (e.g. empty evidence) or an end-of-prompt offset would otherwise
        # produce an empty text part, which the Anthropic API rejects.
        offsets = sorted(
            {off for off in cache_ctx.breakpoint_offsets(model) if 0 < off < len(content)}
        )
        if not offsets:
            out.append(msg)
            continue
        parts: List[Dict[str, Any]] = []
        cursor = 0
        for off in offsets:
            parts.append(
                {
                    "type": "text",
                    "text": content[cursor:off],
                    "cache_control": {"type": "ephemeral", "ttl": cache_ctx.ttl},
                }
            )
            cursor = off
        parts.append({"type": "text", "text": content[cursor:]})
        out.append({**msg, "content": parts})
    return out


def build_openrouter_payload(
    model: str,
    messages: List[Dict[str, Any]],
    reasoning_params: Optional[ReasoningParams] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    disable_tools: bool = False,
) -> Dict[str, Any]:
    """Build OpenRouter API payload with optional reasoning parameters.

    Args:
        model: Model identifier (e.g., "openai/o1")
        messages: List of message dicts in OpenRouter format
        reasoning_params: Optional reasoning parameters (ADR-026 Phase 2)
        max_tokens: Optional max tokens for generation
        temperature: Optional sampling temperature
        disable_tools: Whether to disable tool calling

    Returns:
        Dict payload ready for OpenRouter API
    """
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
    }

    # ADR-049 D2: request-scoped prompt-cache context (segments published by
    # the verification pipeline). Applies Anthropic cache_control breakpoints
    # at the D1 segment boundaries and the OpenRouter session_id affinity
    # key. Kill-switch LLM_COUNCIL_PROMPT_CACHING=false ⇒ byte-identical.
    from ..cache_context import get_cache_context, prompt_caching_enabled

    try:
        cache_ctx = get_cache_context()
        if cache_ctx is not None and prompt_caching_enabled():
            if cache_ctx.session_id:
                # Affinity helps every vendor via OpenRouter sticky routing.
                payload["session_id"] = cache_ctx.session_id
            if model.startswith("anthropic/"):
                payload["messages"] = _apply_cache_breakpoints(
                    messages, model, cache_ctx
                )
    except Exception:  # pragma: no cover - defensive
        # Soft-fail (ADR-011/024 convention): caching changes price class,
        # never content — a bad segment map must never break the query.
        # Revert to the full pre-D2 payload (session_id included: on any
        # anomaly we want the known-good baseline, not a partial mode).
        logging.getLogger(__name__).debug(
            "prompt-cache injection failed for %s; reverting to plain payload",
            model,
            exc_info=True,
        )
        payload["messages"] = messages
        payload.pop("session_id", None)

    if disable_tools:
        payload["tools"] = []
        payload["tool_choice"] = "none"

    if max_tokens is not None:
        payload["max_tokens"] = max_tokens

    if temperature is not None:
        payload["temperature"] = temperature

    # Inject reasoning parameters for reasoning models (ADR-026 Phase 2)
    if reasoning_params is not None:
        # Check if model supports reasoning
        from ..metadata import get_provider

        provider = get_provider()
        if provider.supports_reasoning(model):
            payload["reasoning"] = {
                "effort": reasoning_params.effort,
                "max_tokens": reasoning_params.max_tokens,
                "exclude": reasoning_params.exclude,
            }

    return payload


class OpenRouterGateway(BaseRouter):
    """OpenRouter gateway implementing BaseRouter protocol.

    Provides access to 100+ models via OpenRouter's unified API.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        default_timeout: float = 120.0,
    ):
        """Initialize the OpenRouter gateway.

        Args:
            api_key: OpenRouter API key. If None, uses OPENROUTER_API_KEY from config.
            base_url: Base URL for OpenRouter API. If None, uses OPENROUTER_API_URL.
            default_timeout: Default request timeout in seconds.
        """
        # Store only an EXPLICIT key here; when none is given, resolve
        # per-request in _query_openrouter so a request-scoped BYOK key
        # (ADR-013 ContextVar) is honored instead of a value frozen at import.
        self._api_key = api_key
        self._base_url = base_url or OPENROUTER_API_URL
        self._default_timeout = default_timeout
        self._capabilities = RouterCapabilities(
            supports_streaming=True,
            supports_tools=True,
            supports_vision=True,
            supports_json_mode=True,
            supports_byok=False,  # OpenRouter manages API keys
            requires_byok=False,
            # ADR-049: verified 2026-07-04 (docs + empirical two-call probe) —
            # anthropic/* only; other vendors on this route showed no caching.
            caching=CachingCapability(
                semantics="explicit",
                directive="anthropic_cache_control",
                billing_passthrough=True,
                usage_fields="openrouter_normalized",
            ),
        )

    @property
    def router_id(self) -> str:
        """Return the router identifier."""
        return "openrouter"

    @property
    def capabilities(self) -> RouterCapabilities:
        """Return the capabilities of this router."""
        return self._capabilities

    def _convert_message(self, msg: CanonicalMessage) -> Dict[str, Any]:
        """Convert CanonicalMessage to OpenRouter message format.

        Args:
            msg: Canonical message to convert.

        Returns:
            OpenRouter-format message dict.
        """
        # Check if we have any image content
        has_images = any(block.type == "image" for block in msg.content)

        message: Dict[str, Any]
        if has_images:
            # Multi-part content for vision models
            content_parts = []
            for block in msg.content:
                if block.type == "text" and block.text:
                    content_parts.append({"type": "text", "text": block.text})
                elif block.type == "image" and block.image_url:
                    content_parts.append(
                        {"type": "image_url", "image_url": {"url": block.image_url}}
                    )
            message = {"role": msg.role, "content": content_parts}
        else:
            # Simple text content
            text_content = " ".join(
                block.text for block in msg.content if block.type == "text" and block.text
            )
            message = {"role": msg.role, "content": text_content}

        # Preserve tool-calling fields (OpenRouter/OpenAI carry these on the
        # message, not in content blocks) — previously silently dropped.
        if msg.tool_calls:
            message["tool_calls"] = msg.tool_calls
        if msg.tool_call_id:
            message["tool_call_id"] = msg.tool_call_id
        return message

    def _convert_messages(self, messages: List[CanonicalMessage]) -> List[Dict[str, Any]]:
        """Convert list of CanonicalMessages to OpenRouter format."""
        return [self._convert_message(msg) for msg in messages]

    async def _query_openrouter(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        timeout: float,
        disable_tools: bool = False,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        reasoning_params: Optional[ReasoningParams] = None,
    ) -> Dict[str, Any]:
        """Send a query to OpenRouter API.

        This is the core HTTP request method that can be mocked for testing.

        Args:
            model: Model identifier.
            messages: OpenRouter-format messages.
            timeout: Request timeout.
            disable_tools: Whether to disable tool calling.
            max_tokens: Max tokens to generate.
            temperature: Sampling temperature.

        Returns:
            Structured result dict with status, content, latency_ms, etc.
        """
        # Resolve the key at request time (ADR-013 chain: request ContextVar →
        # env → keychain → config) unless an explicit key was injected.
        api_key = self._api_key or get_api_key("openrouter") or ""
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        # ADR-026: use the shared payload builder so reasoning_params are
        # propagated (previously dropped on this gateway path) — identical
        # tool/token/temperature handling to the inline form it replaces.
        payload = build_openrouter_payload(
            model=model,
            messages=messages,
            reasoning_params=reasoning_params,
            max_tokens=max_tokens,
            temperature=temperature,
            disable_tools=disable_tools,
        )

        start_time = time.time()

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(self._base_url, headers=headers, json=payload)
                latency_ms = int((time.time() - start_time) * 1000)

                # Handle specific HTTP status codes
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After", "60")
                    return {
                        "status": "rate_limited",
                        "latency_ms": latency_ms,
                        "error": f"Rate limited by {model}",
                        "retry_after": int(retry_after) if retry_after.isdigit() else 60,
                    }

                if response.status_code in (401, 403):
                    return {
                        "status": "auth_error",
                        "latency_ms": latency_ms,
                        "error": f"Authentication failed for {model}: {response.status_code}",
                    }

                if response.status_code == 400:
                    return {
                        "status": "error",
                        "latency_ms": latency_ms,
                        "error": f"Bad request for {model}: {response.text[:200]}",
                    }

                response.raise_for_status()

                data = response.json()
                message = data["choices"][0]["message"]
                usage = data.get("usage", {})

                return {
                    "status": "ok",
                    # Content may be null (e.g. a tool-call-only assistant turn);
                    # coerce to "" so downstream str handling never sees None.
                    "content": message.get("content") or "",
                    "reasoning_details": message.get("reasoning_details"),
                    "latency_ms": latency_ms,
                    "usage": {
                        "prompt_tokens": usage.get("prompt_tokens", 0),
                        "completion_tokens": usage.get("completion_tokens", 0),
                        "total_tokens": usage.get("total_tokens", 0),
                        # ADR-011: OpenRouter returns the authoritative billed
                        # cost inline; capture it (previously discarded).
                        "cost": usage.get("cost"),
                        "cached_tokens": (
                            usage.get("cached_tokens")
                            or (usage.get("prompt_tokens_details") or {}).get(
                                "cached_tokens", 0
                            )
                            or 0
                        ),
                    },
                }

        except httpx.TimeoutException:
            latency_ms = int((time.time() - start_time) * 1000)
            return {
                "status": "timeout",
                "latency_ms": latency_ms,
                "error": f"Timeout after {timeout}s",
            }

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            return {
                "status": "error",
                "latency_ms": latency_ms,
                "error": str(e),
            }

    async def complete(self, request: GatewayRequest) -> GatewayResponse:
        """Send a completion request and return the response.

        Args:
            request: The gateway request with model and messages.

        Returns:
            GatewayResponse with the generated content.
        """
        # Convert messages to OpenRouter format
        messages = self._convert_messages(request.messages)

        # Determine timeout
        timeout = request.timeout if request.timeout is not None else self._default_timeout

        # Make the request
        result = await self._query_openrouter(
            model=request.model,
            messages=messages,
            timeout=timeout,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            reasoning_params=request.reasoning_params,
        )

        # Convert to GatewayResponse
        usage = None
        if result.get("usage"):
            usage_data = result["usage"]
            usage = UsageInfo(
                prompt_tokens=usage_data.get("prompt_tokens", 0),
                completion_tokens=usage_data.get("completion_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
            )
            # ADR-011: stamp cost_usd + cost_source (provider ground-truth).
            _COST_RESOLVER.apply(
                usage,
                gateway="openrouter",
                model_id=request.model,
                provider_cost_usd=usage_data.get("cost"),
                cached_tokens=usage_data.get("cached_tokens"),
            )

        return GatewayResponse(
            content=result.get("content", ""),
            model=request.model,
            status=result["status"],
            usage=usage,
            latency_ms=result.get("latency_ms"),
            error=result.get("error"),
            retry_after=result.get("retry_after"),
            # #375: surface the reasoning trace instead of dropping it.
            reasoning_details=result.get("reasoning_details"),
        )

    async def complete_stream(self, request: GatewayRequest) -> AsyncIterator[str]:
        """Send a streaming completion request, yielding content deltas.

        Uses OpenRouter's SSE stream (#375): each `data:` line carries a JSON
        chunk whose `choices[0].delta.content` is the incremental text. Malformed
        chunks are skipped; the stream ends on `data: [DONE]`.

        Args:
            request: The gateway request with model and messages.

        Yields:
            Incremental string chunks of the generated content.
        """
        api_key = self._api_key or get_api_key("openrouter") or ""
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = build_openrouter_payload(
            model=request.model,
            messages=self._convert_messages(request.messages),
            reasoning_params=request.reasoning_params,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
        )
        payload["stream"] = True
        timeout = request.timeout if request.timeout is not None else self._default_timeout

        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST", self._base_url, headers=headers, json=payload
            ) as response:
                # Surface HTTP errors instead of silently parsing an error body
                # as SSE (which would yield nothing).
                if response.status_code >= 400:
                    body = await response.aread()
                    detail = body.decode("utf-8", "replace")[:200]
                    raise httpx.HTTPStatusError(
                        f"OpenRouter streaming failed ({response.status_code}): {detail}",
                        request=response.request,
                        response=response,
                    )
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:") :].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk["choices"][0]["delta"].get("content")
                    except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                        continue
                    if delta:
                        yield delta

    async def health_check(self) -> RouterHealth:
        """Check the health of this router.

        Returns:
            RouterHealth with current status and metrics.
        """
        # Use a fast, cheap model for health check
        result = await self._query_openrouter(
            model=DEFAULT_HEALTH_CHECK_MODEL,
            messages=[{"role": "user", "content": "ping"}],
            timeout=10.0,
        )

        now = datetime.now()
        latency = float(result.get("latency_ms", 0))

        if result["status"] == "ok":
            return RouterHealth(
                router_id=self.router_id,
                status=HealthStatus.HEALTHY,
                latency_ms=latency,
                last_check=now,
            )
        else:
            return RouterHealth(
                router_id=self.router_id,
                status=HealthStatus.UNHEALTHY,
                latency_ms=latency,
                last_check=now,
                error_message=result.get("error"),
            )
