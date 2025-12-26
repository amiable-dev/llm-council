"""Voting Integration for ADR-029 Model Audition Mechanism.

This module maps AuditionState to VotingAuthority from ADR-027:
- SHADOW/PROBATION/EVALUATION → ADVISORY (non-binding votes)
- FULL → FULL (binding votes)
- QUARANTINE → EXCLUDED (not selected)

Example:
    >>> from llm_council.audition.voting import get_audition_voting_authority
    >>> authority = get_audition_voting_authority("openai/gpt-5", tracker)
    >>> if authority == VotingAuthority.FULL:
    ...     # Count vote in consensus
"""

from typing import TYPE_CHECKING, Dict

from ..voting import VotingAuthority
from .types import AuditionState

if TYPE_CHECKING:
    from .tracker import AuditionTracker

# Map AuditionState to VotingAuthority per ADR-029
STATE_VOTING_AUTHORITY: Dict[AuditionState, VotingAuthority] = {
    AuditionState.SHADOW: VotingAuthority.ADVISORY,
    AuditionState.PROBATION: VotingAuthority.ADVISORY,
    AuditionState.EVALUATION: VotingAuthority.ADVISORY,
    AuditionState.FULL: VotingAuthority.FULL,
    AuditionState.QUARANTINE: VotingAuthority.EXCLUDED,
}


def get_audition_voting_authority(
    model_id: str,
    tracker: "AuditionTracker",
) -> VotingAuthority:
    """Get voting authority based on audition state.

    Looks up the model's audition status and returns the corresponding
    voting authority. Unknown models default to ADVISORY (Shadow Mode).

    Args:
        model_id: Full model identifier
        tracker: AuditionTracker for status lookup

    Returns:
        VotingAuthority for the model
    """
    status = tracker.get_status(model_id)

    if status is None:
        # Unknown model = SHADOW = ADVISORY
        return VotingAuthority.ADVISORY

    return STATE_VOTING_AUTHORITY.get(status.state, VotingAuthority.ADVISORY)
