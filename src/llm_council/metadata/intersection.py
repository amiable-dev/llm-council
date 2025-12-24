"""Tier Intersection Logic for ADR-027 Frontier Tier.

This module handles models that belong to multiple conceptual tiers
(e.g., o1-preview is both "reasoning" and "frontier").

Key rules per ADR-027:
1. frontier tier: Accepts all capable models including previews
2. reasoning tier: Excludes preview models by default (require allow_preview=True)
3. high tier: Requires proven stable models (excludes previews)
4. balanced/quick: Standard tier logic based on quality tier

Precedence:
- If user requests "frontier", reasoning models ARE included
- If user requests "reasoning", preview models ARE excluded unless allow_preview=True
- "frontier" acts as an override flag that permits preview models
"""

from .types import ModelInfo, QualityTier


# Quality tier thresholds for each tier
# Maps tier name to (minimum_quality_tier, maximum_quality_tier)
TIER_QUALITY_REQUIREMENTS = {
    "frontier": {QualityTier.FRONTIER},
    "reasoning": {QualityTier.FRONTIER},  # Only top-tier for reasoning
    "high": {QualityTier.FRONTIER, QualityTier.STANDARD},
    "balanced": {QualityTier.FRONTIER, QualityTier.STANDARD, QualityTier.ECONOMY},
    "quick": {QualityTier.FRONTIER, QualityTier.STANDARD, QualityTier.ECONOMY},
    "local": {QualityTier.LOCAL},
}


def resolve_tier_intersection(
    requested_tier: str,
    model_info: ModelInfo,
    allow_preview: bool = False,
) -> bool:
    """Determine if model qualifies for requested tier.

    This function handles the intersection of tier requirements and model
    characteristics, especially for models that belong to multiple tiers
    (e.g., o1-preview is both reasoning-capable and frontier).

    Args:
        requested_tier: The tier being requested (quick, balanced, high, reasoning, frontier)
        model_info: ModelInfo with model characteristics
        allow_preview: Whether to allow preview models in non-frontier tiers

    Returns:
        True if model qualifies for the requested tier, False otherwise

    Examples:
        >>> # Frontier includes preview models
        >>> resolve_tier_intersection("frontier", preview_model)
        True

        >>> # Reasoning excludes previews by default
        >>> resolve_tier_intersection("reasoning", reasoning_preview, allow_preview=False)
        False

        >>> # Reasoning includes previews when explicitly allowed
        >>> resolve_tier_intersection("reasoning", reasoning_preview, allow_preview=True)
        True
    """
    # Handle unknown tiers - fail closed
    if requested_tier not in TIER_QUALITY_REQUIREMENTS:
        return False

    # Frontier tier: accepts all FRONTIER-quality models, including previews
    if requested_tier == "frontier":
        return model_info.quality_tier == QualityTier.FRONTIER

    # Reasoning tier: requires reasoning support, excludes preview by default
    if requested_tier == "reasoning":
        # Check preview status first
        if model_info.is_preview and not allow_preview:
            return False
        # Must have reasoning support
        return model_info.supports_reasoning

    # High tier: requires proven stable models (no previews)
    if requested_tier == "high":
        if model_info.is_preview:
            return False
        # Must be FRONTIER or STANDARD quality
        return model_info.quality_tier in {QualityTier.FRONTIER, QualityTier.STANDARD}

    # Balanced tier: standard and above
    if requested_tier == "balanced":
        if model_info.is_preview and not allow_preview:
            return False
        return model_info.quality_tier in {
            QualityTier.FRONTIER,
            QualityTier.STANDARD,
            QualityTier.ECONOMY,
        }

    # Quick tier: fast response priority, includes economy
    if requested_tier == "quick":
        if model_info.is_preview and not allow_preview:
            return False
        return model_info.quality_tier in {
            QualityTier.FRONTIER,
            QualityTier.STANDARD,
            QualityTier.ECONOMY,
        }

    # Local tier: only local models
    if requested_tier == "local":
        return model_info.quality_tier == QualityTier.LOCAL

    return False


__all__ = [
    "resolve_tier_intersection",
    "TIER_QUALITY_REQUIREMENTS",
]
