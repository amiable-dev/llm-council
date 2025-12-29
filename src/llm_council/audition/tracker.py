"""AuditionTracker for ADR-029 Model Audition Mechanism.

This module provides the main tracker class for managing model audition state:
- In-memory cache for fast lookups
- JSONL persistence for durability
- State transition management
- Singleton factory pattern
- Observability events (ADR-029 Phase 8)

Example:
    >>> from llm_council.audition.tracker import get_audition_tracker
    >>> tracker = get_audition_tracker()
    >>> status = tracker.record_session("openai/gpt-5", success=True)
    >>> tracker.check_transitions(criteria)
"""

import logging
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from .store import append_audition_record, read_audition_records
from .types import (
    AuditionCriteria,
    AuditionState,
    AuditionStatus,
    evaluate_state_transition,
    record_session_result,
)


def _emit_audition_event(event_type_name: str, data: dict) -> None:
    """Emit an audition layer event.

    Args:
        event_type_name: Name of the LayerEventType (without prefix)
        data: Event data dictionary
    """
    try:
        from llm_council.layer_contracts import LayerEventType, emit_layer_event

        event_type = getattr(LayerEventType, event_type_name, None)
        if event_type:
            emit_layer_event(event_type, data)
    except ImportError:
        pass  # layer_contracts not available


logger = logging.getLogger(__name__)

# Default store path
DEFAULT_STORE_PATH = "~/.llm-council/audition_status.jsonl"


class AuditionTracker:
    """Tracks model audition state with persistence.

    Maintains an in-memory cache of model statuses backed by JSONL persistence.
    Provides methods for recording sessions, checking transitions, and
    updating quality percentiles.

    Attributes:
        _cache: In-memory cache mapping model_id to AuditionStatus
        _store_path: Path to JSONL persistence file (None for no persistence)
    """

    def __init__(self, store_path: Optional[str] = None):
        """Initialize tracker with optional persistence.

        Args:
            store_path: Path to JSONL file. If None, operates in memory only.
                       Defaults to None (no persistence) for easy testing.
        """
        self._store_path = store_path
        self._cache: Dict[str, AuditionStatus] = {}

        # Load existing records if store exists
        if store_path:
            self._load_from_store()

    def _load_from_store(self) -> None:
        """Load existing records from JSONL store into cache."""
        if not self._store_path:
            return

        try:
            records = read_audition_records(self._store_path)
            for status in records:
                self._cache[status.model_id] = status
            if records:
                logger.debug(f"Loaded {len(records)} audition records from store")
        except Exception as e:
            logger.warning(f"Failed to load audition store: {e}")

    def _persist(self, status: AuditionStatus) -> None:
        """Persist status to JSONL store."""
        if not self._store_path:
            return

        try:
            append_audition_record(status, self._store_path)
        except Exception as e:
            logger.error(f"Failed to persist audition status: {e}")

    def get_status(self, model_id: str) -> Optional[AuditionStatus]:
        """Get current audition status for a model.

        Args:
            model_id: Full model identifier (e.g., "openai/gpt-5-mini")

        Returns:
            AuditionStatus if model is tracked, None otherwise
        """
        return self._cache.get(model_id)

    def record_session(
        self,
        model_id: str,
        success: bool,
        criteria: Optional[AuditionCriteria] = None,
    ) -> AuditionStatus:
        """Record a session result for a model.

        If the model is not tracked, creates a new status in SHADOW state.
        Updates session count, timestamps, and failure tracking.
        When criteria is provided, also checks and applies state transitions.

        Args:
            model_id: Full model identifier
            success: True if session completed successfully
            criteria: Optional criteria for automatic transition checking

        Returns:
            Updated AuditionStatus
        """
        current = self._cache.get(model_id)

        if current is None:
            # New model - create initial SHADOW status
            now = datetime.utcnow()
            current = AuditionStatus(
                model_id=model_id,
                state=AuditionState.SHADOW,
                session_count=0,
                first_seen=now,
                last_seen=now,
            )

        old_state = current.state

        # Record session result
        updated = record_session_result(current, success)

        # Emit failure event if session failed
        if not success:
            _emit_audition_event(
                "AUDITION_FAILURE_RECORDED",
                {
                    "model_id": model_id,
                    "state": updated.state.value,
                    "consecutive_failures": updated.consecutive_failures,
                },
            )

        # Check for state transitions when criteria provided
        if criteria is not None:
            new_state = evaluate_state_transition(updated, criteria)
            if new_state is not None:
                # Apply transition
                updated = AuditionStatus(
                    model_id=updated.model_id,
                    state=new_state,
                    session_count=updated.session_count,
                    first_seen=updated.first_seen,
                    last_seen=updated.last_seen,
                    consecutive_failures=(
                        0 if new_state == AuditionState.SHADOW else updated.consecutive_failures
                    ),
                    quality_percentile=updated.quality_percentile,
                    quarantine_until=updated.quarantine_until,
                )

                # Emit transition event
                _emit_audition_event(
                    "AUDITION_STATE_TRANSITION",
                    {
                        "model_id": model_id,
                        "from_state": old_state.value,
                        "to_state": new_state.value,
                    },
                )

                # Emit specific events for notable transitions
                if new_state == AuditionState.QUARANTINE:
                    _emit_audition_event(
                        "AUDITION_QUARANTINE_TRIGGERED",
                        {
                            "model_id": model_id,
                            "from_state": old_state.value,
                            "cooldown_hours": criteria.quarantine_cooldown_hours,
                        },
                    )
                elif new_state == AuditionState.FULL:
                    _emit_audition_event(
                        "AUDITION_GRADUATION_COMPLETE",
                        {
                            "model_id": model_id,
                            "quality_percentile": updated.quality_percentile,
                        },
                    )

                logger.info(f"Model {model_id} transitioned: {old_state.value} → {new_state.value}")

        # Update cache and persist
        self._cache[model_id] = updated
        self._persist(updated)

        return updated

    def update_quality_percentile(
        self,
        model_id: str,
        percentile: float,
    ) -> None:
        """Update quality percentile for a model.

        Does nothing if the model is not tracked.

        Args:
            model_id: Full model identifier
            percentile: Quality percentile (0-1)
        """
        current = self._cache.get(model_id)
        if current is None:
            logger.debug(f"Ignoring quality update for untracked model: {model_id}")
            return

        # Create updated status with new percentile
        updated = AuditionStatus(
            model_id=current.model_id,
            state=current.state,
            session_count=current.session_count,
            first_seen=current.first_seen,
            last_seen=current.last_seen,
            consecutive_failures=current.consecutive_failures,
            quality_percentile=percentile,
            quarantine_until=current.quarantine_until,
        )

        self._cache[model_id] = updated
        self._persist(updated)

    def check_transitions(
        self,
        criteria: AuditionCriteria,
    ) -> List[Tuple[str, AuditionState, AuditionState]]:
        """Check and apply state transitions for all tracked models.

        Evaluates each tracked model against criteria and applies
        any warranted state transitions.

        Args:
            criteria: Transition criteria thresholds

        Returns:
            List of (model_id, from_state, to_state) tuples for models that transitioned
        """
        transitions: List[Tuple[str, AuditionState, AuditionState]] = []

        for model_id, status in list(self._cache.items()):
            new_state = evaluate_state_transition(status, criteria)

            if new_state is not None:
                old_state = status.state
                transitions.append((model_id, old_state, new_state))

                # Apply transition
                updated = AuditionStatus(
                    model_id=status.model_id,
                    state=new_state,
                    session_count=status.session_count,
                    first_seen=status.first_seen,
                    last_seen=status.last_seen,
                    consecutive_failures=(
                        0 if new_state == AuditionState.SHADOW else status.consecutive_failures
                    ),
                    quality_percentile=status.quality_percentile,
                    quarantine_until=status.quarantine_until,
                )

                self._cache[model_id] = updated
                self._persist(updated)

                logger.info(f"Model {model_id} transitioned: {old_state.value} → {new_state.value}")

        return transitions

    def get_all_statuses(self) -> List[AuditionStatus]:
        """Get all tracked model statuses.

        Returns:
            List of AuditionStatus for all tracked models
        """
        return list(self._cache.values())


# Singleton instance
_tracker: Optional[AuditionTracker] = None


def get_audition_tracker(store_path: Optional[str] = None) -> AuditionTracker:
    """Get the singleton AuditionTracker instance.

    Creates a new tracker on first call, returns existing instance thereafter.
    The store_path is only used on first call.

    Args:
        store_path: Optional path to JSONL store (only used on first call)

    Returns:
        The global AuditionTracker instance
    """
    global _tracker
    if _tracker is None:
        # Use environment variable or default if no path specified
        path = store_path or os.environ.get(
            "LLM_COUNCIL_AUDITION_STORE",
            DEFAULT_STORE_PATH,
        )
        _tracker = AuditionTracker(store_path=path)
    return _tracker


def _reset_tracker() -> None:
    """Reset the singleton tracker (for testing only)."""
    global _tracker
    _tracker = None
