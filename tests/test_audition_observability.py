"""TDD Tests for ADR-029 Phase 8: Observability Events.

Tests are written FIRST (RED phase) per TDD methodology.
Issue: https://github.com/amiable-dev/llm-council/issues/135

Audition layer events for monitoring state transitions and selections.
"""

import pytest


class TestAuditionEventTypes:
    """Test audition event types in LayerEventType."""

    def test_audition_state_transition_event_exists(self):
        """AUDITION_STATE_TRANSITION event type exists."""
        from llm_council.layer_contracts import LayerEventType

        assert hasattr(LayerEventType, "AUDITION_STATE_TRANSITION")
        assert LayerEventType.AUDITION_STATE_TRANSITION.value == "audition_state_transition"

    def test_audition_model_selected_event_exists(self):
        """AUDITION_MODEL_SELECTED event type exists."""
        from llm_council.layer_contracts import LayerEventType

        assert hasattr(LayerEventType, "AUDITION_MODEL_SELECTED")
        assert LayerEventType.AUDITION_MODEL_SELECTED.value == "audition_model_selected"

    def test_audition_failure_recorded_event_exists(self):
        """AUDITION_FAILURE_RECORDED event type exists."""
        from llm_council.layer_contracts import LayerEventType

        assert hasattr(LayerEventType, "AUDITION_FAILURE_RECORDED")
        assert LayerEventType.AUDITION_FAILURE_RECORDED.value == "audition_failure_recorded"

    def test_audition_quarantine_triggered_event_exists(self):
        """AUDITION_QUARANTINE_TRIGGERED event type exists."""
        from llm_council.layer_contracts import LayerEventType

        assert hasattr(LayerEventType, "AUDITION_QUARANTINE_TRIGGERED")
        assert LayerEventType.AUDITION_QUARANTINE_TRIGGERED.value == "audition_quarantine_triggered"

    def test_audition_graduation_complete_event_exists(self):
        """AUDITION_GRADUATION_COMPLETE event type exists."""
        from llm_council.layer_contracts import LayerEventType

        assert hasattr(LayerEventType, "AUDITION_GRADUATION_COMPLETE")
        assert LayerEventType.AUDITION_GRADUATION_COMPLETE.value == "audition_graduation_complete"


class TestAuditionEventEmission:
    """Test audition event emission from tracker."""

    def test_record_session_emits_state_transition_on_promotion(self):
        """Recording a session that causes promotion emits transition event."""
        from datetime import datetime, timedelta

        from llm_council.audition.tracker import AuditionTracker, _reset_tracker
        from llm_council.audition.types import (
            AuditionCriteria,
            AuditionState,
            AuditionStatus,
        )
        from llm_council.layer_contracts import LayerEventType, clear_layer_events, get_layer_events

        _reset_tracker()
        clear_layer_events()

        tracker = AuditionTracker()
        # Pre-populate with a model ready to graduate from SHADOW
        status = AuditionStatus(
            model_id="test/model",
            state=AuditionState.SHADOW,
            session_count=9,  # One more will trigger promotion
            first_seen=datetime.now() - timedelta(days=5),  # Meets min_days
            last_seen=datetime.now(),
        )
        tracker._cache["test/model"] = status

        # Record session which should trigger promotion
        criteria = AuditionCriteria(shadow_min_sessions=10, shadow_min_days=3)
        new_status = tracker.record_session("test/model", success=True, criteria=criteria)

        # Check event was emitted
        events = get_layer_events()
        transition_events = [
            e for e in events if e.event_type == LayerEventType.AUDITION_STATE_TRANSITION
        ]
        assert len(transition_events) >= 1
        event = transition_events[-1]
        assert event.data["model_id"] == "test/model"
        assert event.data["from_state"] == "shadow"
        assert event.data["to_state"] == "probation"

    def test_record_session_emits_failure_recorded_event(self):
        """Recording a failed session emits failure recorded event."""
        from llm_council.audition.tracker import AuditionTracker, _reset_tracker
        from llm_council.layer_contracts import LayerEventType, clear_layer_events, get_layer_events

        _reset_tracker()
        clear_layer_events()

        tracker = AuditionTracker()
        tracker.record_session("test/model", success=False)

        events = get_layer_events()
        failure_events = [
            e for e in events if e.event_type == LayerEventType.AUDITION_FAILURE_RECORDED
        ]
        assert len(failure_events) >= 1
        event = failure_events[-1]
        assert event.data["model_id"] == "test/model"
        assert event.data["consecutive_failures"] >= 1

    def test_quarantine_emits_quarantine_triggered_event(self):
        """Triggering quarantine emits quarantine event."""
        from datetime import datetime, timedelta

        from llm_council.audition.tracker import AuditionTracker, _reset_tracker
        from llm_council.audition.types import (
            AuditionCriteria,
            AuditionState,
            AuditionStatus,
        )
        from llm_council.layer_contracts import LayerEventType, clear_layer_events, get_layer_events

        _reset_tracker()
        clear_layer_events()

        tracker = AuditionTracker()
        # Pre-populate with a model at 3 consecutive failures (one more exceeds max_failures=3)
        # The check is consecutive_failures > max_failures, so 4 > 3 triggers quarantine
        status = AuditionStatus(
            model_id="test/model",
            state=AuditionState.SHADOW,
            session_count=5,
            first_seen=datetime.now() - timedelta(days=1),
            last_seen=datetime.now(),
            consecutive_failures=3,  # After failure: 4 > 3 triggers quarantine
        )
        tracker._cache["test/model"] = status

        # Record failure to trigger quarantine (4 > 3)
        criteria = AuditionCriteria(shadow_max_failures=3)
        tracker.record_session("test/model", success=False, criteria=criteria)

        events = get_layer_events()
        quarantine_events = [
            e for e in events if e.event_type == LayerEventType.AUDITION_QUARANTINE_TRIGGERED
        ]
        assert len(quarantine_events) >= 1
        event = quarantine_events[-1]
        assert event.data["model_id"] == "test/model"
        assert "cooldown_hours" in event.data

    def test_graduation_emits_graduation_complete_event(self):
        """Graduating to FULL emits graduation complete event."""
        from datetime import datetime, timedelta

        from llm_council.audition.tracker import AuditionTracker, _reset_tracker
        from llm_council.audition.types import (
            AuditionCriteria,
            AuditionState,
            AuditionStatus,
        )
        from llm_council.layer_contracts import LayerEventType, clear_layer_events, get_layer_events

        _reset_tracker()
        clear_layer_events()

        tracker = AuditionTracker()
        # Pre-populate with a model ready to graduate to FULL
        status = AuditionStatus(
            model_id="test/model",
            state=AuditionState.EVALUATION,
            session_count=49,  # One more hits 50
            first_seen=datetime.now() - timedelta(days=30),
            last_seen=datetime.now(),
            quality_percentile=0.80,  # Above 0.75 threshold
        )
        tracker._cache["test/model"] = status

        # Record session which should trigger graduation
        criteria = AuditionCriteria(eval_min_sessions=50, eval_min_quality_percentile=0.75)
        tracker.record_session("test/model", success=True, criteria=criteria)

        events = get_layer_events()
        graduation_events = [
            e for e in events if e.event_type == LayerEventType.AUDITION_GRADUATION_COMPLETE
        ]
        assert len(graduation_events) >= 1
        event = graduation_events[-1]
        assert event.data["model_id"] == "test/model"
        assert event.data["quality_percentile"] == 0.80


class TestAuditionSelectionEventEmission:
    """Test audition event emission from selection."""

    def test_select_with_audition_emits_model_selected_event(self):
        """Selecting an auditioning model emits selection event."""
        from llm_council.audition.selection import select_with_audition
        from llm_council.audition.tracker import AuditionTracker, _reset_tracker
        from llm_council.audition.types import AuditionState, AuditionStatus
        from llm_council.layer_contracts import LayerEventType, clear_layer_events, get_layer_events

        _reset_tracker()
        clear_layer_events()

        tracker = AuditionTracker()
        # Add a FULL model (not auditioning - no event expected)
        tracker._cache["full/model"] = AuditionStatus(
            model_id="full/model",
            state=AuditionState.FULL,
        )
        # Add a SHADOW model (auditioning - event expected)
        tracker._cache["shadow/model"] = AuditionStatus(
            model_id="shadow/model",
            state=AuditionState.SHADOW,
        )

        # Run selection
        scored_candidates = [
            ("full/model", 0.9),
            ("shadow/model", 0.8),
        ]
        result = select_with_audition(scored_candidates, tracker, count=2)

        # Check event was emitted for auditioning model (shadow/model)
        events = get_layer_events()
        selection_events = [
            e for e in events if e.event_type == LayerEventType.AUDITION_MODEL_SELECTED
        ]
        assert len(selection_events) >= 1
        event = selection_events[-1]
        assert event.data["model_id"] == "shadow/model"
        assert event.data["state"] == "shadow"
        assert event.data["selected"] is True


class TestModuleExports:
    """Test module exports."""

    def test_audition_event_types_exported(self):
        """Audition event types are exported from layer_contracts."""
        from llm_council.layer_contracts import LayerEventType

        # All audition event types should be accessible
        assert LayerEventType.AUDITION_STATE_TRANSITION is not None
        assert LayerEventType.AUDITION_MODEL_SELECTED is not None
        assert LayerEventType.AUDITION_FAILURE_RECORDED is not None
        assert LayerEventType.AUDITION_QUARANTINE_TRIGGERED is not None
        assert LayerEventType.AUDITION_GRADUATION_COMPLETE is not None
