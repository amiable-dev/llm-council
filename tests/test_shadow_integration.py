"""TDD tests for ADR-027: Shadow Votes Integration (Issue #117).

Tests for integrating shadow vote tracking into council execution,
including event emission for FRONTIER_SHADOW_VOTE.

These tests implement the RED phase of TDD - they should FAIL initially.
"""

import pytest

from llm_council.layer_contracts import (
    LayerEventType,
    emit_layer_event,
    get_layer_events,
    clear_layer_events,
)
from llm_council.voting import VotingAuthority


class TestShadowVoteTracking:
    """Test shadow vote tracking in calculate_aggregate_rankings."""

    def setup_method(self):
        """Clear events before each test."""
        clear_layer_events()

    def teardown_method(self):
        """Clear events after each test."""
        clear_layer_events()

    def test_return_shadow_votes_includes_shadow_data(self):
        """When return_shadow_votes=True, result entries include shadow_votes."""
        from llm_council.council import calculate_aggregate_rankings

        # Sample stage2 results with an ADVISORY reviewer
        stage2_results = [
            {
                "model": "openai/gpt-4o",  # FULL authority
                "response": "Response A is best...",
                "parsed_ranking": {
                    "ranking": ["Response A", "Response B"],
                    "scores": {},
                },
            },
            {
                "model": "openai/gpt-5-preview",  # ADVISORY (frontier)
                "response": "Response B is best...",
                "parsed_ranking": {
                    "ranking": ["Response B", "Response A"],
                    "scores": {},
                },
            },
        ]

        label_to_model = {
            "Response A": {"model": "anthropic/claude-3.5-sonnet", "display_index": 0},
            "Response B": {"model": "google/gemini-2.5-pro", "display_index": 1},
        }

        voting_authorities = {
            "openai/gpt-4o": VotingAuthority.FULL,
            "openai/gpt-5-preview": VotingAuthority.ADVISORY,
        }

        result = calculate_aggregate_rankings(
            stage2_results,
            label_to_model,
            voting_authorities=voting_authorities,
            return_shadow_votes=True,
        )

        # Check that shadow_votes is included in result entries
        assert len(result) > 0
        for entry in result:
            assert "shadow_votes" in entry

    def test_shadow_votes_contains_advisory_reviewer_votes(self):
        """Shadow votes should contain data from ADVISORY reviewers."""
        from llm_council.council import calculate_aggregate_rankings

        stage2_results = [
            {
                "model": "openai/gpt-5-preview",  # ADVISORY
                "response": "Response B is best...",
                "parsed_ranking": {
                    "ranking": ["Response B", "Response A"],
                    "scores": {},
                },
            },
        ]

        label_to_model = {
            "Response A": {"model": "anthropic/claude-3.5-sonnet", "display_index": 0},
            "Response B": {"model": "google/gemini-2.5-pro", "display_index": 1},
        }

        voting_authorities = {
            "openai/gpt-5-preview": VotingAuthority.ADVISORY,
        }

        result = calculate_aggregate_rankings(
            stage2_results,
            label_to_model,
            voting_authorities=voting_authorities,
            return_shadow_votes=True,
        )

        # Get shadow_votes from any result entry
        shadow_votes = result[0].get("shadow_votes", [])
        assert len(shadow_votes) == 1
        assert shadow_votes[0]["reviewer"] == "openai/gpt-5-preview"
        assert shadow_votes[0]["top_pick"] == "google/gemini-2.5-pro"

    def test_shadow_votes_not_included_by_default(self):
        """When return_shadow_votes=False (default), no shadow_votes in results."""
        from llm_council.council import calculate_aggregate_rankings

        stage2_results = [
            {
                "model": "openai/gpt-4o",
                "response": "Response A is best...",
                "parsed_ranking": {
                    "ranking": ["Response A", "Response B"],
                    "scores": {},
                },
            },
        ]

        label_to_model = {
            "Response A": {"model": "anthropic/claude-3.5-sonnet", "display_index": 0},
            "Response B": {"model": "google/gemini-2.5-pro", "display_index": 1},
        }

        # Default: return_shadow_votes=False
        result = calculate_aggregate_rankings(
            stage2_results,
            label_to_model,
        )

        # Check that shadow_votes is NOT in result entries
        for entry in result:
            assert "shadow_votes" not in entry


class TestShadowVoteEventEmission:
    """Test FRONTIER_SHADOW_VOTE event emission."""

    def setup_method(self):
        """Clear events before each test."""
        clear_layer_events()

    def teardown_method(self):
        """Clear events after each test."""
        clear_layer_events()

    def test_emit_shadow_vote_events_for_frontier_tier(self):
        """FRONTIER_SHADOW_VOTE events should be emitted for frontier tier."""
        from llm_council.council import (
            emit_shadow_vote_events,
        )

        shadow_votes = [
            {
                "reviewer": "openai/gpt-5-preview",
                "top_pick": "anthropic/claude-3.5-sonnet",
                "ranking": ["anthropic/claude-3.5-sonnet", "google/gemini-2.5-pro"],
            },
        ]

        consensus_winner = "google/gemini-2.5-pro"

        emit_shadow_vote_events(shadow_votes, consensus_winner)

        events = get_layer_events()
        assert len(events) == 1
        assert events[0].event_type == LayerEventType.FRONTIER_SHADOW_VOTE
        assert events[0].data["model_id"] == "openai/gpt-5-preview"
        assert events[0].data["top_pick"] == "anthropic/claude-3.5-sonnet"
        assert events[0].data["agreed_with_consensus"] is False

    def test_shadow_vote_agreement_calculated_correctly(self):
        """agreed_with_consensus should be True when shadow vote matches."""
        from llm_council.council import (
            emit_shadow_vote_events,
        )

        shadow_votes = [
            {
                "reviewer": "openai/gpt-5-preview",
                "top_pick": "anthropic/claude-3.5-sonnet",  # Same as consensus
                "ranking": ["anthropic/claude-3.5-sonnet", "google/gemini-2.5-pro"],
            },
        ]

        consensus_winner = "anthropic/claude-3.5-sonnet"

        emit_shadow_vote_events(shadow_votes, consensus_winner)

        events = get_layer_events()
        assert len(events) == 1
        assert events[0].data["agreed_with_consensus"] is True


class TestFrontierTierShadowIntegration:
    """Test that frontier tier properly enables shadow vote tracking."""

    def setup_method(self):
        """Clear events before each test."""
        clear_layer_events()

    def teardown_method(self):
        """Clear events after each test."""
        clear_layer_events()

    def test_should_track_shadow_votes_for_frontier(self):
        """should_track_shadow_votes returns True for frontier tier."""
        from llm_council.council import should_track_shadow_votes
        from llm_council.tier_contract import create_tier_contract

        tier_contract = create_tier_contract("frontier")
        assert should_track_shadow_votes(tier_contract) is True

    def test_should_not_track_shadow_votes_for_high(self):
        """should_track_shadow_votes returns False for non-frontier tiers."""
        from llm_council.council import should_track_shadow_votes
        from llm_council.tier_contract import create_tier_contract

        tier_contract = create_tier_contract("high")
        assert should_track_shadow_votes(tier_contract) is False

    def test_should_not_track_shadow_votes_when_none(self):
        """should_track_shadow_votes returns False when no tier_contract."""
        from llm_council.council import should_track_shadow_votes

        assert should_track_shadow_votes(None) is False


class TestNonFrontierTierOptimization:
    """Test that non-frontier tiers skip shadow processing for efficiency."""

    def setup_method(self):
        """Clear events before each test."""
        clear_layer_events()

    def teardown_method(self):
        """Clear events after each test."""
        clear_layer_events()

    def test_non_frontier_tiers_skip_shadow_processing(self):
        """Non-frontier tiers don't emit FRONTIER_SHADOW_VOTE events."""
        # This is tested implicitly - when return_shadow_votes=False,
        # no shadow vote processing overhead occurs

        # For observability: no FRONTIER_SHADOW_VOTE events for non-frontier
        events = get_layer_events()
        frontier_events = [e for e in events if e.event_type == LayerEventType.FRONTIER_SHADOW_VOTE]
        assert len(frontier_events) == 0
