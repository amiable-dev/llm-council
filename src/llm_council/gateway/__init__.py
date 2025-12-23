"""LLM Council Gateway Abstraction Layer (ADR-023).

This package provides a unified interface for routing LLM requests across
multiple providers (OpenRouter, Requesty, Direct APIs) with features like:

- Provider-agnostic message formats
- Circuit breaker pattern for fault tolerance
- Fallback chains for reliability
- Health monitoring and status tracking

Example usage:
    from llm_council.gateway import GatewayRouter, GatewayRequest, CanonicalMessage

    router = GatewayRouter()
    request = GatewayRequest(
        model="openai/gpt-4o",
        messages=[
            CanonicalMessage(role="user", content=[ContentBlock(type="text", text="Hello")])
        ]
    )
    response = await router.complete(request)
"""

from .types import (
    CanonicalMessage,
    ContentBlock,
    GatewayRequest,
    GatewayResponse,
    UsageInfo,
)
from .base import (
    BaseRouter,
    HealthStatus,
    RouterCapabilities,
    RouterConfig,
    RouterHealth,
)
from .errors import (
    GatewayError,
    TransportFailure,
    RateLimitError,
    AuthenticationError,
    ModelNotFoundError,
    CircuitOpenError,
    ContentFilterError,
    ContextLengthError,
)
from .openrouter import OpenRouterGateway
from .requesty import RequestyGateway
from .direct import DirectGateway
from .ollama import OllamaGateway, QualityDegradationNotice
from .circuit_breaker import CircuitBreaker, CircuitState
from .router import GatewayRouter

__all__ = [
    # Types
    "CanonicalMessage",
    "ContentBlock",
    "GatewayRequest",
    "GatewayResponse",
    "UsageInfo",
    # Base
    "BaseRouter",
    "HealthStatus",
    "RouterCapabilities",
    "RouterConfig",
    "RouterHealth",
    # Errors
    "GatewayError",
    "TransportFailure",
    "RateLimitError",
    "AuthenticationError",
    "ModelNotFoundError",
    "CircuitOpenError",
    "ContentFilterError",
    "ContextLengthError",
    # Gateways
    "OpenRouterGateway",
    "RequestyGateway",
    "DirectGateway",
    "OllamaGateway",
    "QualityDegradationNotice",
    # Circuit Breaker
    "CircuitBreaker",
    "CircuitState",
    # Router
    "GatewayRouter",
]
