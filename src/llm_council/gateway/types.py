"""Gateway types for LLM Council multi-router abstraction (ADR-023).

This module defines canonical message formats and request/response types
that provide a provider-agnostic interface for LLM API interactions.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ContentBlock:
    """A content block within a message.

    Supports text, image, and tool-use content types.
    """

    type: str  # "text", "image", "tool_use", "tool_result"
    text: Optional[str] = None
    image_url: Optional[str] = None
    tool_use: Optional[Dict[str, Any]] = None


@dataclass
class CanonicalMessage:
    """Provider-agnostic message format.

    Represents a single message in a conversation, with role
    (system/user/assistant) and structured content blocks.
    """

    role: str  # "system", "user", "assistant"
    content: List[ContentBlock]
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    tool_call_id: Optional[str] = None


@dataclass
class UsageInfo:
    """Token usage information from an API response."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass
class GatewayRequest:
    """Request to send to a gateway router.

    Contains the model identifier, messages, and optional generation parameters.
    """

    model: str  # e.g., "openai/gpt-4o" or "anthropic/claude-3-5-sonnet"
    messages: List[CanonicalMessage]
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    timeout: Optional[float] = None
    # Additional provider-specific parameters
    extra_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GatewayResponse:
    """Response from a gateway router.

    Contains the generated content, model identifier, and optional metadata.
    """

    content: str
    model: str
    status: str  # "ok", "error", "timeout", "rate_limited"
    usage: Optional[UsageInfo] = None
    latency_ms: Optional[int] = None
    error: Optional[str] = None
    retry_after: Optional[int] = None  # For rate limiting
