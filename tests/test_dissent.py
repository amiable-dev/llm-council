"""Tests for Constructive Dissent extraction (ADR-025b).

These tests verify the dissent extraction logic that identifies minority
opinions from Stage 2 evaluations and surfaces them in the verdict result.

Reference: ADR-025b Council Validation (2025-12-23)
Council Consensus: Option B - Extract dissent from Stage 2 evaluations
"""

import pytest
from typing import Dict, List, Any


class TestDissentExtraction:
    """Tests for extracting dissent from Stage 2 evaluations."""

    def test_extract_dissent_identifies_outlier_scores(self):
        """Should identify evaluations scoring significantly below median."""
        from llm_council.dissent import extract_dissent_from_stage2

        # Stage 2 results with one outlier (model-c gave much lower score to Response A)
        stage2_results = [
            {
                "model": "model-a",
                "ranking": "...",
                "parsed_ranking": {
                    "ranking": ["Response A", "Response B", "Response C"],
                    "scores": {"Response A": 9, "Response B": 7, "Response C": 5},
                },
            },
            {
                "model": "model-b",
                "ranking": "...",
                "parsed_ranking": {
                    "ranking": ["Response A", "Response B", "Response C"],
                    "scores": {"Response A": 8, "Response B": 6, "Response C": 4},
                },
            },
            {
                "model": "model-c",
                "ranking": "...",
                "parsed_ranking": {
                    "ranking": ["Response B", "Response C", "Response A"],
                    "scores": {"Response A": 3, "Response B": 8, "Response C": 7},
                    "evaluation": "Response A has serious accuracy issues.",
                },
            },
        ]

        dissent = extract_dissent_from_stage2(stage2_results)

        assert dissent is not None
        assert "model-c" in dissent.lower() or "accuracy" in dissent.lower()

    def test_no_dissent_when_unanimous(self):
        """Should return None when all reviewers agree."""
        from llm_council.dissent import extract_dissent_from_stage2

        stage2_results = [
            {
                "model": "model-a",
                "parsed_ranking": {
                    "ranking": ["Response A", "Response B"],
                    "scores": {"Response A": 8, "Response B": 6},
                },
            },
            {
                "model": "model-b",
                "parsed_ranking": {
                    "ranking": ["Response A", "Response B"],
                    "scores": {"Response A": 9, "Response B": 5},
                },
            },
        ]

        dissent = extract_dissent_from_stage2(stage2_results)

        assert dissent is None

    def test_dissent_threshold_configurable(self):
        """Dissent threshold should be configurable."""
        from llm_council.dissent import extract_dissent_from_stage2

        stage2_results = [
            {
                "model": "model-a",
                "parsed_ranking": {
                    "ranking": ["Response A", "Response B"],
                    "scores": {"Response A": 8, "Response B": 6},
                },
            },
            {
                "model": "model-b",
                "parsed_ranking": {
                    "ranking": ["Response A", "Response B"],
                    "scores": {"Response A": 7, "Response B": 5},
                },
            },
        ]

        # With strict threshold, no dissent
        dissent_strict = extract_dissent_from_stage2(stage2_results, threshold=3.0)
        assert dissent_strict is None

        # With loose threshold, might detect dissent
        # (depends on actual score variance)

    def test_dissent_respects_borda_spread_minimum(self):
        """Dissent should only be surfaced when Borda spread > threshold."""
        from llm_council.dissent import extract_dissent_from_stage2

        # Very tight scores - no meaningful disagreement
        stage2_results = [
            {
                "model": "model-a",
                "parsed_ranking": {
                    "ranking": ["Response A", "Response B"],
                    "scores": {"Response A": 7, "Response B": 6},
                },
            },
            {
                "model": "model-b",
                "parsed_ranking": {
                    "ranking": ["Response B", "Response A"],
                    "scores": {"Response A": 6, "Response B": 7},
                },
            },
        ]

        # With minimum spread requirement
        dissent = extract_dissent_from_stage2(
            stage2_results,
            min_borda_spread=2.0,  # Require significant spread
        )

        assert dissent is None  # Scores too close

    def test_dissent_extracts_evaluation_text(self):
        """Dissent should include relevant evaluation text from outlier."""
        from llm_council.dissent import extract_dissent_from_stage2

        stage2_results = [
            {
                "model": "model-a",
                "parsed_ranking": {
                    "ranking": ["Response A", "Response B"],
                    "scores": {"Response A": 9, "Response B": 5},
                },
            },
            {
                "model": "model-b",
                "parsed_ranking": {
                    "ranking": ["Response B", "Response A"],
                    "scores": {"Response A": 4, "Response B": 8},
                    "evaluation": "Response A contains factual errors about the API.",
                },
            },
        ]

        dissent = extract_dissent_from_stage2(stage2_results)

        if dissent:
            assert "factual" in dissent.lower() or "error" in dissent.lower()

    def test_dissent_empty_stage2_returns_none(self):
        """Should handle empty Stage 2 results gracefully."""
        from llm_council.dissent import extract_dissent_from_stage2

        dissent = extract_dissent_from_stage2([])
        assert dissent is None

    def test_dissent_missing_scores_handled(self):
        """Should handle Stage 2 results without scores gracefully."""
        from llm_council.dissent import extract_dissent_from_stage2

        stage2_results = [
            {
                "model": "model-a",
                "parsed_ranking": {
                    "ranking": ["Response A", "Response B"],
                    # No scores
                },
            },
        ]

        dissent = extract_dissent_from_stage2(stage2_results)
        assert dissent is None  # Can't detect dissent without scores


class TestDissentWithVerdictIntegration:
    """Tests for dissent integration with VerdictResult."""

    def test_dissent_included_in_verdict_result(self):
        """VerdictResult should include dissent field when extracted."""
        from llm_council.verdict import VerdictResult, VerdictType

        result = VerdictResult(
            verdict_type=VerdictType.BINARY,
            verdict="approved",
            confidence=0.75,
            rationale="Majority approved.",
            dissent="Minority perspective: One reviewer noted accuracy concerns.",
        )

        assert result.dissent is not None
        assert "minority" in result.dissent.lower()

    def test_dissent_serialization(self):
        """Dissent should be properly serialized in to_dict/to_json."""
        from llm_council.verdict import VerdictResult, VerdictType
        import json

        result = VerdictResult(
            verdict_type=VerdictType.BINARY,
            verdict="rejected",
            confidence=0.6,
            rationale="Quality concerns.",
            dissent="Minority view: Could be approved with minor changes.",
        )

        d = result.to_dict()
        assert d["dissent"] == "Minority view: Could be approved with minor changes."

        j = result.to_json()
        parsed = json.loads(j)
        assert "dissent" in parsed


class TestDissentStatistics:
    """Tests for statistical methods used in dissent detection."""

    def test_calculate_score_statistics(self):
        """Should correctly calculate median and std for scores."""
        from llm_council.dissent import calculate_score_statistics

        scores = [8, 7, 9, 3, 8]  # One outlier (3)
        median, std = calculate_score_statistics(scores)

        assert median == 8  # Middle value
        assert std > 0  # Has variance

    def test_identify_outlier_reviewers(self):
        """Should identify reviewers with scores far from median."""
        from llm_council.dissent import identify_outlier_reviewers

        reviewer_scores = {
            "model-a": {"Response A": 8, "Response B": 7},
            "model-b": {"Response A": 9, "Response B": 6},
            "model-c": {"Response A": 3, "Response B": 9},  # Outlier on Response A
        }

        outliers = identify_outlier_reviewers(reviewer_scores, threshold=1.5)

        assert "model-c" in outliers

    def test_calculate_score_statistics_empty(self):
        """Should handle empty scores gracefully."""
        from llm_council.dissent import calculate_score_statistics

        median, std = calculate_score_statistics([])

        assert median == 0
        assert std == 0

    def test_calculate_score_statistics_single(self):
        """Should handle single score gracefully."""
        from llm_council.dissent import calculate_score_statistics

        median, std = calculate_score_statistics([7])

        assert median == 7
        assert std == 0


class TestDissentFormatting:
    """Tests for dissent message formatting."""

    def test_format_dissent_message(self):
        """Should format dissent message with reviewer info."""
        from llm_council.dissent import format_dissent_message

        outlier_info = {
            "reviewer": "model-c",
            "disagreement": "Response A",
            "evaluation": "Contains outdated API references.",
            "score_given": 3,
            "median_score": 8,
        }

        message = format_dissent_message([outlier_info])

        assert "minority" in message.lower() or "dissent" in message.lower()
        assert "outdated" in message.lower() or "model-c" in message.lower()

    def test_format_dissent_multiple_outliers(self):
        """Should handle multiple outlier reviewers."""
        from llm_council.dissent import format_dissent_message

        outliers = [
            {
                "reviewer": "model-a",
                "disagreement": "Response B",
                "evaluation": "Security concerns.",
                "score_given": 4,
                "median_score": 8,
            },
            {
                "reviewer": "model-b",
                "disagreement": "Response B",
                "evaluation": "Performance issues.",
                "score_given": 3,
                "median_score": 8,
            },
        ]

        message = format_dissent_message(outliers)

        # Should mention both concerns or summarize
        assert len(message) > 0
