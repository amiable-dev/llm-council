"""ADR-026 Phase 3: Internal Performance Tracker.

Provides tracking and aggregation of model performance from council sessions,
building an Internal Performance Index with rolling window decay.
"""

import math
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from .store import append_performance_records, read_performance_records
from .types import ModelPerformanceIndex, ModelSessionMetric

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

    Weight = exp(-days_ago / decay_days)

    Args:
        timestamp: ISO 8601 timestamp string
        decay_days: Half-life of decay in days

    Returns:
        Weight between 0 and 1 (1 = most recent, approaching 0 = very old)
    """
    if not timestamp:
        return 1.0

    try:
        record_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        days_ago = (now - record_time).total_seconds() / (24 * 3600)

        # Exponential decay: e^(-days_ago / decay_days)
        return math.exp(-days_ago / decay_days)
    except ValueError:
        # If timestamp parsing fails, give full weight
        return 1.0


class InternalPerformanceTracker:
    """Track and aggregate model performance from council sessions.

    Builds an Internal Performance Index from historical session data,
    using exponential decay to weight recent sessions more heavily.

    Attributes:
        store_path: Path to JSONL storage file
        decay_days: Half-life for exponential decay weighting
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
            decay_days: Half-life for decay weighting. Sessions older than
                       decay_days have reduced weight. Default: 30 days.
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
            session_id: UUID of the council session
            metrics: List of per-model metrics from the session

        Returns:
            Number of records written
        """
        return append_performance_records(metrics, self.store_path)

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

        for record in records:
            weight = _calculate_decay_weight(record.timestamp, self.decay_days)
            total_weight += weight
            weighted_borda_sum += record.borda_score * weight
            if record.parse_success:
                parse_success_count += 1
            latencies.append(record.latency_ms)

        sample_size = len(records)

        # Weighted mean Borda score
        mean_borda = weighted_borda_sum / total_weight if total_weight > 0 else 0.5

        # Parse success rate (unweighted - all samples count equally)
        parse_success_rate = parse_success_count / sample_size if sample_size > 0 else 1.0

        # Latency percentiles
        p50_latency = _calculate_percentile(latencies, 50)
        p95_latency = _calculate_percentile(latencies, 95)

        # Confidence level
        confidence = _determine_confidence_level(sample_size)

        return ModelPerformanceIndex(
            model_id=model_id,
            sample_size=sample_size,
            mean_borda_score=mean_borda,
            p50_latency_ms=p50_latency,
            p95_latency_ms=p95_latency,
            parse_success_rate=parse_success_rate,
            confidence_level=confidence,
        )

    def get_quality_score(self, model_id: str) -> float:
        """Get normalized quality score for model selection.

        Returns a 0-100 score based on mean Borda performance.
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

    def get_all_model_scores(self) -> dict[str, float]:
        """Get quality scores for all tracked models with sufficient data.

        Reads all records and returns mean Borda scores for models
        with at least 10 samples (PRELIMINARY confidence).

        Returns:
            Dict mapping model_id to mean Borda score (0-1)
        """
        all_records = read_performance_records(self.store_path)

        # Group by model_id
        model_records: dict[str, List[ModelSessionMetric]] = {}
        for record in all_records:
            if record.model_id not in model_records:
                model_records[record.model_id] = []
            model_records[record.model_id].append(record)

        # Calculate mean Borda for models with sufficient data
        scores: dict[str, float] = {}
        for model_id, records in model_records.items():
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

        # Calculate percentile: fraction of models this model beats or ties
        scores_list = list(all_scores.values())
        beaten_or_tied = sum(1 for s in scores_list if target_score >= s)
        percentile = beaten_or_tied / len(scores_list)

        return percentile
