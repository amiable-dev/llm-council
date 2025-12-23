"""Static Registry Provider for LLM Council (ADR-026).

This module provides the offline-safe StaticRegistryProvider that loads
model metadata from a bundled YAML registry with LiteLLM fallback.

The priority chain for context window lookup:
1. Local registry.yaml override
2. LiteLLM library data
3. Safe default (4096)

This implements the "Sovereign Orchestrator" philosophy from ADR-026:
the system must function without external dependencies when offline.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from .types import ModelInfo, QualityTier
from .litellm_adapter import LiteLLMAdapter

logger = logging.getLogger(__name__)

# Default path to bundled registry
DEFAULT_REGISTRY_PATH = Path(__file__).parent.parent / "models" / "registry.yaml"

# Safe default context window per ADR-026
DEFAULT_CONTEXT_WINDOW = 4096


class StaticRegistryProvider:
    """Offline-safe metadata provider using bundled YAML registry.

    This provider loads model metadata from a YAML file and uses LiteLLM
    as a fallback for missing data. It is designed to work without any
    external network calls.

    Attributes:
        _registry: Dict mapping model_id to ModelInfo
        _litellm_adapter: Adapter for LiteLLM metadata fallback

    Example:
        >>> provider = StaticRegistryProvider()
        >>> info = provider.get_model_info("openai/gpt-4o")
        >>> print(info.context_window)  # 128000
    """

    def __init__(self, registry_path: Optional[Path] = None):
        """Initialize the provider with a registry file.

        Args:
            registry_path: Path to YAML registry file.
                          Defaults to bundled registry.yaml
        """
        self._registry: Dict[str, ModelInfo] = {}
        self._litellm_adapter = LiteLLMAdapter()

        # Load registry
        path = registry_path or DEFAULT_REGISTRY_PATH
        self._load_registry(path)

    def _load_registry(self, path: Path) -> None:
        """Load model registry from YAML file.

        Args:
            path: Path to YAML registry file
        """
        try:
            if not path.exists():
                logger.warning(f"Registry file not found: {path}")
                return

            with open(path, "r") as f:
                data = yaml.safe_load(f)

            if not data or "models" not in data:
                logger.warning(f"Invalid registry schema in {path}")
                return

            models = data.get("models", [])
            if not isinstance(models, list):
                logger.warning(f"Invalid models list in {path}")
                return

            for model_data in models:
                try:
                    model_info = self._parse_model_entry(model_data)
                    if model_info:
                        self._registry[model_info.id] = model_info
                except Exception as e:
                    logger.warning(f"Failed to parse model entry: {e}")

            logger.info(f"Loaded {len(self._registry)} models from registry")

        except Exception as e:
            logger.error(f"Failed to load registry from {path}: {e}")

    def _parse_model_entry(self, data: dict) -> Optional[ModelInfo]:
        """Parse a model entry from YAML data.

        Args:
            data: Dict with model data from YAML

        Returns:
            ModelInfo if valid, None otherwise
        """
        if not isinstance(data, dict):
            return None

        model_id = data.get("id")
        context_window = data.get("context_window")

        if not model_id or context_window is None:
            return None

        # Parse quality tier
        tier_str = data.get("quality_tier", "standard")
        try:
            quality_tier = QualityTier(tier_str)
        except ValueError:
            quality_tier = QualityTier.STANDARD

        return ModelInfo(
            id=model_id,
            context_window=context_window,
            pricing=data.get("pricing", {}),
            supported_parameters=data.get("supported_parameters", []),
            modalities=data.get("modalities", ["text"]),
            quality_tier=quality_tier,
        )

    def get_model_info(self, model_id: str) -> Optional[ModelInfo]:
        """Get full model information.

        Args:
            model_id: Full model identifier (e.g., "openai/gpt-4o")

        Returns:
            ModelInfo if model is known, None otherwise
        """
        return self._registry.get(model_id)

    def get_context_window(self, model_id: str) -> int:
        """Get context window size for a model.

        Implements priority chain:
        1. Local registry override
        2. LiteLLM library data
        3. Safe default (4096)

        Args:
            model_id: Full model identifier

        Returns:
            Context window size in tokens (always returns a valid int)
        """
        # 1. Check local registry first
        info = self._registry.get(model_id)
        if info:
            return info.context_window

        # 2. Try LiteLLM fallback
        litellm_window = self._litellm_adapter.get_context_window(model_id)
        if litellm_window is not None:
            return litellm_window

        # 3. Safe default
        return DEFAULT_CONTEXT_WINDOW

    def get_pricing(self, model_id: str) -> Dict[str, float]:
        """Get pricing information for a model.

        Args:
            model_id: Full model identifier

        Returns:
            Dict with "prompt" and "completion" costs per 1K tokens.
            Returns empty dict if pricing unknown.
        """
        info = self._registry.get(model_id)
        if info and info.pricing:
            return info.pricing

        # Try LiteLLM fallback
        litellm_pricing = self._litellm_adapter.get_pricing(model_id)
        if litellm_pricing:
            return litellm_pricing

        return {}

    def supports_reasoning(self, model_id: str) -> bool:
        """Check if model supports reasoning parameters.

        Reasoning-capable models (o1, o3, etc.) can use extended
        chain-of-thought with reasoning_effort and budget_tokens.

        Args:
            model_id: Full model identifier

        Returns:
            True if model supports reasoning parameters
        """
        info = self._registry.get(model_id)
        if info:
            return "reasoning" in info.supported_parameters

        # Try LiteLLM fallback
        return self._litellm_adapter.supports_reasoning(model_id)

    def list_available_models(self) -> List[str]:
        """List all available model IDs.

        Returns:
            List of model identifiers known to this provider
        """
        return list(self._registry.keys())
