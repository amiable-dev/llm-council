"""OpenRouter API Client for Model Metadata (ADR-026 Phase 1).

This module provides an async client for fetching model metadata from the
OpenRouter Models API. It supports:
- Fetching model list with metadata (context window, pricing, capabilities)
- Graceful error handling (timeouts, rate limits, connection errors)
- API key authentication (optional but recommended)
"""

import logging
import os
from typing import Any, Dict, List, Optional

import httpx

from .types import ModelInfo, QualityTier

logger = logging.getLogger(__name__)

# OpenRouter API endpoint
OPENROUTER_MODELS_ENDPOINT = "https://openrouter.ai/api/v1/models"

# Default timeout in seconds
DEFAULT_TIMEOUT = 30.0

# Pricing thresholds for quality tier assignment (per 1K tokens)
FRONTIER_THRESHOLD = 0.005  # > $0.005/1K = frontier
ECONOMY_THRESHOLD = 0.001  # < $0.001/1K = economy
# Between these = standard


class OpenRouterClient:
    """Async client for the OpenRouter Models API.

    Fetches model metadata including context windows, pricing, supported
    parameters, and modalities.

    Args:
        api_key: OpenRouter API key (optional, reads from OPENROUTER_API_KEY env)
        timeout: Request timeout in seconds (default 30)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        self.timeout = timeout

    async def fetch_models(self) -> List[ModelInfo]:
        """Fetch model metadata from OpenRouter API.

        Returns:
            List of ModelInfo objects, or empty list on error
        """
        headers = self._build_headers()

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    OPENROUTER_MODELS_ENDPOINT,
                    headers=headers,
                )
                response.raise_for_status()

                data = response.json()
                models = data.get("data", [])

                return [transform_api_model(m) for m in models]

        except httpx.TimeoutException:
            logger.warning("OpenRouter API request timed out")
            return []

        except httpx.ConnectError as e:
            logger.warning(f"OpenRouter API connection error: {e}")
            return []

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.warning("OpenRouter API rate limited")
            else:
                logger.warning(f"OpenRouter API error: {e.response.status_code}")
            return []

        except Exception as e:
            logger.error(f"Unexpected error fetching OpenRouter models: {e}")
            return []

    def _build_headers(self) -> Dict[str, str]:
        """Build request headers including API key if available."""
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers


def transform_api_model(api_model: Dict[str, Any]) -> ModelInfo:
    """Transform an OpenRouter API model response into a ModelInfo object.

    Args:
        api_model: Raw model data from OpenRouter API

    Returns:
        ModelInfo object with normalized fields
    """
    model_id = api_model.get("id", "unknown")
    context_window = api_model.get("context_length", 4096)

    # Extract and convert pricing (string to float)
    pricing_raw = api_model.get("pricing", {})
    pricing = {}
    if pricing_raw:
        for key in ["prompt", "completion"]:
            if key in pricing_raw:
                try:
                    pricing[key] = float(pricing_raw[key])
                except (ValueError, TypeError):
                    pass

    # Extract supported parameters
    supported_parameters = api_model.get("supported_parameters", [])

    # Extract and normalize modalities
    architecture = api_model.get("architecture", {})
    raw_modalities = architecture.get("input_modalities", ["text"])
    modalities = _normalize_modalities(raw_modalities)

    # Determine quality tier from pricing
    quality_tier = _determine_quality_tier(pricing)

    return ModelInfo(
        id=model_id,
        context_window=context_window,
        pricing=pricing,
        supported_parameters=supported_parameters,
        modalities=modalities,
        quality_tier=quality_tier,
    )


def _normalize_modalities(raw_modalities: List[str]) -> List[str]:
    """Normalize modality names (e.g., 'image' -> 'vision')."""
    normalized = []
    for modality in raw_modalities:
        if modality == "image":
            normalized.append("vision")
        else:
            normalized.append(modality)
    return normalized if normalized else ["text"]


def _determine_quality_tier(pricing: Dict[str, float]) -> QualityTier:
    """Determine quality tier based on pricing.

    Args:
        pricing: Dict with 'prompt' and/or 'completion' prices per 1K tokens

    Returns:
        QualityTier enum value
    """
    if not pricing:
        return QualityTier.STANDARD

    # Use prompt price as primary indicator
    prompt_price = pricing.get("prompt", 0.0)

    # Free models are LOCAL tier
    if prompt_price == 0.0 and pricing.get("completion", 0.0) == 0.0:
        return QualityTier.LOCAL

    # High-priced models are FRONTIER
    if prompt_price > FRONTIER_THRESHOLD:
        return QualityTier.FRONTIER

    # Low-priced models are ECONOMY
    if prompt_price < ECONOMY_THRESHOLD:
        return QualityTier.ECONOMY

    # Everything else is STANDARD
    return QualityTier.STANDARD
