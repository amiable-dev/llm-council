"""
Verdict extraction from council deliberation per ADR-034.

Extracts verdicts, confidence scores, and rubric scores from
council stage outputs for verification results.
"""

from __future__ import annotations

import re
import statistics
from typing import Any, Dict, List, Optional, Tuple


# Verdict patterns in synthesis text
APPROVED_PATTERNS = [
    r"\bAPPROVED\b",
    r"\bPASS(?:ED)?\b",
    r"\bACCEPTED\b",
    r"\bRECOMMENDED\b",
]

REJECTED_PATTERNS = [
    r"\bREJECTED\b",
    r"\bFAIL(?:ED)?\b",
    r"\bDENIED\b",
    r"\bNOT\s+RECOMMENDED\b",
]

# Default rubric dimensions
RUBRIC_DIMENSIONS = ["accuracy", "relevance", "completeness", "conciseness", "clarity"]


def extract_verdict_from_synthesis(
    stage3_result: Dict[str, Any],
) -> Tuple[str, float]:
    """
    Extract verdict and base confidence from Stage 3 synthesis.

    Analyzes the chairman's synthesis to determine if the council
    approved or rejected the verification target.

    Args:
        stage3_result: Stage 3 result with 'response' key

    Returns:
        Tuple of (verdict, base_confidence)
        - verdict: "pass", "fail", or "unclear"
        - base_confidence: 0.0-1.0 based on signal strength
    """
    response = stage3_result.get("response", "")
    response_upper = response.upper()

    # Check for explicit verdict markers
    approved_count = 0
    rejected_count = 0

    for pattern in APPROVED_PATTERNS:
        if re.search(pattern, response_upper):
            approved_count += 1

    for pattern in REJECTED_PATTERNS:
        if re.search(pattern, response_upper):
            rejected_count += 1

    # Determine verdict based on pattern matches
    if approved_count > 0 and rejected_count == 0:
        # Clear approval signal
        confidence = min(0.95, 0.70 + (approved_count * 0.10))
        return "pass", confidence
    elif rejected_count > 0 and approved_count == 0:
        # Clear rejection signal
        confidence = min(0.95, 0.70 + (rejected_count * 0.10))
        return "fail", confidence
    elif approved_count > rejected_count:
        # Mixed signals, leaning approved
        confidence = 0.55 + (0.05 * (approved_count - rejected_count))
        return "pass", min(0.75, confidence)
    elif rejected_count > approved_count:
        # Mixed signals, leaning rejected
        confidence = 0.55 + (0.05 * (rejected_count - approved_count))
        return "fail", min(0.75, confidence)
    else:
        # No clear signal or equal signals
        return "unclear", 0.50


def extract_rubric_scores_from_rankings(
    stage2_results: List[Dict[str, Any]],
) -> Dict[str, float]:
    """
    Extract aggregated rubric scores from Stage 2 rankings.

    Averages rubric scores across all reviewers to get a consensus score.

    Args:
        stage2_results: List of Stage 2 ranking results

    Returns:
        Dictionary mapping dimension names to averaged scores (0-10)
    """
    dimension_scores: Dict[str, List[float]] = {dim: [] for dim in RUBRIC_DIMENSIONS}

    for ranking in stage2_results:
        rubric_scores = ranking.get("rubric_scores", {})

        for dimension in RUBRIC_DIMENSIONS:
            if dimension in rubric_scores:
                score = rubric_scores[dimension]
                if isinstance(score, (int, float)) and 0 <= score <= 10:
                    dimension_scores[dimension].append(float(score))

    # Calculate averages
    result: Dict[str, float] = {}
    for dimension in RUBRIC_DIMENSIONS:
        scores = dimension_scores[dimension]
        if scores:
            result[dimension] = round(statistics.mean(scores), 1)
        else:
            result[dimension] = None  # No scores available

    return result


def calculate_confidence_from_agreement(
    stage2_results: List[Dict[str, Any]],
    stage3_verdict: str,
) -> float:
    """
    Calculate confidence score based on council agreement.

    Factors in:
    - Rubric score variance (low variance = high confidence)
    - Overall score levels (high scores for pass = high confidence)
    - Number of reviewers (more reviewers = higher confidence)

    Args:
        stage2_results: Stage 2 ranking results with rubric scores
        stage3_verdict: The extracted verdict ("pass", "fail", "unclear")

    Returns:
        Confidence score between 0.0 and 1.0
    """
    if not stage2_results:
        return 0.50  # No reviews = unclear

    # Collect all scores
    all_scores: List[float] = []
    for ranking in stage2_results:
        rubric_scores = ranking.get("rubric_scores", {})
        for score in rubric_scores.values():
            if isinstance(score, (int, float)):
                all_scores.append(float(score))

    if not all_scores:
        return 0.50  # No scores = unclear

    # Calculate mean and variance
    mean_score = statistics.mean(all_scores)
    variance = statistics.variance(all_scores) if len(all_scores) > 1 else 0

    # Base confidence on mean score
    # For "pass": high scores = high confidence
    # For "fail": low scores = high confidence
    if stage3_verdict == "pass":
        # Score of 8+ = high confidence, 5-8 = medium, <5 = low
        score_confidence = min(1.0, max(0.3, (mean_score - 5) / 5))
    elif stage3_verdict == "fail":
        # Score of 4 or less = high confidence in failure
        score_confidence = min(1.0, max(0.3, (5 - mean_score) / 5 + 0.5))
    else:
        # Unclear - mid-range confidence
        score_confidence = 0.50

    # Adjust for variance (lower variance = higher confidence)
    # Max variance reduction is 0.20
    variance_penalty = min(0.20, variance / 10)
    confidence = score_confidence - variance_penalty

    # Adjust for number of reviewers
    # More reviewers = higher confidence (up to 10% boost)
    reviewer_boost = min(0.10, len(stage2_results) * 0.02)
    confidence += reviewer_boost

    # Clamp to valid range
    return round(max(0.0, min(1.0, confidence)), 2)


def extract_blocking_issues(
    stage3_result: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Extract blocking issues from Stage 3 synthesis.

    Looks for explicit issue markers in the synthesis text.

    Args:
        stage3_result: Stage 3 result with synthesis text

    Returns:
        List of blocking issue dictionaries with severity, description, location
    """
    response = stage3_result.get("response", "")
    issues: List[Dict[str, Any]] = []

    # Look for critical/major/minor issue patterns
    # Pattern: "CRITICAL:", "MAJOR:", "MINOR:" followed by description
    issue_pattern = r"(?P<severity>CRITICAL|MAJOR|MINOR)[:\s]+(?P<description>[^\n]+)"

    for match in re.finditer(issue_pattern, response, re.IGNORECASE):
        severity = match.group("severity").lower()
        description = match.group("description").strip()

        # Try to extract location from description
        location = None
        loc_match = re.search(r"(?:in|at)\s+([^\s]+\.py:\d+|\S+\.py)", description)
        if loc_match:
            location = loc_match.group(1)

        issues.append(
            {
                "severity": severity,
                "description": description,
                "location": location,
            }
        )

    return issues


def build_verification_result(
    stage1_results: List[Dict[str, Any]],
    stage2_results: List[Dict[str, Any]],
    stage3_result: Dict[str, Any],
    confidence_threshold: float = 0.7,
) -> Dict[str, Any]:
    """
    Build complete verification result from council stages.

    Combines all stage outputs into a structured verification result
    per ADR-034 specification.

    Args:
        stage1_results: Individual model responses
        stage2_results: Peer review rankings with rubric scores
        stage3_result: Chairman synthesis
        confidence_threshold: Minimum confidence for PASS verdict

    Returns:
        Verification result dictionary
    """
    # Extract verdict from synthesis
    verdict, base_confidence = extract_verdict_from_synthesis(stage3_result)

    # Extract rubric scores from rankings
    rubric_scores = extract_rubric_scores_from_rankings(stage2_results)

    # Calculate refined confidence from agreement
    agreement_confidence = calculate_confidence_from_agreement(stage2_results, verdict)

    # Final confidence is weighted average of synthesis confidence and agreement
    confidence = round((base_confidence * 0.4) + (agreement_confidence * 0.6), 2)

    # Apply confidence threshold
    if verdict == "pass" and confidence < confidence_threshold:
        verdict = "unclear"

    # Extract blocking issues (only for fail/unclear)
    blocking_issues = []
    if verdict in ("fail", "unclear"):
        blocking_issues = extract_blocking_issues(stage3_result)

    # Get rationale from synthesis
    rationale = stage3_result.get("response", "No synthesis available.")

    return {
        "verdict": verdict,
        "confidence": confidence,
        "rubric_scores": rubric_scores,
        "blocking_issues": blocking_issues,
        "rationale": rationale,
    }
