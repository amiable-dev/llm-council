"""TDD Tests for ADR-029 Phase 1: Core Audition Types.

Tests are written FIRST (RED phase) per TDD methodology.
Issue: https://github.com/amiable-dev/llm-council/issues/128
"""

from datetime import datetime, timedelta

import pytest


class TestAuditionStateEnum:
    """Test AuditionState enum values."""

    def test_audition_state_has_shadow(self):
        """SHADOW state exists for new models."""
        from llm_council.audition.types import AuditionState

        assert AuditionState.SHADOW.value == "shadow"

    def test_audition_state_has_probation(self):
        """PROBATION state exists for models past initial evaluation."""
        from llm_council.audition.types import AuditionState

        assert AuditionState.PROBATION.value == "probation"

    def test_audition_state_has_evaluation(self):
        """EVALUATION state exists for models being assessed."""
        from llm_council.audition.types import AuditionState

        assert AuditionState.EVALUATION.value == "evaluation"

    def test_audition_state_has_full(self):
        """FULL state exists for graduated models."""
        from llm_council.audition.types import AuditionState

        assert AuditionState.FULL.value == "full"

    def test_audition_state_has_quarantine(self):
        """QUARANTINE state exists for failing models."""
        from llm_council.audition.types import AuditionState

        assert AuditionState.QUARANTINE.value == "quarantine"

    def test_audition_state_enum_has_five_states(self):
        """AuditionState has exactly 5 states."""
        from llm_council.audition.types import AuditionState

        assert len(AuditionState) == 5


class TestAuditionStatus:
    """Test AuditionStatus dataclass."""

    def test_audition_status_has_model_id(self):
        """AuditionStatus requires model_id."""
        from llm_council.audition.types import AuditionState, AuditionStatus

        status = AuditionStatus(
            model_id="openai/gpt-5-mini",
            state=AuditionState.SHADOW,
        )
        assert status.model_id == "openai/gpt-5-mini"

    def test_audition_status_has_state(self):
        """AuditionStatus requires state."""
        from llm_council.audition.types import AuditionState, AuditionStatus

        status = AuditionStatus(
            model_id="openai/gpt-5-mini",
            state=AuditionState.PROBATION,
        )
        assert status.state == AuditionState.PROBATION

    def test_audition_status_session_count_defaults_zero(self):
        """session_count defaults to 0."""
        from llm_council.audition.types import AuditionState, AuditionStatus

        status = AuditionStatus(
            model_id="openai/gpt-5-mini",
            state=AuditionState.SHADOW,
        )
        assert status.session_count == 0

    def test_audition_status_first_seen_defaults_none(self):
        """first_seen defaults to None."""
        from llm_council.audition.types import AuditionState, AuditionStatus

        status = AuditionStatus(
            model_id="openai/gpt-5-mini",
            state=AuditionState.SHADOW,
        )
        assert status.first_seen is None

    def test_audition_status_last_seen_defaults_none(self):
        """last_seen defaults to None."""
        from llm_council.audition.types import AuditionState, AuditionStatus

        status = AuditionStatus(
            model_id="openai/gpt-5-mini",
            state=AuditionState.SHADOW,
        )
        assert status.last_seen is None

    def test_audition_status_consecutive_failures_defaults_zero(self):
        """consecutive_failures defaults to 0."""
        from llm_council.audition.types import AuditionState, AuditionStatus

        status = AuditionStatus(
            model_id="openai/gpt-5-mini",
            state=AuditionState.SHADOW,
        )
        assert status.consecutive_failures == 0

    def test_audition_status_quality_percentile_defaults_none(self):
        """quality_percentile defaults to None."""
        from llm_council.audition.types import AuditionState, AuditionStatus

        status = AuditionStatus(
            model_id="openai/gpt-5-mini",
            state=AuditionState.SHADOW,
        )
        assert status.quality_percentile is None

    def test_audition_status_quarantine_until_defaults_none(self):
        """quarantine_until defaults to None."""
        from llm_council.audition.types import AuditionState, AuditionStatus

        status = AuditionStatus(
            model_id="openai/gpt-5-mini",
            state=AuditionState.SHADOW,
        )
        assert status.quarantine_until is None

    def test_audition_status_days_tracked_calculation(self):
        """days_tracked property calculates correctly."""
        from llm_council.audition.types import AuditionState, AuditionStatus

        now = datetime.utcnow()
        five_days_ago = now - timedelta(days=5)
        status = AuditionStatus(
            model_id="openai/gpt-5-mini",
            state=AuditionState.SHADOW,
            first_seen=five_days_ago,
            last_seen=now,
        )
        # days_tracked should be approximately 5
        assert status.days_tracked >= 5
        assert status.days_tracked <= 6  # Allow for slight timing variance

    def test_audition_status_days_tracked_none_when_no_first_seen(self):
        """days_tracked is None when first_seen not set."""
        from llm_council.audition.types import AuditionState, AuditionStatus

        status = AuditionStatus(
            model_id="openai/gpt-5-mini",
            state=AuditionState.SHADOW,
        )
        assert status.days_tracked is None


class TestAuditionCriteria:
    """Test AuditionCriteria frozen dataclass."""

    def test_audition_criteria_shadow_min_sessions_default(self):
        """shadow_min_sessions defaults to 10."""
        from llm_council.audition.types import AuditionCriteria

        criteria = AuditionCriteria()
        assert criteria.shadow_min_sessions == 10

    def test_audition_criteria_shadow_min_days_default(self):
        """shadow_min_days defaults to 3."""
        from llm_council.audition.types import AuditionCriteria

        criteria = AuditionCriteria()
        assert criteria.shadow_min_days == 3

    def test_audition_criteria_shadow_max_failures_default(self):
        """shadow_max_failures defaults to 3."""
        from llm_council.audition.types import AuditionCriteria

        criteria = AuditionCriteria()
        assert criteria.shadow_max_failures == 3

    def test_audition_criteria_probation_min_sessions_default(self):
        """probation_min_sessions defaults to 25."""
        from llm_council.audition.types import AuditionCriteria

        criteria = AuditionCriteria()
        assert criteria.probation_min_sessions == 25

    def test_audition_criteria_probation_min_days_default(self):
        """probation_min_days defaults to 7."""
        from llm_council.audition.types import AuditionCriteria

        criteria = AuditionCriteria()
        assert criteria.probation_min_days == 7

    def test_audition_criteria_probation_max_failures_default(self):
        """probation_max_failures defaults to 5."""
        from llm_council.audition.types import AuditionCriteria

        criteria = AuditionCriteria()
        assert criteria.probation_max_failures == 5

    def test_audition_criteria_eval_min_sessions_default(self):
        """eval_min_sessions defaults to 50."""
        from llm_council.audition.types import AuditionCriteria

        criteria = AuditionCriteria()
        assert criteria.eval_min_sessions == 50

    def test_audition_criteria_eval_min_quality_percentile_default(self):
        """eval_min_quality_percentile defaults to 0.75."""
        from llm_council.audition.types import AuditionCriteria

        criteria = AuditionCriteria()
        assert criteria.eval_min_quality_percentile == 0.75

    def test_audition_criteria_quarantine_cooldown_hours_default(self):
        """quarantine_cooldown_hours defaults to 24."""
        from llm_council.audition.types import AuditionCriteria

        criteria = AuditionCriteria()
        assert criteria.quarantine_cooldown_hours == 24

    def test_audition_criteria_is_frozen(self):
        """AuditionCriteria is immutable (frozen dataclass)."""
        from llm_council.audition.types import AuditionCriteria

        criteria = AuditionCriteria()
        with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
            criteria.shadow_min_sessions = 20

    def test_audition_criteria_custom_values(self):
        """AuditionCriteria accepts custom values."""
        from llm_council.audition.types import AuditionCriteria

        criteria = AuditionCriteria(
            shadow_min_sessions=5,
            shadow_min_days=2,
            eval_min_quality_percentile=0.80,
        )
        assert criteria.shadow_min_sessions == 5
        assert criteria.shadow_min_days == 2
        assert criteria.eval_min_quality_percentile == 0.80


class TestModuleExports:
    """Test that module exports are correct."""

    def test_audition_module_exports_audition_state(self):
        """AuditionState is exported from audition module."""
        from llm_council.audition import AuditionState

        assert AuditionState is not None

    def test_audition_module_exports_audition_status(self):
        """AuditionStatus is exported from audition module."""
        from llm_council.audition import AuditionStatus

        assert AuditionStatus is not None

    def test_audition_module_exports_audition_criteria(self):
        """AuditionCriteria is exported from audition module."""
        from llm_council.audition import AuditionCriteria

        assert AuditionCriteria is not None
