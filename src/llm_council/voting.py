"""VotingAuthority enum and Shadow Mode support for ADR-027.

This module provides voting authority types for the council's tier system.
Frontier tier models operate in Shadow Mode (ADVISORY) by default, meaning
their votes are logged for evaluation but have zero weight in consensus.

Implements Issue #110.
"""

from enum import Enum
from typing import Dict, Optional


class VotingAuthority(Enum):
    """Voting authority levels for council models.

    FULL: Vote counts in consensus calculation (weight = 1.0)
    ADVISORY: Vote is logged/evaluated but has zero weight (Shadow Mode)
    EXCLUDED: Model is not included in deliberation
    """

    FULL = "full"
    ADVISORY = "advisory"
    EXCLUDED = "excluded"


# Default voting authority by tier (ADR-027)
# Frontier tier defaults to ADVISORY (Shadow Mode) to prevent
# experimental models from affecting production consensus.
TIER_VOTING_AUTHORITY: Dict[str, VotingAuthority] = {
    "quick": VotingAuthority.FULL,
    "balanced": VotingAuthority.FULL,
    "high": VotingAuthority.FULL,
    "reasoning": VotingAuthority.FULL,
    "frontier": VotingAuthority.ADVISORY,  # Shadow Mode by default
}


def get_vote_weight(authority: VotingAuthority) -> float:
    """Get the vote weight for a given voting authority.

    Args:
        authority: The VotingAuthority level

    Returns:
        Vote weight: 1.0 for FULL, 0.0 for ADVISORY/EXCLUDED
    """
    if authority == VotingAuthority.FULL:
        return 1.0
    return 0.0


def get_model_voting_authority(
    model_id: str,
    tier: str,
    override: Optional[VotingAuthority] = None,
) -> VotingAuthority:
    """Get the voting authority for a specific model.

    Args:
        model_id: The model identifier
        tier: The tier the model is operating in
        override: Optional override for the voting authority

    Returns:
        The VotingAuthority for this model
    """
    # Override takes precedence
    if override is not None:
        return override

    # Use tier default, or FULL for unknown tiers
    return TIER_VOTING_AUTHORITY.get(tier, VotingAuthority.FULL)


def calculate_shadow_agreement(
    consensus_winner: str,
    shadow_votes: list,
) -> Optional[float]:
    """Calculate the percentage of shadow votes that agree with consensus.

    Args:
        consensus_winner: The model that won the consensus ranking
        shadow_votes: List of dicts with 'reviewer' and 'top_pick' keys

    Returns:
        Agreement ratio [0.0, 1.0], or None if no shadow votes
    """
    if not shadow_votes:
        return None

    agreeing = sum(1 for vote in shadow_votes if vote.get("top_pick") == consensus_winner)

    return agreeing / len(shadow_votes)
