"""Gateway base types and protocols for LLM Council (ADR-023).

This module defines the abstract base router protocol and configuration types
that all gateway implementations must follow.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncIterator, Dict, List, Optional

from .types import GatewayRequest, GatewayResponse


class HealthStatus(Enum):
    """Health status for a gateway router."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class RouterCapabilities:
    """Capabilities supported by a gateway router.

    Used for capability-based routing and feature detection.
    """

    supports_streaming: bool = True
    supports_tools: bool = True
    supports_vision: bool = True
    supports_json_mode: bool = True
    supports_byok: bool = False  # Bring Your Own Key
    requires_byok: bool = False  # Requires user API keys
    max_context_window: Optional[int] = None
    supported_models: List[str] = field(default_factory=list)


@dataclass
class RouterConfig:
    """Configuration for a gateway router.

    Contains connection details, authentication, and retry policies.
    """

    name: str
    base_url: str
    api_key_env: str  # Environment variable name for API key
    timeout: float = 120.0
    retry_policy: Optional[Dict[str, Any]] = None
    extra_headers: Optional[Dict[str, str]] = None


@dataclass
class RouterHealth:
    """Health status of a gateway router.

    Used for monitoring and circuit breaker decisions.
    """

    router_id: str
    status: HealthStatus
    latency_ms: float
    last_check: datetime
    circuit_open: bool = False
    consecutive_failures: int = 0
    error_message: Optional[str] = None


class BaseRouter(ABC):
    """Abstract base class for gateway routers.

    All gateway implementations (OpenRouter, Requesty, Direct APIs) must
    implement this protocol to ensure consistent behavior across routers.
    """

    @property
    @abstractmethod
    def capabilities(self) -> RouterCapabilities:
        """Return the capabilities of this router."""
        pass

    @abstractmethod
    async def complete(self, request: GatewayRequest) -> GatewayResponse:
        """Send a completion request and return the response.

        Args:
            request: The gateway request with model and messages.

        Returns:
            GatewayResponse with the generated content.

        Raises:
            TransportFailure: For network-level errors.
            RateLimitError: When rate limited (429).
            AuthenticationError: For auth failures (401/403).
            ModelNotFoundError: When model is not available.
        """
        pass

    @abstractmethod
    async def complete_stream(self, request: GatewayRequest) -> AsyncIterator[str]:
        """Send a streaming completion request.

        Args:
            request: The gateway request with model and messages.

        Yields:
            String chunks of the generated content.

        Raises:
            Same exceptions as complete().
        """
        pass

    @abstractmethod
    async def health_check(self) -> RouterHealth:
        """Check the health of this router.

        Returns:
            RouterHealth with current status and metrics.
        """
        pass
