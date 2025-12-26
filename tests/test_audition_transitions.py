"""TDD Tests for ADR-029 Phase 2: State Transition Logic.

Tests are written FIRST (RED phase) per TDD methodology.
Issue: https://github.com/amiable-dev/llm-council/issues/129
"""

from datetime import datetime, timedelta

import pytest


class TestShadowToProbation:
    """Test SHADOW → PROBATION transition."""

    def test_shadow_to_probation_requires_sessions_and_days(self):
        """Transition requires both min sessions and min days."""
        from llm_council.audition.types import (
            AuditionCriteria,
            AuditionState,
            AuditionStatus,
            evaluate_state_transition,
        )

        now = datetime.utcnow()
        status = AuditionStatus(
            model_id="openai/gpt-5-mini",
            state=AuditionState.SHADOW,
            session_count=10,  # Meets min sessions
            first_seen=now - timedelta(days=4),  # Meets min days
            last_seen=now,
        )
        criteria = AuditionCriteria()

        result = evaluate_state_transition(status, criteria)
        assert result == AuditionState.PROBATION

    def test_shadow_to_probation_blocked_without_min_sessions(self):
        """No transition if session count not met."""
        from llm_council.audition.types import (
            AuditionCriteria,
            AuditionState,
            AuditionStatus,
            evaluate_state_transition,
        )

        now = datetime.utcnow()
        status = AuditionStatus(
            model_id="openai/gpt-5-mini",
            state=AuditionState.SHADOW,
            session_count=5,  # Below min sessions (10)
            first_seen=now - timedelta(days=4),
            last_seen=now,
        )
        criteria = AuditionCriteria()

        result = evaluate_state_transition(status, criteria)
        assert result is None

    def test_shadow_to_probation_blocked_without_min_days(self):
        """No transition if min days not met."""
        from llm_council.audition.types import (
            AuditionCriteria,
            AuditionState,
            AuditionStatus,
            evaluate_state_transition,
        )

        now = datetime.utcnow()
        status = AuditionStatus(
            model_id="openai/gpt-5-mini",
            state=AuditionState.SHADOW,
            session_count=15,  # Meets min sessions
            first_seen=now - timedelta(days=1),  # Below min days (3)
            last_seen=now,
        )
        criteria = AuditionCriteria()

        result = evaluate_state_transition(status, criteria)
        assert result is None


class TestProbationToEvaluation:
    """Test PROBATION → EVALUATION transition."""

    def test_probation_to_evaluation_requires_sessions_and_days(self):
        """Transition requires both min sessions and min days."""
        from llm_council.audition.types import (
            AuditionCriteria,
            AuditionState,
            AuditionStatus,
            evaluate_state_transition,
        )

        now = datetime.utcnow()
        status = AuditionStatus(
            model_id="openai/gpt-5-mini",
            state=AuditionState.PROBATION,
            session_count=25,  # Meets min sessions
            first_seen=now - timedelta(days=10),  # Meets min days
            last_seen=now,
        )
        criteria = AuditionCriteria()

        result = evaluate_state_transition(status, criteria)
        assert result == AuditionState.EVALUATION

    def test_probation_to_evaluation_blocked_without_min_sessions(self):
        """No transition if session count not met."""
        from llm_council.audition.types import (
            AuditionCriteria,
            AuditionState,
            AuditionStatus,
            evaluate_state_transition,
        )

        now = datetime.utcnow()
        status = AuditionStatus(
            model_id="openai/gpt-5-mini",
            state=AuditionState.PROBATION,
            session_count=20,  # Below min sessions (25)
            first_seen=now - timedelta(days=10),
            last_seen=now,
        )
        criteria = AuditionCriteria()

        result = evaluate_state_transition(status, criteria)
        assert result is None

    def test_probation_to_evaluation_blocked_without_min_days(self):
        """No transition if min days not met."""
        from llm_council.audition.types import (
            AuditionCriteria,
            AuditionState,
            AuditionStatus,
            evaluate_state_transition,
        )

        now = datetime.utcnow()
        status = AuditionStatus(
            model_id="openai/gpt-5-mini",
            state=AuditionState.PROBATION,
            session_count=30,  # Meets min sessions
            first_seen=now - timedelta(days=5),  # Below min days (7)
            last_seen=now,
        )
        criteria = AuditionCriteria()

        result = evaluate_state_transition(status, criteria)
        assert result is None


class TestEvaluationToFull:
    """Test EVALUATION → FULL transition."""

    def test_evaluation_to_full_requires_quality_percentile(self):
        """Transition requires quality >= 75th percentile."""
        from llm_council.audition.types import (
            AuditionCriteria,
            AuditionState,
            AuditionStatus,
            evaluate_state_transition,
        )

        now = datetime.utcnow()
        status = AuditionStatus(
            model_id="openai/gpt-5-mini",
            state=AuditionState.EVALUATION,
            session_count=50,  # Meets min sessions
            first_seen=now - timedelta(days=30),
            last_seen=now,
            quality_percentile=0.80,  # Above threshold (0.75)
        )
        criteria = AuditionCriteria()

        result = evaluate_state_transition(status, criteria)
        assert result == AuditionState.FULL

    def test_evaluation_to_full_blocked_without_min_sessions(self):
        """No transition if session count not met."""
        from llm_council.audition.types import (
            AuditionCriteria,
            AuditionState,
            AuditionStatus,
            evaluate_state_transition,
        )

        now = datetime.utcnow()
        status = AuditionStatus(
            model_id="openai/gpt-5-mini",
            state=AuditionState.EVALUATION,
            session_count=40,  # Below min sessions (50)
            first_seen=now - timedelta(days=30),
            last_seen=now,
            quality_percentile=0.80,
        )
        criteria = AuditionCriteria()

        result = evaluate_state_transition(status, criteria)
        assert result is None

    def test_evaluation_to_full_blocked_without_quality(self):
        """No transition if quality percentile below threshold."""
        from llm_council.audition.types import (
            AuditionCriteria,
            AuditionState,
            AuditionStatus,
            evaluate_state_transition,
        )

        now = datetime.utcnow()
        status = AuditionStatus(
            model_id="openai/gpt-5-mini",
            state=AuditionState.EVALUATION,
            session_count=60,
            first_seen=now - timedelta(days=30),
            last_seen=now,
            quality_percentile=0.70,  # Below threshold (0.75)
        )
        criteria = AuditionCriteria()

        result = evaluate_state_transition(status, criteria)
        assert result is None

    def test_evaluation_to_full_blocked_without_quality_data(self):
        """No transition if quality percentile is None."""
        from llm_council.audition.types import (
            AuditionCriteria,
            AuditionState,
            AuditionStatus,
            evaluate_state_transition,
        )

        now = datetime.utcnow()
        status = AuditionStatus(
            model_id="openai/gpt-5-mini",
            state=AuditionState.EVALUATION,
            session_count=60,
            first_seen=now - timedelta(days=30),
            last_seen=now,
            quality_percentile=None,  # No quality data
        )
        criteria = AuditionCriteria()

        result = evaluate_state_transition(status, criteria)
        assert result is None


class TestQuarantineTransitions:
    """Test QUARANTINE state transitions."""

    def test_failures_trigger_quarantine_from_shadow(self):
        """Exceeding failure threshold in SHADOW triggers QUARANTINE."""
        from llm_council.audition.types import (
            AuditionCriteria,
            AuditionState,
            AuditionStatus,
            evaluate_state_transition,
        )

        now = datetime.utcnow()
        status = AuditionStatus(
            model_id="openai/gpt-5-mini",
            state=AuditionState.SHADOW,
            session_count=5,
            first_seen=now - timedelta(days=2),
            last_seen=now,
            consecutive_failures=4,  # Exceeds threshold (3)
        )
        criteria = AuditionCriteria()

        result = evaluate_state_transition(status, criteria)
        assert result == AuditionState.QUARANTINE

    def test_failures_trigger_quarantine_from_probation(self):
        """Exceeding failure threshold in PROBATION triggers QUARANTINE."""
        from llm_council.audition.types import (
            AuditionCriteria,
            AuditionState,
            AuditionStatus,
            evaluate_state_transition,
        )

        now = datetime.utcnow()
        status = AuditionStatus(
            model_id="openai/gpt-5-mini",
            state=AuditionState.PROBATION,
            session_count=20,
            first_seen=now - timedelta(days=5),
            last_seen=now,
            consecutive_failures=6,  # Exceeds threshold (5)
        )
        criteria = AuditionCriteria()

        result = evaluate_state_transition(status, criteria)
        assert result == AuditionState.QUARANTINE

    def test_quarantine_expires_to_shadow(self):
        """Expired quarantine transitions back to SHADOW."""
        from llm_council.audition.types import (
            AuditionCriteria,
            AuditionState,
            AuditionStatus,
            evaluate_state_transition,
        )

        now = datetime.utcnow()
        status = AuditionStatus(
            model_id="openai/gpt-5-mini",
            state=AuditionState.QUARANTINE,
            session_count=5,
            first_seen=now - timedelta(days=10),
            last_seen=now,
            quarantine_until=now - timedelta(hours=1),  # Expired
        )
        criteria = AuditionCriteria()

        result = evaluate_state_transition(status, criteria)
        assert result == AuditionState.SHADOW

    def test_quarantine_not_expired_stays(self):
        """Unexpired quarantine returns None (no transition)."""
        from llm_council.audition.types import (
            AuditionCriteria,
            AuditionState,
            AuditionStatus,
            evaluate_state_transition,
        )

        now = datetime.utcnow()
        status = AuditionStatus(
            model_id="openai/gpt-5-mini",
            state=AuditionState.QUARANTINE,
            session_count=5,
            first_seen=now - timedelta(days=10),
            last_seen=now,
            quarantine_until=now + timedelta(hours=12),  # Not expired
        )
        criteria = AuditionCriteria()

        result = evaluate_state_transition(status, criteria)
        assert result is None


class TestRecordSessionResult:
    """Test record_session_result function."""

    def test_record_success_increments_session_count(self):
        """Recording success increments session count."""
        from llm_council.audition.types import (
            AuditionState,
            AuditionStatus,
            record_session_result,
        )

        now = datetime.utcnow()
        status = AuditionStatus(
            model_id="openai/gpt-5-mini",
            state=AuditionState.SHADOW,
            session_count=5,
            first_seen=now - timedelta(days=2),
            last_seen=now - timedelta(hours=1),
        )

        result = record_session_result(status, success=True)
        assert result.session_count == 6

    def test_record_success_resets_consecutive_failures(self):
        """Recording success resets consecutive_failures to 0."""
        from llm_council.audition.types import (
            AuditionState,
            AuditionStatus,
            record_session_result,
        )

        now = datetime.utcnow()
        status = AuditionStatus(
            model_id="openai/gpt-5-mini",
            state=AuditionState.SHADOW,
            session_count=5,
            first_seen=now - timedelta(days=2),
            last_seen=now - timedelta(hours=1),
            consecutive_failures=2,
        )

        result = record_session_result(status, success=True)
        assert result.consecutive_failures == 0

    def test_record_failure_increments_consecutive(self):
        """Recording failure increments consecutive_failures."""
        from llm_council.audition.types import (
            AuditionState,
            AuditionStatus,
            record_session_result,
        )

        now = datetime.utcnow()
        status = AuditionStatus(
            model_id="openai/gpt-5-mini",
            state=AuditionState.SHADOW,
            session_count=5,
            first_seen=now - timedelta(days=2),
            last_seen=now - timedelta(hours=1),
            consecutive_failures=1,
        )

        result = record_session_result(status, success=False)
        assert result.consecutive_failures == 2

    def test_record_failure_still_increments_session_count(self):
        """Recording failure still increments session count."""
        from llm_council.audition.types import (
            AuditionState,
            AuditionStatus,
            record_session_result,
        )

        now = datetime.utcnow()
        status = AuditionStatus(
            model_id="openai/gpt-5-mini",
            state=AuditionState.SHADOW,
            session_count=5,
            first_seen=now - timedelta(days=2),
            last_seen=now - timedelta(hours=1),
        )

        result = record_session_result(status, success=False)
        assert result.session_count == 6

    def test_record_session_updates_last_seen(self):
        """Recording session updates last_seen timestamp."""
        from llm_council.audition.types import (
            AuditionState,
            AuditionStatus,
            record_session_result,
        )

        old_last_seen = datetime.utcnow() - timedelta(hours=1)
        status = AuditionStatus(
            model_id="openai/gpt-5-mini",
            state=AuditionState.SHADOW,
            session_count=5,
            first_seen=old_last_seen - timedelta(days=2),
            last_seen=old_last_seen,
        )

        result = record_session_result(status, success=True)
        assert result.last_seen > old_last_seen

    def test_record_session_sets_first_seen_if_none(self):
        """Recording session sets first_seen if None."""
        from llm_council.audition.types import (
            AuditionState,
            AuditionStatus,
            record_session_result,
        )

        status = AuditionStatus(
            model_id="openai/gpt-5-mini",
            state=AuditionState.SHADOW,
            session_count=0,
            first_seen=None,
            last_seen=None,
        )

        result = record_session_result(status, success=True)
        assert result.first_seen is not None


class TestFullStateNoTransition:
    """Test that FULL state has no forward transition."""

    def test_full_state_returns_none(self):
        """FULL state models have no forward transition."""
        from llm_council.audition.types import (
            AuditionCriteria,
            AuditionState,
            AuditionStatus,
            evaluate_state_transition,
        )

        now = datetime.utcnow()
        status = AuditionStatus(
            model_id="openai/gpt-5-mini",
            state=AuditionState.FULL,
            session_count=100,
            first_seen=now - timedelta(days=60),
            last_seen=now,
            quality_percentile=0.90,
        )
        criteria = AuditionCriteria()

        result = evaluate_state_transition(status, criteria)
        assert result is None


class TestModuleExports:
    """Test that transition functions are exported."""

    def test_evaluate_state_transition_exported(self):
        """evaluate_state_transition is exported from types module."""
        from llm_council.audition.types import evaluate_state_transition

        assert callable(evaluate_state_transition)

    def test_record_session_result_exported(self):
        """record_session_result is exported from types module."""
        from llm_council.audition.types import record_session_result

        assert callable(record_session_result)
