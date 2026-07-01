"""Pre-query cost estimation (ADR-011 §5, Phase 4).

Estimates a council query's USD cost BEFORE running it, from the per-model cost
history in the performance index (ADR-011 Phase 3). Returns a low/expected/high
range so the enforcer can choose a risk posture. When no cost history exists
(cold start) the estimate is zero — an honest "unknown", which the enforcer
treats as "allow" rather than guessing.

Posture: estimation is **best-effort and fail-open** — if the tracker is
unavailable the estimate is 0 and the (opt-in) gate allows the query rather than
blocking all traffic. This is deliberate for an opt-in guard; a hard
fail-closed budget gate belongs to a future enforcement tier, not this default.
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

from .types import CostEstimate

logger = logging.getLogger(__name__)

# ADR-011 §5: spread around the expected estimate (≈ p25 low / p95 high buffers).
_LOW_FACTOR = 0.6
_HIGH_FACTOR = 1.5


class CostEstimator:
    """Estimate query cost from per-model performance-index cost history."""

    def __init__(self, tracker: Any = None) -> None:
        self._tracker = tracker  # InternalPerformanceTracker; injectable for tests

    def _get_tracker(self) -> Any:
        if self._tracker is not None:
            return self._tracker
        from ..performance.integration import get_tracker

        return get_tracker()

    def estimate(self, models: List[str]) -> CostEstimate:
        """Return a low/expected/high USD estimate for a query over ``models``.

        Only models with a known mean cost contribute; unknown-cost models add
        nothing (never a guessed value).
        """
        tracker = self._get_tracker()
        expected = 0.0
        for model_id in models:
            try:
                mean_cost: Optional[float] = tracker.get_model_index(model_id).mean_cost_usd
            except Exception as exc:
                # Estimation is best-effort; a tracker failure must not crash it,
                # but it is logged rather than silently swallowed.
                logger.debug("cost estimate: %r lookup failed (ignored): %s", model_id, exc)
                mean_cost = None
            # A known $0 (free/local) contributes 0 but is NOT "unknown".
            # Clamp defensively: a cost must never be negative.
            if mean_cost is not None:
                expected += max(mean_cost, 0.0)
        return CostEstimate(
            low=round(expected * _LOW_FACTOR, 8),
            expected=round(expected, 8),
            high=round(expected * _HIGH_FACTOR, 8),
        )
