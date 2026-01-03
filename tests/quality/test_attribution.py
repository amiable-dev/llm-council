"""
TDD Tests for Synthesis Attribution Score (SAS).

ADR-036: Tests for measuring synthesis grounding in sources.
"""

import pytest
from llm_council.quality import synthesis_attribution_score_sync, SynthesisAttribution


class TestSynthesisAttributionScore:
    """Test cases for SAS calculation."""

    def test_sas_synthesis_from_winner(self):
        """Synthesis closely matches top-ranked response → high winner_alignment."""
        winning_response = "Python is a versatile programming language with many libraries."
        synthesis = "Python is a versatile programming language with extensive library support."
        all_responses = [
            winning_response,
            "Java is an object-oriented language.",
            "C++ provides low-level memory control.",
        ]

        sas = synthesis_attribution_score_sync(
            synthesis=synthesis,
            winning_responses=[winning_response],
            all_responses=all_responses,
        )

        assert (
            sas.winner_alignment >= 0.5
        ), f"Expected high winner alignment, got {sas.winner_alignment}"

    def test_sas_synthesis_novel(self):
        """Synthesis diverges from all responses → high hallucination_risk."""
        synthesis = "The weather in Antarctica is extremely cold year-round."
        all_responses = [
            "Python is a programming language.",
            "Machine learning requires data.",
            "Software development follows agile methodologies.",
        ]

        sas = synthesis_attribution_score_sync(
            synthesis=synthesis,
            winning_responses=[all_responses[0]],
            all_responses=all_responses,
        )

        assert (
            sas.hallucination_risk >= 0.5
        ), f"Expected high hallucination risk, got {sas.hallucination_risk}"
        assert (
            sas.max_source_alignment <= 0.5
        ), f"Expected low source alignment, got {sas.max_source_alignment}"

    def test_sas_grounded(self):
        """max_source_alignment > 0.6 → grounded=True."""
        # Nearly identical to source
        source = "The quick brown fox jumps over the lazy dog."
        synthesis = "The quick brown fox jumps over the lazy sleeping dog."

        sas = synthesis_attribution_score_sync(
            synthesis=synthesis,
            winning_responses=[source],
            all_responses=[source],
        )

        assert sas.grounded is True, f"Expected grounded=True, got {sas.grounded}"
        assert sas.max_source_alignment >= 0.6

    def test_sas_not_grounded(self):
        """max_source_alignment < 0.6 → grounded=False."""
        synthesis = "Artificial intelligence is transforming industries worldwide."
        all_responses = [
            "The cat sat on the mat.",
            "Birds fly south for winter.",
            "Coffee is made from roasted beans.",
        ]

        sas = synthesis_attribution_score_sync(
            synthesis=synthesis,
            winning_responses=[all_responses[0]],
            all_responses=all_responses,
        )

        assert sas.grounded is False, f"Expected grounded=False, got {sas.grounded}"
        assert sas.max_source_alignment < 0.6

    def test_sas_empty_synthesis(self):
        """Empty synthesis → returns default attribution."""
        sas = synthesis_attribution_score_sync(
            synthesis="",
            winning_responses=["Some response"],
            all_responses=["Some response"],
        )

        assert sas.winner_alignment == 0.0
        assert sas.max_source_alignment == 0.0
        assert sas.hallucination_risk == 1.0
        assert sas.grounded is False

    def test_sas_empty_responses(self):
        """Empty responses → returns default attribution."""
        sas = synthesis_attribution_score_sync(
            synthesis="Some synthesis",
            winning_responses=[],
            all_responses=[],
        )

        assert sas.winner_alignment == 0.0
        assert sas.max_source_alignment == 0.0
        assert sas.hallucination_risk == 1.0
        assert sas.grounded is False

    def test_sas_returns_dataclass(self):
        """SAS should return a SynthesisAttribution dataclass."""
        sas = synthesis_attribution_score_sync(
            synthesis="Test synthesis",
            winning_responses=["Test response"],
            all_responses=["Test response"],
        )

        assert isinstance(sas, SynthesisAttribution)
        assert hasattr(sas, "winner_alignment")
        assert hasattr(sas, "max_source_alignment")
        assert hasattr(sas, "hallucination_risk")
        assert hasattr(sas, "grounded")

    def test_sas_hallucination_risk_inverse(self):
        """hallucination_risk should equal 1 - max_source_alignment."""
        sas = synthesis_attribution_score_sync(
            synthesis="Test synthesis text here",
            winning_responses=["Test response text here"],
            all_responses=["Test response text here", "Another response"],
        )

        expected_risk = round(1.0 - sas.max_source_alignment, 3)
        assert sas.hallucination_risk == expected_risk


class TestSynthesisAttributionEdgeCases:
    """Edge case tests for SAS."""

    def test_sas_identical_synthesis_and_source(self):
        """Identical synthesis and source → perfect alignment."""
        text = "This is the exact same text used in both places."

        sas = synthesis_attribution_score_sync(
            synthesis=text,
            winning_responses=[text],
            all_responses=[text],
        )

        assert sas.winner_alignment == 1.0
        assert sas.max_source_alignment == 1.0
        assert sas.hallucination_risk == 0.0
        assert sas.grounded is True

    def test_sas_multiple_winners(self):
        """Multiple winning responses → average alignment."""
        winner1 = "Python is great for data science and machine learning."
        winner2 = "Python excels in data analysis and AI applications."
        synthesis = "Python is excellent for data science and AI."

        sas = synthesis_attribution_score_sync(
            synthesis=synthesis,
            winning_responses=[winner1, winner2],
            all_responses=[winner1, winner2, "Unrelated response here."],
        )

        # Winner alignment should be average of both
        assert 0.0 <= sas.winner_alignment <= 1.0

    def test_sas_custom_threshold(self):
        """Custom grounding threshold should be respected."""
        source = "Some text with moderate similarity."
        synthesis = "Text with some overlap but differences too."

        # Low threshold
        sas_low = synthesis_attribution_score_sync(
            synthesis=synthesis,
            winning_responses=[source],
            all_responses=[source],
            grounding_threshold=0.3,
        )

        # High threshold
        sas_high = synthesis_attribution_score_sync(
            synthesis=synthesis,
            winning_responses=[source],
            all_responses=[source],
            grounding_threshold=0.9,
        )

        # Same alignment, different grounded status
        assert sas_low.max_source_alignment == sas_high.max_source_alignment
        # With different thresholds, grounded may differ
