"""ADR-026 Phase 3: Council Integration for Performance Tracking.

Provides integration points for extracting metrics from council sessions
and persisting them using the InternalPerformanceTracker.
"""

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .store import append_performance_records
from .tracker import DEFAULT_STORE_PATH, InternalPerformanceTracker
from .types import ModelSessionMetric

logger = logging.getLogger(__name__)

# Configuration (can be overridden in config.py later)
PERFORMANCE_TRACKING_ENABLED = os.getenv("LLM_COUNCIL_PERFORMANCE_TRACKING", "true").lower() in (
    "true",
    "1",
    "yes",
    "on",
)

PERFORMANCE_STORE_PATH = Path(
    os.getenv("LLM_COUNCIL_PERFORMANCE_STORE", str(DEFAULT_STORE_PATH))
).expanduser()

# Singleton tracker instance
_tracker_instance: Optional[InternalPerformanceTracker] = None


def _reset_tracker_singleton() -> None:
    """Reset the singleton tracker (for testing)."""
    global _tracker_instance
    _tracker_instance = None


def get_tracker() -> Optional[InternalPerformanceTracker]:
    """Get the singleton InternalPerformanceTracker instance.

    Returns None if performance tracking is disabled.

    Returns:
        InternalPerformanceTracker instance or None if disabled
    """
    global _tracker_instance

    if not PERFORMANCE_TRACKING_ENABLED:
        return None

    if _tracker_instance is None:
        _tracker_instance = InternalPerformanceTracker(store_path=PERFORMANCE_STORE_PATH)

    return _tracker_instance


def _extract_parse_success(
    model_id: str,
    stage2_results: Optional[List[Dict[str, Any]]],
) -> bool:
    """Extract parse success indicator from stage2 results.

    A model is considered to have parsed successfully if:
    - It has a non-empty parsed_ranking
    - It is not marked as abstained

    Args:
        model_id: Model to check
        stage2_results: List of stage2 evaluation results

    Returns:
        True if parse was successful, False otherwise
    """
    if not stage2_results:
        return True  # Default to success if no stage2 data

    for result in stage2_results:
        if result.get("model") == model_id:
            # Check for abstained flag
            if result.get("abstained", False):
                return False
            # Check for empty parsed_ranking
            parsed = result.get("parsed_ranking", [])
            if not parsed:
                return False
            return True

    # Model not found in stage2 results - default to success
    return True


def persist_session_performance_data(
    session_id: str,
    model_statuses: Dict[str, Dict[str, Any]],
    aggregate_rankings: Dict[str, Dict[str, Any]],
    stage2_results: Optional[List[Dict[str, Any]]] = None,
) -> int:
    """Persist performance metrics from a completed council session.

    Extracts latency, Borda score, and parse success from session data
    and appends to the performance metrics JSONL store.

    This is the main integration point called from council.py after
    Stage 2 rankings are computed.

    Args:
        session_id: UUID of the council session
        model_statuses: Dict of model_id -> status info with latency_ms
        aggregate_rankings: Dict of model_id -> ranking info with borda_score
        stage2_results: Optional list of stage2 evaluation results

    Returns:
        Number of records written (0 if tracking disabled)
    """
    if not PERFORMANCE_TRACKING_ENABLED:
        return 0

    timestamp = datetime.now(timezone.utc).isoformat()
    records: List[ModelSessionMetric] = []

    # Only record models that have both status and rankings
    for model_id, ranking_info in aggregate_rankings.items():
        status_info = model_statuses.get(model_id, {})

        # Extract metrics
        latency_ms = status_info.get("latency_ms", 0)
        borda_score = ranking_info.get("borda_score", 0.0)
        parse_success = _extract_parse_success(model_id, stage2_results)

        record = ModelSessionMetric(
            session_id=session_id,
            model_id=model_id,
            timestamp=timestamp,
            latency_ms=latency_ms,
            borda_score=borda_score,
            parse_success=parse_success,
        )
        records.append(record)

    if not records:
        return 0

    count = append_performance_records(records, PERFORMANCE_STORE_PATH)
    logger.debug(f"Persisted {count} performance records for session {session_id}")

    return count
