"""Gateway error types for LLM Council multi-router abstraction (ADR-023).

This module defines a structured error taxonomy for gateway operations,
enabling proper error handling, circuit breaker logic, and fallback decisions.
"""

from typing import Optional


class GatewayError(Exception):
    """Base class for all gateway errors."""

    pass


class TransportFailure(GatewayError):
    """Network-level transport failure.

    Indicates connection issues, DNS failures, or other transport-layer problems.
    These errors may be transient and suitable for retry.
    """

    def __init__(self, message: str, router_id: Optional[str] = None):
        super().__init__(message)
        self.router_id = router_id


class RateLimitError(GatewayError):
    """Rate limit exceeded (HTTP 429).

    Includes optional retry_after hint for when to retry.
    """

    def __init__(self, message: str, retry_after: Optional[int] = None):
        super().__init__(message)
        self.retry_after = retry_after


class AuthenticationError(GatewayError):
    """Authentication or authorization failure (HTTP 401/403).

    Indicates invalid API key or insufficient permissions.
    These errors are typically not retryable.
    """

    pass


class ModelNotFoundError(GatewayError):
    """Model not found or not available (HTTP 404).

    The requested model identifier is not recognized by the gateway.
    """

    def __init__(self, message: str, model_id: Optional[str] = None):
        super().__init__(message)
        self.model_id = model_id


class CircuitOpenError(GatewayError):
    """Circuit breaker is open - requests are being rejected.

    The gateway has been marked as unhealthy due to repeated failures.
    Requests should be routed to fallback gateways.
    """

    def __init__(self, message: str, router_id: Optional[str] = None):
        super().__init__(message)
        self.router_id = router_id


class ContentFilterError(GatewayError):
    """Content was filtered by the provider's safety system.

    The request or response was blocked due to content policy violations.
    """

    pass


class ContextLengthError(GatewayError):
    """Request exceeds the model's context window.

    The input is too long for the specified model.
    """

    def __init__(self, message: str, max_tokens: Optional[int] = None):
        super().__init__(message)
        self.max_tokens = max_tokens
