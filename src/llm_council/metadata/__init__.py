"""Model Metadata Provider for LLM Council (ADR-026).

This module provides model metadata abstraction for the Model Intelligence Layer.
It supports both offline operation (StaticRegistryProvider) and dynamic metadata
fetching (DynamicMetadataProvider).

Example usage:
    from llm_council.metadata import (
        ModelInfo,
        QualityTier,
        MetadataProvider,
        get_provider,
    )

    # Get the configured provider
    provider = get_provider()

    # Query model metadata
    info = provider.get_model_info("openai/gpt-4o")
    window = provider.get_context_window("openai/gpt-4o")
    can_reason = provider.supports_reasoning("openai/o1")

Environment Variables:
    LLM_COUNCIL_OFFLINE: Set to "true" to use StaticRegistryProvider exclusively
    LLM_COUNCIL_MODEL_INTELLIGENCE: Set to "true" to enable DynamicMetadataProvider
"""

import os
from typing import Optional

from .types import (
    ModelInfo,
    QualityTier,
    Modality,
)
from .protocol import MetadataProvider
from .static_registry import StaticRegistryProvider
from .offline import is_offline_mode, check_offline_mode_startup

# Global provider instance (singleton)
_provider: Optional[MetadataProvider] = None

# Truthy values for model intelligence mode
_TRUTHY_VALUES = {"true", "1", "yes", "on"}


def _is_model_intelligence_enabled() -> bool:
    """Check if model intelligence (dynamic provider) is enabled."""
    value = os.environ.get("LLM_COUNCIL_MODEL_INTELLIGENCE", "").lower()
    return value in _TRUTHY_VALUES


def get_provider() -> MetadataProvider:
    """Get the configured metadata provider.

    Returns a singleton instance of the appropriate provider based on
    configuration:
    - Offline mode (LLM_COUNCIL_OFFLINE=true): StaticRegistryProvider
    - Intelligence enabled (LLM_COUNCIL_MODEL_INTELLIGENCE=true): DynamicMetadataProvider
    - Default: StaticRegistryProvider

    Returns:
        MetadataProvider instance
    """
    global _provider
    if _provider is None:
        # Offline mode takes precedence
        if is_offline_mode():
            _provider = StaticRegistryProvider()
            check_offline_mode_startup()
        elif _is_model_intelligence_enabled():
            # Lazy import to avoid circular dependencies
            from .dynamic_provider import DynamicMetadataProvider
            _provider = DynamicMetadataProvider()
        else:
            _provider = StaticRegistryProvider()
            check_offline_mode_startup()
    return _provider


def reload_provider() -> None:
    """Force reload of the metadata provider.

    Creates a fresh provider instance on next get_provider() call.
    Useful for testing or when configuration changes.
    """
    global _provider
    _provider = None


__all__ = [
    # Types
    "ModelInfo",
    "QualityTier",
    "Modality",
    # Protocol
    "MetadataProvider",
    # Provider
    "StaticRegistryProvider",
    # Factory
    "get_provider",
    "reload_provider",
    # Offline mode
    "is_offline_mode",
    "check_offline_mode_startup",
]
