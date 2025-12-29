"""TDD tests for ADR-027: VotingAuthority and Shadow Mode.

Tests for the VotingAuthority enum and tier voting authority defaults.
This implements Issue #110.
"""

import pytest


class TestVotingAuthorityEnum:
    """Test VotingAuthority enum."""

    def test_voting_authority_has_full_value(self):
        """VotingAuthority should have FULL value."""
        from llm_council.voting import VotingAuthority

        assert VotingAuthority.FULL.value == "full"

    def test_voting_authority_has_advisory_value(self):
        """VotingAuthority should have ADVISORY value (Shadow Mode)."""
        from llm_council.voting import VotingAuthority

        assert VotingAuthority.ADVISORY.value == "advisory"

    def test_voting_authority_has_excluded_value(self):
        """VotingAuthority should have EXCLUDED value."""
        from llm_council.voting import VotingAuthority

        assert VotingAuthority.EXCLUDED.value == "excluded"

    def test_voting_authority_has_exactly_three_values(self):
        """VotingAuthority should have exactly 3 values."""
        from llm_council.voting import VotingAuthority

        assert len(VotingAuthority) == 3


class TestTierVotingAuthority:
    """Test tier voting authority defaults (ADR-027)."""

    def test_tier_voting_authority_has_all_tiers(self):
        """TIER_VOTING_AUTHORITY should have all 5 tiers."""
        from llm_council.voting import TIER_VOTING_AUTHORITY

        assert "quick" in TIER_VOTING_AUTHORITY
        assert "balanced" in TIER_VOTING_AUTHORITY
        assert "high" in TIER_VOTING_AUTHORITY
        assert "reasoning" in TIER_VOTING_AUTHORITY
        assert "frontier" in TIER_VOTING_AUTHORITY

    def test_frontier_defaults_to_advisory(self):
        """Frontier tier should default to ADVISORY (Shadow Mode)."""
        from llm_council.voting import TIER_VOTING_AUTHORITY, VotingAuthority

        assert TIER_VOTING_AUTHORITY["frontier"] == VotingAuthority.ADVISORY

    def test_quick_defaults_to_full(self):
        """Quick tier should default to FULL voting."""
        from llm_council.voting import TIER_VOTING_AUTHORITY, VotingAuthority

        assert TIER_VOTING_AUTHORITY["quick"] == VotingAuthority.FULL

    def test_balanced_defaults_to_full(self):
        """Balanced tier should default to FULL voting."""
        from llm_council.voting import TIER_VOTING_AUTHORITY, VotingAuthority

        assert TIER_VOTING_AUTHORITY["balanced"] == VotingAuthority.FULL

    def test_high_defaults_to_full(self):
        """High tier should default to FULL voting."""
        from llm_council.voting import TIER_VOTING_AUTHORITY, VotingAuthority

        assert TIER_VOTING_AUTHORITY["high"] == VotingAuthority.FULL

    def test_reasoning_defaults_to_full(self):
        """Reasoning tier should default to FULL voting."""
        from llm_council.voting import TIER_VOTING_AUTHORITY, VotingAuthority

        assert TIER_VOTING_AUTHORITY["reasoning"] == VotingAuthority.FULL


class TestVoteWeight:
    """Test vote weight calculation based on VotingAuthority."""

    def test_get_vote_weight_full_returns_one(self):
        """FULL voting authority should have weight 1.0."""
        from llm_council.voting import VotingAuthority, get_vote_weight

        assert get_vote_weight(VotingAuthority.FULL) == 1.0

    def test_get_vote_weight_advisory_returns_zero(self):
        """ADVISORY voting authority should have weight 0.0 (shadow vote)."""
        from llm_council.voting import VotingAuthority, get_vote_weight

        assert get_vote_weight(VotingAuthority.ADVISORY) == 0.0

    def test_get_vote_weight_excluded_returns_zero(self):
        """EXCLUDED voting authority should have weight 0.0."""
        from llm_council.voting import VotingAuthority, get_vote_weight

        assert get_vote_weight(VotingAuthority.EXCLUDED) == 0.0


class TestGetModelVotingAuthority:
    """Test getting voting authority for a model."""

    def test_get_model_voting_authority_uses_tier_default(self):
        """Should use tier's default voting authority when not overridden."""
        from llm_council.voting import VotingAuthority, get_model_voting_authority

        # Model in frontier tier should get ADVISORY by default
        authority = get_model_voting_authority(model_id="frontier/preview-model", tier="frontier")
        assert authority == VotingAuthority.ADVISORY

    def test_get_model_voting_authority_high_tier(self):
        """High tier models should get FULL by default."""
        from llm_council.voting import VotingAuthority, get_model_voting_authority

        authority = get_model_voting_authority(model_id="openai/gpt-4o", tier="high")
        assert authority == VotingAuthority.FULL

    def test_get_model_voting_authority_respects_override(self):
        """Should respect model-specific override."""
        from llm_council.voting import VotingAuthority, get_model_voting_authority

        # Override frontier model to have FULL authority
        authority = get_model_voting_authority(
            model_id="frontier/preview-model", tier="frontier", override=VotingAuthority.FULL
        )
        assert authority == VotingAuthority.FULL

    def test_get_model_voting_authority_unknown_tier_defaults_full(self):
        """Unknown tier should default to FULL for safety."""
        from llm_council.voting import VotingAuthority, get_model_voting_authority

        authority = get_model_voting_authority(model_id="unknown/model", tier="unknown_tier")
        assert authority == VotingAuthority.FULL
