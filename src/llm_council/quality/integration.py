"""
ADR-036: Quality Metrics Integration

Integrates quality metrics calculation into the council pipeline.

Note: Phase 1 (OSS Tier) uses synchronous Jaccard-based calculations exclusively.
The async embedding-based functions in deliberation.py and attribution.py are
preserved for Tier 2/3 implementation (future phases) which will support
configurable embedding providers for higher-quality semantic similarity.
"""

import os
from typing import Dict, List, Tuple, Optional, Any
import logging

from .types import QualityMetrics, CoreMetrics, SynthesisAttribution
from .consensus import consensus_strength_score, get_consensus_interpretation
from .deliberation import deliberation_depth_index_sync
from .attribution import synthesis_attribution_score_sync

logger = logging.getLogger(__name__)


def _quality_metrics_enabled() -> bool:
    """Check if quality metrics are enabled via config/env."""
    # Environment variable takes precedence
    env_val = os.environ.get("LLM_COUNCIL_QUALITY_METRICS", "").lower()
    if env_val in ("false", "0", "no", "off"):
        return False
    if env_val in ("true", "1", "yes", "on"):
        return True

    # Try to get from unified config
    try:
        from ..unified_config import get_config

        config = get_config()
        if hasattr(config, "quality") and hasattr(config.quality, "enabled"):
            return config.quality.enabled
    except Exception:
        pass

    # Default: enabled
    return True


def _get_quality_tier() -> str:
    """Get the quality metrics tier (core, standard, enterprise)."""
    # Environment variable takes precedence
    env_val = os.environ.get("LLM_COUNCIL_QUALITY_TIER", "").lower()
    if env_val in ("core", "standard", "enterprise"):
        return env_val

    # Try to get from unified config
    try:
        from ..unified_config import get_config

        config = get_config()
        if hasattr(config, "quality") and hasattr(config.quality, "tier"):
            return config.quality.tier
    except Exception:
        pass

    # Default: core (OSS tier)
    return "core"


def _extract_response_content(stage1_responses: Dict[str, Any]) -> List[str]:
    """Extract text content from Stage 1 responses."""
    contents = []
    for model_id, response in stage1_responses.items():
        if isinstance(response, dict):
            content = response.get("content", "")
        elif isinstance(response, str):
            content = response
        else:
            content = str(response) if response else ""
        if content:
            contents.append(content)
    return contents


def _get_winning_responses(
    stage1_responses: Dict[str, Any],
    aggregate_rankings: List[Tuple[str, float]],
    top_n: int = 2,
) -> List[str]:
    """Get the top N ranked responses."""
    if not aggregate_rankings:
        return []

    winners = []
    for model_id, _ in aggregate_rankings[:top_n]:
        if model_id in stage1_responses:
            response = stage1_responses[model_id]
            if isinstance(response, dict):
                content = response.get("content", "")
            else:
                content = str(response) if response else ""
            if content:
                winners.append(content)

    return winners


def _extract_synthesis_content(stage3_response: Any) -> str:
    """Extract text content from Stage 3 synthesis."""
    if isinstance(stage3_response, dict):
        return stage3_response.get("content", "")
    elif isinstance(stage3_response, str):
        return stage3_response
    else:
        return str(stage3_response) if stage3_response else ""


def calculate_quality_metrics(
    stage1_responses: Dict[str, Any],
    stage2_rankings: List[dict],
    stage3_synthesis: Any,
    aggregate_rankings: List[Tuple[str, float]],
    label_to_model: Optional[Dict[str, Any]] = None,
) -> QualityMetrics:
    """
    Calculate quality metrics for a council session.

    This is the main integration point called by council.py after all stages complete.

    Args:
        stage1_responses: Dict of model_id -> response from Stage 1.
        stage2_rankings: List of Stage 2 ranking results.
        stage3_synthesis: Stage 3 synthesis response.
        aggregate_rankings: Aggregated rankings as (model_id, avg_position) tuples.
        label_to_model: Optional label-to-model mapping for additional analysis.

    Returns:
        QualityMetrics containing all calculated metrics for the current tier.
    """
    tier = _get_quality_tier()
    warnings: List[str] = []

    # Extract content from responses
    response_contents = _extract_response_content(stage1_responses)
    synthesis_content = _extract_synthesis_content(stage3_synthesis)
    winning_contents = _get_winning_responses(stage1_responses, aggregate_rankings, top_n=2)

    # Calculate Consensus Strength Score
    css = consensus_strength_score(aggregate_rankings, stage2_rankings)
    css_interpretation = get_consensus_interpretation(css)

    if css < 0.5:
        warnings.append("low_consensus")

    # Calculate Deliberation Depth Index
    ddi, ddi_components = deliberation_depth_index_sync(
        stage1_responses=response_contents,
        stage2_rankings=stage2_rankings,
    )

    if ddi < 0.4:
        warnings.append("shallow_deliberation")

    # Calculate Synthesis Attribution Score
    sas = synthesis_attribution_score_sync(
        synthesis=synthesis_content,
        winning_responses=winning_contents,
        all_responses=response_contents,
    )

    if sas.hallucination_risk > 0.4:
        warnings.append("hallucination_risk")

    if not sas.grounded:
        warnings.append("synthesis_not_grounded")

    # Build core metrics
    core = CoreMetrics(
        consensus_strength=css,
        deliberation_depth=ddi,
        synthesis_attribution=sas,
    )

    # Build full quality metrics
    quality_metrics = QualityMetrics(
        tier=tier,
        core=core,
        warnings=warnings,
    )

    return quality_metrics


def should_include_quality_metrics() -> bool:
    """Check if quality metrics should be included in response."""
    return _quality_metrics_enabled()
