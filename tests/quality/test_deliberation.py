"""
TDD Tests for Deliberation Depth Index (DDI).

ADR-036: Tests for quantifying deliberation thoroughness.
"""

import pytest
from llm_council.quality import deliberation_depth_index_sync


class TestDeliberationDepthIndex:
    """Test cases for DDI calculation."""

    def test_ddi_diverse_responses(self):
        """Semantically different responses → high diversity score."""
        # Very different responses
        responses = [
            "Python is a great programming language for beginners.",
            "Machine learning models require large datasets for training.",
            "The weather forecast predicts rain tomorrow afternoon.",
            "Ancient Roman architecture influenced modern buildings.",
        ]
        rankings = [{"content": "Evaluation text here."} for _ in range(4)]

        ddi, components = deliberation_depth_index_sync(responses, rankings)

        # Should have high diversity
        assert (
            components["diversity"] >= 0.5
        ), f"Expected diversity >= 0.5, got {components['diversity']}"

    def test_ddi_similar_responses(self):
        """Nearly identical responses → low diversity score."""
        # Very similar responses
        responses = [
            "Python is a programming language.",
            "Python is a popular programming language.",
            "Python is a great programming language.",
            "Python is a widely used programming language.",
        ]
        rankings = [{"content": "Evaluation text."} for _ in range(4)]

        ddi, components = deliberation_depth_index_sync(responses, rankings)

        # Should have low diversity
        assert (
            components["diversity"] <= 0.5
        ), f"Expected diversity <= 0.5, got {components['diversity']}"

    def test_ddi_full_participation(self):
        """All models reviewed → coverage = 1.0."""
        responses = ["Response 1", "Response 2", "Response 3"]
        # 3 responses, 3 reviewers
        rankings = [
            {"content": "Evaluation 1"},
            {"content": "Evaluation 2"},
            {"content": "Evaluation 3"},
        ]

        ddi, components = deliberation_depth_index_sync(responses, rankings)

        assert (
            components["coverage"] == 1.0
        ), f"Expected coverage = 1.0, got {components['coverage']}"

    def test_ddi_partial_participation(self):
        """Some models failed → coverage < 1.0."""
        responses = ["Response 1", "Response 2", "Response 3", "Response 4"]
        # Only 2 of 4 reviewers responded
        rankings = [
            {"content": "Evaluation 1"},
            {"content": "Evaluation 2"},
        ]

        ddi, components = deliberation_depth_index_sync(responses, rankings)

        assert (
            components["coverage"] == 0.5
        ), f"Expected coverage = 0.5, got {components['coverage']}"

    def test_ddi_rich_justifications(self):
        """Long, detailed justifications → high richness."""
        responses = ["Response 1"]
        # Long justification (>50 tokens)
        long_justification = " ".join(["word"] * 60)  # 60 tokens
        rankings = [{"content": f"{long_justification}\n\nFINAL RANKING:\n1. Response A"}]

        ddi, components = deliberation_depth_index_sync(responses, rankings)

        assert (
            components["richness"] >= 0.9
        ), f"Expected richness >= 0.9, got {components['richness']}"

    def test_ddi_minimal_justifications(self):
        """Terse justifications → low richness."""
        responses = ["Response 1"]
        # Very short justification (<10 tokens)
        rankings = [{"content": "A is best.\n\nFINAL RANKING:\n1. Response A"}]

        ddi, components = deliberation_depth_index_sync(responses, rankings)

        assert (
            components["richness"] <= 0.3
        ), f"Expected richness <= 0.3, got {components['richness']}"

    def test_ddi_empty_responses(self):
        """No responses → DDI = 0.0."""
        ddi, components = deliberation_depth_index_sync([], [])

        assert ddi == 0.0, f"Expected DDI = 0.0 for empty input, got {ddi}"
        assert components["diversity"] == 0.0
        assert components["coverage"] == 0.0
        assert components["richness"] == 0.0

    def test_ddi_single_response(self):
        """Single response → diversity = 0.0 (no comparison possible)."""
        responses = ["Single response here."]
        rankings = [{"content": "Evaluation with some detail here."}]

        ddi, components = deliberation_depth_index_sync(responses, rankings)

        assert components["diversity"] == 0.0, "Single response should have 0 diversity"
        assert components["coverage"] == 1.0, "Single reviewer = full coverage"

    def test_ddi_returns_valid_range(self):
        """DDI should always be in [0.0, 1.0]."""
        responses = ["Response A", "Response B", "Response C"]
        rankings = [
            {"content": "Good evaluation with details.\n\nFINAL RANKING:\n1. Response A"},
            {"content": "Another evaluation.\n\nFINAL RANKING:\n1. Response B"},
            {"content": "Third evaluation.\n\nFINAL RANKING:\n1. Response C"},
        ]

        ddi, components = deliberation_depth_index_sync(responses, rankings)

        assert 0.0 <= ddi <= 1.0, f"DDI should be in [0,1], got {ddi}"
        assert 0.0 <= components["diversity"] <= 1.0
        assert 0.0 <= components["coverage"] <= 1.0
        assert 0.0 <= components["richness"] <= 1.0


class TestDeliberationComponents:
    """Test individual DDI components."""

    def test_justification_extraction(self):
        """Justification should be extracted from content before FINAL RANKING."""
        responses = ["Response 1"]
        justification = "This is a detailed evaluation of the responses."
        rankings = [{"content": f"{justification}\n\nFINAL RANKING:\n1. Response A"}]

        ddi, components = deliberation_depth_index_sync(responses, rankings)

        # Richness should reflect the justification length
        expected_richness = min(1.0, len(justification.split()) / 50)
        assert abs(components["richness"] - expected_richness) < 0.1

    def test_raw_text_field_fallback(self):
        """Should handle raw_text field as fallback."""
        responses = ["Response 1"]
        rankings = [
            {"raw_text": "Evaluation using raw_text field.\n\nFINAL RANKING:\n1. Response A"}
        ]

        ddi, components = deliberation_depth_index_sync(responses, rankings)

        assert components["richness"] > 0, "Should extract from raw_text"
