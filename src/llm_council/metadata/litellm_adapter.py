"""LiteLLM Metadata Adapter for LLM Council (ADR-026).

This module provides metadata extraction from LiteLLM's model registry.
LiteLLM maintains a comprehensive model_cost dictionary with context windows,
pricing, and capability information.

The adapter uses lazy importing to keep LiteLLM as an optional dependency.
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class LiteLLMAdapter:
    """Adapter for extracting model metadata from LiteLLM.

    LiteLLM maintains a model_cost dictionary with metadata for most
    major LLM providers. This adapter provides a clean interface for
    querying that data.

    Attributes:
        _litellm: Cached LiteLLM module (lazy imported)

    Example:
        >>> adapter = LiteLLMAdapter()
        >>> window = adapter.get_context_window("openai/gpt-4o")
        >>> print(window)  # 128000
    """

    def __init__(self):
        """Initialize the adapter with lazy LiteLLM import."""
        self._litellm = None

    def _get_litellm(self) -> Any:
        """Lazily import and return the LiteLLM module.

        Returns:
            The litellm module

        Raises:
            ImportError: If LiteLLM is not installed
        """
        if self._litellm is None:
            try:
                import litellm

                self._litellm = litellm
            except ImportError as e:
                raise ImportError(
                    "LiteLLM is required for extended metadata support. "
                    "Install it with: pip install litellm"
                ) from e
        return self._litellm

    def _normalize_model_id(self, model_id: str) -> str:
        """Normalize model ID to LiteLLM format.

        LiteLLM uses different formats:
        - OpenAI: "gpt-4o" (no prefix)
        - Anthropic: "claude-3-5-sonnet-20241022" (no prefix)
        - Ollama: "ollama/llama3.2" (keep prefix)

        Args:
            model_id: Full model ID (e.g., "openai/gpt-4o")

        Returns:
            Normalized model ID for LiteLLM lookup
        """
        # Ollama models keep their prefix
        if model_id.startswith("ollama/"):
            return model_id

        # Strip provider prefix for other models
        if "/" in model_id:
            return model_id.split("/", 1)[1]

        return model_id

    def get_context_window(self, model_id: str) -> Optional[int]:
        """Get context window size from LiteLLM.

        Args:
            model_id: Full model identifier

        Returns:
            Context window size, or None if not found
        """
        try:
            litellm = self._get_litellm()
            normalized_id = self._normalize_model_id(model_id)

            model_info = litellm.model_cost.get(normalized_id, {})
            if "max_tokens" in model_info:
                return model_info["max_tokens"]

            # Try with original ID as fallback
            model_info = litellm.model_cost.get(model_id, {})
            if "max_tokens" in model_info:
                return model_info["max_tokens"]

            return None

        except ImportError:
            logger.debug("LiteLLM not available for context window lookup")
            return None
        except Exception as e:
            logger.warning(f"Error getting context window from LiteLLM: {e}")
            return None

    def get_pricing(self, model_id: str) -> Optional[Dict[str, float]]:
        """Get pricing information from LiteLLM.

        Converts LiteLLM's per-token pricing to per-1K tokens format.

        Args:
            model_id: Full model identifier

        Returns:
            Dict with "prompt" and "completion" costs per 1K tokens,
            or None if not found
        """
        try:
            litellm = self._get_litellm()
            normalized_id = self._normalize_model_id(model_id)

            model_info = litellm.model_cost.get(normalized_id, {})
            if not model_info:
                model_info = litellm.model_cost.get(model_id, {})

            if not model_info:
                return None

            pricing = {}

            # Convert per-token to per-1K tokens
            if "input_cost_per_token" in model_info:
                pricing["prompt"] = model_info["input_cost_per_token"] * 1000
            if "output_cost_per_token" in model_info:
                pricing["completion"] = model_info["output_cost_per_token"] * 1000

            return pricing if pricing else None

        except ImportError:
            logger.debug("LiteLLM not available for pricing lookup")
            return None
        except Exception as e:
            logger.warning(f"Error getting pricing from LiteLLM: {e}")
            return None

    def supports_reasoning(self, model_id: str) -> bool:
        """Check if model supports reasoning from LiteLLM.

        Args:
            model_id: Full model identifier

        Returns:
            True if model supports reasoning parameters
        """
        try:
            litellm = self._get_litellm()
            normalized_id = self._normalize_model_id(model_id)

            model_info = litellm.model_cost.get(normalized_id, {})
            if not model_info:
                model_info = litellm.model_cost.get(model_id, {})

            return model_info.get("supports_reasoning", False)

        except ImportError:
            return False
        except Exception:
            return False

    def list_models(self) -> list:
        """List all models known to LiteLLM.

        Returns:
            List of model IDs
        """
        try:
            litellm = self._get_litellm()
            return list(litellm.model_cost.keys())
        except ImportError:
            return []
        except Exception:
            return []
