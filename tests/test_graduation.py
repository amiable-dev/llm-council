"""TDD tests for ADR-027: GraduationCriteria and should_graduate().

Tests for the graduation criteria that determine when a frontier model
can be promoted to the high tier.

This implements Issue #112.
"""

import pytest
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from dataclasses import dataclass


class TestGraduationCriteriaDataclass:
    """Test GraduationCriteria dataclass structure."""

    def test_graduation_criteria_has_all_required_fields(self):
        """GraduationCriteria should have all fields from ADR-027."""
        from llm_council.graduation import GraduationCriteria

        criteria = GraduationCriteria()

        # Check all fields exist
        assert hasattr(criteria, "min_age_days")
        assert hasattr(criteria, "min_completed_sessions")
        assert hasattr(criteria, "max_error_rate")
        assert hasattr(criteria, "min_quality_percentile")
        assert hasattr(criteria, "api_stability")
        assert hasattr(criteria, "provider_ga_status")

    def test_default_values_match_adr027(self):
        """Default values should match ADR-027 specification."""
        from llm_council.graduation import GraduationCriteria

        criteria = GraduationCriteria()

        assert criteria.min_age_days == 30
        assert criteria.min_completed_sessions == 100
        assert criteria.max_error_rate == 0.02  # < 2% errors
        assert criteria.min_quality_percentile == 0.75  # >= 75th percentile
        assert criteria.api_stability is True
        assert criteria.provider_ga_status is True

    def test_custom_values_can_be_set(self):
        """GraduationCriteria should accept custom values."""
        from llm_council.graduation import GraduationCriteria

        criteria = GraduationCriteria(
            min_age_days=60,
            min_completed_sessions=200,
            max_error_rate=0.01,
            min_quality_percentile=0.90,
            api_stability=False,
            provider_ga_status=False,
        )

        assert criteria.min_age_days == 60
        assert criteria.min_completed_sessions == 200
        assert criteria.max_error_rate == 0.01
        assert criteria.min_quality_percentile == 0.90


class TestModelStats:
    """Test ModelStats dataclass for tracking model performance."""

    def test_model_stats_has_required_fields(self):
        """ModelStats should have all required tracking fields."""
        from llm_council.graduation import ModelStats

        stats = ModelStats(
            model_id="openai/gpt-5.2-pro",
            days_tracked=45,
            completed_sessions=150,
            error_rate=0.01,
            quality_percentile=0.85,
        )

        assert stats.model_id == "openai/gpt-5.2-pro"
        assert stats.days_tracked == 45
        assert stats.completed_sessions == 150
        assert stats.error_rate == 0.01
        assert stats.quality_percentile == 0.85


class TestShouldGraduate:
    """Test should_graduate() function."""

    def test_should_graduate_returns_tuple(self):
        """should_graduate() should return (bool, list) tuple."""
        from llm_council.graduation import (
            GraduationCriteria,
            ModelStats,
            should_graduate,
        )

        criteria = GraduationCriteria()
        stats = ModelStats(
            model_id="test/model",
            days_tracked=30,
            completed_sessions=100,
            error_rate=0.01,
            quality_percentile=0.80,
        )

        result = should_graduate(stats, criteria)

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert isinstance(result[1], list)

    def test_fails_when_age_insufficient(self):
        """Should fail when model age is below minimum."""
        from llm_council.graduation import (
            GraduationCriteria,
            ModelStats,
            should_graduate,
        )

        criteria = GraduationCriteria()
        stats = ModelStats(
            model_id="test/model",
            days_tracked=15,  # Below 30 day minimum
            completed_sessions=100,
            error_rate=0.01,
            quality_percentile=0.80,
        )

        passed, failures = should_graduate(stats, criteria)

        assert passed is False
        assert len(failures) == 1
        assert "age" in failures[0].lower()
        assert "15" in failures[0]
        assert "30" in failures[0]

    def test_fails_when_sessions_insufficient(self):
        """Should fail when completed sessions is below minimum."""
        from llm_council.graduation import (
            GraduationCriteria,
            ModelStats,
            should_graduate,
        )

        criteria = GraduationCriteria()
        stats = ModelStats(
            model_id="test/model",
            days_tracked=45,
            completed_sessions=50,  # Below 100 minimum
            error_rate=0.01,
            quality_percentile=0.80,
        )

        passed, failures = should_graduate(stats, criteria)

        assert passed is False
        assert len(failures) == 1
        assert "sessions" in failures[0].lower()
        assert "50" in failures[0]
        assert "100" in failures[0]

    def test_fails_when_error_rate_too_high(self):
        """Should fail when error rate exceeds maximum."""
        from llm_council.graduation import (
            GraduationCriteria,
            ModelStats,
            should_graduate,
        )

        criteria = GraduationCriteria()
        stats = ModelStats(
            model_id="test/model",
            days_tracked=45,
            completed_sessions=150,
            error_rate=0.05,  # Above 2% maximum
            quality_percentile=0.80,
        )

        passed, failures = should_graduate(stats, criteria)

        assert passed is False
        assert len(failures) == 1
        assert "error" in failures[0].lower()

    def test_fails_when_quality_too_low(self):
        """Should fail when quality percentile is below minimum."""
        from llm_council.graduation import (
            GraduationCriteria,
            ModelStats,
            should_graduate,
        )

        criteria = GraduationCriteria()
        stats = ModelStats(
            model_id="test/model",
            days_tracked=45,
            completed_sessions=150,
            error_rate=0.01,
            quality_percentile=0.60,  # Below 75th percentile
        )

        passed, failures = should_graduate(stats, criteria)

        assert passed is False
        assert len(failures) == 1
        assert "quality" in failures[0].lower()

    def test_passes_when_all_criteria_met(self):
        """Should pass when all criteria are met."""
        from llm_council.graduation import (
            GraduationCriteria,
            ModelStats,
            should_graduate,
        )

        criteria = GraduationCriteria()
        stats = ModelStats(
            model_id="openai/gpt-5.2-pro",
            days_tracked=45,
            completed_sessions=150,
            error_rate=0.01,
            quality_percentile=0.85,
        )

        passed, failures = should_graduate(stats, criteria)

        assert passed is True
        assert len(failures) == 0

    def test_collects_all_failures(self):
        """Should collect all failures when multiple criteria fail."""
        from llm_council.graduation import (
            GraduationCriteria,
            ModelStats,
            should_graduate,
        )

        criteria = GraduationCriteria()
        stats = ModelStats(
            model_id="test/model",
            days_tracked=10,  # Fail: age
            completed_sessions=50,  # Fail: sessions
            error_rate=0.05,  # Fail: error rate
            quality_percentile=0.50,  # Fail: quality
        )

        passed, failures = should_graduate(stats, criteria)

        assert passed is False
        assert len(failures) == 4

    def test_passes_at_exact_thresholds(self):
        """Should pass when values exactly meet thresholds."""
        from llm_council.graduation import (
            GraduationCriteria,
            ModelStats,
            should_graduate,
        )

        criteria = GraduationCriteria()
        stats = ModelStats(
            model_id="test/model",
            days_tracked=30,  # Exactly at threshold
            completed_sessions=100,  # Exactly at threshold
            error_rate=0.02,  # Exactly at threshold
            quality_percentile=0.75,  # Exactly at threshold
        )

        passed, failures = should_graduate(stats, criteria)

        assert passed is True
        assert len(failures) == 0


class TestGraduationCandidates:
    """Test functions for finding graduation candidates."""

    def test_get_graduation_candidates_returns_list(self):
        """get_graduation_candidates() should return list of candidates."""
        from llm_council.graduation import (
            GraduationCriteria,
            get_graduation_candidates,
        )

        # Create mock stats for multiple models
        candidates = get_graduation_candidates(
            tier="frontier",
            criteria=GraduationCriteria(),
        )

        assert isinstance(candidates, list)

    def test_graduation_candidate_includes_stats_and_result(self):
        """Each candidate should include stats and graduation result."""
        from llm_council.graduation import GraduationCandidate

        # GraduationCandidate should have model_id, stats, passed, failures
        candidate = GraduationCandidate(
            model_id="test/model",
            passed=True,
            failures=[],
            days_tracked=45,
            completed_sessions=150,
            error_rate=0.01,
            quality_percentile=0.85,
        )

        assert candidate.model_id == "test/model"
        assert candidate.passed is True
        assert candidate.failures == []
