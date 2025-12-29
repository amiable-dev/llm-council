"""ADR-015: Bias Auditing and Length Correlation Tracking.

Detects systematic biases in peer review scoring:
- Length-score correlation (verbosity bias)
- Position bias (primacy/recency effects)
- Reviewer calibration (harsh vs generous reviewers)

Uses pure Python with statistics module (no scipy/numpy dependency).
"""

import math
from dataclasses import dataclass
from statistics import mean, stdev, median, variance
from typing import Dict, List, Optional, Tuple, Any

from .unified_config import get_config


@dataclass
class BiasAuditResult:
    """Results from bias analysis of a council session."""

    # Length bias
    length_score_correlation: float  # Pearson r
    length_score_p_value: float  # Statistical significance
    length_bias_detected: bool  # |r| > 0.3 and p < 0.05

    # Position bias (if randomization data available)
    position_score_variance: Optional[float]
    position_bias_detected: Optional[bool]

    # Reviewer calibration
    reviewer_mean_scores: Dict[str, float]
    reviewer_score_variance: Dict[str, float]
    harsh_reviewers: List[str]  # Mean score < median - 1 std
    generous_reviewers: List[str]  # Mean score > median + 1 std

    # Summary
    overall_bias_risk: str  # "low", "medium", "high"


def _pearson_correlation(x: List[float], y: List[float]) -> Tuple[float, float]:
    """Calculate Pearson correlation coefficient and approximate p-value.

    Pure Python implementation without scipy.

    Args:
        x: First variable values
        y: Second variable values (must be same length as x)

    Returns:
        (correlation coefficient r, approximate p-value)
    """
    n = len(x)
    if n < 3 or len(y) != n:
        return 0.0, 1.0

    # Calculate means
    mean_x = sum(x) / n
    mean_y = sum(y) / n

    # Calculate covariance and standard deviations
    covariance = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    std_x = math.sqrt(sum((xi - mean_x) ** 2 for xi in x))
    std_y = math.sqrt(sum((yi - mean_y) ** 2 for yi in y))

    # Handle zero variance case
    if std_x == 0 or std_y == 0:
        return 0.0, 1.0

    # Pearson r
    r = covariance / (std_x * std_y)

    # Approximate p-value using t-distribution approximation
    # t = r * sqrt(n-2) / sqrt(1-r^2)
    # For small n, use a rough approximation
    if abs(r) >= 1.0:
        p = 0.0 if abs(r) == 1.0 else 1.0
    else:
        t_stat = r * math.sqrt(n - 2) / math.sqrt(1 - r**2)
        # Rough p-value approximation (two-tailed)
        # For n-2 degrees of freedom, use normal approximation for simplicity
        # This is not exact but sufficient for bias detection
        p = 2 * (1 - _normal_cdf(abs(t_stat)))

    return r, p


def _normal_cdf(x: float) -> float:
    """Approximate cumulative distribution function for standard normal.

    Uses Abramowitz and Stegun approximation.
    """
    # Constants for approximation
    a1 = 0.254829592
    a2 = -0.284496736
    a3 = 1.421413741
    a4 = -1.453152027
    a5 = 1.061405429
    p = 0.3275911

    sign = 1 if x >= 0 else -1
    x = abs(x) / math.sqrt(2)

    t = 1.0 / (1.0 + p * x)
    y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * math.exp(-x * x)

    return 0.5 * (1.0 + sign * y)


def calculate_length_correlation(
    responses: List[Dict[str, Any]], scores: Dict[str, Dict[str, float]]
) -> Tuple[float, float]:
    """Calculate Pearson correlation between response length and average score.

    Args:
        responses: List of {model, response} dicts
        scores: {reviewer: {candidate: score}} nested dict

    Returns:
        (correlation coefficient, p-value)
    """
    if not responses or not scores:
        return 0.0, 1.0

    # Calculate word counts
    word_counts = {r["model"]: len(r["response"].split()) for r in responses}

    # Calculate average score per response
    avg_scores: Dict[str, float] = {}
    for model in word_counts.keys():
        model_scores = [
            reviewer_scores.get(model, reviewer_scores.get(f"Response {chr(65 + i)}", None))
            for i, reviewer_scores in enumerate(scores.values())
            if model in reviewer_scores
        ]
        # Also check if scores use model names directly
        model_scores = [
            reviewer_scores[model]
            for reviewer_scores in scores.values()
            if model in reviewer_scores
        ]
        if model_scores:
            avg_scores[model] = mean(model_scores)

    # Need at least 3 data points for meaningful correlation
    if len(avg_scores) < 3:
        return 0.0, 1.0

    # Align data
    models = list(avg_scores.keys())
    lengths = [float(word_counts[m]) for m in models]
    score_values = [avg_scores[m] for m in models]

    return _pearson_correlation(lengths, score_values)


def audit_reviewer_calibration(scores: Dict[str, Dict[str, float]]) -> Dict[str, Dict[str, float]]:
    """Analyze score calibration across reviewers.

    Args:
        scores: {reviewer: {candidate: score}} nested dict

    Returns:
        {reviewer: {mean, std, count}}
    """
    calibration: Dict[str, Dict[str, float]] = {}

    for reviewer, reviewer_scores in scores.items():
        values = list(reviewer_scores.values())
        if values:
            reviewer_mean = mean(values)
            # stdev requires at least 2 values
            reviewer_std = stdev(values) if len(values) >= 2 else 0.0
            calibration[reviewer] = {
                "mean": reviewer_mean,
                "std": reviewer_std,
                "count": len(values),
            }

    return calibration


def calculate_position_bias(
    scores: Dict[str, Dict[str, float]], position_mapping: Optional[Dict[str, int]]
) -> Tuple[Optional[float], Optional[bool]]:
    """Calculate position bias from score distribution by position.

    Args:
        scores: {reviewer: {candidate: score}} nested dict
        position_mapping: {candidate: position_index} mapping

    Returns:
        (variance of position means, bias detected bool) or (None, None) if no data
    """
    if not position_mapping:
        return None, None

    # Group scores by position
    position_scores: Dict[int, List[float]] = {}
    for reviewer_scores in scores.values():
        for candidate, score in reviewer_scores.items():
            pos = position_mapping.get(candidate)
            if pos is not None:
                position_scores.setdefault(pos, []).append(score)

    if not position_scores or len(position_scores) < 2:
        return None, None

    # Calculate mean score per position
    position_means = [mean(s) for s in position_scores.values() if s]

    if len(position_means) < 2:
        return None, None

    # Calculate variance of position means
    pos_variance = variance(position_means)
    config = get_config()
    detected = pos_variance > config.evaluation.bias.position_variance_threshold

    return round(pos_variance, 3), detected


def derive_position_mapping(label_to_model: Optional[Dict[str, Any]]) -> Dict[str, int]:
    """Derive position mapping from label_to_model mapping.

    Supports two formats:
    1. Enhanced format (v0.3.0+): {"Response A": {"model": "gpt-4", "display_index": 0}}
    2. Legacy format: {"Response A": "gpt-4"}

    The enhanced format uses display_index directly, eliminating string parsing fragility.
    Falls back to letter parsing (A=0, B=1) for legacy format or missing display_index.

    INVARIANT: Anonymization labels are assigned in lexicographic order corresponding
    to presentation order (A=first, B=second). This invariant MUST be maintained.

    Args:
        label_to_model: Mapping from labels like 'Response A' to model names or
                        enhanced dicts with {model, display_index}

    Returns:
        {model_name: position_index} mapping
    """
    if not label_to_model:
        return {}

    import re

    position_mapping: Dict[str, int] = {}

    for label, value in label_to_model.items():
        # Handle enhanced format: {"model": "...", "display_index": N}
        if isinstance(value, dict):
            model = value.get("model")
            display_index = value.get("display_index")

            if model:
                if display_index is not None:
                    # Use explicit display_index (preferred)
                    position_mapping[model] = display_index
                else:
                    # Fall back to letter parsing if display_index missing
                    match = re.match(r"^[Rr]esponse\s+([A-Za-z])$", label.strip())
                    if match:
                        letter = match.group(1).upper()
                        position = ord(letter) - ord("A")
                        position_mapping[model] = position
        else:
            # Legacy format: value is the model name string
            model = value
            match = re.match(r"^[Rr]esponse\s+([A-Za-z])$", label.strip())
            if match:
                letter = match.group(1).upper()
                position = ord(letter) - ord("A")
                position_mapping[model] = position

    return position_mapping


def _get_model_from_label_value(value: Any) -> Optional[str]:
    """Extract model name from label_to_model value (enhanced or legacy format).

    Args:
        value: Either a string (legacy) or dict with 'model' key (enhanced)

    Returns:
        Model name string or None
    """
    if isinstance(value, dict):
        return value.get("model")
    return value if isinstance(value, str) else None


def extract_scores_from_stage2(
    stage2_results: List[Dict[str, Any]], label_to_model: Dict[str, Any]
) -> Dict[str, Dict[str, float]]:
    """Extract scores from Stage 2 parsed rankings.

    Converts {reviewer: {label: score}} to {reviewer: {model: score}}.

    Supports both enhanced format (v0.3.0+) and legacy format:
    - Enhanced: {"Response A": {"model": "gpt-4", "display_index": 0}}
    - Legacy: {"Response A": "gpt-4"}

    Args:
        stage2_results: List of Stage 2 result dicts with parsed_ranking
        label_to_model: Mapping from "Response A" labels to model names or enhanced dicts

    Returns:
        {reviewer_model: {candidate_model: score}} nested dict
    """
    extracted: Dict[str, Dict[str, float]] = {}

    for result in stage2_results:
        reviewer = result.get("model")
        parsed = result.get("parsed_ranking", {})

        # Skip if abstained
        if parsed.get("abstained"):
            continue

        scores = parsed.get("scores", {})
        if not scores:
            extracted[reviewer] = {}
            continue

        reviewer_scores: Dict[str, float] = {}
        for label, score in scores.items():
            # Convert label (e.g., "Response A") to model name
            # Supports both enhanced and legacy formats
            label_value = label_to_model.get(label)
            model = _get_model_from_label_value(label_value) if label_value else None
            if model:
                reviewer_scores[model] = score

        if reviewer:
            extracted[reviewer] = reviewer_scores

    return extracted


def run_bias_audit(
    stage1_responses: List[Dict[str, Any]],
    stage2_scores: Dict[str, Dict[str, float]],
    position_mapping: Optional[Dict[str, int]] = None,
) -> BiasAuditResult:
    """Run full bias audit on a council session.

    Args:
        stage1_responses: List of {model, response} from Stage 1
        stage2_scores: {reviewer: {candidate: score}} from Stage 2
        position_mapping: Optional {candidate: position_shown} for position bias

    Returns:
        BiasAuditResult with all metrics
    """
    # Length correlation
    r, p = calculate_length_correlation(stage1_responses, stage2_scores)
    config = get_config()
    length_bias = abs(r) > config.evaluation.bias.length_correlation_threshold and p < 0.05

    # Reviewer calibration
    calibration = audit_reviewer_calibration(stage2_scores)

    # Calculate harsh/generous thresholds
    means = [c["mean"] for c in calibration.values()]
    harsh_reviewers: List[str] = []
    generous_reviewers: List[str] = []

    if len(means) >= 2:
        median_mean = median(means)
        std_mean = stdev(means) if len(means) >= 2 else 1.0

        harsh_threshold = median_mean - std_mean
        generous_threshold = median_mean + std_mean

        harsh_reviewers = [r for r, c in calibration.items() if c["mean"] < harsh_threshold]
        generous_reviewers = [r for r, c in calibration.items() if c["mean"] > generous_threshold]

    # Position bias
    position_variance, position_bias = calculate_position_bias(stage2_scores, position_mapping)

    # Overall risk assessment
    risk_factors = sum(
        [length_bias, position_bias or False, len(harsh_reviewers) > 0, len(generous_reviewers) > 0]
    )

    if risk_factors == 0:
        overall_risk = "low"
    elif risk_factors <= 2:
        overall_risk = "medium"
    else:
        overall_risk = "high"

    return BiasAuditResult(
        length_score_correlation=round(r, 3),
        length_score_p_value=round(p, 4),
        length_bias_detected=length_bias,
        position_score_variance=position_variance,
        position_bias_detected=position_bias,
        reviewer_mean_scores={r: round(c["mean"], 2) for r, c in calibration.items()},
        reviewer_score_variance={r: round(c["std"], 2) for r, c in calibration.items()},
        harsh_reviewers=harsh_reviewers,
        generous_reviewers=generous_reviewers,
        overall_bias_risk=overall_risk,
    )
