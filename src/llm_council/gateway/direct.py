"""Direct API gateway implementation for LLM Council (ADR-023 Phase 3, Issue #67).

This module provides direct API access to LLM providers (Anthropic, OpenAI, Google)
without going through intermediate routers like OpenRouter or Requesty.

Use this gateway when:
- You have direct API agreements with providers
- You want maximum control over API calls
- You need to avoid router overhead/latency
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


# Provider API endpoints
PROVIDER_ENDPOINTS = {
    "anthropic": "https://api.anthropic.com/v1/messages",
    "openai": "https://api.openai.com/v1/chat/completions",
    "google": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
}

# Provider API key environment variable names
PROVIDER_KEY_ENV_VARS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
}


class DirectGateway(BaseRouter):
    """Direct API gateway implementing BaseRouter protocol.

    Provides direct access to LLM provider APIs without intermediate routers.
    Requires provider-specific API keys (BYOK mode).
    """

    def __init__(
        self,
        provider_keys: Optional[Dict[str, str]] = None,
        default_timeout: float = 120.0,
    ):
        """Initialize the Direct gateway.

        Args:
            provider_keys: Dict mapping provider names to API keys.
                          If not provided, keys are read from environment.
            default_timeout: Default request timeout in seconds.
        """
        self._provider_keys = provider_keys or {}
        self._default_timeout = default_timeout
        self._capabilities = RouterCapabilities(
            supports_streaming=True,
            supports_tools=True,
            supports_vision=True,
            supports_json_mode=True,
            supports_byok=True,
            requires_byok=True,  # Direct requires provider keys
        )

    @property
    def router_id(self) -> str:
        """Return the router identifier."""
        return "direct"

    @property
    def capabilities(self) -> RouterCapabilities:
        """Return the capabilities of this router."""
        return self._capabilities

    def _get_provider(self, model: str) -> str:
        """Extract provider name from model identifier.

        Args:
            model: Model identifier (e.g., "anthropic/claude-3-5-sonnet-20241022")

        Returns:
            Provider name (e.g., "anthropic")
        """
        if "/" in model:
            return model.split("/")[0]
        return model

    def _get_model_name(self, model: str) -> str:
        """Extract model name from model identifier.

        Args:
            model: Model identifier (e.g., "anthropic/claude-3-5-sonnet-20241022")

        Returns:
            Model name without provider prefix
        """
        if "/" in model:
            return model.split("/", 1)[1]
        return model

    def _get_api_key(self, provider: str) -> Optional[str]:
        """Get API key for a provider.

        Args:
            provider: Provider name

        Returns:
            API key or None if not configured
        """
        # Check constructor-provided keys first
        if provider in self._provider_keys:
            return self._provider_keys[provider]

        # Fall back to environment variable
        env_var = PROVIDER_KEY_ENV_VARS.get(provider)
        if env_var:
            return os.environ.get(env_var)

        return None

    def _get_provider_endpoint(self, provider: str) -> str:
        """Get API endpoint for a provider.

        Args:
            provider: Provider name

        Returns:
            API endpoint URL
        """
        return PROVIDER_ENDPOINTS.get(provider, f"https://api.{provider}.com/v1")

    def _convert_message_for_provider(self, msg: CanonicalMessage, provider: str) -> Dict[str, Any]:
        """Convert CanonicalMessage to provider-specific format.

        Args:
            msg: Canonical message to convert.
            provider: Target provider.

        Returns:
            Provider-format message dict.
        """
        if provider == "anthropic":
            return self._convert_to_anthropic(msg)
        elif provider == "google":
            return self._convert_to_google(msg)
        else:
            # OpenAI-compatible format (default)
            return self._convert_to_openai(msg)

    def _convert_to_openai(self, msg: CanonicalMessage) -> Dict[str, Any]:
        """Convert to OpenAI message format."""
        has_images = any(block.type == "image" for block in msg.content)

        if has_images:
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
            text_content = " ".join(
                block.text for block in msg.content if block.type == "text" and block.text
            )
            return {"role": msg.role, "content": text_content}

    def _convert_to_anthropic(self, msg: CanonicalMessage) -> Dict[str, Any]:
        """Convert to Anthropic message format."""
        has_images = any(block.type == "image" for block in msg.content)

        if has_images:
            content_parts = []
            for block in msg.content:
                if block.type == "text" and block.text:
                    content_parts.append({"type": "text", "text": block.text})
                elif block.type == "image" and block.image_url:
                    content_parts.append(
                        {"type": "image", "source": {"type": "url", "url": block.image_url}}
                    )
            return {"role": msg.role, "content": content_parts}
        else:
            text_content = " ".join(
                block.text for block in msg.content if block.type == "text" and block.text
            )
            return {"role": msg.role, "content": text_content}

    def _convert_to_google(self, msg: CanonicalMessage) -> Dict[str, Any]:
        """Convert to Google Gemini message format."""
        parts = []
        for block in msg.content:
            if block.type == "text" and block.text:
                parts.append({"text": block.text})
            elif block.type == "image" and block.image_url:
                parts.append({"inlineData": {"mimeType": "image/png", "data": block.image_url}})

        # Google uses 'user' and 'model' roles
        role = "model" if msg.role == "assistant" else msg.role
        return {"role": role, "parts": parts}

    def _convert_messages_for_provider(
        self, messages: List[CanonicalMessage], provider: str
    ) -> List[Dict[str, Any]]:
        """Convert list of CanonicalMessages to provider format."""
        return [self._convert_message_for_provider(msg, provider) for msg in messages]

    async def _query_provider(
        self,
        provider: str,
        model: str,
        messages: List[Dict[str, Any]],
        timeout: float,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Send a query to a provider's API.

        Args:
            provider: Provider name (anthropic, openai, google).
            model: Model name (without provider prefix).
            messages: Provider-format messages.
            timeout: Request timeout.
            max_tokens: Max tokens to generate.
            temperature: Sampling temperature.

        Returns:
            Structured result dict with status, content, latency_ms, etc.
        """
        api_key = self._get_api_key(provider)
        if not api_key:
            return {
                "status": "auth_error",
                "latency_ms": 0,
                "error": f"No API key configured for {provider}",
            }

        endpoint = self._get_provider_endpoint(provider)
        start_time = time.time()

        try:
            if provider == "anthropic":
                return await self._query_anthropic(
                    api_key, model, messages, timeout, max_tokens, temperature
                )
            elif provider == "google":
                return await self._query_google(
                    api_key, model, messages, timeout, max_tokens, temperature
                )
            else:
                # OpenAI and OpenAI-compatible
                return await self._query_openai(
                    api_key, endpoint, model, messages, timeout, max_tokens, temperature
                )

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

    async def _query_openai(
        self,
        api_key: str,
        endpoint: str,
        model: str,
        messages: List[Dict[str, Any]],
        timeout: float,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Query OpenAI API."""
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
        }

        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if temperature is not None:
            payload["temperature"] = temperature

        start_time = time.time()

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
            latency_ms = int((time.time() - start_time) * 1000)

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After", "60")
                return {
                    "status": "rate_limited",
                    "latency_ms": latency_ms,
                    "error": f"Rate limited",
                    "retry_after": int(retry_after) if retry_after.isdigit() else 60,
                }

            if response.status_code in (401, 403):
                return {
                    "status": "auth_error",
                    "latency_ms": latency_ms,
                    "error": f"Authentication failed: {response.status_code}",
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

    async def _query_anthropic(
        self,
        api_key: str,
        model: str,
        messages: List[Dict[str, Any]],
        timeout: float,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Query Anthropic API."""
        endpoint = PROVIDER_ENDPOINTS["anthropic"]
        headers = {
            "x-api-key": api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }

        # Anthropic requires system message to be separate
        system_msg = None
        user_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                system_msg = msg.get("content", "")
            else:
                user_messages.append(msg)

        payload: Dict[str, Any] = {
            "model": model,
            "messages": user_messages,
            "max_tokens": max_tokens or 4096,
        }

        if system_msg:
            payload["system"] = system_msg
        if temperature is not None:
            payload["temperature"] = temperature

        start_time = time.time()

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
            latency_ms = int((time.time() - start_time) * 1000)

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After", "60")
                return {
                    "status": "rate_limited",
                    "latency_ms": latency_ms,
                    "error": f"Rate limited",
                    "retry_after": int(retry_after) if retry_after.isdigit() else 60,
                }

            if response.status_code in (401, 403):
                return {
                    "status": "auth_error",
                    "latency_ms": latency_ms,
                    "error": f"Authentication failed: {response.status_code}",
                }

            response.raise_for_status()

            data = response.json()
            content = ""
            if data.get("content"):
                content = "".join(
                    block.get("text", "")
                    for block in data["content"]
                    if block.get("type") == "text"
                )

            usage = data.get("usage", {})

            return {
                "status": "ok",
                "content": content,
                "latency_ms": latency_ms,
                "usage": {
                    "prompt_tokens": usage.get("input_tokens", 0),
                    "completion_tokens": usage.get("output_tokens", 0),
                    "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
                },
            }

    async def _query_google(
        self,
        api_key: str,
        model: str,
        messages: List[Dict[str, Any]],
        timeout: float,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Query Google Gemini API."""
        endpoint = PROVIDER_ENDPOINTS["google"].format(model=model)
        headers = {
            "Content-Type": "application/json",
        }

        # Google uses URL param for API key
        params = {"key": api_key}

        payload: Dict[str, Any] = {
            "contents": messages,
        }

        if max_tokens is not None or temperature is not None:
            generation_config = {}
            if max_tokens is not None:
                generation_config["maxOutputTokens"] = max_tokens
            if temperature is not None:
                generation_config["temperature"] = temperature
            payload["generationConfig"] = generation_config

        start_time = time.time()

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(endpoint, headers=headers, params=params, json=payload)
            latency_ms = int((time.time() - start_time) * 1000)

            if response.status_code == 429:
                return {
                    "status": "rate_limited",
                    "latency_ms": latency_ms,
                    "error": f"Rate limited",
                    "retry_after": 60,
                }

            if response.status_code in (401, 403):
                return {
                    "status": "auth_error",
                    "latency_ms": latency_ms,
                    "error": f"Authentication failed: {response.status_code}",
                }

            response.raise_for_status()

            data = response.json()
            content = ""
            if data.get("candidates"):
                candidate = data["candidates"][0]
                if candidate.get("content", {}).get("parts"):
                    content = "".join(
                        part.get("text", "") for part in candidate["content"]["parts"]
                    )

            usage = data.get("usageMetadata", {})

            return {
                "status": "ok",
                "content": content,
                "latency_ms": latency_ms,
                "usage": {
                    "prompt_tokens": usage.get("promptTokenCount", 0),
                    "completion_tokens": usage.get("candidatesTokenCount", 0),
                    "total_tokens": usage.get("totalTokenCount", 0),
                },
            }

    async def complete(self, request: GatewayRequest) -> GatewayResponse:
        """Send a completion request and return the response.

        Args:
            request: The gateway request with model and messages.

        Returns:
            GatewayResponse with the generated content.
        """
        provider = self._get_provider(request.model)
        model_name = self._get_model_name(request.model)

        # Check for API key
        if not self._get_api_key(provider):
            return GatewayResponse(
                content="",
                model=request.model,
                status="auth_error",
                error=f"No API key configured for {provider}",
            )

        # Convert messages to provider format
        messages = self._convert_messages_for_provider(request.messages, provider)

        # Determine timeout
        timeout = request.timeout if request.timeout is not None else self._default_timeout

        # Make the request
        result = await self._query_provider(
            provider=provider,
            model=model_name,
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
        response = await self.complete(request)
        if response.content:
            yield response.content

    async def health_check(self) -> RouterHealth:
        """Check the health of this router.

        Returns:
            RouterHealth with current status and metrics.
        """
        # Try to find any configured provider
        for provider in ["openai", "anthropic", "google"]:
            if self._get_api_key(provider):
                # Use a minimal query to check health
                result = await self._query_provider(
                    provider=provider,
                    model="gpt-4o-mini"
                    if provider == "openai"
                    else "claude-3-5-haiku-20241022"
                    if provider == "anthropic"
                    else "gemini-2.0-flash-001",
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

        # No provider keys configured
        return RouterHealth(
            router_id=self.router_id,
            status=HealthStatus.UNHEALTHY,
            latency_ms=0.0,
            last_check=datetime.now(),
            error_message="No provider API keys configured",
        )
