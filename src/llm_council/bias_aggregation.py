"""ADR-018 Phase 2-3: Cross-session bias aggregation and analysis.

This module provides statistical aggregation and analysis functions
for bias metrics collected across multiple council sessions.

Key components:
- StatisticalConfidence: Confidence tiers based on sample size
- Fisher z-transform utilities for correlation confidence intervals
- Reviewer profile aggregation with harshness z-scores
- Position bias detection via variance of position means
- Temporal trend detection and anomaly flagging
"""

import json
import logging
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from llm_council.bias_persistence import (
    BiasMetricRecord,
    read_bias_records,
)
from llm_council.unified_config import get_config


def _get_bias_store_path() -> Path:
    """Get bias store path from unified config."""
    try:
        path_str = get_config().evaluation.bias.store_path
        return Path(path_str).expanduser()
    except Exception:
        return Path.home() / ".llm-council" / "bias_metrics.jsonl"


logger = logging.getLogger(__name__)


# =============================================================================
# Statistical Confidence Enum
# =============================================================================


class StatisticalConfidence(Enum):
    """Confidence level based on sample size.

    Thresholds:
        INSUFFICIENT: N < 10
        PRELIMINARY: 10 <= N < 20
        MODERATE: 20 <= N < 50
        HIGH: N >= 50
    """

    INSUFFICIENT = "insufficient"
    PRELIMINARY = "preliminary"
    MODERATE = "moderate"
    HIGH = "high"


def determine_confidence_level(sample_size: int) -> StatisticalConfidence:
    """Determine statistical confidence tier from sample size.

    Args:
        sample_size: Number of samples/sessions

    Returns:
        StatisticalConfidence enum value
    """
    if sample_size < 10:
        return StatisticalConfidence.INSUFFICIENT
    elif sample_size < 20:
        return StatisticalConfidence.PRELIMINARY
    elif sample_size < 50:
        return StatisticalConfidence.MODERATE
    else:
        return StatisticalConfidence.HIGH


# =============================================================================
# Fisher z-Transform Utilities
# =============================================================================


def fisher_z_transform(r: float) -> float:
    """Apply Fisher z-transformation to correlation coefficient.

    z = 0.5 * ln((1+r)/(1-r)) = arctanh(r)

    Args:
        r: Correlation coefficient (-1 to 1)

    Returns:
        Fisher z-transformed value
    """
    # Handle boundary values gracefully
    if r >= 1.0:
        r = 0.9999
    elif r <= -1.0:
        r = -0.9999

    return 0.5 * math.log((1 + r) / (1 - r))


def inverse_fisher_z(z: float) -> float:
    """Apply inverse Fisher z-transformation to recover correlation.

    r = tanh(z) = (e^(2z) - 1) / (e^(2z) + 1)

    Args:
        z: Fisher z-transformed value

    Returns:
        Correlation coefficient (-1 to 1)
    """
    return math.tanh(z)


# =============================================================================
# Dataclasses
# =============================================================================


@dataclass
class ReviewerProfile:
    """Aggregated profile of a single reviewer across sessions.

    Attributes:
        reviewer_id: Model identifier for the reviewer
        sample_size: Number of scores given
        mean_score: Average score given by this reviewer
        std_score: Standard deviation of scores
        harshness_z_score: Z-score relative to all reviewers (negative=harsh)
        ci_lower: 95% CI lower bound on mean
        ci_upper: 95% CI upper bound on mean
    """

    reviewer_id: str
    sample_size: int
    mean_score: float
    std_score: float
    harshness_z_score: float
    ci_lower: float
    ci_upper: float


@dataclass
class LengthCorrelationReport:
    """Report on length-score correlation with confidence interval.

    Uses Fisher z-transformation for proper CI calculation.
    """

    metric_name: str = "length_correlation"
    point_estimate: float = 0.0
    ci_lower: float = 0.0
    ci_upper: float = 0.0
    sample_size: int = 0
    window_start: Optional[str] = None
    window_end: Optional[str] = None
    statistical_confidence: str = "insufficient"
    fisher_z: float = 0.0
    fisher_se: float = 0.0


@dataclass
class PositionBiasReport:
    """Report on position bias with variance of position means."""

    metric_name: str = "position_bias"
    point_estimate: float = 0.0  # Variance of position means
    ci_lower: float = 0.0
    ci_upper: float = 0.0
    sample_size: int = 0
    window_start: Optional[str] = None
    window_end: Optional[str] = None
    statistical_confidence: str = "insufficient"
    position_means: Dict[int, float] = field(default_factory=dict)
    position_counts: Dict[int, int] = field(default_factory=dict)


@dataclass
class AggregatedBiasAuditResult:
    """Complete cross-session bias audit result.

    Aggregates length correlation, position bias, and reviewer profiles
    across a time window of sessions.
    """

    # Window metadata
    window_start: Optional[str] = None
    window_end: Optional[str] = None
    unique_sessions: int = 0
    total_records: int = 0
    overall_confidence: str = "insufficient"

    # Bias metrics
    length_correlation: Optional[LengthCorrelationReport] = None
    position_bias: Optional[PositionBiasReport] = None
    reviewer_profiles: List[ReviewerProfile] = field(default_factory=list)

    # Warnings
    warnings: List[str] = field(default_factory=list)


# =============================================================================
# Aggregation Functions
# =============================================================================


def _calculate_pearson_correlation(x: List[float], y: List[float]) -> float:
    """Pure Python Pearson correlation calculation.

    Args:
        x: First variable values
        y: Second variable values (same length as x)

    Returns:
        Pearson correlation coefficient r
    """
    n = len(x)
    if n < 2:
        return 0.0

    mean_x = sum(x) / n
    mean_y = sum(y) / n

    # Calculate covariance and standard deviations
    cov = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    std_x = math.sqrt(sum((xi - mean_x) ** 2 for xi in x))
    std_y = math.sqrt(sum((yi - mean_y) ** 2 for yi in y))

    if std_x == 0 or std_y == 0:
        return 0.0

    return cov / (std_x * std_y)


def pooled_correlation_with_ci(
    records: List[BiasMetricRecord],
    alpha: float = 0.05,
) -> Optional[LengthCorrelationReport]:
    """Calculate pooled length-score correlation with confidence interval.

    Uses Fisher z-transformation for proper CI calculation.

    Args:
        records: List of bias metric records
        alpha: Significance level for CI (default 0.05 for 95% CI)

    Returns:
        LengthCorrelationReport or None if insufficient data
    """
    if len(records) < 10:
        return None

    # Extract length and score pairs
    lengths = [r.response_length_chars for r in records]
    scores = [r.score_value for r in records]

    # Calculate Pearson correlation
    r = _calculate_pearson_correlation(lengths, scores)
    n = len(records)

    # Fisher z-transform
    z = fisher_z_transform(r)

    # Standard error of z
    se_z = 1.0 / math.sqrt(n - 3) if n > 3 else 1.0

    # Critical value for 95% CI (z_alpha/2 ≈ 1.96)
    z_crit = 1.96

    # CI in z-space
    z_lower = z - z_crit * se_z
    z_upper = z + z_crit * se_z

    # Transform back to r-space
    ci_lower = inverse_fisher_z(z_lower)
    ci_upper = inverse_fisher_z(z_upper)

    # Get timestamps for window
    timestamps = [r.timestamp for r in records if r.timestamp]
    window_start = min(timestamps) if timestamps else None
    window_end = max(timestamps) if timestamps else None

    confidence = determine_confidence_level(n)

    return LengthCorrelationReport(
        metric_name="length_correlation",
        point_estimate=r,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        sample_size=n,
        window_start=window_start,
        window_end=window_end,
        statistical_confidence=confidence.value,
        fisher_z=z,
        fisher_se=se_z,
    )


def aggregate_reviewer_profiles(
    records: List[BiasMetricRecord],
) -> List[ReviewerProfile]:
    """Aggregate per-reviewer statistics with harshness z-scores.

    Harshness z-score is calculated relative to the population of reviewers:
    - Negative z-score = harsh (scores below average)
    - Positive z-score = generous (scores above average)

    Args:
        records: List of bias metric records

    Returns:
        List of ReviewerProfile dataclasses
    """
    # Group by reviewer
    reviewer_scores: Dict[str, List[float]] = {}
    for r in records:
        if r.reviewer_id:
            if r.reviewer_id not in reviewer_scores:
                reviewer_scores[r.reviewer_id] = []
            reviewer_scores[r.reviewer_id].append(r.score_value)

    if not reviewer_scores:
        return []

    # Calculate per-reviewer means
    reviewer_means: Dict[str, float] = {}
    for reviewer_id, scores in reviewer_scores.items():
        reviewer_means[reviewer_id] = sum(scores) / len(scores)

    # Calculate mean and std of reviewer means (for z-scores)
    all_means = list(reviewer_means.values())
    population_mean = sum(all_means) / len(all_means) if all_means else 0

    if len(all_means) > 1:
        population_std = math.sqrt(
            sum((m - population_mean) ** 2 for m in all_means) / (len(all_means) - 1)
        )
    else:
        population_std = 0

    # Build profiles
    profiles = []
    for reviewer_id, scores in reviewer_scores.items():
        n = len(scores)
        mean_score = sum(scores) / n

        if n > 1:
            std_score = math.sqrt(sum((s - mean_score) ** 2 for s in scores) / (n - 1))
        else:
            std_score = 0.0

        # Harshness z-score (relative to other reviewers)
        if population_std > 0:
            harshness_z = (mean_score - population_mean) / population_std
        else:
            harshness_z = 0.0

        # 95% CI on mean (using t-distribution approximation, z ≈ 1.96 for large n)
        if n > 1:
            se = std_score / math.sqrt(n)
            ci_lower = mean_score - 1.96 * se
            ci_upper = mean_score + 1.96 * se
        else:
            ci_lower = mean_score
            ci_upper = mean_score

        profiles.append(
            ReviewerProfile(
                reviewer_id=reviewer_id,
                sample_size=n,
                mean_score=mean_score,
                std_score=std_score,
                harshness_z_score=harshness_z,
                ci_lower=ci_lower,
                ci_upper=ci_upper,
            )
        )

    return profiles


def aggregate_position_bias(
    records: List[BiasMetricRecord],
) -> Optional[PositionBiasReport]:
    """Aggregate position bias across sessions.

    Calculates variance of position means as the bias metric.
    Higher variance indicates more position bias.

    Args:
        records: List of bias metric records

    Returns:
        PositionBiasReport or None if insufficient position variation
    """
    # Group scores by position
    position_scores: Dict[int, List[float]] = {}
    for r in records:
        pos = r.position
        if pos not in position_scores:
            position_scores[pos] = []
        position_scores[pos].append(r.score_value)

    # Need at least 2 positions
    if len(position_scores) < 2:
        return None

    # Calculate mean per position
    position_means: Dict[int, float] = {}
    position_counts: Dict[int, int] = {}
    for pos, scores in position_scores.items():
        position_means[pos] = sum(scores) / len(scores)
        position_counts[pos] = len(scores)

    # Calculate variance of position means
    all_means = list(position_means.values())
    grand_mean = sum(all_means) / len(all_means)
    variance = sum((m - grand_mean) ** 2 for m in all_means) / len(all_means)

    # Get timestamps for window
    timestamps = [r.timestamp for r in records if r.timestamp]
    window_start = min(timestamps) if timestamps else None
    window_end = max(timestamps) if timestamps else None

    n = len(records)
    confidence = determine_confidence_level(n)

    return PositionBiasReport(
        metric_name="position_bias",
        point_estimate=variance,
        ci_lower=0.0,  # Variance CI calculation is complex, skip for now
        ci_upper=0.0,
        sample_size=n,
        window_start=window_start,
        window_end=window_end,
        statistical_confidence=confidence.value,
        position_means=position_means,
        position_counts=position_counts,
    )


def run_aggregated_bias_audit(
    store_path: Optional[Path] = None,
    max_sessions: Optional[int] = None,
    max_days: Optional[int] = None,
) -> AggregatedBiasAuditResult:
    """Run complete cross-session bias audit.

    Main entry point for Phase 2 aggregation.

    Args:
        store_path: Path to JSONL store (default from config)
        max_sessions: Limit to last N sessions
        max_days: Limit to last N days

    Returns:
        AggregatedBiasAuditResult with all metrics
    """
    if store_path is None:
        store_path = _get_bias_store_path()

    # Read records with filters
    records = read_bias_records(
        store_path=store_path,
        max_sessions=max_sessions,
        max_days=max_days,
    )

    if not records:
        return AggregatedBiasAuditResult(
            warnings=["No bias data found in store"],
        )

    # Calculate metadata
    unique_sessions = len(set(r.session_id for r in records))
    timestamps = [r.timestamp for r in records if r.timestamp]
    window_start = min(timestamps) if timestamps else None
    window_end = max(timestamps) if timestamps else None

    # Determine overall confidence
    confidence = determine_confidence_level(unique_sessions)

    # Run aggregations
    length_correlation = pooled_correlation_with_ci(records)
    position_bias = aggregate_position_bias(records)
    reviewer_profiles = aggregate_reviewer_profiles(records)

    # Generate warnings
    warnings = []
    if confidence == StatisticalConfidence.INSUFFICIENT:
        warnings.append(
            f"Only {unique_sessions} sessions - need at least 10 for preliminary analysis"
        )
    elif confidence == StatisticalConfidence.PRELIMINARY:
        warnings.append(f"Only {unique_sessions} sessions - results are preliminary")

    # Check for harsh/generous reviewers
    for profile in reviewer_profiles:
        if profile.harshness_z_score < -1.5:
            warnings.append(
                f"Reviewer {profile.reviewer_id} appears harsh (z={profile.harshness_z_score:.2f})"
            )
        elif profile.harshness_z_score > 1.5:
            warnings.append(
                f"Reviewer {profile.reviewer_id} appears generous (z={profile.harshness_z_score:.2f})"
            )

    return AggregatedBiasAuditResult(
        window_start=window_start,
        window_end=window_end,
        unique_sessions=unique_sessions,
        total_records=len(records),
        overall_confidence=confidence.value,
        length_correlation=length_correlation,
        position_bias=position_bias,
        reviewer_profiles=reviewer_profiles,
        warnings=warnings,
    )


# =============================================================================
# CLI Report Generation
# =============================================================================


def _generate_ascii_chart(data: Dict[str, float], title: str, width: int = 40) -> str:
    """Generate a simple ASCII bar chart."""
    if not data:
        return ""

    lines = [f"\n{title}:"]
    max_val = max(data.values()) if data else 1.0

    # Sort by value descending
    sorted_items = sorted(data.items(), key=lambda x: x[1], reverse=True)

    for label, val in sorted_items:
        bar_len = int((val / max_val) * width) if max_val > 0 else 0
        bar = "█" * bar_len
        lines.append(f"{label[:15]:<15} |{bar:<{width}}| {val:.2f}")

    return "\n".join(lines)


def generate_bias_report_text(
    store_path: Optional[Path] = None,
    max_sessions: Optional[int] = None,
    max_days: Optional[int] = None,
    verbose: bool = False,
) -> str:
    """Generate a human-readable text report of the bias audit."""
    result = run_aggregated_bias_audit(store_path, max_sessions, max_days)

    lines = []
    lines.append("LLM Council - Cross-Session Bias Audit")
    lines.append("======================================")
    lines.append(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"Sessions Analyzed: {result.unique_sessions}")
    lines.append(f"Total Reviews: {result.total_records}")
    lines.append(f"Confidence Level: {result.overall_confidence}")
    lines.append("")

    # 1. Length Correlation (Verbosity Bias)
    lines.append("1. Response Length Correlation (Verbosity Bias)")
    lines.append("----------------------------------------------")
    if result.length_correlation:
        lc = result.length_correlation
        lines.append(f"Pooled Correlation (r): {lc.point_estimate:.3f}")
        lines.append(f"95% CI: [{lc.ci_lower:.3f}, {lc.ci_upper:.3f}]")

        threshold = 0.3
        if abs(lc.point_estimate) > threshold:
            lines.append("⚠️  Significant verbosity bias detected.")
        else:
            lines.append("✅ No significant verbosity bias detected.")
    else:
        lines.append("Insufficient data for length correlation analysis.")
    lines.append("")

    # 2. Position Bias
    lines.append("2. Position Bias (Score by Position)")
    lines.append("------------------------------------")
    if result.position_bias:
        pb = result.position_bias
        # Simple extraction for chart, assuming positions are 1-indexed
        pos_data = {f"Pos {k}": v for k, v in pb.position_means.items() if k <= 5}
        lines.append(_generate_ascii_chart(pos_data, "Average Score per Position"))
    else:
        lines.append("Insufficient data for position analysis.")
    lines.append("")

    # 3. Reviewer Profiles (Harshness)
    lines.append("3. Reviewer Profiles (Harshness Analysis)")
    lines.append("-----------------------------------------")
    if result.reviewer_profiles:
        # Generate chart for z-scores
        z_scores = {r.reviewer_id: r.harshness_z_score for r in result.reviewer_profiles}
        lines.append(_generate_ascii_chart(z_scores, "Reviewer Harshness (Z-Score)"))
        lines.append("")

        for profile in sorted(result.reviewer_profiles, key=lambda p: p.harshness_z_score):
            if verbose:
                lines.append(f"Reviewer: {profile.reviewer_id}")
                lines.append(f"  Reviews: {profile.sample_size}")
                lines.append(f"  Avg Score: {profile.mean_score:.2f}")
                lines.append(f"  Harshness (z-score): {profile.harshness_z_score:.2f}")
                lines.append("")
    else:
        lines.append("Insufficient data for reviewer profiles.")
    lines.append("")

    # Warnings
    if result.warnings:
        lines.append("Warnings")
        lines.append("-" * 30)
        for warning in result.warnings:
            lines.append(f"  ⚠ {warning}")
        lines.append("")

    return "\n".join(lines)


def generate_bias_report_json(
    store_path: Optional[Path] = None,
    max_sessions: Optional[int] = None,
    max_days: Optional[int] = None,
) -> str:
    """Generate JSON bias report.

    Args:
        store_path: Path to JSONL store
        max_sessions: Limit to last N sessions
        max_days: Limit to last N days

    Returns:
        JSON string
    """
    result = run_aggregated_bias_audit(
        store_path=store_path,
        max_sessions=max_sessions,
        max_days=max_days,
    )

    result_dict = asdict(result)
    return json.dumps(result_dict, indent=2, default=str)


def generate_bias_report_csv(
    store_path: Optional[Path] = None,
    max_sessions: Optional[int] = None,
    max_days: Optional[int] = None,
) -> str:
    """Generate a CSV export of raw bias metrics."""
    import csv
    import io

    # Fetch records directly instead of aggregated result
    records = read_bias_records(store_path, max_sessions, max_days)

    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow(
        [
            "session_id",
            "timestamp",
            "reviewer_id",
            "model_id",
            "position",
            "score",
            "length_chars",
            "query_category",
            "token_bucket",
        ]
    )

    for r in records:
        writer.writerow(
            [
                r.session_id,
                r.timestamp,
                r.reviewer_id,
                r.model_id,
                r.position,
                r.score_value,
                r.response_length_chars,
                # Metadata might be None for old records
                r.query_metadata.get("category", "") if r.query_metadata else "",
                r.query_metadata.get("token_bucket", "") if r.query_metadata else "",
            ]
        )

    return output.getvalue()


# =============================================================================
# Phase 3: Temporal Trends and Anomaly Detection
# =============================================================================


def detect_temporal_trends(
    records: List[BiasMetricRecord],
    window_size: int = 7,
) -> Optional[Dict[str, Any]]:
    """Detect temporal trends in bias metrics.

    Uses rolling window to smooth data and detect direction.

    Args:
        records: List of bias metric records (should be chronologically sorted)
        window_size: Number of days for rolling window

    Returns:
        Dict with trend info or None if insufficient data
    """
    if len(records) < 10:
        return None

    # Sort by timestamp
    sorted_records = sorted(records, key=lambda r: r.timestamp)

    # Calculate early and late averages
    n = len(sorted_records)
    early_half = sorted_records[: n // 2]
    late_half = sorted_records[n // 2 :]

    early_mean = sum(r.score_value for r in early_half) / len(early_half)
    late_mean = sum(r.score_value for r in late_half) / len(late_half)

    # Determine trend direction
    diff = late_mean - early_mean
    if abs(diff) < 0.5:
        direction = "stable"
    elif diff > 0:
        direction = "increasing"
    else:
        direction = "decreasing"

    return {
        "trend_direction": direction,
        "early_mean": early_mean,
        "late_mean": late_mean,
        "difference": diff,
        "sample_size": n,
    }


def detect_anomalies(
    records: List[BiasMetricRecord],
    z_threshold: float = 2.5,
) -> List[Dict[str, Any]]:
    """Detect anomalous sessions or reviewer behavior.

    Flags sessions with scores significantly different from population.

    Args:
        records: List of bias metric records
        z_threshold: Z-score threshold for flagging (default 2.5)

    Returns:
        List of anomaly descriptions
    """
    anomalies = []

    if len(records) < 10:
        return anomalies

    # Calculate population statistics
    all_scores = [r.score_value for r in records]
    mean_score = sum(all_scores) / len(all_scores)

    if len(all_scores) > 1:
        std_score = math.sqrt(
            sum((s - mean_score) ** 2 for s in all_scores) / (len(all_scores) - 1)
        )
    else:
        return anomalies

    if std_score == 0:
        return anomalies

    # Check each session's mean score
    session_scores: Dict[str, List[float]] = {}
    for r in records:
        if r.session_id:
            if r.session_id not in session_scores:
                session_scores[r.session_id] = []
            session_scores[r.session_id].append(r.score_value)

    for session_id, scores in session_scores.items():
        session_mean = sum(scores) / len(scores)
        z_score = (session_mean - mean_score) / std_score

        if abs(z_score) > z_threshold:
            anomalies.append(
                {
                    "type": "outlier_session",
                    "session_id": session_id,
                    "session_mean": session_mean,
                    "z_score": z_score,
                    "direction": "low" if z_score < 0 else "high",
                }
            )

    return anomalies
