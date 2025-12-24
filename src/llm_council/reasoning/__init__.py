"""ADR-026 Phase 2: Reasoning Parameter Optimization module.

Provides automatic reasoning parameter injection for models that support
reasoning (o1, o3, deepseek-r1, etc.). Parameters are determined by tier
and task domain.

Usage:
    from llm_council.reasoning import ReasoningConfig, ReasoningEffort

    # Get tier-appropriate config
    config = ReasoningConfig.for_tier("reasoning", task_domain="math")

    # Check effort level
    print(config.effort)  # ReasoningEffort.HIGH
    print(config.budget_tokens)  # 25600

    # Track reasoning usage
    from llm_council.reasoning import extract_reasoning_usage, aggregate_reasoning_usage

    usage = extract_reasoning_usage(response, "openai/o1", budget=32000)
    aggregated = aggregate_reasoning_usage([usage1, usage2, usage3])
"""

from .types import (
    EFFORT_RATIOS,
    ReasoningConfig,
    ReasoningEffort,
    should_apply_reasoning,
)
from .tracker import (
    AggregatedUsage,
    ReasoningUsage,
    aggregate_reasoning_usage,
    extract_reasoning_usage,
)

__all__ = [
    # Types (types.py)
    "ReasoningEffort",
    "ReasoningConfig",
    "EFFORT_RATIOS",
    "should_apply_reasoning",
    # Tracking (tracker.py)
    "ReasoningUsage",
    "AggregatedUsage",
    "extract_reasoning_usage",
    "aggregate_reasoning_usage",
]
