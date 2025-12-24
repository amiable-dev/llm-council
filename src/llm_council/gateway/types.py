"""Gateway types for LLM Council multi-router abstraction (ADR-023).

This module defines canonical message formats and request/response types
that provide a provider-agnostic interface for LLM API interactions.

ADR-026 Phase 2: Added ReasoningParams for reasoning parameter injection.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from ..reasoning import ReasoningConfig


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
class ReasoningParams:
    """Reasoning parameters for OpenRouter API (ADR-026 Phase 2).

    Controls reasoning behavior for models that support reasoning
    (o1, o3, deepseek-r1, etc.).

    Attributes:
        effort: Reasoning effort level (minimal|low|medium|high|xhigh)
        max_tokens: Maximum tokens allocated for reasoning
        exclude: Whether to exclude reasoning from response (default False)
    """

    effort: str  # minimal|low|medium|high|xhigh
    max_tokens: int  # Budget for reasoning tokens
    exclude: bool = False  # Whether to exclude reasoning from response

    @classmethod
    def from_config(cls, config: "ReasoningConfig") -> Optional["ReasoningParams"]:
        """Create ReasoningParams from a ReasoningConfig.

        Args:
            config: ReasoningConfig with effort and budget settings

        Returns:
            ReasoningParams if config is enabled, None otherwise
        """
        if not config.enabled:
            return None

        return cls(
            effort=config.effort.value,
            max_tokens=config.budget_tokens,
            exclude=False,
        )


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
    # Reasoning parameters for reasoning models (ADR-026 Phase 2)
    reasoning_params: Optional[ReasoningParams] = None


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
