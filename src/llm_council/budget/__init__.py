"""Opt-in budget estimation & enforcement (ADR-011 Phase 4).

DISABLED by default. Wire it in at the L1 entry point when
``budget_enforcement_enabled()`` is true:

    from llm_council.budget import CostEstimator, BudgetEnforcer, BudgetDecision

    estimate = CostEstimator().estimate(models)
    result = BudgetEnforcer().pre_query_check(estimate, budget_remaining)
    if result.decision == BudgetDecision.REJECT:
        ...  # surface result.message; do not run the query
"""

from .enforcer import BudgetEnforcer, budget_enforcement_enabled, configured_budget_mode
from .estimator import CostEstimator
from .types import BudgetDecision, BudgetMode, BudgetResult, CostEstimate

__all__ = [
    "CostEstimator",
    "BudgetEnforcer",
    "BudgetDecision",
    "BudgetMode",
    "BudgetResult",
    "CostEstimate",
    "budget_enforcement_enabled",
    "configured_budget_mode",
]
