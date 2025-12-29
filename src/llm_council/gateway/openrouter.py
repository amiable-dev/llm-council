"""OpenRouter gateway implementation for LLM Council (ADR-023).

This module provides an OpenRouter-specific implementation of the BaseRouter
protocol, enabling unified access to 100+ models via OpenRouter's API.

The gateway wraps the existing openrouter module functionality while
conforming to the BaseRouter interface.
"""

import time
from datetime import datetime
from typing import AsyncIterator, Dict, Any, List, Optional

import httpx

# ADR-032: Migrated to unified_config
from llm_council.unified_config import get_api_key

# Default constants
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"


def _get_openrouter_api_key() -> str:
    """Get OpenRouter API key via ADR-013 resolution chain."""
    return get_api_key("openrouter") or ""


OPENROUTER_API_KEY = _get_openrouter_api_key()

from .base import (
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
        self._api_key = api_key or OPENROUTER_API_KEY
        self._base_url = base_url or OPENROUTER_API_URL
        self._default_timeout = default_timeout
        self._capabilities = RouterCapabilities(
            supports_streaming=True,
            supports_tools=True,
            supports_vision=True,
            supports_json_mode=True,
            supports_byok=False,  # OpenRouter manages API keys
            requires_byok=False,
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
            return {"role": msg.role, "content": content_parts}
        else:
            # Simple text content
            text_content = " ".join(
                block.text for block in msg.content if block.type == "text" and block.text
            )
            return {"role": msg.role, "content": text_content}

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
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
        }

        if disable_tools:
            payload["tools"] = []
            payload["tool_choice"] = "none"

        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        if temperature is not None:
            payload["temperature"] = temperature

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

                response.raise_for_status()

                data = response.json()
                message = data["choices"][0]["message"]
                usage = data.get("usage", {})

                return {
                    "status": "ok",
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

        return GatewayResponse(
            content=result.get("content", ""),
            model=request.model,
            status=result["status"],
            usage=usage,
            latency_ms=result.get("latency_ms"),
            error=result.get("error"),
            retry_after=result.get("retry_after"),
        )

    async def complete_stream(self, request: GatewayRequest) -> AsyncIterator[str]:
        """Send a streaming completion request.

        Args:
            request: The gateway request with model and messages.

        Yields:
            String chunks of the generated content.

        Note:
            Streaming is not yet fully implemented. This yields the complete
            response as a single chunk for now.
        """
        # For now, just yield the complete response
        # Full streaming implementation can be added later
        response = await self.complete(request)
        if response.content:
            yield response.content

    async def health_check(self) -> RouterHealth:
        """Check the health of this router.

        Returns:
            RouterHealth with current status and metrics.
        """
        # Use a fast, cheap model for health check
        result = await self._query_openrouter(
            model="google/gemini-2.0-flash-001",
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
