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

import json
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
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


DEFAULT_DEPTH_DECISIONS_PATH = Path(".council") / "depth" / "decisions.jsonl"


def _label_model(value: Any) -> Optional[str]:
    """label_to_model values are enhanced dicts ({model, display_index}) or plain strings."""
    if isinstance(value, dict):
        return value.get("model")
    return value if isinstance(value, str) else None


def _css_from(stage2_results: Any, aggregate_rankings: Any) -> Optional[float]:
    """ADR-036 CSS from in-memory Stage-2 data — pure, no model calls.

    Deliberately independent of LLM_COUNCIL_QUALITY_METRICS: that flag governs
    response annotation, not internal control-flow signals (#618 design review).
    """
    try:
        from .quality.consensus import consensus_strength_score

        tuples = [
            (r["model"], r.get("average_position", r.get("borda_score", 0.0)))
            for r in aggregate_rankings
        ]
        if not tuples:
            return None
        return consensus_strength_score(tuples, stage2_results)
    except Exception:
        logger.debug("shadow depth: CSS computation failed", exc_info=True)
        return None


def _counterfactual_mini_css(
    stage2_results: Any, label_to_model: Any, mini_models: List[str]
) -> Optional[float]:
    """Approximate the mini rung's CSS by subsetting the full run's rankings.

    Keeps only the mini models' reviews, restricted to the mini models'
    responses (relative order preserved), and re-runs Borda + CSS on the
    subset. An approximation — rankings were elicited in an N-candidate
    context — but it observes both error directions (see ADR-044 note).
    """
    try:
        from .council_rankings import calculate_aggregate_rankings

        mini_set = set(mini_models)
        sub_l2m = {
            lab: val
            for lab, val in label_to_model.items()
            if _label_model(val) in mini_set
        }
        if len(sub_l2m) < 2:
            return None
        keep_labels = set(sub_l2m)
        sub_entries = []
        for entry in stage2_results:
            if entry.get("model") not in mini_set:
                continue
            parsed = entry.get("parsed_ranking") or {}
            if parsed.get("abstained"):
                continue
            order = [lbl for lbl in parsed.get("ranking", []) if lbl in keep_labels]
            if len(order) < 2:
                continue
            sub_entries.append(
                {"model": entry["model"], "parsed_ranking": {"ranking": order}}
            )
        if not sub_entries:
            return None
        sub_agg = calculate_aggregate_rankings(sub_entries, sub_l2m)
        return _css_from(sub_entries, sub_agg)
    except Exception:
        logger.debug("shadow depth: counterfactual mini CSS failed", exc_info=True)
        return None


def evaluate_and_log_shadow_depth(
    *,
    entry_point: str,
    stage2_results: List[Dict[str, Any]],
    label_to_model: Dict[str, Any],
    aggregate_rankings: List[Dict[str, Any]],
    council_models: List[str],
    confidence: Optional[float] = None,
    path: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    """Shadow-mode depth telemetry (#618): "was full depth necessary?"

    Called by both orchestrators after aggregate rankings exist. Classifies
    the run against the ladder's thresholds, appends one JSON line to
    ``.council/depth/decisions.jsonl`` (numeric signals and model names only,
    never response content), and returns the record. Soft-fail throughout —
    telemetry never breaks a council run, and the response payload is
    unchanged. ``est_saved_usd`` is included only when the ADR-011 estimator
    has real history (a 0.0 from unknown costs is omitted, never fabricated).
    """
    try:
        css_full = _css_from(stage2_results, aggregate_rankings)
        mini_models = models_for_rung(council_models, DepthRung.MINI)
        css_mini = _counterfactual_mini_css(stage2_results, label_to_model, mini_models)

        if css_full is None:
            decision = "signals_unavailable"
        elif len(council_models) <= _MINI_COUNCIL_SIZE:
            decision = "ladder_inapplicable"
        elif css_mini is None:
            decision = "counterfactual_unavailable"
        elif should_escalate(css_mini, confidence):
            decision = "would_escalate"
        elif should_escalate(css_full, confidence):
            decision = "premature_halt_risk"
        else:
            decision = "mini_would_suffice"

        record: Dict[str, Any] = {
            "ts": time.time(),
            "entry_point": entry_point,
            "council_size": len(council_models),
            "mini_council_models": list(mini_models),
            "css_full": css_full,
            "css_mini_counterfactual": css_mini,
            "confidence": confidence,
            "decision": decision,
            "hypothetical_saved_models": (
                len(council_models) - len(mini_models)
                if decision == "mini_would_suffice"
                else 0
            ),
            "extra_stage2_reviews_if_escalated": (
                len(mini_models) if decision == "would_escalate" else 0
            ),
        }
        if decision == "mini_would_suffice":
            try:
                from .budget import CostEstimator

                saved = [m for m in council_models if m not in set(mini_models)]
                est = CostEstimator().estimate(saved)
                if est.expected > 0:
                    record["est_saved_usd"] = est.expected
            except Exception:
                logger.debug("shadow depth: saved-cost estimate failed", exc_info=True)

        p = path if path is not None else DEFAULT_DEPTH_DECISIONS_PATH
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("a") as fh:
                fh.write(json.dumps(record) + "\n")
        except Exception as exc:
            logger.debug("shadow depth decision log failed (%s)", exc)
        return record
    except Exception:
        logger.debug("shadow depth evaluation failed", exc_info=True)
        return None


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
