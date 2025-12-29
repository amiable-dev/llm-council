"""TierContract dataclass for tier-appropriate council execution (ADR-022).

Defines the contract for each confidence tier, including timeouts, model pools,
and execution policies. Created per council consultation request.

ADR-026 Extension: When model intelligence is enabled, uses dynamic model
selection via select_tier_models() instead of static TIER_MODEL_POOLS.

ADR-026 Phase 2: When model intelligence is enabled, populates reasoning_config
with tier-appropriate reasoning parameters for models that support reasoning.
"""

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Optional

# ADR-032: Migrated to unified_config (lazy import to avoid circular dependency)


def _get_tier_model_pools() -> Dict[str, List[str]]:
    """Get tier model pools from unified config."""
    # Lazy import to avoid circular dependency
    from .unified_config import get_config

    config = get_config()

    def get_models(tier: str) -> List[str]:
        """Extract models list from TierPoolConfig or return empty list."""
        pool = config.tiers.pools.get(tier)
        if pool is None:
            return []
        # TierPoolConfig has a 'models' attribute
        if hasattr(pool, "models"):
            return pool.models
        # Fallback if it's already a list
        if isinstance(pool, list):
            return pool
        return []

    return {
        "quick": get_models("quick"),
        "balanced": get_models("balanced"),
        "high": get_models("high"),
        "reasoning": get_models("reasoning"),
        "frontier": get_models("frontier"),
    }


def _get_tier_timeout(tier: str) -> Dict[str, int]:
    """Get tier timeout config from unified config."""
    # Lazy import to avoid circular dependency
    from .unified_config import get_config

    config = get_config()
    timeouts = config.timeouts
    return {
        "total": timeouts.get_timeout(tier, "total") // 1000,  # Convert ms to seconds
        "per_model": timeouts.get_timeout(tier, "per_model") // 1000,
    }


def get_tier_timeout(tier: str) -> Dict[str, int]:
    """Get timeout configuration for a tier.

    Public API for getting tier timeouts.

    Args:
        tier: One of "quick", "balanced", "high", "reasoning", "frontier"

    Returns:
        dict with "total" and "per_model" timeout values in seconds
    """
    return _get_tier_timeout(tier)


# Default pools used when config isn't loaded yet
_DEFAULT_TIER_MODEL_POOLS = {
    "quick": ["openai/gpt-4o-mini", "google/gemini-2.0-flash-001"],
    "balanced": ["openai/gpt-4o", "anthropic/claude-sonnet-4", "google/gemini-2.0-pro-exp"],
    "high": [
        "openai/gpt-4o",
        "anthropic/claude-sonnet-4",
        "google/gemini-2.5-pro-preview",
        "x-ai/grok-3",
    ],
    "reasoning": ["openai/o1", "openai/o3-mini", "deepseek/deepseek-r1"],
    "frontier": ["openai/o3", "anthropic/claude-opus-4-5-20250514"],
}


# Module-level alias for backwards compatibility
# Uses default pools at import time to avoid import errors
TIER_MODEL_POOLS = _DEFAULT_TIER_MODEL_POOLS

if TYPE_CHECKING:
    from .reasoning import ReasoningConfig


# Tier-appropriate aggregator models (ADR-022 council recommendation)
# Warning: Do not use a "mini" model to aggregate reasoning model outputs.
TIER_AGGREGATORS: Dict[str, str] = {
    "quick": "openai/gpt-4o-mini",  # Speed-matched
    "balanced": "openai/gpt-4o",  # Quality-matched
    "high": "openai/gpt-4o",  # Full capability
    "reasoning": "anthropic/claude-opus-4-5-20250514",  # Can understand o1 outputs
    "frontier": "anthropic/claude-opus-4.5",  # Best available for cutting-edge synthesis (ADR-027)
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
    - reasoning_config: Optional reasoning parameters (ADR-026 Phase 2)
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
    reasoning_config: Optional["ReasoningConfig"] = None


def _is_model_intelligence_enabled() -> bool:
    """Check if model intelligence (dynamic selection) is enabled."""
    value = os.environ.get("LLM_COUNCIL_MODEL_INTELLIGENCE", "").lower()
    return value in {"true", "1", "yes", "on"}


def _get_allowed_models(tier: str, task_domain: Optional[str] = None) -> List[str]:
    """Get allowed models for a tier, using dynamic selection if enabled.

    Args:
        tier: Confidence tier
        task_domain: Optional domain hint for selection

    Returns:
        List of model IDs
    """
    if _is_model_intelligence_enabled():
        # Lazy import to avoid circular dependencies
        from .metadata.selection import select_tier_models

        return select_tier_models(tier=tier, task_domain=task_domain)

    # Fall back to static pools
    pools = _get_tier_model_pools()
    return pools[tier]


def create_tier_contract(
    tier: str,
    task_domain: Optional[str] = None,
) -> TierContract:
    """Factory function to create a TierContract from a confidence tier.

    Args:
        tier: Confidence level ('quick', 'balanced', 'high', 'reasoning')
        task_domain: Optional domain hint for model selection (e.g., 'coding',
                     'creative', 'reasoning'). Used when model intelligence is
                     enabled (ADR-026).

    Returns:
        TierContract with appropriate defaults for the tier

    Raises:
        ValueError: If tier is not recognized
    """
    tier_lower = tier.lower()

    pools = _get_tier_model_pools()
    if tier_lower not in pools:
        raise ValueError(
            f"Unknown tier: {tier}. Valid tiers: quick, balanced, high, reasoning, frontier"
        )

    # Get timeout config from ADR-012
    timeout_config = _get_tier_timeout(tier_lower)
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
        # ADR-027: Frontier tier for cutting-edge/preview models
        "frontier": {
            "token_budget": 8192,  # Allow large responses
            "max_attempts": 2,  # Limited retries (preview APIs less stable)
            "requires_peer_review": True,
            "requires_verifier": False,
            "override_policy": {"can_escalate": False, "can_deescalate": True},
        },
    }

    config = tier_configs[tier_lower]

    # Get allowed models - uses dynamic selection if intelligence enabled (ADR-026)
    allowed_models = _get_allowed_models(tier_lower, task_domain)

    # Get reasoning config if model intelligence is enabled (ADR-026 Phase 2)
    reasoning_config = None
    if _is_model_intelligence_enabled():
        # Lazy import to avoid circular dependencies
        from .reasoning import ReasoningConfig

        reasoning_config = ReasoningConfig.for_tier(
            tier=tier_lower,
            task_domain=task_domain,
        )

    return TierContract(
        tier=tier_lower,
        deadline_ms=deadline_ms,
        per_model_timeout_ms=per_model_timeout_ms,
        token_budget=config["token_budget"],
        max_attempts=config["max_attempts"],
        requires_peer_review=config["requires_peer_review"],
        requires_verifier=config["requires_verifier"],
        allowed_models=allowed_models,
        aggregator_model=TIER_AGGREGATORS[tier_lower],
        override_policy=config["override_policy"],
        reasoning_config=reasoning_config,
    )


# Lazy-loaded default contracts for each tier
_default_tier_contracts: Optional[Dict[str, TierContract]] = None


def get_default_tier_contracts() -> Dict[str, TierContract]:
    """Get pre-built default contracts for each tier (lazy-loaded)."""
    global _default_tier_contracts
    if _default_tier_contracts is None:
        _default_tier_contracts = {
            tier: create_tier_contract(tier)
            for tier in ["quick", "balanced", "high", "reasoning", "frontier"]
        }
    return _default_tier_contracts


# For backwards compatibility, access via property-like behavior
# Note: This may cause issues if used at import time - use get_default_tier_contracts() instead
class _DefaultTierContractsProxy(dict):
    """Proxy object that lazily loads tier contracts on first access.

    Inherits from dict to pass isinstance checks while still being lazy.
    """

    def __init__(self):
        # Don't call dict.__init__ with data - we populate lazily
        super().__init__()
        self._initialized = False

    def _ensure_initialized(self):
        if not self._initialized:
            self._initialized = True
            data = get_default_tier_contracts()
            super().update(data)

    def __getitem__(self, key: str) -> TierContract:
        self._ensure_initialized()
        return super().__getitem__(key)

    def __iter__(self):
        self._ensure_initialized()
        return super().__iter__()

    def items(self):
        self._ensure_initialized()
        return super().items()

    def keys(self):
        self._ensure_initialized()
        return super().keys()

    def values(self):
        self._ensure_initialized()
        return super().values()

    def __len__(self):
        self._ensure_initialized()
        return super().__len__()

    def __contains__(self, key):
        self._ensure_initialized()
        return super().__contains__(key)


DEFAULT_TIER_CONTRACTS = _DefaultTierContractsProxy()
