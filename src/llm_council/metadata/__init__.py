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
"""

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


def get_provider() -> MetadataProvider:
    """Get the configured metadata provider.

    Returns a singleton instance of the appropriate provider based on
    configuration. Currently always returns StaticRegistryProvider.
    Future: May return DynamicMetadataProvider when online.

    Returns:
        MetadataProvider instance
    """
    global _provider
    if _provider is None:
        _provider = StaticRegistryProvider()
        # Log offline mode status on first access
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
