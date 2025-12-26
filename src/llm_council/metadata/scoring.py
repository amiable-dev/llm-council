"""Cost Scoring Algorithms for ADR-030 Scoring Refinements.

This module provides configurable cost scoring algorithms:
- log_ratio: Logarithmic ratio scoring (default, handles exponential price differences)
- exponential: Exponential decay scoring
- linear: Legacy linear scoring (backward compatible, but breaks for expensive models)

Usage:
    >>> from llm_council.metadata.scoring import get_cost_score
    >>> score = get_cost_score(0.015)  # Uses default log_ratio
    >>> score = get_cost_score(0.015, algorithm="exponential")

Configuration:
- Environment variable LLM_COUNCIL_COST_SCALE: Override default algorithm
- Config file scoring.cost_scale: Set algorithm in llm_council.yaml
"""

import logging
import math
import os
from typing import Dict, List, Literal

from .types import QualityTier

logger = logging.getLogger(__name__)

# Type alias for algorithm selection
CostScaleAlgorithm = Literal["linear", "log_ratio", "exponential"]

# Minimum price floor to prevent log(0) and division by zero
MIN_PRICE = 0.0001

# Default reference high price (most expensive models)
DEFAULT_REFERENCE_HIGH = 0.015

# Benchmark evidence sources for quality tier scores (ADR-030 Phase 2)
# These sources document the MMLU and other benchmark scores used to justify
# the quality tier score assignments in QUALITY_TIER_SCORES.
QUALITY_TIER_BENCHMARK_SOURCES: Dict[QualityTier, List[str]] = {
    QualityTier.FRONTIER: [
        # GPT-4o: MMLU 88.7%
        "https://openai.com/index/hello-gpt-4o/",
        # Claude 3.5 Sonnet: MMLU 88.7%
        "https://www.anthropic.com/news/claude-3-5-sonnet",
        # Gemini 1.5 Pro: MMLU 85.9%
        "https://deepmind.google/technologies/gemini/pro/",
    ],
    QualityTier.STANDARD: [
        # GPT-4o-mini: MMLU 82%
        "https://openai.com/index/gpt-4o-mini-advancing-cost-efficient-intelligence/",
        # Claude 3.5 Haiku: MMLU 80.4%
        "https://www.anthropic.com/claude/haiku",
        # Gemini 2.0 Flash: MMLU 81%
        "https://deepmind.google/technologies/gemini/flash/",
    ],
    QualityTier.ECONOMY: [
        # GPT-3.5 Turbo: MMLU ~70%
        "https://platform.openai.com/docs/models/gpt-3-5-turbo",
        # Mistral 7B: MMLU ~70-75%
        "https://mistral.ai/news/announcing-mistral-7b/",
    ],
    QualityTier.LOCAL: [
        # Llama 2 7B: MMLU 45-50%
        "https://ai.meta.com/llama/",
        # Phi-3 Mini: MMLU 70%
        "https://azure.microsoft.com/en-us/blog/introducing-phi-3-redefining-whats-possible-with-slms/",
        # Various quantized models perform in 55-80% range
        "https://ollama.com/library",
    ],
}


def get_cost_score_log_ratio(
    price: float,
    reference_high: float = DEFAULT_REFERENCE_HIGH,
) -> float:
    """Log-ratio cost scoring algorithm.

    Formula: score = 0.5 - (log10(price/reference) * 0.25)
    Clamped to [0, 1]

    This algorithm handles exponential price differences gracefully:
    - At reference price: returns 0.5
    - Cheaper models: scores increase toward 1.0
    - Expensive models: scores decrease toward 0.0 but stay positive

    Args:
        price: Cost per 1K tokens (prompt price)
        reference_high: Reference high price for normalization

    Returns:
        Score between 0.0 and 1.0

    Raises:
        ValueError: If reference_high is zero or negative
        TypeError: If price is None
    """
    if price is None:
        raise TypeError("price cannot be None")

    if reference_high <= 0:
        raise ValueError("reference_high must be positive")

    # Handle negative/zero prices - treat as free
    if price <= 0:
        return 1.0

    # Apply minimum price floor
    effective_price = max(price, MIN_PRICE)

    # Calculate log ratio
    ratio = effective_price / reference_high
    log_ratio = math.log10(ratio)

    # Score formula: 0.5 at reference, higher for cheaper, lower for expensive
    score = 0.5 - (log_ratio * 0.25)

    # Clamp to [0, 1]
    return max(0.0, min(1.0, score))


def get_cost_score_exponential(
    price: float,
    reference_high: float = DEFAULT_REFERENCE_HIGH,
) -> float:
    """Exponential decay cost scoring algorithm.

    Formula: score = exp(-price / reference_high)

    This provides a smooth exponential decay:
    - At price=0: returns 1.0
    - At reference price: returns exp(-1) = 0.368
    - Approaches 0 for very expensive models

    Args:
        price: Cost per 1K tokens (prompt price)
        reference_high: Reference high price for decay rate

    Returns:
        Score between 0.0 and 1.0

    Raises:
        ValueError: If reference_high is zero or negative
        TypeError: If price is None
    """
    if price is None:
        raise TypeError("price cannot be None")

    if reference_high <= 0:
        raise ValueError("reference_high must be positive")

    # Handle negative prices - treat as free
    if price < 0:
        return 1.0

    # Exponential decay
    return math.exp(-price / reference_high)


def get_cost_score_linear(
    price: float,
    reference_high: float = DEFAULT_REFERENCE_HIGH,
) -> float:
    """Linear cost scoring algorithm (legacy/backward compatible).

    Formula: score = 1.0 - (price / reference_high)
    Clamped to [0, 1]

    WARNING: This formula returns 0 for prices >= reference_high.
    Use log_ratio for better handling of expensive models.

    Args:
        price: Cost per 1K tokens (prompt price)
        reference_high: Reference high price for normalization

    Returns:
        Score between 0.0 and 1.0

    Raises:
        ValueError: If reference_high is zero or negative
        TypeError: If price is None
    """
    if price is None:
        raise TypeError("price cannot be None")

    if reference_high <= 0:
        raise ValueError("reference_high must be positive")

    # Handle negative prices - treat as free
    if price < 0:
        return 1.0

    # Linear formula (legacy)
    normalized = 1.0 - (price / reference_high)

    # Clamp to [0, 1]
    return max(0.0, min(1.0, normalized))


def get_cost_score(
    price: float,
    reference_high: float = DEFAULT_REFERENCE_HIGH,
    algorithm: CostScaleAlgorithm = "log_ratio",
) -> float:
    """Unified cost scoring with configurable algorithm.

    Args:
        price: Cost per 1K tokens (prompt price)
        reference_high: Reference high price for normalization
        algorithm: Scoring algorithm ("linear", "log_ratio", "exponential")

    Returns:
        Score between 0.0 and 1.0

    Raises:
        ValueError: If algorithm is unknown
        TypeError: If price is None
    """
    if algorithm == "log_ratio":
        return get_cost_score_log_ratio(price, reference_high)
    elif algorithm == "exponential":
        return get_cost_score_exponential(price, reference_high)
    elif algorithm == "linear":
        return get_cost_score_linear(price, reference_high)
    else:
        raise ValueError(f"Unknown cost scoring algorithm: {algorithm}")


def _get_algorithm_from_env() -> CostScaleAlgorithm:
    """Get algorithm from environment variable.

    Returns:
        Algorithm from LLM_COUNCIL_COST_SCALE or default "log_ratio"
    """
    env_value = os.environ.get("LLM_COUNCIL_COST_SCALE", "").lower()

    if env_value in ("linear", "log_ratio", "exponential"):
        return env_value  # type: ignore[return-value]

    if env_value:
        logger.warning(
            "Invalid LLM_COUNCIL_COST_SCALE value '%s', using default 'log_ratio'",
            env_value,
        )

    return "log_ratio"


def get_cost_score_with_config(
    price: float,
    reference_high: float = DEFAULT_REFERENCE_HIGH,
) -> float:
    """Get cost score using algorithm from environment/config.

    This function respects the LLM_COUNCIL_COST_SCALE environment variable.

    Args:
        price: Cost per 1K tokens (prompt price)
        reference_high: Reference high price for normalization

    Returns:
        Score between 0.0 and 1.0
    """
    algorithm = _get_algorithm_from_env()
    return get_cost_score(price, reference_high, algorithm)


# Module exports
__all__ = [
    # Constants
    "MIN_PRICE",
    "DEFAULT_REFERENCE_HIGH",
    "QUALITY_TIER_BENCHMARK_SOURCES",
    # Types
    "CostScaleAlgorithm",
    # Core functions
    "get_cost_score",
    "get_cost_score_log_ratio",
    "get_cost_score_exponential",
    "get_cost_score_linear",
    "get_cost_score_with_config",
]
