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

_TRUTHY = ("true", "1", "yes", "on")

# Explicit overrides. `None` means "resolve from the environment on every
# call".
#
# #693: these used to BE the resolved values, computed at import time. That
# made `LLM_COUNCIL_PERFORMANCE_STORE` unsettable from a test — collection
# imports this module before any test body runs, so the env var was read
# before anyone could set it — and the suite appended 1,868 fixture records
# to the operator's real `~/.llm-council/performance_metrics.jsonl`. Those
# rows carry `cost_usd: null`, so a third of the file looked like a cost
# capture failure and the investigation went after the wrong defect.
#
# They survive as overrides rather than being deleted because patching them
# directly is an established pattern in this suite and a legitimate embedding
# hook. An override wins; absent one, the environment is read fresh.
PERFORMANCE_TRACKING_ENABLED: Optional[bool] = None
PERFORMANCE_STORE_PATH: Optional[Path] = None


def tracking_enabled() -> bool:
    """Whether to persist performance records, resolved per call."""
    if PERFORMANCE_TRACKING_ENABLED is not None:
        return bool(PERFORMANCE_TRACKING_ENABLED)
    return os.getenv("LLM_COUNCIL_PERFORMANCE_TRACKING", "true").strip().lower() in _TRUTHY


def resolve_store_path() -> Path:
    """Where records are appended, resolved per call.

    A blank or whitespace-only `LLM_COUNCIL_PERFORMANCE_STORE` falls back to
    the default rather than to a relative path: an empty string is a
    configuration mistake, and treating it as `./performance_metrics.jsonl`
    would scatter records through whatever directory the process started in.
    """
    if PERFORMANCE_STORE_PATH is not None:
        return Path(PERFORMANCE_STORE_PATH).expanduser()
    raw = os.getenv("LLM_COUNCIL_PERFORMANCE_STORE", "").strip()
    return Path(raw).expanduser() if raw else DEFAULT_STORE_PATH

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

    if not tracking_enabled():
        return None

    if _tracker_instance is None:
        _tracker_instance = InternalPerformanceTracker(store_path=resolve_store_path())

    return _tracker_instance


def _extract_parse_success(
    model_id: str,
    stage2_results: Optional[List[Dict[str, Any]]],
) -> Optional[bool]:
    """Extract parse success indicator from stage2 results.

    A model is considered to have parsed successfully if:
    - It has a non-empty parsed_ranking
    - It is not marked as abstained

    Args:
        model_id: Model to check
        stage2_results: List of stage2 evaluation results

    Returns:
        True if the ranking parsed, False if it did not, or None when peer
        review never reached this model (no stage-2 data for it at all).
    """
    if not stage2_results:
        # #692 gate round 2: this was the SECOND `return True`, and the one on
        # the default path — `stage2_results` is optional and defaults to None
        # in `persist_session_performance_data`, so any caller omitting it
        # fabricated a parse success for every model in the session. Round 1
        # fixed only the tail branch; fixing one of two exits left the defect
        # exactly where it did the most damage.
        return None

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

    # #692 gate: a model absent from stage 2 did not "succeed" — peer review
    # never reached it. Returning True here systematically inflated the
    # parse-success rate once #692 started recording unranked models, which is
    # the same fabrication this change fixes for borda_score.
    return None


def persist_session_performance_data(
    session_id: str,
    model_statuses: Dict[str, Dict[str, Any]],
    aggregate_rankings: Dict[str, Dict[str, Any]],
    stage2_results: Optional[List[Dict[str, Any]]] = None,
    usage_by_model: Optional[Dict[str, Dict[str, Any]]] = None,
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
        usage_by_model: Optional ADR-011 per-model usage (``metadata['usage']
            ['by_model']``). Drives ``cost_usd``, which stays None unless
            that model's entry reports ``cost_known`` — a null is the
            absence of a measurement, never a $0 one.

    Returns:
        Number of records written (0 if tracking disabled)
    """
    if not tracking_enabled():
        return 0

    timestamp = datetime.now(timezone.utc).isoformat()
    records: List[ModelSessionMetric] = []

    # #692: every model we saw, not only the ranked ones. A model that answered
    # and was billed but never reached peer review (a partial or timed-out run)
    # still has a cost, and a cost that is not recorded cannot be reconciled
    # against an invoice. Its Borda score is None rather than 0.0 — see below.
    seen = list(aggregate_rankings) + [m for m in model_statuses if m not in aggregate_rankings]

    for model_id in seen:
        ranking_info = aggregate_rankings.get(model_id) or {}
        # `or {}` not a get-default: a key present with a null value returns
        # None, and `.get` on that raises. Same trap as #594/#677/#680.
        status_info = model_statuses.get(model_id) or {}

        # Extract metrics
        latency_ms = status_info.get("latency_ms")
        # Unranked => None, never 0.0. A zero says "peer review placed this
        # model last"; a null says "peer review never saw it".
        borda_score = ranking_info.get("borda_score") if ranking_info else None
        parse_success = _extract_parse_success(model_id, stage2_results)

        # ADR-011 Phase 3: record cost only when it was actually reported
        # (cost_known), so unknown costs stay None rather than a phantom $0.
        cost_usd = None
        if usage_by_model:
            model_usage = usage_by_model.get(model_id) or {}
            if model_usage.get("cost_known"):
                cost_usd = model_usage.get("cost_usd")

        record = ModelSessionMetric(
            session_id=session_id,
            model_id=model_id,
            timestamp=timestamp,
            latency_ms=latency_ms,
            borda_score=borda_score,
            parse_success=parse_success,
            cost_usd=cost_usd,
        )
        records.append(record)

    if not records:
        return 0

    count = append_performance_records(records, resolve_store_path())
    logger.debug(f"Persisted {count} performance records for session {session_id}")

    return count
