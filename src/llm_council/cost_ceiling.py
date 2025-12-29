"""Cost Ceiling Protection for frontier tier (ADR-027).

This module provides cost ceiling protection to prevent frontier models
from having runaway costs compared to high-tier models.

Implements Issue #113.
"""

from typing import Optional, Tuple

# Default cost multiplier for frontier tier (ADR-027)
# Frontier models can cost up to 5x the high-tier average
FRONTIER_COST_MULTIPLIER: float = 5.0

# Fallback ceiling when high tier avg is zero or unavailable
FALLBACK_COST_CEILING: float = 0.10  # $0.10 per 1K tokens


def apply_cost_ceiling(
    model_id: str,
    model_cost: float,
    tier: str,
    high_tier_avg_cost: float,
    multiplier: float = FRONTIER_COST_MULTIPLIER,
) -> Tuple[bool, Optional[str]]:
    """Check if model cost exceeds tier ceiling.

    For frontier tier, models can cost up to multiplier * high_tier_avg_cost.
    Non-frontier tiers bypass this check entirely.

    Args:
        model_id: The model identifier
        model_cost: The model's cost (per 1K tokens)
        tier: The tier the model is being used in
        high_tier_avg_cost: Average cost of high-tier models
        multiplier: Cost multiplier for ceiling (default 5.0)

    Returns:
        Tuple of (allowed, reason) where:
        - allowed: True if model cost is within ceiling
        - reason: Rejection reason if not allowed, None otherwise
    """
    # Non-frontier tiers bypass cost ceiling check
    if tier != "frontier":
        return (True, None)

    # Handle zero baseline gracefully
    if high_tier_avg_cost <= 0:
        ceiling = FALLBACK_COST_CEILING
    else:
        ceiling = high_tier_avg_cost * multiplier

    # Check if model cost exceeds ceiling
    if model_cost > ceiling:
        return (
            False,
            f"cost ${model_cost:.4f} exceeds ceiling ${ceiling:.4f}",
        )

    return (True, None)


def get_high_tier_avg_cost() -> float:
    """Get the average cost of high-tier models.

    This is used as the baseline for calculating the frontier tier
    cost ceiling.

    Returns:
        Average cost per 1K tokens for high-tier models
    """
    # TODO: Integrate with metadata provider to calculate real average
    # For now, use the reference cost from selection.py
    try:
        from .metadata.selection import COST_REFERENCE_HIGH

        return COST_REFERENCE_HIGH
    except ImportError:
        # Fallback to reasonable default
        return 0.015  # $0.015 per 1K tokens


def check_model_cost_ceiling(
    model_id: str,
    model_cost: float,
    tier: str,
    multiplier: float = FRONTIER_COST_MULTIPLIER,
) -> Tuple[bool, Optional[str]]:
    """Convenience function to check model cost ceiling.

    Automatically fetches the high-tier average cost.

    Args:
        model_id: The model identifier
        model_cost: The model's cost (per 1K tokens)
        tier: The tier the model is being used in
        multiplier: Cost multiplier for ceiling (default 5.0)

    Returns:
        Tuple of (allowed, reason)
    """
    high_tier_avg = get_high_tier_avg_cost()
    return apply_cost_ceiling(
        model_id=model_id,
        model_cost=model_cost,
        tier=tier,
        high_tier_avg_cost=high_tier_avg,
        multiplier=multiplier,
    )
