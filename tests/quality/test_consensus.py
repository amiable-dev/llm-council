"""
TDD Tests for Consensus Strength Score (CSS).

ADR-036: Tests for quantifying agreement among council members.
"""

import pytest
from llm_council.quality import consensus_strength_score, get_consensus_interpretation


class TestConsensusStrengthScore:
    """Test cases for CSS calculation."""

    def test_css_perfect_consensus(self):
        """All reviewers rank same response #1 → CSS should be high."""
        # Perfect consensus: Response A has avg position 1.0, others have 2.0, 3.0, 4.0
        # This means all reviewers agreed A is best with clear ordering
        aggregate_rankings = [
            ("model_a", 1.0),  # Clear winner
            ("model_b", 2.0),
            ("model_c", 3.0),
            ("model_d", 4.0),
        ]

        css = consensus_strength_score(aggregate_rankings)

        # Uniform spacing = moderate-to-strong consensus (clear ordering, all unique positions)
        # CSS >= 0.7 indicates strong agreement on relative ordering
        assert css >= 0.7, f"Expected CSS >= 0.7 for perfect ordering consensus, got {css}"
        assert css <= 1.0, f"Expected CSS <= 1.0, got {css}"

    def test_css_dominant_winner(self):
        """Winner far ahead of pack → CSS should be very high (≈0.85+)."""
        # Dominant winner: model_a clearly best (1.0), others clustered (3.5, 3.5, 4.0)
        aggregate_rankings = [
            ("model_a", 1.0),  # Dominant winner
            ("model_b", 3.5),  # Pack is far behind
            ("model_c", 3.5),
            ("model_d", 4.0),
        ]

        css = consensus_strength_score(aggregate_rankings)

        # Clear dominant winner = strong consensus
        assert css >= 0.75, f"Expected CSS >= 0.75 for dominant winner, got {css}"

    def test_css_split_consensus(self):
        """2-2 split on top rank → CSS should be around 0.5."""
        # 2-2 split: two responses tied for first, two for last
        aggregate_rankings = [
            ("model_a", 1.5),  # Tied for 1st-2nd
            ("model_b", 1.5),
            ("model_c", 3.5),  # Tied for 3rd-4th
            ("model_d", 3.5),
        ]

        css = consensus_strength_score(aggregate_rankings)

        # Should be moderate/weak consensus
        assert 0.3 <= css <= 0.7, f"Expected CSS 0.3-0.7 for split consensus, got {css}"

    def test_css_moderate_consensus(self):
        """Clear winner but varied lower ranks → CSS ≈ 0.7-0.8."""
        # Clear winner but mixed middle/bottom
        aggregate_rankings = [
            ("model_a", 1.2),  # Clear winner
            ("model_b", 2.4),
            ("model_c", 2.8),
            ("model_d", 3.6),
        ]

        css = consensus_strength_score(aggregate_rankings)

        # Should be moderate consensus
        assert 0.6 <= css <= 0.9, f"Expected CSS 0.6-0.9 for moderate consensus, got {css}"

    def test_css_no_rankings(self):
        """Empty rankings → CSS = 0.0."""
        aggregate_rankings = []

        css = consensus_strength_score(aggregate_rankings)

        assert css == 0.0, f"Expected CSS = 0.0 for empty rankings, got {css}"

    def test_css_single_reviewer(self):
        """Only one response → CSS = 1.0 (trivial consensus)."""
        aggregate_rankings = [("model_a", 1.0)]

        css = consensus_strength_score(aggregate_rankings)

        assert css == 1.0, f"Expected CSS = 1.0 for single reviewer, got {css}"

    def test_css_all_tied(self):
        """All responses tied → CSS = 1.0 (consensus on equality)."""
        aggregate_rankings = [
            ("model_a", 2.5),
            ("model_b", 2.5),
            ("model_c", 2.5),
            ("model_d", 2.5),
        ]

        css = consensus_strength_score(aggregate_rankings)

        assert css == 1.0, f"Expected CSS = 1.0 for all tied, got {css}"

    def test_css_returns_float_in_range(self):
        """CSS should always be a float in [0.0, 1.0]."""
        test_cases = [
            [("a", 1.0), ("b", 2.0), ("c", 3.0)],
            [("a", 1.0), ("b", 4.0)],
            [("a", 1.5), ("b", 1.5), ("c", 3.0), ("d", 4.0)],
        ]

        for rankings in test_cases:
            css = consensus_strength_score(rankings)
            assert isinstance(css, float), f"CSS should be float, got {type(css)}"
            assert 0.0 <= css <= 1.0, f"CSS should be in [0,1], got {css}"


class TestConsensusInterpretation:
    """Test cases for CSS interpretation."""

    def test_strong_consensus_interpretation(self):
        """CSS >= 0.85 should be 'strong_consensus'."""
        assert get_consensus_interpretation(0.85) == "strong_consensus"
        assert get_consensus_interpretation(0.95) == "strong_consensus"
        assert get_consensus_interpretation(1.0) == "strong_consensus"

    def test_moderate_consensus_interpretation(self):
        """CSS 0.70-0.84 should be 'moderate_consensus'."""
        assert get_consensus_interpretation(0.70) == "moderate_consensus"
        assert get_consensus_interpretation(0.77) == "moderate_consensus"
        assert get_consensus_interpretation(0.84) == "moderate_consensus"

    def test_weak_consensus_interpretation(self):
        """CSS 0.50-0.69 should be 'weak_consensus'."""
        assert get_consensus_interpretation(0.50) == "weak_consensus"
        assert get_consensus_interpretation(0.60) == "weak_consensus"
        assert get_consensus_interpretation(0.69) == "weak_consensus"

    def test_significant_disagreement_interpretation(self):
        """CSS < 0.50 should be 'significant_disagreement'."""
        assert get_consensus_interpretation(0.49) == "significant_disagreement"
        assert get_consensus_interpretation(0.30) == "significant_disagreement"
        assert get_consensus_interpretation(0.0) == "significant_disagreement"
