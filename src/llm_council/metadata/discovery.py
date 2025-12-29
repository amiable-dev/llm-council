"""Request-Time Discovery for ADR-028.

This module implements request-time filtering of candidates from the cached
registry. It runs in the Data Plane with zero external API calls.

Key components:
- discover_tier_candidates(): Main entry point for tier-based discovery
- _model_qualifies_for_tier(): Tier-specific qualification logic
- _merge_deduplicate(): Merge dynamic and static candidates
- KNOWN_REASONING_FAMILIES: Set of model families with reasoning capability

Example:
    >>> from llm_council.metadata.discovery import discover_tier_candidates
    >>> from llm_council.metadata.registry import get_registry
    >>>
    >>> registry = get_registry()
    >>> candidates = discover_tier_candidates("high", registry, required_context=100000)
"""

import logging
from typing import TYPE_CHECKING, List, Optional, Set

from .types import ModelInfo, QualityTier

if TYPE_CHECKING:
    from .registry import ModelRegistry
    from .selection import ModelCandidate

logger = logging.getLogger(__name__)


def emit_discovery_fallback(
    tier: str,
    reason: str,
    dynamic_count: int,
    static_count: int,
) -> None:
    """Emit a DISCOVERY_FALLBACK_TRIGGERED event.

    Called when dynamic discovery falls back to static pools.

    Args:
        tier: Tier being selected for
        reason: Reason for fallback (e.g., "insufficient_candidates")
        dynamic_count: Number of candidates from dynamic discovery
        static_count: Number of candidates from static fallback
    """
    try:
        from ..layer_contracts import LayerEventType, emit_layer_event

        emit_layer_event(
            LayerEventType.DISCOVERY_FALLBACK_TRIGGERED,
            {
                "tier": tier,
                "reason": reason,
                "dynamic_count": dynamic_count,
                "static_count": static_count,
            },
        )
    except Exception as e:
        logger.debug(f"Failed to emit discovery fallback event: {e}")


# Minimum candidates before falling back to static
MIN_CANDIDATES_PER_TIER = 3

# Known reasoning model families (avoid brittle string matching)
# Per ADR-028, these families have strong reasoning capability
KNOWN_REASONING_FAMILIES: Set[str] = {
    "o1",
    "o3",
    "o1-mini",
    "o3-mini",
    "deepseek-r1",
    "deepseek-reasoner",
    "claude-3-opus",
}

# Cost thresholds per ADR-028
BALANCED_COST_CEILING = 0.03  # $0.03 per 1K tokens
QUICK_COST_THRESHOLD = 0.005  # $0.005 per 1K tokens


def _get_model_family(model_id: str) -> str:
    """Extract model family from model ID.

    Examples:
        openai/o1-preview -> o1
        anthropic/claude-3-opus -> claude-3-opus
        deepseek/deepseek-r1 -> deepseek-r1

    Args:
        model_id: Full model identifier

    Returns:
        Model family name
    """
    # Get the part after provider prefix
    if "/" in model_id:
        model_name = model_id.split("/", 1)[1]
    else:
        model_name = model_id

    # Check known families
    for family in KNOWN_REASONING_FAMILIES:
        if model_name.startswith(family):
            return family

    # Default: use base model name (before version suffixes)
    return model_name.split("-")[0] if "-" in model_name else model_name


def _get_total_cost(info: ModelInfo) -> float:
    """Get total cost per 1K tokens (prompt + completion average).

    Args:
        info: ModelInfo with pricing

    Returns:
        Average cost per 1K tokens
    """
    prompt_cost = info.pricing.get("prompt", 0.0)
    completion_cost = info.pricing.get("completion", 0.0)
    # Use average or max for cost comparison
    return (prompt_cost + completion_cost) / 2


def _model_qualifies_for_tier(
    info: ModelInfo,
    tier: str,
    required_context: Optional[int],
) -> bool:
    """Check if model meets tier requirements.

    Per ADR-028, each tier has specific constraints:
    - frontier: FRONTIER quality tier
    - reasoning: supports_reasoning OR known reasoning family
    - high: FRONTIER/STANDARD quality, no preview
    - balanced: FRONTIER/STANDARD quality, cost < $0.03
    - quick: latency < 1500ms OR cost < $0.005

    Args:
        info: ModelInfo to check
        tier: Tier name (frontier, reasoning, high, balanced, quick)
        required_context: Optional minimum context window

    Returns:
        True if model qualifies for tier

    Raises:
        ValueError: If tier is unknown
    """
    # Universal Hard Constraints
    if required_context and info.context_window < required_context:
        return False

    # Tier-Specific Constraints
    if tier == "frontier":
        return info.quality_tier == QualityTier.FRONTIER

    elif tier == "reasoning":
        # Use capability flag or known family
        if info.supports_reasoning:
            return True
        model_family = _get_model_family(info.id)
        return model_family in KNOWN_REASONING_FAMILIES

    elif tier == "high":
        # FRONTIER or STANDARD, no preview
        if info.is_preview:
            return False
        return info.quality_tier in (QualityTier.FRONTIER, QualityTier.STANDARD)

    elif tier == "balanced":
        # Quality tier check + cost ceiling
        if info.quality_tier not in (QualityTier.FRONTIER, QualityTier.STANDARD):
            return False
        total_cost = _get_total_cost(info)
        return total_cost < BALANCED_COST_CEILING

    elif tier == "quick":
        # Must meet cost threshold (latency check requires runtime data)
        total_cost = _get_total_cost(info)
        return total_cost < QUICK_COST_THRESHOLD

    elif tier == "local":
        return info.quality_tier == QualityTier.LOCAL

    else:
        raise ValueError(f"Unknown tier: {tier}")


def _create_candidate_from_info(info: ModelInfo, tier: str) -> "ModelCandidate":
    """Create a ModelCandidate from ModelInfo.

    Args:
        info: ModelInfo to convert
        tier: Tier being selected for (affects scoring weights)

    Returns:
        ModelCandidate with estimated scores
    """
    from .selection import ModelCandidate, QUALITY_TIER_SCORES

    # Get quality score from tier
    quality_score = QUALITY_TIER_SCORES.get(info.quality_tier, 0.5)

    # Estimate cost score (inverse of cost, normalized)
    total_cost = _get_total_cost(info)
    if total_cost > 0:
        cost_score = min(1.0, 0.01 / total_cost)  # $0.01 = 1.0 score
    else:
        cost_score = 1.0  # Free = best score

    return ModelCandidate(
        model_id=info.id,
        latency_score=0.8,  # Estimated, will be refined with runtime data
        cost_score=cost_score,
        quality_score=quality_score,
        availability_score=1.0,  # Available since in registry
        diversity_score=0.5,  # Will be calculated during selection
        recent_traffic=0.1,  # Default low traffic
    )


def discover_tier_candidates(
    tier: str,
    registry: "ModelRegistry",
    required_context: Optional[int] = None,
) -> List["ModelCandidate"]:
    """Discover candidates for a tier from cached registry.

    This is the main entry point for request-time discovery.
    It reads from the cached registry (zero API calls) and
    filters by tier requirements.

    Args:
        tier: Tier name (frontier, reasoning, high, balanced, quick)
        registry: ModelRegistry with cached model data
        required_context: Optional minimum context window

    Returns:
        List of ModelCandidate meeting tier requirements
    """
    from .selection import ModelCandidate

    candidates: List[ModelCandidate] = []

    # 1. Filter from cached registry (O(n) in-memory, fast)
    all_models = registry.get_candidates()

    for info in all_models:
        if _model_qualifies_for_tier(info, tier, required_context):
            candidate = _create_candidate_from_info(info, tier)
            candidates.append(candidate)

    # 2. Static fallback (only if registry empty/insufficient)
    if len(candidates) < MIN_CANDIDATES_PER_TIER:
        logger.warning(
            f"Insufficient dynamic candidates for tier {tier}: "
            f"{len(candidates)} < {MIN_CANDIDATES_PER_TIER}. Using static fallback."
        )

        static = _get_static_fallback(tier)

        # Emit fallback event
        emit_discovery_fallback(
            tier=tier,
            reason="insufficient_candidates",
            dynamic_count=len(candidates),
            static_count=len(static),
        )

        candidates = _merge_deduplicate(dynamic=candidates, static=static)

    return candidates


def _get_static_fallback(tier: str) -> List["ModelCandidate"]:
    """Get static fallback candidates for a tier.

    Args:
        tier: Tier name

    Returns:
        List of ModelCandidate from static pool
    """
    from .selection import ModelCandidate

    try:
        from ..tier_contract import _get_tier_model_pools

        TIER_MODEL_POOLS = _get_tier_model_pools()
        pool = TIER_MODEL_POOLS.get(tier, [])
        candidates = []

        for model_id in pool:
            candidates.append(
                ModelCandidate(
                    model_id=model_id,
                    latency_score=0.7,
                    cost_score=0.7,
                    quality_score=0.7,
                    availability_score=0.9,
                    diversity_score=0.5,
                    recent_traffic=0.1,
                )
            )

        return candidates
    except ImportError:
        return []


def _merge_deduplicate(
    dynamic: List["ModelCandidate"],
    static: List["ModelCandidate"],
) -> List["ModelCandidate"]:
    """Merge candidates with dynamic taking precedence.

    Dynamic has fresher metadata/pricing, so it takes precedence
    when the same model appears in both lists.

    Args:
        dynamic: Candidates from dynamic discovery
        static: Candidates from static fallback

    Returns:
        Merged list with duplicates removed
    """
    seen = {c.model_id for c in dynamic}
    merged = list(dynamic)

    for candidate in static:
        if candidate.model_id not in seen:
            merged.append(candidate)
            seen.add(candidate.model_id)

    return merged
