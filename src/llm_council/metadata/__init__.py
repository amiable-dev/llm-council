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

from .types import (
    ModelInfo,
    QualityTier,
    Modality,
)
from .protocol import MetadataProvider

__all__ = [
    # Types
    "ModelInfo",
    "QualityTier",
    "Modality",
    # Protocol
    "MetadataProvider",
]
