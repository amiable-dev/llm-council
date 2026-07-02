"""Graduated deliberation depth — the ADR-044 Phase 3 cascade (default OFF).

Extends the ADR-020 Tier-1 binary fast path (single model vs. full council)
to a graduated ladder: ``SINGLE → MINI (3) → FULL``. Escalation is gated on
consensus signals (ADR-036 CSS + verdict confidence) and, optionally, vetoed
by the opt-in budget enforcer (ADR-011 Phase 4) — auditably, never silently.

Deeper rungs use PREFIX-SUPERSET model sets, so every response collected at a
shallow rung is reusable as a Stage-1 member of the deeper pass: escalation
only ever *adds* models, never re-calls one.

This module is the decision engine + opt-in hook; orchestrators call
``plan_escalation`` between passes. It deliberately does not rewire
``run_full_council``'s hot path (bounded-module pattern, cf. ``budget/``).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Escalate when consensus or confidence is BELOW these (known) values.
DEFAULT_CSS_THRESHOLD = 0.7
DEFAULT_CONFIDENCE_THRESHOLD = 0.7

_MINI_COUNCIL_SIZE = 3


class DepthRung(str, Enum):
    SINGLE = "single"
    MINI = "mini"
    FULL = "full"


def graduated_depth_enabled() -> bool:
    """ADR-044 P3: opt-in graduated deliberation depth (default OFF)."""
    return os.getenv("LLM_COUNCIL_GRADUATED_DEPTH", "false").lower() in (
        "true",
        "1",
        "yes",
    )


def next_rung(rung: DepthRung) -> Optional[DepthRung]:
    """The rung above ``rung``, or None at full depth."""
    ladder = [DepthRung.SINGLE, DepthRung.MINI, DepthRung.FULL]
    idx = ladder.index(rung)
    return ladder[idx + 1] if idx + 1 < len(ladder) else None


def models_for_rung(all_models: List[str], rung: DepthRung) -> List[str]:
    """Model set for a rung — prefix subsets, so deeper ⊇ shallower (reuse)."""
    if rung == DepthRung.SINGLE:
        return all_models[:1]
    if rung == DepthRung.MINI:
        return all_models[:_MINI_COUNCIL_SIZE]
    return list(all_models)


def should_escalate(
    css: Optional[float],
    confidence: Optional[float],
    css_threshold: float = DEFAULT_CSS_THRESHOLD,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> bool:
    """Escalate iff a KNOWN signal is below threshold.

    Unknown (None) signals never trigger escalation: extra spend must be
    justified by evidence of weak consensus, not by missing data.
    """
    if css is not None and css < css_threshold:
        return True
    if confidence is not None and confidence < confidence_threshold:
        return True
    return False


@dataclass(frozen=True)
class EscalationPlan:
    """Outcome of a between-pass depth decision."""

    decision: str  # "escalate" | "stop" | "vetoed"
    reason: str
    next_rung: Optional[DepthRung] = None
    added_models: List[str] = field(default_factory=list)
    estimate: Optional[Any] = None  # budget.CostEstimate when priced


def plan_escalation(
    all_models: List[str],
    current_rung: DepthRung,
    css: Optional[float],
    confidence: Optional[float],
    budget_remaining: Optional[float] = None,
    estimator: Any = None,
    enforcer: Any = None,
) -> EscalationPlan:
    """Decide whether to escalate one rung (the ADR-044 P3 opt-in hook).

    - Flag off ⇒ stop (``disabled``): behaviour identical to today.
    - Strong consensus ⇒ stop (``consensus_sufficient``).
    - At full depth ⇒ stop (``at_full_depth``).
    - Otherwise price the ADDED models (ADR-011 estimator); if budget
      enforcement is on and the enforcer rejects, the escalation is
      **vetoed** — the enforcer emits its own auditable budget LayerEvent,
      and the caller stays at the current depth (never a silent downgrade).
    - An approved escalation emits ``L2_DELIBERATION_ESCALATION`` with the
      signals and the added models.
    """
    if not graduated_depth_enabled():
        return EscalationPlan(decision="stop", reason="disabled")

    if not should_escalate(css, confidence):
        return EscalationPlan(decision="stop", reason="consensus_sufficient")

    target = next_rung(current_rung)
    if target is None:
        return EscalationPlan(decision="stop", reason="at_full_depth")

    current_set = set(models_for_rung(all_models, current_rung))
    added = [m for m in models_for_rung(all_models, target) if m not in current_set]

    estimate = None
    try:
        if estimator is None:
            from .budget import CostEstimator

            estimator = CostEstimator()
        estimate = estimator.estimate(added)
    except Exception as exc:  # pricing is best-effort
        logger.debug("escalation estimate failed (ignored): %s", exc)

    if enforcer is not None and estimate is not None:
        try:
            from .budget import BudgetDecision, budget_enforcement_enabled

            if budget_enforcement_enabled():
                result = enforcer.pre_query_check(estimate, budget_remaining)
                if result.decision == BudgetDecision.REJECT:
                    # The enforcer already emitted its auditable budget event.
                    return EscalationPlan(
                        decision="vetoed",
                        reason=f"budget: {result.message}",
                        estimate=estimate,
                    )
        except Exception as exc:
            logger.debug("budget veto check failed (ignored): %s", exc)

    try:
        from .layer_contracts import LayerEventType, emit_layer_event

        emit_layer_event(
            LayerEventType.L2_DELIBERATION_ESCALATION,
            {
                "reason": "graduated_depth",
                "from_rung": current_rung.value,
                "to_rung": target.value,
                "added_models": added,
                "css": css,
                "confidence": confidence,
                "est_cost_usd": getattr(estimate, "expected", None),
            },
            layer_from="L2",
            layer_to="L3",
        )
    except Exception as exc:  # observability never blocks the decision
        logger.debug("escalation event emit failed (ignored): %s", exc)

    return EscalationPlan(
        decision="escalate",
        reason="weak_consensus",
        next_rung=target,
        added_models=added,
        estimate=estimate,
    )


_NUMERIC_KEYS = ("prompt_tokens", "completion_tokens", "total_tokens", "cost_usd", "cached_tokens")


def _merge_numeric(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key in _NUMERIC_KEYS:
        val = (a.get(key, 0) or 0) + (b.get(key, 0) or 0)
        if key in a or key in b:
            out[key] = val
    if a.get("cost_known") or b.get("cost_known"):
        out["cost_known"] = True
    return out


def merge_usage_summaries(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """Merge two ``metadata["usage"]`` summaries across cascade rungs.

    Per-stage and per-model entries are summed key-wise; ``cost_known`` uses
    OR-semantics (a genuine cost anywhere makes the merged cost known).
    """
    merged: Dict[str, Any] = {"by_stage": {}, "by_model": {}, "total": {}}
    for section in ("by_stage", "by_model"):
        keys = set((a.get(section) or {}).keys()) | set((b.get(section) or {}).keys())
        for key in keys:
            merged[section][key] = _merge_numeric(
                (a.get(section) or {}).get(key, {}),
                (b.get(section) or {}).get(key, {}),
            )
    merged["total"] = _merge_numeric(a.get("total") or {}, b.get("total") or {})
    return merged
