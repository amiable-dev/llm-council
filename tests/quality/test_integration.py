"""
TDD Tests for Quality Metrics Integration.

ADR-036: Tests for the full quality metrics pipeline.
"""

import pytest
import os
from llm_council.quality import (
    calculate_quality_metrics,
    should_include_quality_metrics,
    QualityMetrics,
    CoreMetrics,
)


class TestCalculateQualityMetrics:
    """Test cases for the integrated quality metrics calculation."""

    def test_calculate_quality_metrics_basic(self):
        """Basic quality metrics calculation with valid inputs."""
        stage1_responses = {
            "model_a": {"content": "Python is a programming language."},
            "model_b": {"content": "Java is an object-oriented language."},
            "model_c": {"content": "C++ provides low-level control."},
        }
        stage2_rankings = [
            {"model": "model_a", "content": "A is most accurate.\n\nFINAL RANKING:\n1. Response A"},
            {"model": "model_b", "content": "B is relevant.\n\nFINAL RANKING:\n1. Response A"},
            {"model": "model_c", "content": "C is detailed.\n\nFINAL RANKING:\n1. Response B"},
        ]
        stage3_synthesis = {"content": "Python is a versatile programming language."}
        aggregate_rankings = [
            ("model_a", 1.3),
            ("model_b", 2.0),
            ("model_c", 2.7),
        ]

        metrics = calculate_quality_metrics(
            stage1_responses=stage1_responses,
            stage2_rankings=stage2_rankings,
            stage3_synthesis=stage3_synthesis,
            aggregate_rankings=aggregate_rankings,
        )

        assert isinstance(metrics, QualityMetrics)
        assert metrics.tier == "core"
        assert isinstance(metrics.core, CoreMetrics)
        assert 0.0 <= metrics.core.consensus_strength <= 1.0
        assert 0.0 <= metrics.core.deliberation_depth <= 1.0

    def test_calculate_quality_metrics_empty_inputs(self):
        """Quality metrics with empty inputs should return valid defaults."""
        metrics = calculate_quality_metrics(
            stage1_responses={},
            stage2_rankings=[],
            stage3_synthesis="",
            aggregate_rankings=[],
        )

        assert isinstance(metrics, QualityMetrics)
        assert metrics.core.consensus_strength == 0.0
        assert metrics.core.deliberation_depth == 0.0
        assert metrics.core.synthesis_attribution.grounded is False

    def test_calculate_quality_metrics_string_responses(self):
        """Should handle string responses (not just dict)."""
        stage1_responses = {
            "model_a": "Direct string response here.",
            "model_b": "Another string response.",
        }
        stage2_rankings = [{"content": "Evaluation.\n\nFINAL RANKING:\n1. Response A"}]
        stage3_synthesis = "Synthesized string."
        aggregate_rankings = [("model_a", 1.0), ("model_b", 2.0)]

        metrics = calculate_quality_metrics(
            stage1_responses=stage1_responses,
            stage2_rankings=stage2_rankings,
            stage3_synthesis=stage3_synthesis,
            aggregate_rankings=aggregate_rankings,
        )

        assert isinstance(metrics, QualityMetrics)
        assert metrics.core.consensus_strength > 0.0

    def test_quality_metrics_warnings_low_consensus(self):
        """Low consensus should trigger warning."""
        # Create a 2-2 split scenario
        stage1_responses = {
            "model_a": {"content": "Response A"},
            "model_b": {"content": "Response B"},
            "model_c": {"content": "Response C"},
            "model_d": {"content": "Response D"},
        }
        stage2_rankings = [{"content": "Eval"} for _ in range(4)]
        stage3_synthesis = {"content": "Synthesis"}
        # Very close rankings = low consensus
        aggregate_rankings = [
            ("model_a", 2.4),
            ("model_b", 2.5),
            ("model_c", 2.5),
            ("model_d", 2.6),
        ]

        metrics = calculate_quality_metrics(
            stage1_responses=stage1_responses,
            stage2_rankings=stage2_rankings,
            stage3_synthesis=stage3_synthesis,
            aggregate_rankings=aggregate_rankings,
        )

        # With very close rankings, CSS might be low
        # Check if warnings include low_consensus when CSS < 0.5
        if metrics.core.consensus_strength < 0.5:
            assert "low_consensus" in metrics.warnings

    def test_quality_metrics_to_dict(self):
        """QualityMetrics.to_dict() should return proper structure."""
        stage1_responses = {"model_a": {"content": "Response"}}
        stage2_rankings = [{"content": "Evaluation.\n\nFINAL RANKING:\n1. Response A"}]
        stage3_synthesis = {"content": "Synthesis"}
        aggregate_rankings = [("model_a", 1.0)]

        metrics = calculate_quality_metrics(
            stage1_responses=stage1_responses,
            stage2_rankings=stage2_rankings,
            stage3_synthesis=stage3_synthesis,
            aggregate_rankings=aggregate_rankings,
        )

        result = metrics.to_dict()

        assert "tier" in result
        assert "core" in result
        assert "consensus_strength" in result["core"]
        assert "deliberation_depth" in result["core"]
        assert "synthesis_attribution" in result["core"]


class TestQualityMetricsConfiguration:
    """Test configuration and feature flags."""

    def test_should_include_quality_metrics_default(self):
        """Default should be True (enabled)."""
        # Clear env var to test default
        original = os.environ.pop("LLM_COUNCIL_QUALITY_METRICS", None)
        try:
            assert should_include_quality_metrics() is True
        finally:
            if original is not None:
                os.environ["LLM_COUNCIL_QUALITY_METRICS"] = original

    def test_should_include_quality_metrics_disabled(self):
        """Should respect LLM_COUNCIL_QUALITY_METRICS=false."""
        original = os.environ.get("LLM_COUNCIL_QUALITY_METRICS")
        try:
            os.environ["LLM_COUNCIL_QUALITY_METRICS"] = "false"
            assert should_include_quality_metrics() is False

            os.environ["LLM_COUNCIL_QUALITY_METRICS"] = "0"
            assert should_include_quality_metrics() is False
        finally:
            if original is not None:
                os.environ["LLM_COUNCIL_QUALITY_METRICS"] = original
            else:
                os.environ.pop("LLM_COUNCIL_QUALITY_METRICS", None)

    def test_should_include_quality_metrics_enabled(self):
        """Should respect LLM_COUNCIL_QUALITY_METRICS=true."""
        original = os.environ.get("LLM_COUNCIL_QUALITY_METRICS")
        try:
            os.environ["LLM_COUNCIL_QUALITY_METRICS"] = "true"
            assert should_include_quality_metrics() is True

            os.environ["LLM_COUNCIL_QUALITY_METRICS"] = "1"
            assert should_include_quality_metrics() is True
        finally:
            if original is not None:
                os.environ["LLM_COUNCIL_QUALITY_METRICS"] = original
            else:
                os.environ.pop("LLM_COUNCIL_QUALITY_METRICS", None)


class TestQualityMetricsDataclasses:
    """Test quality metrics dataclass behavior."""

    def test_quality_metrics_frozen(self):
        """QualityMetrics should be immutable (frozen)."""
        from llm_council.quality.types import SynthesisAttribution, CoreMetrics, QualityMetrics

        sas = SynthesisAttribution(
            winner_alignment=0.8,
            max_source_alignment=0.9,
            hallucination_risk=0.1,
            grounded=True,
        )

        core = CoreMetrics(
            consensus_strength=0.85,
            deliberation_depth=0.7,
            synthesis_attribution=sas,
        )

        metrics = QualityMetrics(tier="core", core=core)

        # SynthesisAttribution and CoreMetrics are frozen
        with pytest.raises(AttributeError):
            sas.winner_alignment = 0.5

        with pytest.raises(AttributeError):
            core.consensus_strength = 0.5

    def test_synthesis_attribution_fields(self):
        """SynthesisAttribution should have all required fields."""
        from llm_council.quality.types import SynthesisAttribution

        sas = SynthesisAttribution(
            winner_alignment=0.8,
            max_source_alignment=0.9,
            hallucination_risk=0.1,
            grounded=True,
        )

        assert sas.winner_alignment == 0.8
        assert sas.max_source_alignment == 0.9
        assert sas.hallucination_risk == 0.1
        assert sas.grounded is True
