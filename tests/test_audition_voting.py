"""TDD Tests for ADR-029 Phase 6: Voting Integration.

Tests are written FIRST (RED phase) per TDD methodology.
Issue: https://github.com/amiable-dev/llm-council/issues/133

Maps AuditionState to VotingAuthority from ADR-027.
"""

import pytest


class TestStateVotingAuthorityMapping:
    """Test STATE_VOTING_AUTHORITY mapping."""

    def test_shadow_state_has_advisory_authority(self):
        """SHADOW state maps to ADVISORY authority."""
        from llm_council.audition.types import AuditionState
        from llm_council.audition.voting import STATE_VOTING_AUTHORITY
        from llm_council.voting import VotingAuthority

        assert STATE_VOTING_AUTHORITY[AuditionState.SHADOW] == VotingAuthority.ADVISORY

    def test_probation_state_has_advisory_authority(self):
        """PROBATION state maps to ADVISORY authority."""
        from llm_council.audition.types import AuditionState
        from llm_council.audition.voting import STATE_VOTING_AUTHORITY
        from llm_council.voting import VotingAuthority

        assert STATE_VOTING_AUTHORITY[AuditionState.PROBATION] == VotingAuthority.ADVISORY

    def test_evaluation_state_has_advisory_authority(self):
        """EVALUATION state maps to ADVISORY authority."""
        from llm_council.audition.types import AuditionState
        from llm_council.audition.voting import STATE_VOTING_AUTHORITY
        from llm_council.voting import VotingAuthority

        assert STATE_VOTING_AUTHORITY[AuditionState.EVALUATION] == VotingAuthority.ADVISORY

    def test_full_state_has_full_authority(self):
        """FULL state maps to FULL authority."""
        from llm_council.audition.types import AuditionState
        from llm_council.audition.voting import STATE_VOTING_AUTHORITY
        from llm_council.voting import VotingAuthority

        assert STATE_VOTING_AUTHORITY[AuditionState.FULL] == VotingAuthority.FULL

    def test_quarantine_state_has_excluded_authority(self):
        """QUARANTINE state maps to EXCLUDED authority."""
        from llm_council.audition.types import AuditionState
        from llm_council.audition.voting import STATE_VOTING_AUTHORITY
        from llm_council.voting import VotingAuthority

        assert STATE_VOTING_AUTHORITY[AuditionState.QUARANTINE] == VotingAuthority.EXCLUDED


class TestGetAuditionVotingAuthority:
    """Test get_audition_voting_authority function."""

    def test_unknown_model_defaults_to_advisory(self):
        """Unknown model (no status) defaults to ADVISORY."""
        from llm_council.audition.tracker import AuditionTracker
        from llm_council.audition.voting import get_audition_voting_authority
        from llm_council.voting import VotingAuthority

        tracker = AuditionTracker()

        result = get_audition_voting_authority("unknown/model", tracker)
        assert result == VotingAuthority.ADVISORY

    def test_shadow_model_returns_advisory(self):
        """SHADOW model returns ADVISORY authority."""
        from llm_council.audition.tracker import AuditionTracker
        from llm_council.audition.types import AuditionState, AuditionStatus
        from llm_council.audition.voting import get_audition_voting_authority
        from llm_council.voting import VotingAuthority

        tracker = AuditionTracker()
        tracker._cache["model"] = AuditionStatus(
            model_id="model",
            state=AuditionState.SHADOW,
        )

        result = get_audition_voting_authority("model", tracker)
        assert result == VotingAuthority.ADVISORY

    def test_full_model_returns_full(self):
        """FULL model returns FULL authority."""
        from llm_council.audition.tracker import AuditionTracker
        from llm_council.audition.types import AuditionState, AuditionStatus
        from llm_council.audition.voting import get_audition_voting_authority
        from llm_council.voting import VotingAuthority

        tracker = AuditionTracker()
        tracker._cache["model"] = AuditionStatus(
            model_id="model",
            state=AuditionState.FULL,
        )

        result = get_audition_voting_authority("model", tracker)
        assert result == VotingAuthority.FULL

    def test_quarantine_model_returns_excluded(self):
        """QUARANTINE model returns EXCLUDED authority."""
        from llm_council.audition.tracker import AuditionTracker
        from llm_council.audition.types import AuditionState, AuditionStatus
        from llm_council.audition.voting import get_audition_voting_authority
        from llm_council.voting import VotingAuthority

        tracker = AuditionTracker()
        tracker._cache["model"] = AuditionStatus(
            model_id="model",
            state=AuditionState.QUARANTINE,
        )

        result = get_audition_voting_authority("model", tracker)
        assert result == VotingAuthority.EXCLUDED


class TestModuleExports:
    """Test module exports."""

    def test_state_voting_authority_exported(self):
        """STATE_VOTING_AUTHORITY is exported from module."""
        from llm_council.audition import STATE_VOTING_AUTHORITY

        assert STATE_VOTING_AUTHORITY is not None

    def test_get_audition_voting_authority_exported(self):
        """get_audition_voting_authority is exported from module."""
        from llm_council.audition import get_audition_voting_authority

        assert callable(get_audition_voting_authority)
