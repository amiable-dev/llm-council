"""Tests for ADR-015: Bias Auditing and Length Correlation Tracking.

TDD tests for bias detection in peer review scoring.
"""

import pytest
from dataclasses import asdict

from llm_council.bias_audit import (
    BiasAuditResult,
    calculate_length_correlation,
    audit_reviewer_calibration,
    calculate_position_bias,
    run_bias_audit,
    extract_scores_from_stage2,
    derive_position_mapping,
)
from llm_council.unified_config import get_config

# Get thresholds from config
_config = get_config()
LENGTH_CORRELATION_THRESHOLD = _config.evaluation.bias.length_correlation_threshold
POSITION_VARIANCE_THRESHOLD = _config.evaluation.bias.position_variance_threshold


class TestBiasAuditResult:
    """Tests for BiasAuditResult dataclass."""

    def test_dataclass_creation(self):
        """Test creating BiasAuditResult with all fields."""
        result = BiasAuditResult(
            length_score_correlation=0.42,
            length_score_p_value=0.023,
            length_bias_detected=True,
            position_score_variance=0.12,
            position_bias_detected=False,
            reviewer_mean_scores={"model-a": 6.5, "model-b": 7.2},
            reviewer_score_variance={"model-a": 1.2, "model-b": 0.8},
            harsh_reviewers=["model-a"],
            generous_reviewers=[],
            overall_bias_risk="medium",
        )
        assert result.length_score_correlation == 0.42
        assert result.length_bias_detected is True
        assert result.overall_bias_risk == "medium"

    def test_dataclass_to_dict(self):
        """Test converting to dict for JSON serialization."""
        result = BiasAuditResult(
            length_score_correlation=0.15,
            length_score_p_value=0.5,
            length_bias_detected=False,
            position_score_variance=None,
            position_bias_detected=None,
            reviewer_mean_scores={},
            reviewer_score_variance={},
            harsh_reviewers=[],
            generous_reviewers=[],
            overall_bias_risk="low",
        )
        d = asdict(result)
        assert d["length_score_correlation"] == 0.15
        assert d["overall_bias_risk"] == "low"


class TestLengthCorrelation:
    """Tests for length-score correlation calculation."""

    def test_positive_correlation(self):
        """Detect positive correlation (longer responses score higher)."""
        responses = [
            {"model": "model-a", "response": "short"},  # 1 word
            {"model": "model-b", "response": "medium length response here"},  # 4 words
            {
                "model": "model-c",
                "response": "this is a much longer response with many words",
            },  # 9 words
        ]
        # Scores increase with length
        scores = {
            "reviewer-1": {"model-a": 5, "model-b": 7, "model-c": 9},
            "reviewer-2": {"model-a": 4, "model-b": 6, "model-c": 8},
        }
        r, p = calculate_length_correlation(responses, scores)
        assert r > 0.9  # Strong positive correlation
        assert p < 0.5  # Reasonably significant (with only 3 points)

    def test_negative_correlation(self):
        """Detect negative correlation (shorter responses score higher)."""
        responses = [
            {"model": "model-a", "response": "short"},  # 1 word
            {"model": "model-b", "response": "medium length response here"},  # 4 words
            {
                "model": "model-c",
                "response": "this is a much longer response with many words",
            },  # 9 words
        ]
        # Scores decrease with length
        scores = {
            "reviewer-1": {"model-a": 9, "model-b": 7, "model-c": 5},
            "reviewer-2": {"model-a": 8, "model-b": 6, "model-c": 4},
        }
        r, p = calculate_length_correlation(responses, scores)
        assert r < -0.9  # Strong negative correlation

    def test_no_correlation(self):
        """No significant correlation when scores don't correlate with length."""
        responses = [
            {"model": "model-a", "response": "a"},  # 1 word
            {"model": "model-b", "response": "a b c d e"},  # 5 words
            {"model": "model-c", "response": "a b c d e f g h i j"},  # 10 words
        ]
        # Scores designed to have no correlation with length
        # Middle length gets highest, extremes get similar scores
        scores = {
            "reviewer-1": {"model-a": 7, "model-b": 9, "model-c": 7},
            "reviewer-2": {"model-a": 8, "model-b": 8, "model-c": 6},
        }
        r, p = calculate_length_correlation(responses, scores)
        assert abs(r) < 0.7  # Weak correlation at most

    def test_insufficient_data(self):
        """Return (0.0, 1.0) when fewer than 3 responses."""
        responses = [
            {"model": "model-a", "response": "short"},
            {"model": "model-b", "response": "longer response"},
        ]
        scores = {
            "reviewer-1": {"model-a": 5, "model-b": 8},
        }
        r, p = calculate_length_correlation(responses, scores)
        assert r == 0.0
        assert p == 1.0

    def test_empty_responses(self):
        """Handle empty response list."""
        r, p = calculate_length_correlation([], {})
        assert r == 0.0
        assert p == 1.0

    def test_missing_scores_for_some_models(self):
        """Handle case where not all models have scores."""
        responses = [
            {"model": "model-a", "response": "short"},
            {"model": "model-b", "response": "medium response"},
            {"model": "model-c", "response": "longer response here"},
        ]
        # Only two models have scores
        scores = {
            "reviewer-1": {"model-a": 5, "model-c": 8},
        }
        r, p = calculate_length_correlation(responses, scores)
        # Should handle gracefully with available data
        assert isinstance(r, float)
        assert isinstance(p, float)


class TestReviewerCalibration:
    """Tests for reviewer calibration analysis."""

    def test_calibration_calculation(self):
        """Calculate mean and std for each reviewer."""
        scores = {
            "reviewer-a": {"model-1": 7, "model-2": 8, "model-3": 6},
            "reviewer-b": {"model-1": 5, "model-2": 4, "model-3": 6},
        }
        calibration = audit_reviewer_calibration(scores)

        assert "reviewer-a" in calibration
        assert "reviewer-b" in calibration
        assert abs(calibration["reviewer-a"]["mean"] - 7.0) < 0.01
        assert abs(calibration["reviewer-b"]["mean"] - 5.0) < 0.01
        assert calibration["reviewer-a"]["count"] == 3

    def test_identifies_harsh_reviewer(self):
        """Identify reviewer with mean significantly below median."""
        scores = {
            "generous": {"m1": 10, "m2": 10, "m3": 10},  # mean = 10.0
            "normal-1": {"m1": 7, "m2": 6, "m3": 7},  # mean = 6.67
            "normal-2": {"m1": 7, "m2": 7, "m3": 6},  # mean = 6.67
            "harsh": {"m1": 2, "m2": 3, "m3": 2},  # mean = 2.33
        }
        calibration = audit_reviewer_calibration(scores)

        # Calculate harsh/generous thresholds
        means = [c["mean"] for c in calibration.values()]
        from statistics import median, stdev

        med = median(means)
        std = stdev(means)

        harsh_threshold = med - std
        generous_threshold = med + std

        assert calibration["harsh"]["mean"] < harsh_threshold
        assert calibration["generous"]["mean"] > generous_threshold

    def test_empty_scores(self):
        """Handle empty scores dict."""
        calibration = audit_reviewer_calibration({})
        assert calibration == {}

    def test_single_reviewer(self):
        """Handle single reviewer case."""
        scores = {
            "only-reviewer": {"m1": 7, "m2": 8, "m3": 6},
        }
        calibration = audit_reviewer_calibration(scores)
        assert len(calibration) == 1
        assert "only-reviewer" in calibration


class TestPositionBias:
    """Tests for position bias detection."""

    def test_position_bias_detected(self):
        """Detect when position A consistently scores higher."""
        # Position mapping: which label was shown in which position
        position_mapping = {
            "Response A": 0,  # First position
            "Response B": 1,  # Second position
            "Response C": 2,  # Third position
        }
        # Scores by reviewer showing first position always rates highest
        scores = {
            "reviewer-1": {"Response A": 9, "Response B": 5, "Response C": 4},
            "reviewer-2": {"Response A": 8, "Response B": 6, "Response C": 5},
            "reviewer-3": {"Response A": 9, "Response B": 4, "Response C": 5},
        }
        variance, detected = calculate_position_bias(scores, position_mapping)
        assert variance is not None
        assert variance > POSITION_VARIANCE_THRESHOLD
        assert detected is True

    def test_no_position_bias(self):
        """No bias when scores are similar across positions."""
        position_mapping = {
            "Response A": 0,
            "Response B": 1,
            "Response C": 2,
        }
        # Scores relatively uniform across positions
        scores = {
            "reviewer-1": {"Response A": 7, "Response B": 7, "Response C": 7},
            "reviewer-2": {"Response A": 6, "Response B": 8, "Response C": 7},
            "reviewer-3": {"Response A": 8, "Response B": 6, "Response C": 7},
        }
        variance, detected = calculate_position_bias(scores, position_mapping)
        assert variance is not None
        assert variance < POSITION_VARIANCE_THRESHOLD
        assert detected is False

    def test_no_position_mapping(self):
        """Return None when no position mapping provided."""
        scores = {
            "reviewer-1": {"Response A": 7, "Response B": 8},
        }
        variance, detected = calculate_position_bias(scores, None)
        assert variance is None
        assert detected is None

    def test_empty_position_mapping(self):
        """Handle empty position mapping."""
        scores = {
            "reviewer-1": {"Response A": 7, "Response B": 8},
        }
        variance, detected = calculate_position_bias(scores, {})
        assert variance is None
        assert detected is None


class TestOverallRiskAssessment:
    """Tests for overall bias risk calculation."""

    def test_low_risk_no_biases(self):
        """Low risk when no biases detected."""
        responses = [
            {"model": "m1", "response": "a b c"},
            {"model": "m2", "response": "d e f g"},
            {"model": "m3", "response": "h i j k l"},
        ]
        scores = {
            "r1": {"m1": 7, "m2": 7, "m3": 7},
            "r2": {"m1": 6, "m2": 8, "m3": 7},
        }
        result = run_bias_audit(responses, scores)
        assert result.overall_bias_risk == "low"

    def test_medium_risk_some_biases(self):
        """Medium risk when 1-2 biases detected."""
        responses = [
            {"model": "m1", "response": "a"},
            {"model": "m2", "response": "a b c d e"},
            {"model": "m3", "response": "a b c d e f g h i j"},
        ]
        # Strong length correlation
        scores = {
            "r1": {"m1": 3, "m2": 6, "m3": 9},
            "r2": {"m1": 4, "m2": 7, "m3": 10},
        }
        result = run_bias_audit(responses, scores)
        # Should detect length bias
        assert result.length_bias_detected is True
        assert result.overall_bias_risk in ["medium", "high"]

    def test_high_risk_multiple_biases(self):
        """High risk when 3+ biases detected."""
        responses = [
            {"model": "m1", "response": "a"},
            {"model": "m2", "response": "a b c d e"},
            {"model": "m3", "response": "a b c d e f g h i j"},
        ]
        # Strong length correlation + harsh/generous reviewers + position bias
        scores = {
            "harsh": {"m1": 1, "m2": 2, "m3": 3},  # Very low scores (mean=2)
            "generous": {"m1": 9, "m2": 10, "m3": 10},  # Very high scores (mean=9.67)
            "normal": {"m1": 4, "m2": 6, "m3": 8},  # Normal scores (mean=6)
        }
        # Position mapping showing first position gets highest scores consistently
        position_mapping = {"m1": 0, "m2": 1, "m3": 2}
        result = run_bias_audit(responses, scores, position_mapping)
        # Should detect: length bias + harsh reviewer + generous reviewer = 3+ biases
        assert result.overall_bias_risk == "high"


class TestExtractScoresFromStage2:
    """Tests for extracting scores from Stage 2 results."""

    def test_extract_holistic_scores(self):
        """Extract scores from holistic scoring format."""
        stage2_results = [
            {
                "model": "reviewer-a",
                "parsed_ranking": {
                    "ranking": ["Response A", "Response B"],
                    "scores": {"Response A": 8, "Response B": 6},
                },
            },
            {
                "model": "reviewer-b",
                "parsed_ranking": {
                    "ranking": ["Response B", "Response A"],
                    "scores": {"Response A": 7, "Response B": 9},
                },
            },
        ]
        label_to_model = {
            "Response A": "model-1",
            "Response B": "model-2",
        }
        scores = extract_scores_from_stage2(stage2_results, label_to_model)

        assert "reviewer-a" in scores
        assert "reviewer-b" in scores
        assert scores["reviewer-a"]["model-1"] == 8
        assert scores["reviewer-a"]["model-2"] == 6
        assert scores["reviewer-b"]["model-1"] == 7
        assert scores["reviewer-b"]["model-2"] == 9

    def test_extract_rubric_scores(self):
        """Extract overall scores from rubric scoring format."""
        stage2_results = [
            {
                "model": "reviewer-a",
                "parsed_ranking": {
                    "ranking": ["Response A", "Response B"],
                    "scores": {"Response A": 8.5, "Response B": 6.2},
                    "evaluations": {
                        "Response A": {"accuracy": 9, "clarity": 8},
                        "Response B": {"accuracy": 6, "clarity": 7},
                    },
                    "rubric_scoring": True,
                },
            },
        ]
        label_to_model = {
            "Response A": "model-1",
            "Response B": "model-2",
        }
        scores = extract_scores_from_stage2(stage2_results, label_to_model)

        assert scores["reviewer-a"]["model-1"] == 8.5
        assert scores["reviewer-a"]["model-2"] == 6.2

    def test_handle_missing_scores(self):
        """Handle results with missing scores gracefully."""
        stage2_results = [
            {
                "model": "reviewer-a",
                "parsed_ranking": {
                    "ranking": ["Response A"],
                    # No scores dict
                },
            },
        ]
        label_to_model = {"Response A": "model-1"}
        scores = extract_scores_from_stage2(stage2_results, label_to_model)

        # Should return empty or partial results
        assert "reviewer-a" in scores
        assert len(scores["reviewer-a"]) == 0  # No scores extracted

    def test_handle_abstained_reviewer(self):
        """Handle reviewer that abstained from scoring."""
        stage2_results = [
            {
                "model": "reviewer-a",
                "parsed_ranking": {
                    "ranking": [],
                    "scores": {},
                    "abstained": True,
                },
            },
        ]
        label_to_model = {"Response A": "model-1"}
        scores = extract_scores_from_stage2(stage2_results, label_to_model)

        assert scores == {} or len(scores.get("reviewer-a", {})) == 0


class TestBiasAuditIntegration:
    """Integration tests for full bias audit pipeline."""

    def test_full_audit_with_position_data(self):
        """Run full audit with position mapping."""
        responses = [
            {"model": "model-a", "response": "short answer"},
            {"model": "model-b", "response": "medium length answer here"},
            {"model": "model-c", "response": "this is a longer answer with more content"},
        ]
        scores = {
            "reviewer-1": {"model-a": 7, "model-b": 8, "model-c": 6},
            "reviewer-2": {"model-a": 6, "model-b": 7, "model-c": 8},
        }
        position_mapping = {
            "model-a": 0,
            "model-b": 1,
            "model-c": 2,
        }

        result = run_bias_audit(responses, scores, position_mapping)

        assert isinstance(result, BiasAuditResult)
        assert isinstance(result.length_score_correlation, float)
        assert isinstance(result.length_bias_detected, bool)
        assert result.position_score_variance is not None
        assert result.position_bias_detected is not None
        assert result.overall_bias_risk in ["low", "medium", "high"]

    def test_audit_result_serializable(self):
        """Ensure audit result can be serialized to JSON."""
        import json

        responses = [
            {"model": "m1", "response": "a b c"},
            {"model": "m2", "response": "d e f g"},
            {"model": "m3", "response": "h i j k l"},
        ]
        scores = {
            "r1": {"m1": 7, "m2": 8, "m3": 6},
        }

        result = run_bias_audit(responses, scores)
        result_dict = asdict(result)

        # Should serialize without error
        json_str = json.dumps(result_dict)
        assert isinstance(json_str, str)

        # Should deserialize back
        parsed = json.loads(json_str)
        assert parsed["overall_bias_risk"] in ["low", "medium", "high"]


class TestDerivePositionMapping:
    """Tests for derive_position_mapping helper function.

    This function derives position indices from label_to_model mapping.
    'Response A' → position 0, 'Response B' → position 1, etc.
    """

    def test_basic_mapping_three_responses(self):
        """Derive positions for 3 responses."""
        label_to_model = {
            "Response A": "openai/gpt-4",
            "Response B": "anthropic/claude-3",
            "Response C": "google/gemini-pro",
        }
        position_mapping = derive_position_mapping(label_to_model)

        assert position_mapping == {
            "openai/gpt-4": 0,
            "anthropic/claude-3": 1,
            "google/gemini-pro": 2,
        }

    def test_four_responses(self):
        """Derive positions for 4 responses."""
        label_to_model = {
            "Response A": "model-a",
            "Response B": "model-b",
            "Response C": "model-c",
            "Response D": "model-d",
        }
        position_mapping = derive_position_mapping(label_to_model)

        assert position_mapping["model-a"] == 0
        assert position_mapping["model-b"] == 1
        assert position_mapping["model-c"] == 2
        assert position_mapping["model-d"] == 3

    def test_handles_out_of_order_dict(self):
        """Handle dict that isn't in A, B, C order (unlikely but possible)."""
        label_to_model = {
            "Response C": "model-c",
            "Response A": "model-a",
            "Response B": "model-b",
        }
        position_mapping = derive_position_mapping(label_to_model)

        # Position is derived from letter, not insertion order
        assert position_mapping["model-a"] == 0
        assert position_mapping["model-b"] == 1
        assert position_mapping["model-c"] == 2

    def test_empty_mapping(self):
        """Return empty dict for empty input."""
        position_mapping = derive_position_mapping({})
        assert position_mapping == {}

    def test_none_input(self):
        """Return empty dict for None input."""
        position_mapping = derive_position_mapping(None)
        assert position_mapping == {}

    def test_single_response(self):
        """Handle single response case."""
        label_to_model = {"Response A": "only-model"}
        position_mapping = derive_position_mapping(label_to_model)

        assert position_mapping == {"only-model": 0}

    def test_non_standard_label_format(self):
        """Handle labels that don't match expected format gracefully."""
        label_to_model = {
            "Response A": "model-a",
            "Model B": "model-b",  # Non-standard format
            "Response C": "model-c",
        }
        position_mapping = derive_position_mapping(label_to_model)

        # Should still map valid Response X labels
        assert position_mapping.get("model-a") == 0
        assert position_mapping.get("model-c") == 2
        # Non-standard label might be skipped or handled gracefully

    def test_lowercase_response_labels(self):
        """Handle lowercase 'response a' format gracefully."""
        label_to_model = {
            "response a": "model-a",
            "response b": "model-b",
        }
        position_mapping = derive_position_mapping(label_to_model)

        # Should handle case-insensitively
        assert position_mapping.get("model-a") == 0
        assert position_mapping.get("model-b") == 1

    def test_enhanced_format_with_display_index(self):
        """Use display_index from enhanced format (council-recommended hardening)."""
        label_to_model = {
            "Response A": {"model": "openai/gpt-4", "display_index": 0},
            "Response B": {"model": "anthropic/claude-3", "display_index": 1},
            "Response C": {"model": "google/gemini-pro", "display_index": 2},
        }
        position_mapping = derive_position_mapping(label_to_model)

        assert position_mapping == {
            "openai/gpt-4": 0,
            "anthropic/claude-3": 1,
            "google/gemini-pro": 2,
        }

    def test_enhanced_format_with_shuffled_indices(self):
        """Enhanced format correctly handles non-alphabetical display order."""
        # Simulates a scenario where Response A was shown second
        label_to_model = {
            "Response A": {"model": "model-a", "display_index": 1},
            "Response B": {"model": "model-b", "display_index": 0},
            "Response C": {"model": "model-c", "display_index": 2},
        }
        position_mapping = derive_position_mapping(label_to_model)

        # display_index takes precedence over label letter
        assert position_mapping["model-a"] == 1  # A was shown second
        assert position_mapping["model-b"] == 0  # B was shown first
        assert position_mapping["model-c"] == 2

    def test_mixed_format_prefers_enhanced(self):
        """When both formats present, prefer enhanced display_index."""
        # This shouldn't happen in practice, but test defensive behavior
        label_to_model = {
            "Response A": {"model": "model-a", "display_index": 2},  # Enhanced
            "Response B": "model-b",  # Legacy
        }
        position_mapping = derive_position_mapping(label_to_model)

        # Enhanced format uses display_index
        assert position_mapping.get("model-a") == 2
        # Legacy format falls back to letter parsing
        assert position_mapping.get("model-b") == 1

    def test_enhanced_format_missing_display_index(self):
        """Handle enhanced format dict missing display_index gracefully."""
        label_to_model = {
            "Response A": {"model": "model-a"},  # Missing display_index
            "Response B": {"model": "model-b", "display_index": 1},
        }
        position_mapping = derive_position_mapping(label_to_model)

        # Falls back to letter parsing when display_index missing
        assert position_mapping.get("model-a") == 0
        assert position_mapping.get("model-b") == 1
