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
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple

from ..tier_contract import _get_tier_model_pools
from .types import QualityTier

if TYPE_CHECKING:
    from .protocol import MetadataProvider


# Quality tier to numeric score mapping (ADR-026 Phase 1)
# Quality tier scores based on benchmark evidence (ADR-030)
# See QUALITY_TIER_BENCHMARK_SOURCES in scoring.py for citations
QUALITY_TIER_SCORES: Dict[QualityTier, float] = {
    QualityTier.FRONTIER: 0.95,  # MMLU 87-90%
    QualityTier.STANDARD: 0.85,  # MMLU 80-86% (+0.10 from 0.75)
    QualityTier.ECONOMY: 0.70,  # MMLU 70-79% (+0.15 from 0.55)
    QualityTier.LOCAL: 0.50,  # MMLU 55-80% (+0.10 from 0.40)
}

# Cost normalization reference points (per 1K tokens)
COST_REFERENCE_HIGH = 0.015  # Most expensive models (Claude Opus, o1)


# Tier-specific weight matrices for model scoring
# Each tier prioritizes different attributes based on use case
TIER_WEIGHTS: Dict[str, Dict[str, float]] = {
    "quick": {
        "latency": 0.45,  # Speed is primary concern
        "cost": 0.25,  # Cost-efficiency important
        "quality": 0.15,  # Acceptable quality
        "availability": 0.10,  # Must be available
        "diversity": 0.05,  # Nice to have
    },
    "balanced": {
        "quality": 0.30,  # Good quality
        "latency": 0.25,  # Reasonable speed
        "cost": 0.20,  # Cost-conscious
        "availability": 0.15,  # Reliable
        "diversity": 0.10,  # Variety helps
    },
    "high": {
        "quality": 0.50,  # Quality is paramount
        "availability": 0.20,  # Must be reliable
        "latency": 0.15,  # Speed secondary
        "diversity": 0.10,  # Want different perspectives
        "cost": 0.05,  # Cost less important
    },
    "reasoning": {
        "quality": 0.60,  # Best possible quality
        "availability": 0.20,  # Must be available
        "diversity": 0.10,  # Different reasoning styles
        "latency": 0.05,  # Speed not critical
        "cost": 0.05,  # Cost not a concern
    },
    # Frontier tier: cutting-edge/preview models, quality above all else
    "frontier": {
        "quality": 0.70,  # Absolute best quality
        "diversity": 0.15,  # Want variety of latest models
        "availability": 0.10,  # Accept some instability
        "latency": 0.03,  # Speed least important
        "cost": 0.02,  # Cost irrelevant for frontier
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
        weights["latency"] * candidate.latency_score
        + weights["cost"] * candidate.cost_score
        + weights["quality"] * candidate.quality_score
        + weights["availability"] * candidate.availability_score
        + weights["diversity"] * candidate.diversity_score
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
        remaining_models = [(m, s) for m, s in sorted_models if m not in selected]

        for model_id, score in remaining_models:
            provider = model_id.split("/")[0] if "/" in model_id else model_id

            if provider not in providers_selected:
                # Swap out lowest scored model for this one
                selected[-1] = model_id
                providers_selected.add(provider)

                if len(providers_selected) >= min_providers:
                    break

    return selected


def _is_discovery_enabled() -> bool:
    """Check if dynamic discovery is enabled via configuration.

    Returns:
        True if model_intelligence.discovery.enabled is True
    """
    try:
        from ..unified_config import get_config

        config = get_config()
        return config.model_intelligence.enabled and config.model_intelligence.discovery.enabled
    except Exception:
        return False


def _is_circuit_breaker_enabled() -> bool:
    """Check if circuit breaker is enabled via configuration or env var.

    Priority: Environment variable > YAML config > Default (True)

    Returns:
        True if circuit breaker is enabled
    """
    import os

    # Check environment variable first (highest priority)
    env_val = os.getenv("LLM_COUNCIL_CIRCUIT_BREAKER")
    if env_val is not None:
        return env_val.lower() in ("true", "1", "yes")

    # Check config
    try:
        from ..unified_config import get_config

        config = get_config()
        return config.model_intelligence.circuit_breaker.enabled
    except Exception:
        return True  # Default to enabled


def _is_circuit_breaker_open(model_id: str) -> bool:
    """Check if circuit breaker is open for a model.

    Args:
        model_id: Model identifier

    Returns:
        True if circuit is open (model should be excluded)
        False if circuit is closed or half-open (model can be used)
    """
    # Check if circuit breaker is disabled
    if not _is_circuit_breaker_enabled():
        return False

    try:
        from ..gateway.circuit_breaker_registry import check_circuit_breaker

        allowed, reason = check_circuit_breaker(model_id)
        return not allowed  # Return True if circuit is OPEN (not allowed)
    except ImportError:
        # Circuit breaker registry not available
        return False
    except Exception:
        # Any other error - fail open (allow the model)
        return False


def _get_min_candidates_per_tier() -> int:
    """Get minimum candidates per tier from configuration.

    Returns:
        Minimum candidates threshold (default: 3)
    """
    try:
        from ..unified_config import get_config

        config = get_config()
        return config.model_intelligence.discovery.min_candidates_per_tier
    except Exception:
        return 3


def _select_from_dynamic_discovery(
    tier: str,
    count: int,
    required_context: Optional[int],
    allow_preview: bool,
) -> Optional[List[str]]:
    """Try to select models using dynamic discovery from registry.

    Args:
        tier: Tier name
        count: Number of models to select
        required_context: Minimum context window required
        allow_preview: Whether to allow preview models

    Returns:
        List of model IDs if successful, None to fall back to static
    """
    import logging

    from .registry import get_registry
    from .discovery import discover_tier_candidates

    logger = logging.getLogger(__name__)
    registry = get_registry()

    # Check if registry is stale
    if registry.is_stale:
        logger.debug("Registry is stale, falling back to static selection")
        return None

    # Get candidates from registry
    candidates = discover_tier_candidates(tier, registry, required_context)

    # Check minimum candidates threshold
    min_candidates = _get_min_candidates_per_tier()
    if len(candidates) < min_candidates:
        logger.debug(
            f"Insufficient candidates ({len(candidates)} < {min_candidates}), "
            "falling back to static selection"
        )
        return None

    # Filter by preview status if needed (for tiers that exclude preview)
    if not allow_preview and tier not in ("frontier",):
        candidates = [c for c in candidates if not _is_preview_model(c.model_id)]

    if not candidates:
        return None

    # Score and sort candidates
    scored: List[Tuple[str, float]] = []
    for candidate in candidates:
        score = calculate_model_score(candidate, tier)
        scored.append((candidate.model_id, score))

    # Select with diversity enforcement
    return select_with_diversity(scored, count=count, min_providers=2)


def _is_preview_model(model_id: str) -> bool:
    """Check if model is a preview model based on ID.

    Args:
        model_id: Model identifier

    Returns:
        True if model appears to be a preview/beta
    """
    model_lower = model_id.lower()
    preview_indicators = ["preview", "beta", "experimental", "dev"]
    return any(indicator in model_lower for indicator in preview_indicators)


def select_tier_models(
    tier: str,
    task_domain: Optional[str] = None,
    count: int = 4,
    required_context: Optional[int] = None,
    allow_preview: bool = False,
) -> List[str]:
    """Select optimal models for a tier using weighted scoring.

    This is the main entry point for tier-specific model selection.
    When model intelligence is enabled with discovery, uses dynamic
    candidate selection from the cached registry. Otherwise, falls
    back to static tier model pools from tier_contract.

    Args:
        tier: Tier name (quick, balanced, high, reasoning, frontier)
        task_domain: Optional domain hint (coding, creative, etc.)
        count: Number of models to select
        required_context: Minimum context window required
        allow_preview: Whether to allow preview models (ADR-027)

    Returns:
        List of model IDs selected for this tier
    """
    # ADR-028: Try dynamic discovery first
    if _is_discovery_enabled():
        dynamic_result = _select_from_dynamic_discovery(
            tier, count, required_context, allow_preview
        )
        if dynamic_result:
            return dynamic_result

    # Get static pool as baseline/fallback
    tier_pools = _get_tier_model_pools()
    static_pool = tier_pools.get(tier, tier_pools.get("high", []))

    # Create candidates from static pool with estimated scores
    candidates = _create_candidates_from_pool(static_pool, tier)

    if not candidates:
        # Fallback to static pool directly
        return static_pool[:count]

    # Apply tier intersection filtering (ADR-027)
    candidates = _filter_by_tier_intersection(candidates, tier, allow_preview)

    if not candidates:
        # Fallback if no candidates meet tier requirements
        return static_pool[:count]

    # Filter by context window if required
    if required_context:
        candidates = [c for c in candidates if _meets_context_requirement(c, required_context)]

    if not candidates:
        # Fallback if no candidates meet requirements
        return static_pool[:count]

    # ADR-030: Filter out models with open circuit breakers
    candidates = [c for c in candidates if not _is_circuit_breaker_open(c.model_id)]

    if not candidates:
        # Fallback if all models have open circuits
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
            diversity_score=0.5,  # Neutral diversity
            recent_traffic=0.0,  # No traffic data for static
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


def _get_provider_safe() -> Optional["MetadataProvider"]:
    """Get metadata provider without crashing if unavailable.

    Returns the singleton MetadataProvider instance, or None if
    the provider cannot be imported or initialized.

    This provides graceful degradation for selection algorithms -
    if metadata is unavailable, callers can fall back to heuristics.

    Returns:
        MetadataProvider instance or None if unavailable
    """
    try:
        from . import get_provider

        return get_provider()
    except Exception:
        return None


def _get_quality_score_from_metadata(
    model_id: str,
    provider: Optional["MetadataProvider"],
) -> Optional[float]:
    """Get quality score from real QualityTier metadata.

    Converts QualityTier to a numeric score using QUALITY_TIER_SCORES.
    Returns None if provider is unavailable or model is unknown,
    allowing caller to fall back to heuristic estimation.

    Args:
        model_id: Full model identifier (e.g., 'openai/gpt-4o')
        provider: MetadataProvider instance or None

    Returns:
        Quality score (0-1) or None if metadata unavailable
    """
    if provider is None:
        return None

    info = provider.get_model_info(model_id)
    if info is None:
        return None

    return QUALITY_TIER_SCORES.get(info.quality_tier, 0.70)


def _get_cost_score_from_metadata(
    model_id: str,
    provider: Optional["MetadataProvider"],
) -> Optional[float]:
    """Get cost efficiency score from real pricing data.

    Normalizes pricing to a 0-1 score where higher = cheaper.
    Free models (price=0) get a score of 1.0.
    Uses configurable scoring algorithm (default: log_ratio per ADR-030).

    Args:
        model_id: Full model identifier
        provider: MetadataProvider instance or None

    Returns:
        Cost score (0-1) or None if pricing unavailable
    """
    if provider is None:
        return None

    pricing = provider.get_pricing(model_id)
    if not pricing:
        return None

    prompt_price = pricing.get("prompt", 0.0)

    # Use the new scoring module (ADR-030)
    from .scoring import get_cost_score_with_config

    return get_cost_score_with_config(prompt_price, COST_REFERENCE_HIGH)


def _meets_context_requirement(
    candidate: ModelCandidate,
    required: int,
    provider: Optional["MetadataProvider"] = None,
) -> bool:
    """Check if a candidate meets context window requirement.

    Uses real context window from metadata provider when available.
    Falls back to returning True (legacy behavior) when no provider.

    Args:
        candidate: ModelCandidate to check
        required: Minimum context window required (tokens)
        provider: Optional MetadataProvider (fetched if not provided)

    Returns:
        True if model meets requirement, False otherwise
    """
    if provider is None:
        provider = _get_provider_safe()

    if provider is not None:
        context_window = provider.get_context_window(candidate.model_id)
        return context_window >= required

    # Fallback: legacy behavior when no provider
    return True


def _filter_by_tier_intersection(
    candidates: List[ModelCandidate],
    tier: str,
    allow_preview: bool = False,
) -> List[ModelCandidate]:
    """Filter candidates using tier intersection logic (ADR-027).

    Uses resolve_tier_intersection() to determine if each candidate
    qualifies for the requested tier based on its ModelInfo.

    Args:
        candidates: List of ModelCandidates to filter
        tier: Requested tier (quick, balanced, high, reasoning, frontier)
        allow_preview: Whether to allow preview models

    Returns:
        Filtered list of ModelCandidates that qualify for the tier
    """
    from .intersection import resolve_tier_intersection
    from .types import ModelInfo, QualityTier

    provider = _get_provider_safe()
    filtered = []

    for candidate in candidates:
        # Get ModelInfo from provider
        model_info = None
        if provider is not None:
            model_info = provider.get_model_info(candidate.model_id)

        if model_info is None:
            # No metadata available - create synthetic ModelInfo from heuristics
            model_info = _create_synthetic_model_info(candidate.model_id)

        # Apply tier intersection filter
        if resolve_tier_intersection(tier, model_info, allow_preview=allow_preview):
            filtered.append(candidate)

    return filtered


def _create_synthetic_model_info(model_id: str) -> "ModelInfo":
    """Create synthetic ModelInfo from model ID heuristics.

    When no metadata provider is available, we create a best-guess
    ModelInfo based on common patterns in model naming.

    Args:
        model_id: Full model identifier (e.g., 'openai/gpt-4o')

    Returns:
        Synthetic ModelInfo with heuristic-based values
    """
    from .types import ModelInfo, QualityTier

    model_lower = model_id.lower()

    # Determine quality tier from model name
    quality_tier = QualityTier.STANDARD
    if any(x in model_lower for x in ["opus", "o1", "o3", "gpt-4", "claude-3-opus"]):
        quality_tier = QualityTier.FRONTIER
    elif any(x in model_lower for x in ["mini", "flash", "haiku"]):
        quality_tier = QualityTier.ECONOMY
    elif any(x in model_lower for x in ["ollama", "local"]):
        quality_tier = QualityTier.LOCAL

    # Detect preview/beta status
    is_preview = any(x in model_lower for x in ["preview", "beta", "exp", "experimental"])

    # Detect reasoning support
    supports_reasoning = any(x in model_lower for x in ["o1", "o3", "deepseek-r1", "r1"])

    return ModelInfo(
        id=model_id,
        context_window=128000,  # Default assumption
        quality_tier=quality_tier,
        is_preview=is_preview,
        supports_reasoning=supports_reasoning,
    )


__all__ = [
    # Constants
    "TIER_WEIGHTS",
    "QUALITY_TIER_SCORES",
    "COST_REFERENCE_HIGH",
    # Types
    "ModelCandidate",
    # Core functions
    "apply_anti_herding_penalty",
    "calculate_model_score",
    "select_with_diversity",
    "select_tier_models",
    # Metadata integration (ADR-026 Phase 1)
    "_get_provider_safe",
    "_get_quality_score_from_metadata",
    "_get_cost_score_from_metadata",
    "_meets_context_requirement",
]
