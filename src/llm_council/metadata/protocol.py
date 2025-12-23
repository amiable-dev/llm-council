"""MetadataProvider Protocol for LLM Council (ADR-026).

This module defines the abstract protocol that all metadata sources must implement.
The protocol is runtime_checkable, allowing isinstance() checks for duck typing.

Implementations:
- StaticRegistryProvider: Offline-safe provider using bundled YAML + LiteLLM
- DynamicMetadataProvider: (Future) Real-time metadata from OpenRouter API

The protocol follows the "Sovereign Orchestrator" philosophy from ADR-026:
the system must function without external dependencies when offline.
"""

from typing import Dict, List, Optional, Protocol, runtime_checkable

from .types import ModelInfo


@runtime_checkable
class MetadataProvider(Protocol):
    """Abstract protocol for model metadata sources.

    All metadata providers must implement this protocol to ensure
    consistent behavior across different data sources (static registry,
    LiteLLM, OpenRouter API, etc.).

    The protocol is @runtime_checkable, allowing isinstance() checks:

        >>> provider = StaticRegistryProvider()
        >>> isinstance(provider, MetadataProvider)
        True

    Methods:
        get_model_info: Get full ModelInfo for a model
        get_context_window: Get context window size with fallback
        get_pricing: Get prompt/completion pricing
        supports_reasoning: Check if model supports reasoning parameters
        list_available_models: List all known model IDs
    """

    def get_model_info(self, model_id: str) -> Optional[ModelInfo]:
        """Get full model information.

        Args:
            model_id: Full model identifier (e.g., "openai/gpt-4o")

        Returns:
            ModelInfo if model is known, None otherwise
        """
        ...

    def get_context_window(self, model_id: str) -> int:
        """Get context window size for a model.

        This method should implement a fallback chain:
        1. Local registry override
        2. LiteLLM library data
        3. Safe default (4096)

        Args:
            model_id: Full model identifier

        Returns:
            Context window size in tokens (always returns a valid int)
        """
        ...

    def get_pricing(self, model_id: str) -> Dict[str, float]:
        """Get pricing information for a model.

        Args:
            model_id: Full model identifier

        Returns:
            Dict with "prompt" and "completion" costs per 1K tokens.
            Returns empty dict if pricing unknown.
        """
        ...

    def supports_reasoning(self, model_id: str) -> bool:
        """Check if model supports reasoning parameters.

        Reasoning-capable models (o1, o3, etc.) can use extended
        chain-of-thought with reasoning_effort and budget_tokens.

        Args:
            model_id: Full model identifier

        Returns:
            True if model supports reasoning parameters
        """
        ...

    def list_available_models(self) -> List[str]:
        """List all available model IDs.

        Returns:
            List of model identifiers known to this provider
        """
        ...
