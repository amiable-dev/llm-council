"""TierContract dataclass for tier-appropriate council execution (ADR-022).

Defines the contract for each confidence tier, including timeouts, model pools,
and execution policies. Created per council consultation request.
"""

from dataclasses import dataclass
from typing import Dict, List

from .config import TIER_MODEL_POOLS, get_tier_timeout


# Tier-appropriate aggregator models (ADR-022 council recommendation)
# Warning: Do not use a "mini" model to aggregate reasoning model outputs.
TIER_AGGREGATORS: Dict[str, str] = {
    "quick": "openai/gpt-4o-mini",  # Speed-matched
    "balanced": "openai/gpt-4o",  # Quality-matched
    "high": "openai/gpt-4o",  # Full capability
    "reasoning": "anthropic/claude-opus-4-5-20250514",  # Can understand o1 outputs
}


@dataclass(frozen=True)
class TierContract:
    """Immutable contract defining tier execution parameters.

    Fields per ADR-022 council recommendation:
    - tier: Confidence level (quick|balanced|high|reasoning)
    - deadline_ms: Total timeout for council execution
    - per_model_timeout_ms: Per-model timeout (ADR-012 compliance)
    - token_budget: Max tokens per response
    - max_attempts: Retry attempts before fallback
    - requires_peer_review: Whether Stage 2 runs
    - requires_verifier: Whether lightweight verifier runs (quick tier)
    - allowed_models: Model pool for this tier
    - aggregator_model: Model used for synthesis/aggregation
    - override_policy: Escalation/de-escalation rules
    """

    tier: str
    deadline_ms: int
    per_model_timeout_ms: int
    token_budget: int
    max_attempts: int
    requires_peer_review: bool
    requires_verifier: bool
    allowed_models: List[str]
    aggregator_model: str
    override_policy: Dict[str, bool]


def create_tier_contract(tier: str) -> TierContract:
    """Factory function to create a TierContract from a confidence tier.

    Args:
        tier: Confidence level ('quick', 'balanced', 'high', 'reasoning')

    Returns:
        TierContract with appropriate defaults for the tier

    Raises:
        ValueError: If tier is not recognized
    """
    tier_lower = tier.lower()

    if tier_lower not in TIER_MODEL_POOLS:
        raise ValueError(
            f"Unknown tier: {tier}. Valid tiers: quick, balanced, high, reasoning"
        )

    # Get timeout config from ADR-012
    timeout_config = get_tier_timeout(tier_lower)
    deadline_ms = timeout_config["total"] * 1000
    per_model_timeout_ms = timeout_config["per_model"] * 1000

    # Tier-specific configurations per ADR-022
    tier_configs = {
        "quick": {
            "token_budget": 2048,
            "max_attempts": 1,
            "requires_peer_review": False,  # Quick skips full peer review
            "requires_verifier": True,  # Uses lightweight verifier instead
            "override_policy": {"can_escalate": True, "can_deescalate": False},
        },
        "balanced": {
            "token_budget": 4096,
            "max_attempts": 2,
            "requires_peer_review": True,
            "requires_verifier": False,
            "override_policy": {"can_escalate": True, "can_deescalate": True},
        },
        "high": {
            "token_budget": 4096,
            "max_attempts": 3,
            "requires_peer_review": True,
            "requires_verifier": False,
            "override_policy": {"can_escalate": True, "can_deescalate": True},
        },
        "reasoning": {
            "token_budget": 8192,
            "max_attempts": 2,
            "requires_peer_review": True,
            "requires_verifier": False,
            "override_policy": {"can_escalate": False, "can_deescalate": True},
        },
    }

    config = tier_configs[tier_lower]

    return TierContract(
        tier=tier_lower,
        deadline_ms=deadline_ms,
        per_model_timeout_ms=per_model_timeout_ms,
        token_budget=config["token_budget"],
        max_attempts=config["max_attempts"],
        requires_peer_review=config["requires_peer_review"],
        requires_verifier=config["requires_verifier"],
        allowed_models=TIER_MODEL_POOLS[tier_lower],
        aggregator_model=TIER_AGGREGATORS[tier_lower],
        override_policy=config["override_policy"],
    )


# Pre-built default contracts for each tier
DEFAULT_TIER_CONTRACTS: Dict[str, TierContract] = {
    tier: create_tier_contract(tier) for tier in ["quick", "balanced", "high", "reasoning"]
}
