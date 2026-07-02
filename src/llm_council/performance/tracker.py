"""ADR-026 Phase 3: Internal Performance Tracker.

Provides tracking and aggregation of model performance from council sessions,
building an Internal Performance Index with rolling window decay.
"""

import math
import os
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from .store import append_performance_records, read_performance_records
from .types import ModelPerformanceIndex, ModelSessionMetric


def cost_aware_selection_enabled() -> bool:
    """ADR-011 Phase 3: opt-in cost-aware selection (default OFF).

    When false, selection behaves exactly as before this phase — cost never
    influences routing. This is the single audited toggle for that behaviour.
    """
    return os.getenv("LLM_COUNCIL_COST_AWARE_SELECTION", "false").lower() in (
        "true",
        "1",
        "yes",
    )

# Default store path
DEFAULT_STORE_PATH = Path.home() / ".llm-council" / "performance_metrics.jsonl"


def _calculate_percentile(values: List[int], percentile: float) -> int:
    """Calculate percentile of a list of values.

    Args:
        values: List of integer values
        percentile: Percentile to calculate (0-100)

    Returns:
        Value at the given percentile
    """
    if not values:
        return 0

    sorted_values = sorted(values)
    n = len(sorted_values)

    if n == 1:
        return sorted_values[0]

    # Linear interpolation between closest ranks
    k = (n - 1) * (percentile / 100.0)
    f = math.floor(k)
    c = math.ceil(k)

    if f == c:
        return sorted_values[int(k)]

    return int(sorted_values[int(f)] + (k - f) * (sorted_values[int(c)] - sorted_values[int(f)]))


def _determine_confidence_level(sample_size: int) -> str:
    """Determine statistical confidence level based on sample size.

    Args:
        sample_size: Number of samples

    Returns:
        Confidence level string: INSUFFICIENT, PRELIMINARY, MODERATE, or HIGH
    """
    if sample_size < 10:
        return "INSUFFICIENT"
    elif sample_size < 30:
        return "PRELIMINARY"
    elif sample_size < 100:
        return "MODERATE"
    else:
        return "HIGH"


def _calculate_decay_weight(timestamp: str, decay_days: int) -> float:
    """Calculate exponential decay weight based on age.

    Uses e-folding decay: ``weight = exp(-days_ago / decay_days)``, so a record
    ``decay_days`` old has weight 1/e (~0.37). NOTE: ``decay_days`` is the decay
    time-constant (mean lifetime), NOT a half-life — the half-life would be
    ``decay_days * ln 2``.

    Args:
        timestamp: ISO 8601 timestamp string
        decay_days: Decay time-constant (e-folding lifetime) in days

    Returns:
        Weight between 0 and 1 (1 = most recent, approaching 0 = very old)
    """
    if not timestamp:
        return 1.0

    if decay_days <= 0:
        return 1.0  # no decay configured -> avoid division by zero

    try:
        record_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        # Treat a naive timestamp as UTC so it is comparable to an aware `now`
        # (otherwise the subtraction raises TypeError).
        if record_time.tzinfo is None:
            record_time = record_time.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        # Clamp to >= 0: a future timestamp (clock skew) would otherwise give a
        # negative age and a weight > 1, over-weighting the record. Treat future
        # records as "now" (weight 1.0).
        days_ago = max((now - record_time).total_seconds() / (24 * 3600), 0.0)

        # Exponential decay: e^(-days_ago / decay_days)
        return math.exp(-days_ago / decay_days)
    except (ValueError, TypeError):
        # If timestamp parsing fails, give full weight
        return 1.0


class InternalPerformanceTracker:
    """Track and aggregate model performance from council sessions.

    Builds an Internal Performance Index from historical session data,
    using exponential decay to weight recent sessions more heavily.

    Attributes:
        store_path: Path to JSONL storage file
        decay_days: e-folding decay time-constant in days (NOT a half-life)
    """

    def __init__(
        self,
        store_path: Optional[Path] = None,
        decay_days: int = 30,
    ):
        """Initialize the tracker.

        Args:
            store_path: Path to JSONL file for storing metrics.
                       Defaults to ~/.llm-council/performance_metrics.jsonl
            decay_days: e-folding decay time-constant in days (NOT a half-life);
                       a session decay_days old has weight 1/e. Default: 30 days.
        """
        self.store_path = store_path or DEFAULT_STORE_PATH
        self.decay_days = decay_days

    def record_session(
        self,
        session_id: str,
        metrics: List[ModelSessionMetric],
    ) -> int:
        """Record performance metrics from a completed council session.

        Args:
            session_id: UUID of the council session — stamped onto every metric
                as the authoritative session id (so records are consistent even
                if a caller left it unset or mismatched).
            metrics: List of per-model metrics from the session

        Returns:
            Number of records written
        """
        # Stamp the authoritative session_id WITHOUT mutating the caller's
        # objects (record_session must have no side effects on its inputs).
        stamped = [replace(metric, session_id=session_id) for metric in metrics]
        return append_performance_records(stamped, self.store_path)

    def get_model_index(self, model_id: str) -> ModelPerformanceIndex:
        """Get aggregated performance index for a model.

        Uses exponential decay to weight recent sessions more heavily.
        Returns cold-start defaults for unknown models.

        Args:
            model_id: Full model identifier (e.g., 'openai/gpt-4o')

        Returns:
            ModelPerformanceIndex with aggregated metrics
        """
        # Read all records for this model
        records = read_performance_records(self.store_path, model_id=model_id)
        return self._index_from_records(model_id, records)

    def _index_from_records(
        self, model_id: str, records: List[ModelSessionMetric]
    ) -> ModelPerformanceIndex:
        """Aggregate an index from already-loaded records (#384: lets callers
        read the store once and group, instead of one read per model)."""
        if not records:
            # Cold start: return neutral defaults
            return ModelPerformanceIndex(
                model_id=model_id,
                sample_size=0,
                mean_borda_score=0.5,  # Neutral
                p50_latency_ms=0,
                p95_latency_ms=0,
                parse_success_rate=1.0,  # Assume success
                confidence_level="INSUFFICIENT",
            )

        # Calculate weighted metrics with decay
        total_weight = 0.0
        weighted_borda_sum = 0.0
        parse_success_count = 0
        latencies: List[int] = []
        # ADR-011 Phase 3: weighted cost, averaged only over records that
        # actually recorded a cost (None costs are excluded, not treated as 0).
        weighted_cost_sum = 0.0
        cost_weight = 0.0

        for record in records:
            weight = _calculate_decay_weight(record.timestamp, self.decay_days)
            total_weight += weight
            weighted_borda_sum += record.borda_score * weight
            if record.parse_success:
                parse_success_count += 1
            latencies.append(record.latency_ms)
            if record.cost_usd is not None:
                weighted_cost_sum += record.cost_usd * weight
                cost_weight += weight

        sample_size = len(records)

        # Weighted mean Borda score
        mean_borda = weighted_borda_sum / total_weight if total_weight > 0 else 0.5

        # Parse success rate: intentionally UNWEIGHTED (unlike decay-weighted
        # Borda) — it is a reliability metric where every historical failure
        # should count in full, not be discounted by age.
        parse_success_rate = parse_success_count / sample_size if sample_size > 0 else 1.0

        # Latency percentiles — intentionally UNWEIGHTED (percentiles are taken
        # over the raw sample set; recency-weighting order statistics is
        # non-standard and would distort p50/p95).
        p50_latency = _calculate_percentile(latencies, 50)
        p95_latency = _calculate_percentile(latencies, 95)

        # Confidence level
        confidence = _determine_confidence_level(sample_size)

        # Weighted mean cost (None if no record carried a cost)
        mean_cost = (weighted_cost_sum / cost_weight) if cost_weight > 0 else None

        return ModelPerformanceIndex(
            model_id=model_id,
            sample_size=sample_size,
            mean_borda_score=mean_borda,
            p50_latency_ms=p50_latency,
            p95_latency_ms=p95_latency,
            parse_success_rate=parse_success_rate,
            confidence_level=confidence,
            mean_cost_usd=mean_cost,
        )

    def get_quality_score(self, model_id: str) -> float:
        """Get normalized quality score for model selection.

        Returns a 0-100 score based on mean Borda performance. This 0-100 scale
        is intentional and selection-facing (consumed by selection.py); it is
        deliberately distinct from ``get_all_model_scores``' raw 0-1 scale used
        by the percentile math — the two must not be compared directly.
        Cold-start models get a neutral score of 50.

        Args:
            model_id: Full model identifier

        Returns:
            Quality score between 0 and 100
        """
        index = self.get_model_index(model_id)

        if index.sample_size == 0:
            return 50.0  # Cold start neutral

        # Convert 0-1 Borda score to 0-100 scale
        return index.mean_borda_score * 100.0

    def get_cost_per_quality(self, model_id: str) -> Optional[float]:
        """Borda-per-dollar for a model (ADR-011 Phase 3), or None if unknown."""
        return self.get_model_index(model_id).quality_per_cost

    def get_all_cost_aware_scores(self) -> dict[str, float]:
        """Quality scores, optionally cost-adjusted (ADR-011 Phase 3).

        DISABLED by default: returns exactly ``get_all_model_scores()`` — the
        only behavioural change is opt-in via ``LLM_COUNCIL_COST_AWARE_SELECTION``.
        This is the SOLE path by which cost may influence selection (audited);
        no other selection code reads cost.

        When enabled, models with a known quality-per-cost are re-scored by that
        value min-max-normalized onto the same 0–1 scale ``get_all_model_scores``
        uses; models with unknown cost keep their quality score (neither rewarded
        nor punished for missing data).
        """
        if not cost_aware_selection_enabled():
            return self.get_all_model_scores()

        # #384: read the store ONCE — the quality pass and the quality-per-cost
        # pass share a single consistent snapshot (was 1+N reads, then 2).
        grouped = self._read_grouped()
        quality = self._scores_from_grouped(grouped)

        qpc = {}
        for model_id in quality:
            index = self._index_from_records(model_id, grouped.get(model_id, []))
            value = index.quality_per_cost
            if value is not None and value > 0:
                qpc[model_id] = value
        if not qpc:
            return quality

        low, high = min(qpc.values()), max(qpc.values())
        if high == low:
            # One cost-known model, or all with identical value-for-money: no
            # differentiation is possible, so keep quality scores rather than
            # collapsing everyone to 0.0.
            return quality
        span = high - low
        result = dict(quality)
        for model_id, value in qpc.items():
            # Same 0–1 scale as the plain quality scores.
            result[model_id] = (value - low) / span
        return result

    def get_all_model_scores(self) -> dict[str, float]:
        """Get quality scores for all tracked models with sufficient data.

        Reads all records and returns mean Borda scores for models
        with at least 10 samples (PRELIMINARY confidence).

        Scale note: this returns the raw mean Borda on a **0–1** scale (used by
        the percentile math), whereas ``get_quality_score`` returns a **0–100**
        selection score. The two scales are intentional and must not be compared
        directly.

        Returns:
            Dict mapping model_id to mean Borda score (0-1)
        """
        grouped = self._read_grouped()
        return self._scores_from_grouped(grouped)

    def _read_grouped(self) -> dict[str, List[ModelSessionMetric]]:
        """Read the store ONCE and group records by model (#384)."""
        grouped: dict[str, List[ModelSessionMetric]] = {}
        for record in read_performance_records(self.store_path):
            grouped.setdefault(record.model_id, []).append(record)
        return grouped

    def _scores_from_grouped(
        self, grouped: dict[str, List[ModelSessionMetric]]
    ) -> dict[str, float]:
        """Mean Borda (0-1) per model with >=10 samples, from a loaded snapshot."""
        scores: dict[str, float] = {}
        for model_id, records in grouped.items():
            if len(records) < 10:  # Need PRELIMINARY confidence
                continue

            # Weighted mean with decay
            total_weight = 0.0
            weighted_sum = 0.0
            for record in records:
                weight = _calculate_decay_weight(record.timestamp, self.decay_days)
                total_weight += weight
                weighted_sum += record.borda_score * weight

            if total_weight > 0:
                scores[model_id] = weighted_sum / total_weight

        return scores

    def get_quality_percentile(self, model_id: str) -> Optional[float]:
        """Calculate percentile rank of model quality among all models.

        Ranks the model's mean Borda score against all other tracked models.
        Returns None if the model has insufficient data.

        For ADR-029 EVALUATION → FULL graduation, models need >= 75th percentile.

        Args:
            model_id: Full model identifier

        Returns:
            Percentile (0-1) where 0.75 = top 25%, None if insufficient data
        """
        # Get all model scores
        all_scores = self.get_all_model_scores()

        # Check if target model has sufficient data
        if model_id not in all_scores:
            return None

        target_score = all_scores[model_id]

        # Single model case
        if len(all_scores) == 1:
            return 1.0

        # Percentile = fraction of OTHER models this model beats or ties.
        # Excluding self matters: including it always adds a self-tie, inflating
        # the rank by 1/N and biasing the ADR-029 graduation gate upward.
        others = [score for other_id, score in all_scores.items() if other_id != model_id]
        if not others:
            return 1.0
        beaten_or_tied = sum(1 for s in others if target_score >= s)
        return beaten_or_tied / len(others)
