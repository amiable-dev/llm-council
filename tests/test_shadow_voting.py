"""TDD tests for ADR-027: Shadow Voting Integration.

Tests for integrating Shadow Mode voting into calculate_aggregate_rankings().
This implements Issue #111.
"""

import pytest
from typing import Dict, Any, List


class TestShadowVotingIntegration:
    """Test Shadow Mode voting integration in calculate_aggregate_rankings()."""

    def _create_stage2_result(
        self, reviewer: str, ranking: List[str], scores: Dict[str, float] = None
    ) -> Dict[str, Any]:
        """Helper to create a stage2 result dict."""
        return {"model": reviewer, "parsed_ranking": {"ranking": ranking, "scores": scores or {}}}

    def _create_label_to_model(self, models: List[str]) -> Dict[str, Any]:
        """Helper to create label_to_model mapping."""
        labels = ["Response A", "Response B", "Response C", "Response D"]
        return {labels[i]: {"model": model, "display_index": i} for i, model in enumerate(models)}

    def test_backward_compatible_without_voting_authorities(self):
        """calculate_aggregate_rankings should work without voting_authorities parameter."""
        from llm_council.council import calculate_aggregate_rankings

        stage2_results = [
            self._create_stage2_result("openai/gpt-4o", ["Response A", "Response B"]),
            self._create_stage2_result("anthropic/claude", ["Response A", "Response B"]),
        ]
        label_to_model = self._create_label_to_model(["model-a", "model-b"])

        # Should not raise - backward compatible
        rankings = calculate_aggregate_rankings(stage2_results, label_to_model)

        assert len(rankings) == 2
        assert rankings[0]["model"] == "model-a"  # Got 2 first-place votes

    def test_full_votes_count_in_rankings(self):
        """FULL voting authority votes should count normally."""
        from llm_council.council import calculate_aggregate_rankings
        from llm_council.voting import VotingAuthority

        stage2_results = [
            self._create_stage2_result("openai/gpt-4o", ["Response A", "Response B"]),
            self._create_stage2_result("anthropic/claude", ["Response A", "Response B"]),
        ]
        label_to_model = self._create_label_to_model(["model-a", "model-b"])
        voting_authorities = {
            "openai/gpt-4o": VotingAuthority.FULL,
            "anthropic/claude": VotingAuthority.FULL,
        }

        rankings = calculate_aggregate_rankings(
            stage2_results, label_to_model, voting_authorities=voting_authorities
        )

        assert rankings[0]["model"] == "model-a"
        assert rankings[0]["vote_count"] == 2

    def test_advisory_votes_excluded_from_rankings(self):
        """ADVISORY votes should not affect final rankings."""
        from llm_council.council import calculate_aggregate_rankings
        from llm_council.voting import VotingAuthority

        # Frontier model votes for A, others vote for B
        stage2_results = [
            self._create_stage2_result("frontier/preview", ["Response A", "Response B"]),
            self._create_stage2_result("openai/gpt-4o", ["Response B", "Response A"]),
            self._create_stage2_result("anthropic/claude", ["Response B", "Response A"]),
        ]
        label_to_model = self._create_label_to_model(["model-a", "model-b"])
        voting_authorities = {
            "frontier/preview": VotingAuthority.ADVISORY,  # Shadow vote
            "openai/gpt-4o": VotingAuthority.FULL,
            "anthropic/claude": VotingAuthority.FULL,
        }

        rankings = calculate_aggregate_rankings(
            stage2_results, label_to_model, voting_authorities=voting_authorities
        )

        # Model B should win (2 FULL first-place votes)
        assert rankings[0]["model"] == "model-b"
        # Both models get ranked by 2 FULL voters
        assert rankings[0]["vote_count"] == 2
        assert rankings[1]["vote_count"] == 2
        # Model B has perfect borda score (all 1st place), Model A has 0 (all 2nd place)
        assert rankings[0]["borda_score"] == 1.0
        assert rankings[1]["borda_score"] == 0.0

    def test_advisory_only_council_returns_empty_rankings(self):
        """A council with only ADVISORY votes should return empty effective rankings."""
        from llm_council.council import calculate_aggregate_rankings
        from llm_council.voting import VotingAuthority

        stage2_results = [
            self._create_stage2_result("frontier/a", ["Response A", "Response B"]),
            self._create_stage2_result("frontier/b", ["Response B", "Response A"]),
        ]
        label_to_model = self._create_label_to_model(["model-a", "model-b"])
        voting_authorities = {
            "frontier/a": VotingAuthority.ADVISORY,
            "frontier/b": VotingAuthority.ADVISORY,
        }

        rankings = calculate_aggregate_rankings(
            stage2_results, label_to_model, voting_authorities=voting_authorities
        )

        # No effective votes - both models should have 0 vote_count
        for entry in rankings:
            assert entry["vote_count"] == 0

    def test_mixed_council_frontier_and_high(self):
        """Mixed council with frontier and high tier models."""
        from llm_council.council import calculate_aggregate_rankings
        from llm_council.voting import VotingAuthority

        # 2 FULL votes for A, 2 ADVISORY votes for B
        stage2_results = [
            self._create_stage2_result("openai/gpt-4o", ["Response A", "Response B"]),
            self._create_stage2_result("anthropic/claude", ["Response A", "Response B"]),
            self._create_stage2_result("frontier/a", ["Response B", "Response A"]),
            self._create_stage2_result("frontier/b", ["Response B", "Response A"]),
        ]
        label_to_model = self._create_label_to_model(["model-a", "model-b"])
        voting_authorities = {
            "openai/gpt-4o": VotingAuthority.FULL,
            "anthropic/claude": VotingAuthority.FULL,
            "frontier/a": VotingAuthority.ADVISORY,
            "frontier/b": VotingAuthority.ADVISORY,
        }

        rankings = calculate_aggregate_rankings(
            stage2_results, label_to_model, voting_authorities=voting_authorities
        )

        # Model A should win (2 FULL votes)
        assert rankings[0]["model"] == "model-a"
        assert rankings[0]["vote_count"] == 2

    def test_excluded_votes_not_processed(self):
        """EXCLUDED votes should not be processed at all."""
        from llm_council.council import calculate_aggregate_rankings
        from llm_council.voting import VotingAuthority

        stage2_results = [
            self._create_stage2_result("openai/gpt-4o", ["Response A", "Response B"]),
            self._create_stage2_result("excluded/model", ["Response B", "Response A"]),
        ]
        label_to_model = self._create_label_to_model(["model-a", "model-b"])
        voting_authorities = {
            "openai/gpt-4o": VotingAuthority.FULL,
            "excluded/model": VotingAuthority.EXCLUDED,
        }

        rankings = calculate_aggregate_rankings(
            stage2_results, label_to_model, voting_authorities=voting_authorities
        )

        # Only 1 effective vote from gpt-4o
        assert rankings[0]["model"] == "model-a"
        assert rankings[0]["vote_count"] == 1


class TestShadowVoteTracking:
    """Test shadow vote tracking in metadata."""

    def _create_stage2_result(
        self,
        reviewer: str,
        ranking: List[str],
    ) -> Dict[str, Any]:
        """Helper to create a stage2 result dict."""
        return {"model": reviewer, "parsed_ranking": {"ranking": ranking, "scores": {}}}

    def _create_label_to_model(self, models: List[str]) -> Dict[str, Any]:
        """Helper to create label_to_model mapping."""
        labels = ["Response A", "Response B", "Response C", "Response D"]
        return {labels[i]: {"model": model, "display_index": i} for i, model in enumerate(models)}

    def test_shadow_votes_returned_in_result(self):
        """Shadow votes should be returned for observability."""
        from llm_council.council import calculate_aggregate_rankings
        from llm_council.voting import VotingAuthority

        stage2_results = [
            self._create_stage2_result("openai/gpt-4o", ["Response A", "Response B"]),
            self._create_stage2_result("frontier/preview", ["Response B", "Response A"]),
        ]
        label_to_model = self._create_label_to_model(["model-a", "model-b"])
        voting_authorities = {
            "openai/gpt-4o": VotingAuthority.FULL,
            "frontier/preview": VotingAuthority.ADVISORY,
        }

        rankings = calculate_aggregate_rankings(
            stage2_results,
            label_to_model,
            voting_authorities=voting_authorities,
            return_shadow_votes=True,
        )

        # Rankings should include shadow_votes metadata
        assert "shadow_votes" in rankings[0] or hasattr(rankings, "__shadow_votes__")

    def test_default_voting_authority_uses_tier(self):
        """When model not in voting_authorities, should use tier default."""
        from llm_council.council import calculate_aggregate_rankings
        from llm_council.voting import VotingAuthority

        stage2_results = [
            self._create_stage2_result("openai/gpt-4o", ["Response A", "Response B"]),
            self._create_stage2_result("frontier/preview", ["Response B", "Response A"]),
        ]
        label_to_model = self._create_label_to_model(["model-a", "model-b"])

        # Only specify authority for some models
        voting_authorities = {
            "openai/gpt-4o": VotingAuthority.FULL,
            # frontier/preview not specified - should still work
        }

        # Should not raise
        rankings = calculate_aggregate_rankings(
            stage2_results, label_to_model, voting_authorities=voting_authorities
        )

        assert len(rankings) == 2


class TestShadowVoteAgreement:
    """Test shadow vote agreement calculation."""

    def test_calculate_shadow_agreement_all_agree(self):
        """Should return 1.0 when all shadow votes agree with consensus."""
        from llm_council.voting import calculate_shadow_agreement

        consensus_winner = "model-a"
        shadow_votes = [
            {"reviewer": "frontier/a", "top_pick": "model-a"},
            {"reviewer": "frontier/b", "top_pick": "model-a"},
        ]

        agreement = calculate_shadow_agreement(consensus_winner, shadow_votes)
        assert agreement == 1.0

    def test_calculate_shadow_agreement_none_agree(self):
        """Should return 0.0 when no shadow votes agree with consensus."""
        from llm_council.voting import calculate_shadow_agreement

        consensus_winner = "model-a"
        shadow_votes = [
            {"reviewer": "frontier/a", "top_pick": "model-b"},
            {"reviewer": "frontier/b", "top_pick": "model-c"},
        ]

        agreement = calculate_shadow_agreement(consensus_winner, shadow_votes)
        assert agreement == 0.0

    def test_calculate_shadow_agreement_partial(self):
        """Should return correct ratio for partial agreement."""
        from llm_council.voting import calculate_shadow_agreement

        consensus_winner = "model-a"
        shadow_votes = [
            {"reviewer": "frontier/a", "top_pick": "model-a"},  # Agrees
            {"reviewer": "frontier/b", "top_pick": "model-b"},  # Disagrees
        ]

        agreement = calculate_shadow_agreement(consensus_winner, shadow_votes)
        assert agreement == 0.5

    def test_calculate_shadow_agreement_empty(self):
        """Should return None for empty shadow votes."""
        from llm_council.voting import calculate_shadow_agreement

        agreement = calculate_shadow_agreement("model-a", [])
        assert agreement is None
