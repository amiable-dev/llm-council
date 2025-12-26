"""Core Types for ADR-029 Model Audition Mechanism.

This module defines the state machine and data structures for model audition:
- AuditionState: Lifecycle states (SHADOW → PROBATION → EVALUATION → FULL)
- AuditionStatus: Tracks a model's audition progress
- AuditionCriteria: Volume-based graduation criteria

Example:
    >>> from llm_council.audition.types import AuditionState, AuditionStatus
    >>> status = AuditionStatus(model_id="openai/gpt-5", state=AuditionState.SHADOW)
    >>> status.session_count
    0
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class AuditionState(Enum):
    """Model audition lifecycle states.

    State machine per ADR-029:
        SHADOW (30%) --[10 sessions, 3+ days]--> PROBATION (30%)
        PROBATION (30%) --[25 sessions, 7+ days]--> EVALUATION (30-100%)
        EVALUATION --[50 sessions, quality ≥75th percentile]--> FULL (100%)
        Any --[failures exceed threshold]--> QUARANTINE (0%)
        QUARANTINE --[24h cooldown]--> SHADOW
    """

    SHADOW = "shadow"  # Non-binding votes, 30% selection weight
    PROBATION = "probation"  # Limited selection, 30% weight
    EVALUATION = "evaluation"  # Weighted 30-100% (progressive)
    FULL = "full"  # Normal selection, 100% weight
    QUARANTINE = "quarantine"  # Excluded, 0% weight


@dataclass
class AuditionStatus:
    """Tracks a model's audition progress.

    Attributes:
        model_id: Full model identifier (e.g., "openai/gpt-5-mini")
        state: Current audition state
        session_count: Number of council sessions participated in
        first_seen: When the model was first discovered
        last_seen: When the model was last used in a session
        consecutive_failures: Count of consecutive errors/timeouts
        quality_percentile: Borda score percentile among all models (0-1)
        quarantine_until: When quarantine expires (if in QUARANTINE)
    """

    model_id: str
    state: AuditionState
    session_count: int = 0
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    consecutive_failures: int = 0
    quality_percentile: Optional[float] = None
    quarantine_until: Optional[datetime] = None

    @property
    def days_tracked(self) -> Optional[int]:
        """Calculate days since first seen.

        Returns:
            Number of days between first_seen and now, or None if first_seen not set.
        """
        if self.first_seen is None:
            return None
        delta = datetime.utcnow() - self.first_seen
        return delta.days


@dataclass(frozen=True)
class AuditionCriteria:
    """Criteria for state transitions (volume-based).

    All thresholds are configurable per ADR-029 requirements.
    Frozen to ensure immutability.

    Attributes:
        shadow_min_sessions: Sessions needed to exit SHADOW (default: 10)
        shadow_min_days: Days needed to exit SHADOW (default: 3)
        shadow_max_failures: Max failures before quarantine from SHADOW (default: 3)
        probation_min_sessions: Sessions needed to exit PROBATION (default: 25)
        probation_min_days: Days needed to exit PROBATION (default: 7)
        probation_max_failures: Max failures before quarantine from PROBATION (default: 5)
        eval_min_sessions: Sessions needed to exit EVALUATION (default: 50)
        eval_min_quality_percentile: Quality threshold for FULL (default: 0.75)
        quarantine_cooldown_hours: Cooldown before retry from QUARANTINE (default: 24)
    """

    shadow_min_sessions: int = 10
    shadow_min_days: int = 3
    shadow_max_failures: int = 3
    probation_min_sessions: int = 25
    probation_min_days: int = 7
    probation_max_failures: int = 5
    eval_min_sessions: int = 50
    eval_min_quality_percentile: float = 0.75
    quarantine_cooldown_hours: int = 24


def evaluate_state_transition(
    status: AuditionStatus,
    criteria: AuditionCriteria,
) -> Optional[AuditionState]:
    """Determine if model should transition states (volume-based).

    Evaluates the model's current status against criteria to determine
    if a state transition should occur. Returns the new state if transition
    is warranted, None otherwise.

    State machine per ADR-029:
        SHADOW → PROBATION: 10 sessions + 3 days
        PROBATION → EVALUATION: 25 sessions + 7 days
        EVALUATION → FULL: 50 sessions + quality >= 75th percentile
        Any → QUARANTINE: consecutive failures exceed threshold
        QUARANTINE → SHADOW: cooldown expired

    Args:
        status: Current audition status of the model
        criteria: Transition criteria thresholds

    Returns:
        New AuditionState if transition should occur, None otherwise
    """
    # Check quarantine expiry first (highest priority for QUARANTINE state)
    if status.state == AuditionState.QUARANTINE:
        if status.quarantine_until is not None:
            now = datetime.utcnow()
            if now >= status.quarantine_until:
                return AuditionState.SHADOW
        return None

    # Check failure thresholds (can trigger from any non-FULL state)
    if status.state == AuditionState.SHADOW:
        if status.consecutive_failures > criteria.shadow_max_failures:
            return AuditionState.QUARANTINE
    elif status.state == AuditionState.PROBATION:
        if status.consecutive_failures > criteria.probation_max_failures:
            return AuditionState.QUARANTINE

    # FULL state has no forward transition
    if status.state == AuditionState.FULL:
        return None

    days_tracked = status.days_tracked or 0

    # Check SHADOW → PROBATION
    if status.state == AuditionState.SHADOW:
        if (
            status.session_count >= criteria.shadow_min_sessions
            and days_tracked >= criteria.shadow_min_days
        ):
            return AuditionState.PROBATION
        return None

    # Check PROBATION → EVALUATION
    if status.state == AuditionState.PROBATION:
        if (
            status.session_count >= criteria.probation_min_sessions
            and days_tracked >= criteria.probation_min_days
        ):
            return AuditionState.EVALUATION
        return None

    # Check EVALUATION → FULL
    if status.state == AuditionState.EVALUATION:
        if (
            status.session_count >= criteria.eval_min_sessions
            and status.quality_percentile is not None
            and status.quality_percentile >= criteria.eval_min_quality_percentile
        ):
            return AuditionState.FULL
        return None

    return None


def record_session_result(
    status: AuditionStatus,
    success: bool,
) -> AuditionStatus:
    """Update status after session completion.

    Creates a new AuditionStatus with updated fields based on session outcome.
    Increments session_count, updates timestamps, and adjusts failure count.

    Args:
        status: Current audition status
        success: True if session completed successfully, False if error/timeout

    Returns:
        New AuditionStatus with updated fields
    """
    now = datetime.utcnow()

    # Set first_seen if this is the first session
    first_seen = status.first_seen if status.first_seen is not None else now

    # Update consecutive failures
    consecutive_failures = 0 if success else status.consecutive_failures + 1

    return AuditionStatus(
        model_id=status.model_id,
        state=status.state,
        session_count=status.session_count + 1,
        first_seen=first_seen,
        last_seen=now,
        consecutive_failures=consecutive_failures,
        quality_percentile=status.quality_percentile,
        quarantine_until=status.quarantine_until,
    )
