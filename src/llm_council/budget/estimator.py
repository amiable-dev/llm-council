"""Pre-query cost estimation (ADR-011 §5, Phase 4).

Estimates a council query's USD cost BEFORE running it, from the per-model cost
history in the performance index (ADR-011 Phase 3). Returns a low/expected/high
range so the enforcer can choose a risk posture. When no cost history exists
(cold start) the estimate is zero — an honest "unknown", which the enforcer
treats as "allow" rather than guessing.
"""

from __future__ import annotations

from typing import Any, List, Optional

from .types import CostEstimate

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
            except Exception:
                mean_cost = None
            if mean_cost:
                expected += mean_cost
        return CostEstimate(
            low=round(expected * _LOW_FACTOR, 8),
            expected=round(expected, 8),
            high=round(expected * _HIGH_FACTOR, 8),
        )
