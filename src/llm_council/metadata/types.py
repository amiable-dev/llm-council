"""Model Metadata Types for LLM Council (ADR-026).

This module defines the core data structures for model metadata:
- ModelInfo: Frozen dataclass containing model capabilities and pricing
- QualityTier: Classification of model quality/capability
- Modality: Input/output modalities supported by models

These types are used throughout the Model Intelligence Layer for
capability detection, tier selection, and cost optimization.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List


class QualityTier(Enum):
    """Quality tier classification for models.

    Tiers are used for tier-specific model selection and weighting.
    Per ADR-026, different tiers have different selection priorities.
    """

    FRONTIER = "frontier"  # Top-tier models (GPT-4o, Claude Opus, etc.)
    STANDARD = "standard"  # Good quality, balanced cost (GPT-4o-mini, Sonnet)
    ECONOMY = "economy"  # Cost-optimized (Haiku, Flash)
    LOCAL = "local"  # Locally-run models (Ollama)


class Modality(Enum):
    """Input/output modalities supported by models.

    Used for capability-aware routing and feature detection.
    """

    TEXT = "text"  # Text input/output
    VISION = "vision"  # Image input support
    AUDIO = "audio"  # Audio input/output support


class ModelStatus(Enum):
    """Model availability status for dynamic discovery (ADR-028).

    Used to filter models during discovery and selection.
    Models with DEPRECATED status are excluded from selection.
    """

    AVAILABLE = "available"  # Model is available for use
    DEPRECATED = "deprecated"  # Model is deprecated, should not be selected
    PREVIEW = "preview"  # Model is in preview, may be unstable
    BETA = "beta"  # Model is in beta testing


@dataclass(frozen=True)
class ModelInfo:
    """Immutable model metadata information.

    This is the core data structure for model capabilities and pricing.
    It is frozen (immutable) to ensure thread-safety and hashability.

    Attributes:
        id: Full model identifier (e.g., "openai/gpt-4o")
        context_window: Maximum context length in tokens
        pricing: Dict with "prompt" and "completion" costs per 1K tokens
        supported_parameters: List of supported API parameters
        modalities: List of supported input modalities
        quality_tier: Classification of model quality level
        is_preview: Whether model is in preview/beta status (ADR-027)
        supports_reasoning: Whether model supports extended reasoning (ADR-027)

    Example:
        >>> info = ModelInfo(
        ...     id="openai/gpt-4o",
        ...     context_window=128000,
        ...     pricing={"prompt": 0.0025, "completion": 0.01},
        ...     supported_parameters=["temperature", "top_p", "tools"],
        ...     modalities=["text", "vision"],
        ...     quality_tier=QualityTier.FRONTIER,
        ... )
    """

    id: str
    context_window: int
    pricing: Dict[str, float] = field(default_factory=dict)
    supported_parameters: List[str] = field(default_factory=list)
    modalities: List[str] = field(default_factory=lambda: ["text"])
    quality_tier: QualityTier = QualityTier.STANDARD
    is_preview: bool = False
    supports_reasoning: bool = False

    def __post_init__(self):
        """Validate required fields."""
        if not self.id:
            raise ValueError("ModelInfo.id cannot be empty")
        if self.context_window < 0:
            raise ValueError("ModelInfo.context_window must be non-negative")
