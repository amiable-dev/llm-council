"""
ADR-036: Consensus Strength Score (CSS)

Quantifies agreement among council members during Stage 2 peer review.
"""

import statistics
from typing import List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


def consensus_strength_score(
    aggregate_rankings: List[Tuple[str, float]],
    stage2_results: Optional[List[dict]] = None,
) -> float:
    """
    Calculate Consensus Strength Score from Stage 2 rankings.

    The CSS measures how strongly reviewers agree on the ranking. Key signals:
    - Clear separation between ranks = strong consensus (reviewers agree on ordering)
    - Ties in positions = weak consensus (reviewers disagree)
    - Winner clearly ahead of pack = strong consensus

    Args:
        aggregate_rankings: List of (model_id, avg_rank_position) tuples,
            sorted by rank position (lower is better).
        stage2_results: Optional raw Stage 2 results for additional analysis.

    Returns:
        Float in range [0.0, 1.0] where higher = stronger consensus.

    Interpretation:
        0.85-1.0: Strong consensus - high confidence in synthesis
        0.70-0.84: Moderate consensus - synthesis reliable, note minority views
        0.50-0.69: Weak consensus - consider include_dissent=true
        <0.50: Significant disagreement - recommend debate mode
    """
    if not aggregate_rankings:
        logger.warning("No rankings provided for CSS calculation, returning 0.0")
        return 0.0

    n = len(aggregate_rankings)
    if n == 1:
        # Single response = trivial consensus
        return 1.0

    # Extract positions (lower = better)
    positions = [pos for _, pos in aggregate_rankings]
    sorted_positions = sorted(positions)

    min_pos = min(positions)
    max_pos = max(positions)
    pos_range = max_pos - min_pos

    if pos_range == 0:
        # All tied - perfect consensus on equality
        return 1.0

    # Component 1: Winner Margin (40%)
    # How far ahead is #1 from #2? Normalized by max possible gap.
    # Max gap = n-1 (if #1 got 1.0 and #2 got n)
    winner_gap = sorted_positions[1] - sorted_positions[0]
    max_possible_gap = n - 1
    winner_margin = min(1.0, winner_gap / max_possible_gap)

    # Component 2: Ordering Clarity (40%)
    # How evenly spread are the positions? Uniform spread = clear ordering.
    # Compare to ideal uniform spread: 1, 2, 3, ..., n
    ideal_positions = list(range(1, n + 1))
    ideal_range = ideal_positions[-1] - ideal_positions[0]

    # Measure how close actual range is to ideal range
    actual_range = sorted_positions[-1] - sorted_positions[0]
    range_ratio = actual_range / ideal_range if ideal_range > 0 else 1.0

    # Measure average gap consistency (are gaps between ranks similar?)
    gaps = [sorted_positions[i + 1] - sorted_positions[i] for i in range(n - 1)]
    if gaps:
        avg_gap = sum(gaps) / len(gaps)
        gap_variance = sum((g - avg_gap) ** 2 for g in gaps) / len(gaps)
        ideal_gap = (n - 1) / (n - 1)  # = 1.0 for uniform spacing
        # Low gap variance = consistent ordering = high clarity
        gap_consistency = 1.0 / (1.0 + gap_variance)
    else:
        gap_consistency = 1.0

    ordering_clarity = range_ratio * 0.5 + gap_consistency * 0.5

    # Component 3: Non-Tie Factor (20%)
    # Penalize ties - if multiple models have same position, that's disagreement
    unique_positions = len(set(positions))
    non_tie_factor = unique_positions / n

    # CSS = weighted combination
    css = (winner_margin * 0.4) + (ordering_clarity * 0.4) + (non_tie_factor * 0.2)

    return round(min(1.0, max(0.0, css)), 3)


def get_consensus_interpretation(css: float) -> str:
    """Get human-readable interpretation of CSS value."""
    if css >= 0.85:
        return "strong_consensus"
    elif css >= 0.70:
        return "moderate_consensus"
    elif css >= 0.50:
        return "weak_consensus"
    else:
        return "significant_disagreement"
