"""Triage package for ADR-020 Layer 2 (Query Triage).

This package handles query classification, model selection, and prompt optimization
before council execution.

Current implementation is a passthrough stub that will be enhanced with:
- Wildcard selection (Issue #48)
- Prompt optimizer (Issue #49)
- Complexity classifier (Issue #50)
"""

from typing import Optional

from llm_council.config import COUNCIL_MODELS
from llm_council.tier_contract import TierContract

from .types import (
    DEFAULT_SPECIALIST_POOLS,
    DomainCategory,
    TriageRequest,
    TriageResult,
    WildcardConfig,
)

__all__ = [
    "run_triage",
    "TriageResult",
    "TriageRequest",
    "WildcardConfig",
    "DomainCategory",
    "DEFAULT_SPECIALIST_POOLS",
]


def run_triage(
    query: str,
    tier_contract: Optional[TierContract] = None,
    domain_hint: Optional[DomainCategory] = None,
) -> TriageResult:
    """Run query triage to determine models and optimize prompts.

    This is currently a passthrough stub that:
    - Uses tier_contract's allowed_models if provided, else COUNCIL_MODELS
    - Passes through query unchanged to all models
    - Sets passthrough mode in metadata

    Future enhancements (per ADR-020):
    - Wildcard selection from specialist pools
    - Per-model prompt optimization
    - Complexity classification for tier escalation

    Args:
        query: The user query to triage
        tier_contract: Optional tier contract constraining model selection
        domain_hint: Optional domain hint for specialist selection

    Returns:
        TriageResult with resolved models and prompts
    """
    # Determine models to use
    if tier_contract is not None:
        models = list(tier_contract.allowed_models)
    else:
        models = list(COUNCIL_MODELS)

    # Passthrough: use original query for all models
    optimized_prompts = {model: query for model in models}

    return TriageResult(
        resolved_models=models,
        optimized_prompts=optimized_prompts,
        fast_path=False,
        escalation_recommended=False,
        metadata={"mode": "passthrough"},
    )
