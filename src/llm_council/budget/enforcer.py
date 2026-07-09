"""Opt-in, tiered budget enforcement (ADR-011 §4, Phase 4).

DISABLED by default. When enabled, a pre-query check may reject or warn based on
the estimated cost vs the remaining budget, per the configured ``BudgetMode``.
Between stages a check may abort *gracefully* (returning partial results) — it
NEVER aborts a model completion in flight (ADR-040 durable partial state).

Every reject/warn/abort emits an auditable ``L1_BUDGET_DECISION`` LayerEvent —
budget never causes a silent tier change (ADR-024 layer sovereignty).
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from .types import BudgetDecision, BudgetMode, BudgetResult, CostEstimate

logger = logging.getLogger(__name__)


def budget_enforcement_enabled() -> bool:
    """ADR-011 Phase 4: opt-in budget enforcement (default OFF)."""
    return os.getenv("LLM_COUNCIL_BUDGET_ENFORCEMENT", "false").lower() in ("true", "1", "yes")


def configured_budget_mode() -> BudgetMode:
    """Budget mode from config (default BALANCED); unknown values fall back."""
    raw = os.getenv("LLM_COUNCIL_BUDGET_MODE", "balanced").lower()
    try:
        return BudgetMode(raw)
    except ValueError:
        return BudgetMode.BALANCED


def _emit(decision: BudgetDecision, mode: BudgetMode, estimate: Optional[CostEstimate],
          budget_remaining: Optional[float], phase: str) -> None:
    """Emit an auditable budget LayerEvent (soft — never breaks the caller)."""
    try:
        from ..layer_contracts import LayerEventType, emit_layer_event

        emit_layer_event(
            LayerEventType.L1_BUDGET_DECISION,
            {
                "decision": decision.value,
                "mode": mode.value,
                "phase": phase,
                "estimate_expected": estimate.expected if estimate else None,
                "estimate_high": estimate.high if estimate else None,
                "budget_remaining": budget_remaining,
            },
            layer_from="L1",
            layer_to="L1",
        )
    except Exception as exc:  # observability must not break enforcement
        logger.debug("budget LayerEvent emit failed (ignored): %s", exc)


class BudgetEnforcer:
    """Tiered pre-query and between-stage budget checks."""

    def __init__(self, mode: Optional[BudgetMode] = None) -> None:
        self._mode = mode or configured_budget_mode()

    @property
    def mode(self) -> BudgetMode:
        return self._mode

    def pre_query_check(
        self, estimate: CostEstimate, budget_remaining: Optional[float]
    ) -> BudgetResult:
        """Decide whether to allow/warn/reject a query before running it.

        ``budget_remaining is None`` means "no budget set" → always ALLOW.
        """
        if budget_remaining is None:
            return BudgetResult(BudgetDecision.ALLOW, estimate)

        mode = self._mode
        decision = BudgetDecision.ALLOW
        message: Optional[str] = None

        if mode == BudgetMode.STRICT:
            if estimate.high > budget_remaining:
                decision = BudgetDecision.REJECT
                message = f"High estimate ${estimate.high:.4f} exceeds budget ${budget_remaining:.4f}"
        elif mode == BudgetMode.BALANCED:
            if estimate.expected > budget_remaining:
                decision = BudgetDecision.REJECT
                message = (
                    f"Expected estimate ${estimate.expected:.4f} exceeds budget "
                    f"${budget_remaining:.4f}"
                )
            elif estimate.high > budget_remaining:
                decision = BudgetDecision.WARN
                message = (
                    f"May exceed budget (expected ${estimate.expected:.4f}, up to "
                    f"${estimate.high:.4f} vs ${budget_remaining:.4f})"
                )
        elif mode == BudgetMode.PERMISSIVE:
            if estimate.expected > budget_remaining:
                decision = BudgetDecision.WARN
                message = f"Likely to exceed budget (expected ${estimate.expected:.4f})"

        if decision != BudgetDecision.ALLOW:
            _emit(decision, mode, estimate, budget_remaining, phase="pre_query")
        return BudgetResult(decision, estimate, message)

    def mid_query_check(
        self, spent_so_far: float, budget_remaining: Optional[float]
    ) -> BudgetResult:
        """Between-stage check — abort GRACEFULLY (partial results), never mid-completion."""
        if budget_remaining is not None and spent_so_far > budget_remaining:
            _emit(BudgetDecision.ABORT_GRACEFULLY, self._mode, None, budget_remaining, phase="mid_query")
            return BudgetResult(
                BudgetDecision.ABORT_GRACEFULLY,
                message=f"Budget exceeded (${spent_so_far:.4f} > ${budget_remaining:.4f}); returning partial results",
            )
        return BudgetResult(BudgetDecision.CONTINUE)
