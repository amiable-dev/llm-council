"""GraduationCriteria for frontier → high tier promotion (ADR-027).

This module provides graduation criteria and evaluation logic to determine
when a frontier tier model is ready for promotion to the high tier.

Implements Issue #112.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class GraduationCriteria:
    """Criteria for promoting a model from frontier to high tier.

    Default values match ADR-027 specification:
    - min_age_days: 30 days of evaluation
    - min_completed_sessions: 100 council sessions
    - max_error_rate: 2% maximum error rate
    - min_quality_percentile: 75th percentile quality
    - api_stability: No breaking API changes
    - provider_ga_status: Provider marked as GA (not preview/beta)
    """

    min_age_days: int = 30
    min_completed_sessions: int = 100
    max_error_rate: float = 0.02  # < 2% errors
    min_quality_percentile: float = 0.75  # >= 75th percentile
    api_stability: bool = True
    provider_ga_status: bool = True


@dataclass
class ModelStats:
    """Tracked performance statistics for a model.

    Used to evaluate graduation criteria.
    """

    model_id: str
    days_tracked: int
    completed_sessions: int
    error_rate: float
    quality_percentile: float


@dataclass
class GraduationCandidate:
    """A model candidate for graduation with evaluation results.

    Contains both the model stats and the graduation evaluation outcome.
    """

    model_id: str
    passed: bool
    failures: List[str]
    days_tracked: int
    completed_sessions: int
    error_rate: float
    quality_percentile: float


def should_graduate(
    stats: ModelStats,
    criteria: GraduationCriteria,
) -> Tuple[bool, List[str]]:
    """Check if a model meets graduation criteria.

    Args:
        stats: The model's performance statistics
        criteria: The graduation criteria to check against

    Returns:
        Tuple of (passed, failures) where:
        - passed: True if all criteria are met
        - failures: List of failure messages for unmet criteria
    """
    failures: List[str] = []

    # Check age requirement
    if stats.days_tracked < criteria.min_age_days:
        failures.append(f"age: {stats.days_tracked} < {criteria.min_age_days} days")

    # Check session count requirement
    if stats.completed_sessions < criteria.min_completed_sessions:
        failures.append(f"sessions: {stats.completed_sessions} < {criteria.min_completed_sessions}")

    # Check error rate requirement
    if stats.error_rate > criteria.max_error_rate:
        failures.append(f"error_rate: {stats.error_rate:.1%} > {criteria.max_error_rate:.1%}")

    # Check quality percentile requirement
    if stats.quality_percentile < criteria.min_quality_percentile:
        failures.append(
            f"quality: {stats.quality_percentile:.0%} < {criteria.min_quality_percentile:.0%}"
        )

    return (len(failures) == 0, failures)


def get_graduation_candidates(
    tier: str,
    criteria: Optional[GraduationCriteria] = None,
) -> List[GraduationCandidate]:
    """Get all models in a tier that could potentially graduate.

    This function checks all models in the specified tier against the
    graduation criteria and returns candidates with their evaluation results.

    Args:
        tier: The tier to check (typically "frontier")
        criteria: The graduation criteria to use (defaults to standard criteria)

    Returns:
        List of GraduationCandidate with evaluation results
    """
    if criteria is None:
        criteria = GraduationCriteria()

    # TODO: Integrate with InternalPerformanceTracker to get real stats
    # For now, return empty list as placeholder
    return []
