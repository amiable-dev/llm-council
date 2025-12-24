"""ADR-026 Phase 2: Reasoning Token Usage Tracking.

Provides types and functions for extracting and aggregating reasoning token
usage from OpenRouter API responses.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class ReasoningUsage:
    """Usage data for a single reasoning model response.

    Attributes:
        model_id: Model identifier (e.g., "openai/o1")
        reasoning_tokens: Number of tokens used for reasoning
        budget_tokens: Maximum tokens allocated for reasoning
        efficiency: Ratio of reasoning_tokens to budget_tokens
    """

    model_id: str
    reasoning_tokens: int
    budget_tokens: int
    efficiency: float

    @property
    def under_budget(self) -> bool:
        """Check if reasoning stayed within budget."""
        return self.reasoning_tokens <= self.budget_tokens


@dataclass
class AggregatedUsage:
    """Aggregated reasoning usage across multiple models.

    Attributes:
        total_reasoning_tokens: Sum of reasoning tokens across all models
        total_budget_tokens: Sum of budget tokens across all models
        overall_efficiency: Ratio of total reasoning to total budget
        per_model: List of individual model usages
        models_over_budget: Count of models that exceeded their budget
    """

    total_reasoning_tokens: int
    total_budget_tokens: int
    overall_efficiency: float
    per_model: List[ReasoningUsage]
    models_over_budget: int


def extract_reasoning_usage(
    response: Dict[str, Any],
    model_id: str,
    budget: int,
) -> Optional[ReasoningUsage]:
    """Extract reasoning usage from an OpenRouter API response.

    Supports multiple response formats:
    1. usage.reasoning_tokens (primary)
    2. reasoning_details.tokens (alternate)

    Args:
        response: OpenRouter API response dict
        model_id: Model identifier
        budget: Budget tokens allocated for reasoning

    Returns:
        ReasoningUsage if reasoning tokens found, None otherwise
    """
    reasoning_tokens = None

    # Try primary format: usage.reasoning_tokens
    usage = response.get("usage", {})
    if "reasoning_tokens" in usage:
        reasoning_tokens = usage["reasoning_tokens"]

    # Try alternate format: reasoning_details.tokens
    if reasoning_tokens is None:
        reasoning_details = response.get("reasoning_details", {})
        if isinstance(reasoning_details, dict) and "tokens" in reasoning_details:
            reasoning_tokens = reasoning_details["tokens"]

    if reasoning_tokens is None:
        return None

    efficiency = reasoning_tokens / budget if budget > 0 else 0.0

    return ReasoningUsage(
        model_id=model_id,
        reasoning_tokens=reasoning_tokens,
        budget_tokens=budget,
        efficiency=efficiency,
    )


def aggregate_reasoning_usage(usages: List[ReasoningUsage]) -> AggregatedUsage:
    """Aggregate reasoning usage across multiple models.

    Args:
        usages: List of individual ReasoningUsage objects

    Returns:
        AggregatedUsage with totals and per-model breakdown
    """
    if not usages:
        return AggregatedUsage(
            total_reasoning_tokens=0,
            total_budget_tokens=0,
            overall_efficiency=0.0,
            per_model=[],
            models_over_budget=0,
        )

    total_reasoning = sum(u.reasoning_tokens for u in usages)
    total_budget = sum(u.budget_tokens for u in usages)
    over_budget = sum(1 for u in usages if not u.under_budget)

    efficiency = total_reasoning / total_budget if total_budget > 0 else 0.0

    return AggregatedUsage(
        total_reasoning_tokens=total_reasoning,
        total_budget_tokens=total_budget,
        overall_efficiency=efficiency,
        per_model=usages,
        models_over_budget=over_budget,
    )
