"""Tier Selection Algorithm for Model Intelligence (ADR-026 Phase 1).

This module provides tier-specific model selection with:
- Weighted scoring based on tier requirements
- Anti-herding penalties to prevent over-concentration
- Provider diversity enforcement
- Fallback to static configuration

Example usage:
    from llm_council.metadata.selection import select_tier_models

    # Select 4 models for high-confidence tier
    models = select_tier_models(tier="high")

    # Select with specific count and context requirement
    models = select_tier_models(
        tier="reasoning",
        count=3,
        required_context=32000
    )
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from ..config import TIER_MODEL_POOLS


# Tier-specific weight matrices for model scoring
# Each tier prioritizes different attributes based on use case
TIER_WEIGHTS: Dict[str, Dict[str, float]] = {
    "quick": {
        "latency": 0.45,      # Speed is primary concern
        "cost": 0.25,         # Cost-efficiency important
        "quality": 0.15,      # Acceptable quality
        "availability": 0.10, # Must be available
        "diversity": 0.05,    # Nice to have
    },
    "balanced": {
        "quality": 0.30,      # Good quality
        "latency": 0.25,      # Reasonable speed
        "cost": 0.20,         # Cost-conscious
        "availability": 0.15, # Reliable
        "diversity": 0.10,    # Variety helps
    },
    "high": {
        "quality": 0.50,      # Quality is paramount
        "availability": 0.20, # Must be reliable
        "latency": 0.15,      # Speed secondary
        "diversity": 0.10,    # Want different perspectives
        "cost": 0.05,         # Cost less important
    },
    "reasoning": {
        "quality": 0.60,      # Best possible quality
        "availability": 0.20, # Must be available
        "diversity": 0.10,    # Different reasoning styles
        "latency": 0.05,      # Speed not critical
        "cost": 0.05,         # Cost not a concern
    },
}

# Anti-herding configuration
ANTI_HERDING_THRESHOLD = 0.30  # 30% traffic threshold
ANTI_HERDING_MAX_PENALTY = 0.35  # 35% max score reduction


@dataclass
class ModelCandidate:
    """Candidate model with scoring attributes.

    Attributes:
        model_id: Full model identifier (e.g., 'openai/gpt-4o')
        latency_score: 0-1 score for response latency (higher = faster)
        cost_score: 0-1 score for cost efficiency (higher = cheaper)
        quality_score: 0-1 score for output quality (higher = better)
        availability_score: 0-1 score for uptime/reliability
        diversity_score: 0-1 score for diversity contribution
        recent_traffic: Recent traffic share (0-1) for anti-herding
    """
    model_id: str
    latency_score: float
    cost_score: float
    quality_score: float
    availability_score: float
    diversity_score: float
    recent_traffic: float = 0.0


def apply_anti_herding_penalty(score: float, traffic: float) -> float:
    """Apply anti-herding penalty to model score.

    Models with > 30% recent traffic receive a proportional penalty
    to encourage diversity and prevent over-concentration on popular models.

    Args:
        score: Original model score (0-1)
        traffic: Recent traffic share (0-1)

    Returns:
        Adjusted score with anti-herding penalty applied
    """
    if traffic <= ANTI_HERDING_THRESHOLD:
        return score

    # Calculate penalty: linear increase from 0 at 30% to max at 100%
    # excess = traffic - 0.3, max excess = 0.7
    excess = traffic - ANTI_HERDING_THRESHOLD
    max_excess = 1.0 - ANTI_HERDING_THRESHOLD

    # Penalty scales linearly with excess traffic
    penalty_rate = excess / max_excess
    penalty = ANTI_HERDING_MAX_PENALTY * penalty_rate

    return score * (1 - penalty)


def calculate_model_score(candidate: ModelCandidate, tier: str) -> float:
    """Calculate weighted score for a model based on tier weights.

    Args:
        candidate: ModelCandidate with attribute scores
        tier: Tier name (quick, balanced, high, reasoning)

    Returns:
        Weighted score (0-1)
    """
    weights = TIER_WEIGHTS.get(tier, TIER_WEIGHTS["balanced"])

    score = (
        weights["latency"] * candidate.latency_score +
        weights["cost"] * candidate.cost_score +
        weights["quality"] * candidate.quality_score +
        weights["availability"] * candidate.availability_score +
        weights["diversity"] * candidate.diversity_score
    )

    # Apply anti-herding penalty
    return apply_anti_herding_penalty(score, candidate.recent_traffic)


def select_with_diversity(
    scored: List[Tuple[str, float]],
    count: int = 4,
    min_providers: int = 2,
) -> List[str]:
    """Select models with provider diversity enforcement.

    Selects top-scored models while ensuring representation from
    multiple providers when possible.

    Args:
        scored: List of (model_id, score) tuples, sorted by score descending
        count: Number of models to select
        min_providers: Minimum number of distinct providers desired

    Returns:
        List of selected model IDs
    """
    if not scored:
        return []

    if len(scored) <= count:
        return [model_id for model_id, _ in scored]

    # Sort by score descending
    sorted_models = sorted(scored, key=lambda x: x[1], reverse=True)

    selected: List[str] = []
    providers_selected: Set[str] = set()

    # First pass: select top models while tracking providers
    for model_id, score in sorted_models:
        if len(selected) >= count:
            break

        provider = model_id.split("/")[0] if "/" in model_id else model_id
        providers_selected.add(provider)
        selected.append(model_id)

    # Check if we need to enforce diversity
    if len(providers_selected) < min_providers and len(selected) >= count:
        # Try to swap in models from underrepresented providers
        remaining_models = [
            (m, s) for m, s in sorted_models
            if m not in selected
        ]

        for model_id, score in remaining_models:
            provider = model_id.split("/")[0] if "/" in model_id else model_id

            if provider not in providers_selected:
                # Swap out lowest scored model for this one
                selected[-1] = model_id
                providers_selected.add(provider)

                if len(providers_selected) >= min_providers:
                    break

    return selected


def select_tier_models(
    tier: str,
    task_domain: Optional[str] = None,
    count: int = 4,
    required_context: Optional[int] = None,
) -> List[str]:
    """Select optimal models for a tier using weighted scoring.

    This is the main entry point for tier-specific model selection.
    When model intelligence is enabled, this uses dynamic scoring.
    Otherwise, falls back to static TIER_MODEL_POOLS.

    Args:
        tier: Tier name (quick, balanced, high, reasoning)
        task_domain: Optional domain hint (coding, creative, etc.)
        count: Number of models to select
        required_context: Minimum context window required

    Returns:
        List of model IDs selected for this tier
    """
    # Get static pool as baseline/fallback
    static_pool = TIER_MODEL_POOLS.get(tier, TIER_MODEL_POOLS.get("high", []))

    # For now, create candidates from static pool with default scores
    # Future: populate from DynamicMetadataProvider cache
    candidates = _create_candidates_from_pool(static_pool, tier)

    if not candidates:
        # Fallback to static pool directly
        return static_pool[:count]

    # Filter by context window if required
    if required_context:
        candidates = [c for c in candidates if _meets_context_requirement(c, required_context)]

    if not candidates:
        # Fallback if no candidates meet requirements
        return static_pool[:count]

    # Score and sort candidates
    scored: List[Tuple[str, float]] = []
    for candidate in candidates:
        score = calculate_model_score(candidate, tier)
        scored.append((candidate.model_id, score))

    # Select with diversity enforcement
    return select_with_diversity(scored, count=count, min_providers=2)


def _create_candidates_from_pool(pool: List[str], tier: str) -> List[ModelCandidate]:
    """Create ModelCandidates from a static pool with estimated scores.

    For static pools, we estimate scores based on tier and model characteristics.
    Future: This will be populated from actual metadata.

    Args:
        pool: List of model IDs
        tier: Tier name for score estimation

    Returns:
        List of ModelCandidate objects
    """
    candidates = []

    for model_id in pool:
        # Estimate scores based on model ID patterns
        # Future: Use actual metadata from DynamicMetadataProvider
        candidate = ModelCandidate(
            model_id=model_id,
            latency_score=_estimate_latency_score(model_id),
            cost_score=_estimate_cost_score(model_id),
            quality_score=_estimate_quality_score(model_id, tier),
            availability_score=0.95,  # Assume high availability for static pool
            diversity_score=0.5,      # Neutral diversity
            recent_traffic=0.0,       # No traffic data for static
        )
        candidates.append(candidate)

    return candidates


def _estimate_latency_score(model_id: str) -> float:
    """Estimate latency score from model ID patterns."""
    model_lower = model_id.lower()

    # Fast models
    if any(x in model_lower for x in ["mini", "flash", "haiku", "small"]):
        return 0.95

    # Medium speed
    if any(x in model_lower for x in ["sonnet", "4o", "pro"]):
        return 0.75

    # Slower models (larger, reasoning)
    if any(x in model_lower for x in ["opus", "o1", "o3", "deepseek-r1"]):
        return 0.45

    return 0.70  # Default


def _estimate_cost_score(model_id: str) -> float:
    """Estimate cost score from model ID patterns."""
    model_lower = model_id.lower()

    # Cheap models
    if any(x in model_lower for x in ["mini", "flash", "haiku", "small"]):
        return 0.95

    # Medium cost
    if any(x in model_lower for x in ["sonnet", "4o", "pro"]):
        return 0.65

    # Expensive models
    if any(x in model_lower for x in ["opus", "o1", "o3"]):
        return 0.30

    return 0.60  # Default


def _estimate_quality_score(model_id: str, tier: str) -> float:
    """Estimate quality score from model ID patterns and tier."""
    model_lower = model_id.lower()

    # Top-tier models
    if any(x in model_lower for x in ["opus", "o1", "o3", "gpt-4", "claude-3"]):
        return 0.95

    # Good quality models
    if any(x in model_lower for x in ["sonnet", "pro", "deepseek"]):
        return 0.85

    # Reasonable quality
    if any(x in model_lower for x in ["4o", "gemini"]):
        return 0.80

    # Fast but lower quality
    if any(x in model_lower for x in ["mini", "flash", "haiku"]):
        return 0.65

    return 0.70  # Default


def _meets_context_requirement(candidate: ModelCandidate, required: int) -> bool:
    """Check if a candidate meets context window requirement.

    Future: Use actual context window from metadata.
    For now, assume all models meet reasonable requirements.
    """
    # TODO: Get actual context window from metadata provider
    return True


__all__ = [
    "TIER_WEIGHTS",
    "ModelCandidate",
    "apply_anti_herding_penalty",
    "calculate_model_score",
    "select_with_diversity",
    "select_tier_models",
]
