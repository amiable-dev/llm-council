"""Requesty gateway implementation for LLM Council (ADR-023 Phase 2, Issue #66).

This module provides a Requesty-specific implementation of the BaseRouter
protocol, enabling access to multiple LLM providers with BYOK (Bring Your Own Key)
support and advanced analytics features.

Requesty API: https://api.requesty.ai/v1/chat/completions
"""

import os
import time
from datetime import datetime
from typing import AsyncIterator, Dict, Any, List, Optional

import httpx

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
    UsageInfo,
)


# Default Requesty API URL
REQUESTY_API_URL = "https://router.requesty.ai/v1/chat/completions"


class RequestyGateway(BaseRouter):
    """Requesty gateway implementing BaseRouter protocol.

    Provides access to multiple LLM providers with BYOK support,
    analytics, and caching capabilities.

    Features:
    - BYOK (Bring Your Own Key): Use your own provider API keys
    - Analytics: Request/response logging and metrics
    - Fallback chains: Automatic retry with alternative providers
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        default_timeout: float = 120.0,
        byok_enabled: bool = False,
        byok_keys: Optional[Dict[str, str]] = None,
    ):
        """Initialize the Requesty gateway.

        Args:
            api_key: Requesty API key. If None, uses REQUESTY_API_KEY from env.
            base_url: Base URL for Requesty API. If None, uses default.
            default_timeout: Default request timeout in seconds.
            byok_enabled: Whether to use BYOK (Bring Your Own Key) mode.
            byok_keys: Dict mapping provider names to API keys for BYOK mode.
        """
        self._api_key = api_key or os.environ.get("REQUESTY_API_KEY", "")
        self._base_url = base_url or REQUESTY_API_URL
        self._default_timeout = default_timeout
        self._byok_enabled = byok_enabled
        self._byok_keys = byok_keys or {}
        self._capabilities = RouterCapabilities(
            supports_streaming=True,
            supports_tools=True,
            supports_vision=True,
            supports_json_mode=True,
            supports_byok=True,  # Requesty supports BYOK
            requires_byok=False,
        )

    @property
    def router_id(self) -> str:
        """Return the router identifier."""
        return "requesty"

    @property
    def capabilities(self) -> RouterCapabilities:
        """Return the capabilities of this router."""
        return self._capabilities

    @property
    def byok_enabled(self) -> bool:
        """Return whether BYOK mode is enabled."""
        return self._byok_enabled

    @property
    def byok_keys(self) -> Dict[str, str]:
        """Return the BYOK provider keys."""
        return self._byok_keys

    def _get_provider_from_model(self, model: str) -> str:
        """Extract provider name from model identifier.

        Args:
            model: Model identifier (e.g., "anthropic/claude-3-5-sonnet-20241022")

        Returns:
            Provider name (e.g., "anthropic")
        """
        if "/" in model:
            return model.split("/")[0]
        return model

    def _get_byok_headers(self, model: str) -> Dict[str, str]:
        """Get BYOK headers for the given model.

        Args:
            model: Model identifier

        Returns:
            Dict with BYOK headers if applicable
        """
        if not self._byok_enabled:
            return {}

        provider = self._get_provider_from_model(model)
        provider_key = self._byok_keys.get(provider)

        if provider_key:
            return {"X-Provider-API-Key": provider_key}

        return {}

    def _convert_message(self, msg: CanonicalMessage) -> Dict[str, Any]:
        """Convert CanonicalMessage to Requesty message format.

        Args:
            msg: Canonical message to convert.

        Returns:
            Requesty-format message dict.
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
        """Convert list of CanonicalMessages to Requesty format."""
        return [self._convert_message(msg) for msg in messages]

    async def _query_requesty(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        timeout: float,
        byok_headers: Optional[Dict[str, str]] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Send a query to Requesty API.

        This is the core HTTP request method that can be mocked for testing.

        Args:
            model: Model identifier.
            messages: Requesty-format messages.
            timeout: Request timeout.
            byok_headers: Optional BYOK headers.
            max_tokens: Max tokens to generate.
            temperature: Sampling temperature.

        Returns:
            Structured result dict with status, content, latency_ms, etc.
        """
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        # Add BYOK headers if provided
        if byok_headers:
            headers.update(byok_headers)

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
        }

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
        # Convert messages to Requesty format
        messages = self._convert_messages(request.messages)

        # Determine timeout
        timeout = request.timeout if request.timeout is not None else self._default_timeout

        # Get BYOK headers if enabled
        byok_headers = self._get_byok_headers(request.model)

        # Make the request
        result = await self._query_requesty(
            model=request.model,
            messages=messages,
            timeout=timeout,
            byok_headers=byok_headers,
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
        result = await self._query_requesty(
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
