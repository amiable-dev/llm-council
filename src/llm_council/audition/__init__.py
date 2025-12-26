"""Model Audition Mechanism for LLM Council (ADR-029).

This module implements volume-based model audition to solve the cold start problem
for newly discovered models. New models progress through a state machine:

    SHADOW → PROBATION → EVALUATION → FULL

Key concepts:
- Shadow Mode: New models have non-binding votes (VotingAuthority.ADVISORY)
- Volume-based graduation: Session counts + min days, not just time
- Progressive weighting: Selection weight scales from 30% to 100%
- Quarantine: Models with repeated failures are excluded temporarily

Example:
    >>> from llm_council.audition import AuditionState, AuditionStatus, AuditionCriteria
    >>> status = AuditionStatus(model_id="openai/gpt-5", state=AuditionState.SHADOW)
    >>> criteria = AuditionCriteria()
    >>> criteria.shadow_min_sessions
    10

Environment Variables:
    LLM_COUNCIL_AUDITION_ENABLED: Enable audition mechanism (default: true)
    LLM_COUNCIL_AUDITION_MAX_SEATS: Max audition models per session (default: 1)
"""

from .types import (
    AuditionCriteria,
    AuditionState,
    AuditionStatus,
    evaluate_state_transition,
    record_session_result,
)
from .tracker import (
    AuditionTracker,
    get_audition_tracker,
    _reset_tracker,
)
from .selection import (
    get_selection_weight,
    select_with_audition,
    is_auditioning_model,
)
from .voting import (
    STATE_VOTING_AUTHORITY,
    get_audition_voting_authority,
)

__all__ = [
    # Core Types
    "AuditionState",
    "AuditionStatus",
    "AuditionCriteria",
    # Transition Functions
    "evaluate_state_transition",
    "record_session_result",
    # Tracker
    "AuditionTracker",
    "get_audition_tracker",
    "_reset_tracker",
    # Selection
    "get_selection_weight",
    "select_with_audition",
    "is_auditioning_model",
    # Voting
    "STATE_VOTING_AUTHORITY",
    "get_audition_voting_authority",
]
