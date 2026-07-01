"""Types for opt-in budget enforcement (ADR-011 Phase 4)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class BudgetMode(str, Enum):
    """How strictly a pre-query budget check rejects.

    STRICT      — reject if even the HIGH estimate exceeds the budget.
    BALANCED    — reject if the EXPECTED estimate exceeds; warn if HIGH exceeds.
    PERMISSIVE  — never reject up front; warn if EXPECTED exceeds.
    """

    STRICT = "strict"
    BALANCED = "balanced"
    PERMISSIVE = "permissive"


class BudgetDecision(str, Enum):
    ALLOW = "allow"
    WARN = "warn"
    REJECT = "reject"
    # Between-stage decisions (mid-query): never abort a completion in flight.
    CONTINUE = "continue"
    ABORT_GRACEFULLY = "abort_gracefully"


@dataclass(frozen=True)
class CostEstimate:
    """A pre-query cost estimate range in USD (ADR-011 §5)."""

    low: float
    expected: float
    high: float


@dataclass(frozen=True)
class BudgetResult:
    """Outcome of a budget check."""

    decision: BudgetDecision
    estimate: Optional[CostEstimate] = None
    message: Optional[str] = None
