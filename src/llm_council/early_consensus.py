"""Early consensus termination for Stage-2 peer review (ADR-044 Phase 2).

Implements ADR-040 Option F: when the leading response's Borda margin is
mathematically unassailable given the reviewers still outstanding, the
remaining reviewer calls can be cancelled (flag ON) — or, in **shadow mode**
(flag OFF, the default), the would-have-terminated point is only logged so
savings are measurable before enabling.

All helpers are soft: they never raise into the council hot path.
"""

from __future__ import annotations

import logging
import os
from typing import Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)


def early_consensus_enabled() -> bool:
    """ADR-044 P2: opt-in early consensus termination (default OFF = shadow)."""
    return os.getenv("LLM_COUNCIL_EARLY_CONSENSUS", "false").lower() in (
        "true",
        "1",
        "yes",
    )


def borda_update(
    points: Dict[str, float], ranking: List[str], num_candidates: int
) -> None:
    """Add one reviewer's Borda contribution: rank i gets (n-1-i) points."""
    for idx, label in enumerate(ranking[:num_candidates]):
        points[label] = points.get(label, 0.0) + float(num_candidates - 1 - idx)


def unassailable_leader(
    points: Dict[str, float], remaining_votes: int, num_candidates: int
) -> Optional[str]:
    """Return the leader's label iff no remaining votes can dethrone it.

    Worst case for the leader: every outstanding reviewer awards it 0 points
    and awards some rival the maximum (num_candidates - 1). The ranking is
    decided iff ``leader > best_rival + remaining * (n - 1)`` — strictly, so
    ties are never "decided".
    """
    if not points or num_candidates < 2:
        return None
    ordered = sorted(points.items(), key=lambda kv: kv[1], reverse=True)
    leader_label, leader_points = ordered[0]
    best_rival = ordered[1][1] if len(ordered) > 1 else 0.0
    max_swing = remaining_votes * (num_candidates - 1)
    if leader_points > best_rival + max_swing:
        return leader_label
    return None


def estimate_reviewers_cost(models: Iterable[str]) -> float:
    """Best-effort USD estimate for a set of reviewer calls (ADR-011 history).

    Sums each model's mean historical cost; unknown-cost models contribute 0.
    Never raises.
    """
    total = 0.0
    try:
        from .performance.integration import get_tracker

        tracker = get_tracker()
        for model_id in models:
            try:
                mean_cost = tracker.get_model_index(model_id).mean_cost_usd
            except Exception:
                mean_cost = None
            if mean_cost:
                total += max(float(mean_cost), 0.0)
    except Exception as exc:  # telemetry-grade: never break the caller
        logger.debug("reviewer cost estimate failed (ignored): %s", exc)
    return round(total, 8)
