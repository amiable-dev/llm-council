"""ADR-016: Structured Rubric Scoring.

Multi-dimensional evaluation rubric with accuracy ceiling mechanism.

This module provides:
- RubricScore dataclass for dimension scores
- Weighted score calculation with configurable weights
- Accuracy ceiling mechanism to prevent hallucinations from ranking well
- JSON parsing for rubric evaluation responses
"""

import json
import re
from dataclasses import dataclass, field
from typing import Dict, Optional, Any


class InvalidWeightsError(ValueError):
    """Raised when rubric weights are invalid."""

    pass


# Default weights (original ADR-016 proposal)
DEFAULT_RUBRIC_WEIGHTS: Dict[str, float] = {
    "accuracy": 0.35,
    "relevance": 0.10,
    "completeness": 0.20,
    "conciseness": 0.15,
    "clarity": 0.20,
}

# Updated weights per council review (same values, just explicit)
UPDATED_RUBRIC_WEIGHTS: Dict[str, float] = {
    "accuracy": 0.35,
    "relevance": 0.10,
    "completeness": 0.20,
    "conciseness": 0.15,
    "clarity": 0.20,
}

# Required dimensions for validation
REQUIRED_DIMENSIONS = {"accuracy", "relevance", "completeness", "conciseness", "clarity"}


@dataclass
class RubricScore:
    """Multi-dimensional rubric score for a response evaluation.

    Attributes:
        accuracy: Factual correctness (1-10)
        relevance: Addresses the actual question (1-10)
        completeness: Covers all aspects (1-10)
        conciseness: Efficient communication (1-10)
        clarity: Well-organized, easy to understand (1-10)
        overall: Pre-calculated weighted score (optional)
        notes: Reviewer notes explaining the scores (optional)
    """

    accuracy: int
    relevance: int
    completeness: int
    conciseness: int
    clarity: int
    overall: Optional[float] = None
    notes: Optional[str] = None


def validate_weights(weights: Dict[str, float]) -> None:
    """Validate that weights sum to 1.0 and include all dimensions.

    Args:
        weights: Dict mapping dimension names to weights

    Raises:
        InvalidWeightsError: If weights are invalid
    """
    # Check all required dimensions are present
    missing = REQUIRED_DIMENSIONS - set(weights.keys())
    if missing:
        raise InvalidWeightsError(f"Missing weight dimensions: {missing}")

    # Check weights sum to 1.0
    total = sum(weights.values())
    if abs(total - 1.0) > 0.001:
        raise InvalidWeightsError(f"Weights must sum to 1.0, got {total}")


def calculate_weighted_score(
    scores: Dict[str, int],
    weights: Optional[Dict[str, float]] = None,
) -> float:
    """Calculate weighted overall score from rubric dimensions.

    Args:
        scores: Dict mapping dimension names to scores (1-10)
        weights: Optional custom weights (defaults to UPDATED_RUBRIC_WEIGHTS)

    Returns:
        Weighted average score rounded to 2 decimal places
    """
    if weights is None:
        weights = UPDATED_RUBRIC_WEIGHTS

    total = sum(scores.get(dim, 0) * weights.get(dim, 0) for dim in weights)
    return round(total, 2)


def calculate_weighted_score_with_accuracy_ceiling(
    scores: Dict[str, int],
    weights: Optional[Dict[str, float]] = None,
) -> float:
    """Calculate weighted score with accuracy acting as a ceiling.

    Per ADR-016 council recommendation, accuracy should limit the maximum
    possible score to prevent well-written hallucinations from ranking well.

    Ceiling thresholds:
        - Accuracy < 5: Overall score caps at 4.0 (40%)
        - Accuracy 5-6: Overall score caps at 7.0 (70%)
        - Accuracy >= 7: No ceiling applied

    Args:
        scores: Dict mapping dimension names to scores (1-10)
        weights: Optional custom weights (defaults to UPDATED_RUBRIC_WEIGHTS)

    Returns:
        Weighted average score with ceiling applied, rounded to 2 decimal places
    """
    if weights is None:
        weights = UPDATED_RUBRIC_WEIGHTS

    # Calculate base weighted score
    base_score = calculate_weighted_score(scores, weights)

    # Apply accuracy ceiling
    accuracy = scores.get("accuracy", 10)
    if accuracy < 5:
        ceiling = 4.0  # Max 40% of possible score
    elif accuracy < 7:
        ceiling = 7.0  # Max 70% of possible score
    else:
        ceiling = 10.0  # No ceiling

    return round(min(base_score, ceiling), 2)


def parse_rubric_evaluation(response_text: str) -> Optional[Dict[str, Any]]:
    """Parse rubric evaluation JSON from a model response.

    Extracts JSON block containing ranking and evaluations from the response.
    Handles both code-fenced JSON and raw JSON in the response.

    Args:
        response_text: Full text response from the evaluator model

    Returns:
        Parsed dict with 'ranking' and 'evaluations' keys, or None if parsing fails
    """
    if not response_text:
        return None

    # Try to find JSON in code block first
    code_block_pattern = r"```(?:json)?\s*\n?(.*?)\n?```"
    matches = re.findall(code_block_pattern, response_text, re.DOTALL)

    json_candidates = []

    # Add code block matches
    for match in matches:
        json_candidates.append(match.strip())

    # Also try to find raw JSON object by finding balanced braces
    # Find all potential JSON start positions
    for i, char in enumerate(response_text):
        if char == "{":
            # Try to find matching closing brace
            depth = 0
            for j in range(i, len(response_text)):
                if response_text[j] == "{":
                    depth += 1
                elif response_text[j] == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = response_text[i : j + 1]
                        json_candidates.append(candidate)
                        break

    # Try to parse each candidate
    for candidate in json_candidates:
        try:
            parsed = json.loads(candidate)

            # Validate it has required fields
            if isinstance(parsed, dict) and "ranking" in parsed and "evaluations" in parsed:
                return parsed
        except json.JSONDecodeError:
            continue

    return None
