"""Constructive Dissent extraction from Stage 2 evaluations (ADR-025b).

This module implements Option B from the council validation:
Extract dissenting points from Stage 2 peer review evaluations.

The algorithm:
1. Collect scores from all reviewers for each response
2. Calculate median and standard deviation for each response
3. Identify outlier reviewers (score < median - threshold * std)
4. Extract evaluation text from outliers
5. Format as minority perspective

Reference: ADR-025b Council Validation (2025-12-23)
Council Consensus: Option B - Extract from Stage 2 (minimal effort, data exists)
"""

import logging
from dataclasses import dataclass
from statistics import median as calc_median, stdev
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def calculate_score_statistics(scores: List[float]) -> Tuple[float, float]:
    """Calculate median and standard deviation for a list of scores.

    Args:
        scores: List of numeric scores

    Returns:
        Tuple of (median, standard_deviation)
    """
    if not scores:
        return 0.0, 0.0

    if len(scores) == 1:
        return float(scores[0]), 0.0

    med = calc_median(scores)

    # Calculate population standard deviation
    if len(scores) < 2:
        std = 0.0
    else:
        try:
            std = stdev(scores)
        except Exception:
            std = 0.0

    return float(med), float(std)


def identify_outlier_reviewers(
    reviewer_scores: Dict[str, Dict[str, float]],
    threshold: float = 1.5,
) -> List[str]:
    """Identify reviewers whose scores are outliers.

    A reviewer is an outlier if they give a score significantly below
    the median for any response (score < median - threshold * std).

    Args:
        reviewer_scores: Dict mapping reviewer -> {response_label: score}
        threshold: Number of standard deviations below median to flag

    Returns:
        List of outlier reviewer model names
    """
    if not reviewer_scores:
        return []

    # Collect all scores per response
    response_scores: Dict[str, List[float]] = {}
    for reviewer, scores in reviewer_scores.items():
        for response, score in scores.items():
            if response not in response_scores:
                response_scores[response] = []
            response_scores[response].append(score)

    # Calculate statistics per response
    response_stats: Dict[str, Tuple[float, float]] = {}
    for response, scores in response_scores.items():
        response_stats[response] = calculate_score_statistics(scores)

    # Find outliers
    outliers = set()
    for reviewer, scores in reviewer_scores.items():
        for response, score in scores.items():
            if response not in response_stats:
                continue
            median, std = response_stats[response]
            if std > 0:
                # Check if score is significantly below median
                if score < median - threshold * std:
                    outliers.add(reviewer)

    return list(outliers)


@dataclass
class OutlierInfo:
    """Information about an outlier reviewer."""

    reviewer: str
    disagreement: str  # Which response they disagreed on
    evaluation: str  # Their evaluation text
    score_given: float
    median_score: float


def extract_outlier_info(
    stage2_results: List[Dict[str, Any]],
    threshold: float = 1.5,
) -> List[OutlierInfo]:
    """Extract detailed information about outlier reviewers.

    Args:
        stage2_results: Stage 2 results with parsed rankings
        threshold: Outlier threshold (std deviations below median)

    Returns:
        List of OutlierInfo for each outlier found
    """
    if not stage2_results:
        return []

    # Build reviewer scores dict
    reviewer_scores: Dict[str, Dict[str, float]] = {}
    reviewer_evaluations: Dict[str, str] = {}

    for result in stage2_results:
        model = result.get("model", "unknown")
        parsed = result.get("parsed_ranking", {})
        scores = parsed.get("scores", {})

        if scores:
            reviewer_scores[model] = scores
            reviewer_evaluations[model] = parsed.get("evaluation", "")

    if not reviewer_scores:
        return []

    # Collect all scores per response
    response_scores: Dict[str, List[float]] = {}
    for reviewer, scores in reviewer_scores.items():
        for response, score in scores.items():
            if response not in response_scores:
                response_scores[response] = []
            response_scores[response].append(score)

    # Calculate statistics per response
    response_stats: Dict[str, Tuple[float, float]] = {}
    for response, scores in response_scores.items():
        response_stats[response] = calculate_score_statistics(scores)

    # Find outliers and extract info
    outliers: List[OutlierInfo] = []
    for reviewer, scores in reviewer_scores.items():
        for response, score in scores.items():
            if response not in response_stats:
                continue
            median, std = response_stats[response]
            if std > 0 and score < median - threshold * std:
                outliers.append(
                    OutlierInfo(
                        reviewer=reviewer,
                        disagreement=response,
                        evaluation=reviewer_evaluations.get(reviewer, ""),
                        score_given=score,
                        median_score=median,
                    )
                )

    return outliers


def format_dissent_message(outliers: List[OutlierInfo]) -> str:
    """Format outlier information into a dissent message.

    Args:
        outliers: List of OutlierInfo or dicts with outlier data

    Returns:
        Formatted dissent message string
    """
    if not outliers:
        return ""

    # Handle both OutlierInfo objects and dicts
    points = []
    for outlier in outliers:
        if isinstance(outlier, dict):
            reviewer = outlier.get("reviewer", "Unknown")
            evaluation = outlier.get("evaluation", "")
            score = outlier.get("score_given", 0)
            median = outlier.get("median_score", 0)
        else:
            reviewer = outlier.reviewer
            evaluation = outlier.evaluation
            score = outlier.score_given
            median = outlier.median_score

        if evaluation:
            points.append(f"{evaluation}")
        else:
            points.append(
                f"{reviewer} scored significantly lower (gave {score}, median was {median})"
            )

    if len(points) == 1:
        return f"Minority perspective: {points[0]}"
    else:
        concerns = "; ".join(points[:3])  # Limit to 3 points
        return f"Minority perspectives: {concerns}"


def extract_dissent_from_stage2(
    stage2_results: List[Dict[str, Any]],
    threshold: float = 1.5,
    min_borda_spread: float = 0.0,
) -> Optional[str]:
    """Extract constructive dissent from Stage 2 evaluations.

    This function identifies minority opinions by finding reviewers
    who scored responses significantly below the median, then
    extracts their evaluation text as dissenting points.

    Args:
        stage2_results: List of Stage 2 results with parsed_ranking
        threshold: Number of std deviations below median to flag as outlier
        min_borda_spread: Minimum Borda spread required to surface dissent

    Returns:
        Formatted dissent string, or None if no meaningful dissent found
    """
    if not stage2_results:
        return None

    # Check if any results have scores
    has_scores = any(result.get("parsed_ranking", {}).get("scores") for result in stage2_results)
    if not has_scores:
        return None

    # Extract outlier information
    outliers = extract_outlier_info(stage2_results, threshold=threshold)

    if not outliers:
        return None

    # Check Borda spread requirement if specified
    if min_borda_spread > 0:
        # Calculate rough spread from scores
        all_scores = []
        for result in stage2_results:
            scores = result.get("parsed_ranking", {}).get("scores", {})
            all_scores.extend(scores.values())

        if all_scores:
            spread = max(all_scores) - min(all_scores)
            if spread < min_borda_spread:
                logger.debug(
                    f"Dissent suppressed: Borda spread {spread:.2f} < "
                    f"minimum {min_borda_spread:.2f}"
                )
                return None

    # Format the dissent message
    message = format_dissent_message(outliers)

    if message:
        logger.info(f"Extracted dissent from {len(outliers)} outlier reviewer(s)")

    return message if message else None
