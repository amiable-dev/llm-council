"""ADR-026 Phase 2: Reasoning parameter types and configuration.

Provides ReasoningEffort enum, ReasoningConfig dataclass, and helper functions
for automatic reasoning parameter optimization based on tier and task domain.
"""

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Dict, Optional

if TYPE_CHECKING:
    from ..unified_config import UnifiedConfig


class ReasoningEffort(Enum):
    """Reasoning effort levels with associated token budget ratios.

    Maps to OpenRouter API 'effort' parameter values.
    """

    MINIMAL = "minimal"  # 10% of max tokens
    LOW = "low"  # 20% of max tokens
    MEDIUM = "medium"  # 50% of max tokens
    HIGH = "high"  # 80% of max tokens
    XHIGH = "xhigh"  # 95% of max tokens (explicit opt-in only)


# Effort level to budget ratio mapping
EFFORT_RATIOS: Dict[ReasoningEffort, float] = {
    ReasoningEffort.MINIMAL: 0.10,
    ReasoningEffort.LOW: 0.20,
    ReasoningEffort.MEDIUM: 0.50,
    ReasoningEffort.HIGH: 0.80,
    ReasoningEffort.XHIGH: 0.95,
}

# Tier to default effort mapping
TIER_EFFORT_DEFAULTS: Dict[str, ReasoningEffort] = {
    "quick": ReasoningEffort.MINIMAL,
    "balanced": ReasoningEffort.LOW,
    "high": ReasoningEffort.MEDIUM,
    "reasoning": ReasoningEffort.HIGH,
}

# Task domain to effort override mapping
DOMAIN_EFFORT_OVERRIDES: Dict[str, ReasoningEffort] = {
    "math": ReasoningEffort.HIGH,
    "coding": ReasoningEffort.MEDIUM,
    "creative": ReasoningEffort.MINIMAL,
}

# Default budget bounds
DEFAULT_MIN_BUDGET = 1024
DEFAULT_MAX_BUDGET = 32000


@dataclass(frozen=True)
class ReasoningConfig:
    """Configuration for reasoning model parameters.

    Attributes:
        effort: Reasoning effort level (determines token budget ratio)
        budget_tokens: Maximum tokens allocated for reasoning
        enabled: Whether reasoning optimization is active
    """

    effort: ReasoningEffort
    budget_tokens: int
    enabled: bool = True

    @classmethod
    def for_tier(
        cls,
        tier: str,
        max_tokens: int = DEFAULT_MAX_BUDGET,
        task_domain: Optional[str] = None,
        min_budget: int = DEFAULT_MIN_BUDGET,
        max_budget: int = DEFAULT_MAX_BUDGET,
    ) -> "ReasoningConfig":
        """Create a ReasoningConfig appropriate for a given tier.

        Args:
            tier: Confidence tier (quick, balanced, high, reasoning)
            max_tokens: Maximum tokens available for response
            task_domain: Optional domain hint (math, coding, creative)
            min_budget: Minimum budget tokens (default 1024)
            max_budget: Maximum budget tokens (default 32000)

        Returns:
            ReasoningConfig with tier-appropriate settings
        """
        # Determine effort level
        if task_domain and task_domain in DOMAIN_EFFORT_OVERRIDES:
            effort = DOMAIN_EFFORT_OVERRIDES[task_domain]
        else:
            effort = TIER_EFFORT_DEFAULTS.get(tier, ReasoningEffort.MEDIUM)

        # Calculate budget with bounds
        ratio = EFFORT_RATIOS[effort]
        raw_budget = int(max_tokens * ratio)
        budget_tokens = max(min(raw_budget, max_budget), min_budget)

        return cls(
            effort=effort,
            budget_tokens=budget_tokens,
            enabled=True,
        )


def should_apply_reasoning(stage: int, config: "UnifiedConfig") -> bool:
    """Check if reasoning parameters should apply to a given council stage.

    Args:
        stage: Council stage number (1, 2, or 3)
        config: Unified configuration with reasoning settings

    Returns:
        True if reasoning should be applied to this stage
    """
    stages = config.model_intelligence.reasoning.stages
    stage_mapping = {
        1: stages.stage1,
        2: stages.stage2,
        3: stages.stage3,
    }
    return stage_mapping.get(stage, False)
