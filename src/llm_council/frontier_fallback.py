"""Frontier Hard Fallback mechanism (ADR-027).

This module provides automatic fallback from frontier tier to high tier
when frontier models fail due to timeout, rate limits, or API errors.

Implements Issue #114.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, Optional

# ADR-032: Migrated to unified_config
from .unified_config import get_config
from .openrouter import query_model


def get_tier_models(tier: str) -> list:
    """Get models for a tier from unified config."""
    config = get_config()
    return config.tiers.pools.get(tier, [])


if TYPE_CHECKING:
    from .tier_contract import TierContract

# Configure logging
logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_FALLBACK_TIER: str = "high"
DEFAULT_FRONTIER_TIMEOUT: int = 300  # 5 minutes for frontier models


def emit_fallback_event(
    frontier_model: str,
    fallback_model: str,
    reason: str,
) -> None:
    """Emit FRONTIER_FALLBACK_TRIGGERED event for observability.

    Per ADR-027, fallback events are logged for monitoring and debugging
    of frontier model reliability.

    Args:
        frontier_model: The frontier model that failed
        fallback_model: The model used as fallback
        reason: Reason for fallback (timeout, rate_limit, api_error)
    """
    from .layer_contracts import LayerEventType, emit_layer_event

    emit_layer_event(
        LayerEventType.FRONTIER_FALLBACK_TRIGGERED,
        {
            "model_id": frontier_model,
            "fallback_model": fallback_model,
            "reason": reason,
        },
    )


def should_use_fallback_wrapper(tier_contract: Optional["TierContract"]) -> bool:
    """Determine if fallback wrapper should be used for this tier.

    Per ADR-027, fallback wrapping is only applied to the frontier tier
    to avoid overhead for stable tiers.

    Args:
        tier_contract: Optional tier contract specifying the tier.

    Returns:
        True if fallback wrapper should be used, False otherwise.
    """
    if tier_contract is None:
        return False
    return tier_contract.tier == "frontier"


def get_fallback_tier_from_config() -> str:
    """Get the fallback tier from configuration.

    Reads from unified config if available, otherwise returns default.

    Returns:
        The fallback tier name (default: "high")
    """
    try:
        from .unified_config import get_config

        config = get_config()
        # Check if frontier tier config has a fallback tier specified
        frontier_config = config.tiers.pools.get("frontier", {})
        if hasattr(frontier_config, "fallback_tier"):
            return frontier_config.fallback_tier
    except Exception:
        pass

    return DEFAULT_FALLBACK_TIER


class RateLimitError(Exception):
    """Raised when API rate limit is exceeded."""

    pass


class APIError(Exception):
    """Raised when API returns an error."""

    pass


@dataclass
class FallbackResult:
    """Result from execute_with_fallback including fallback metadata.

    Attributes:
        response: The model response dict
        used_fallback: Whether fallback was triggered
        original_error: Error message if fallback was used
        fallback_model: Model used for fallback if applicable
    """

    response: Dict[str, Any]
    used_fallback: bool
    original_error: Optional[str]
    fallback_model: Optional[str]


async def execute_with_fallback(
    query: str,
    frontier_model: str,
    fallback_tier: str = DEFAULT_FALLBACK_TIER,
    timeout: int = DEFAULT_FRONTIER_TIMEOUT,
) -> Dict[str, Any]:
    """Execute frontier model with automatic fallback.

    Attempts to query the frontier model first. If it fails due to
    timeout, rate limiting, or API error, automatically falls back
    to the first available model in the fallback tier.

    Args:
        query: The query to send to the model
        frontier_model: The frontier model to try first
        fallback_tier: Tier to fall back to on failure (default: "high")
        timeout: Timeout in seconds for frontier model (default: 300)

    Returns:
        Model response dict with 'content' key
    """
    try:
        response = await query_model(frontier_model, query, timeout=timeout)
        return response

    except (asyncio.TimeoutError, RateLimitError, APIError) as e:
        error_msg = str(e)
        logger.warning(
            f"Frontier model {frontier_model} failed: {error_msg}. "
            f"Falling back to {fallback_tier}"
        )

        # Get fallback models from tier
        fallback_models = get_tier_models(fallback_tier)

        if not fallback_models:
            logger.error(f"No models available in fallback tier {fallback_tier}")
            raise

        # Use first available fallback model
        fallback_model = fallback_models[0]
        return await query_model(fallback_model, query)


async def execute_with_fallback_detailed(
    query: str,
    frontier_model: str,
    fallback_tier: str = DEFAULT_FALLBACK_TIER,
    timeout: int = DEFAULT_FRONTIER_TIMEOUT,
) -> FallbackResult:
    """Execute frontier model with detailed fallback result.

    Same as execute_with_fallback but returns FallbackResult with metadata
    about whether fallback was used.

    Args:
        query: The query to send to the model
        frontier_model: The frontier model to try first
        fallback_tier: Tier to fall back to on failure (default: "high")
        timeout: Timeout in seconds for frontier model (default: 300)

    Returns:
        FallbackResult with response and fallback metadata
    """
    try:
        response = await query_model(frontier_model, query, timeout=timeout)
        return FallbackResult(
            response=response,
            used_fallback=False,
            original_error=None,
            fallback_model=None,
        )

    except (asyncio.TimeoutError, RateLimitError, APIError) as e:
        error_msg = str(e)

        # Determine reason type for event emission
        if isinstance(e, asyncio.TimeoutError):
            reason = "timeout"
        elif isinstance(e, RateLimitError):
            reason = "rate_limit"
        else:
            reason = "api_error"

        logger.warning(
            f"Frontier model {frontier_model} failed: {error_msg}. "
            f"Falling back to {fallback_tier}"
        )

        # Get fallback models from tier
        fallback_models = get_tier_models(fallback_tier)

        if not fallback_models:
            logger.error(f"No models available in fallback tier {fallback_tier}")
            raise

        # Use first available fallback model
        fallback_model = fallback_models[0]
        response = await query_model(fallback_model, query)

        # ADR-027: Emit fallback event for observability
        emit_fallback_event(frontier_model, fallback_model, reason)

        return FallbackResult(
            response=response,
            used_fallback=True,
            original_error=error_msg,
            fallback_model=fallback_model,
        )
