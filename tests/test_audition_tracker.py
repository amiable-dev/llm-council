"""TDD Tests for ADR-029 Phase 3: AuditionTracker Persistence Layer.

Tests are written FIRST (RED phase) per TDD methodology.
Issue: https://github.com/amiable-dev/llm-council/issues/130
"""

import tempfile
from datetime import datetime, timedelta, timezone

UTC = timezone.utc
from pathlib import Path

import pytest
from llm_council import model_constants as mc


class TestAuditionTrackerSingleton:
    """Test singleton pattern for AuditionTracker."""

    def test_tracker_singleton_returns_same_instance(self):
        """get_audition_tracker returns same instance."""
        from llm_council.audition.tracker import (
            _reset_tracker,
            get_audition_tracker,
        )

        _reset_tracker()  # Reset for clean test
        tracker1 = get_audition_tracker()
        tracker2 = get_audition_tracker()
        assert tracker1 is tracker2
        _reset_tracker()


class TestAuditionTrackerGetStatus:
    """Test AuditionTracker.get_status()."""

    def test_get_status_returns_none_for_unknown(self):
        """Unknown model returns None."""
        from llm_council.audition.tracker import AuditionTracker

        tracker = AuditionTracker()
        result = tracker.get_status("generic/local")
        assert result is None


class TestAuditionTrackerRecordSession:
    """Test AuditionTracker.record_session()."""

    def test_record_session_creates_new_status(self):
        """Recording session for new model creates status."""
        from llm_council.audition.tracker import AuditionTracker
        from llm_council.audition.types import AuditionState

        tracker = AuditionTracker()
        status = tracker.record_session(mc.OPENAI_BALANCED, success=True)

        assert status.model_id == mc.OPENAI_BALANCED
        assert status.state == AuditionState.SHADOW  # New models start in SHADOW
        assert status.session_count == 1

    def test_record_session_increments_count(self):
        """Recording subsequent sessions increments count."""
        from llm_council.audition.tracker import AuditionTracker

        tracker = AuditionTracker()
        tracker.record_session(mc.OPENAI_BALANCED, success=True)
        status = tracker.record_session(mc.OPENAI_BALANCED, success=True)

        assert status.session_count == 2

    def test_record_failure_increments_consecutive(self):
        """Recording failure increments consecutive_failures."""
        from llm_council.audition.tracker import AuditionTracker

        tracker = AuditionTracker()
        tracker.record_session(mc.OPENAI_BALANCED, success=True)
        status = tracker.record_session(mc.OPENAI_BALANCED, success=False)

        assert status.consecutive_failures == 1

    def test_record_success_resets_consecutive_failures(self):
        """Recording success resets consecutive_failures."""
        from llm_council.audition.tracker import AuditionTracker

        tracker = AuditionTracker()
        tracker.record_session(mc.OPENAI_BALANCED, success=False)
        tracker.record_session(mc.OPENAI_BALANCED, success=False)
        status = tracker.record_session(mc.OPENAI_BALANCED, success=True)

        assert status.consecutive_failures == 0

    def test_record_session_updates_cache(self):
        """Recording session updates internal cache."""
        from llm_council.audition.tracker import AuditionTracker

        tracker = AuditionTracker()
        tracker.record_session(mc.OPENAI_BALANCED, success=True)

        cached = tracker.get_status(mc.OPENAI_BALANCED)
        assert cached is not None
        assert cached.session_count == 1


class TestAuditionTrackerQualityPercentile:
    """Test AuditionTracker.update_quality_percentile()."""

    def test_update_quality_percentile(self):
        """Updating quality percentile is reflected in status."""
        from llm_council.audition.tracker import AuditionTracker

        tracker = AuditionTracker()
        tracker.record_session(mc.OPENAI_BALANCED, success=True)
        tracker.update_quality_percentile(mc.OPENAI_BALANCED, 0.82)

        status = tracker.get_status(mc.OPENAI_BALANCED)
        assert status is not None
        assert status.quality_percentile == 0.82

    def test_update_quality_percentile_unknown_model_ignored(self):
        """Updating unknown model does not raise."""
        from llm_council.audition.tracker import AuditionTracker

        tracker = AuditionTracker()
        # Should not raise
        tracker.update_quality_percentile("generic/local", 0.80)


class TestAuditionTrackerCheckTransitions:
    """Test AuditionTracker.check_transitions()."""

    def test_check_transitions_returns_graduated_models(self):
        """check_transitions returns list of state changes."""
        from llm_council.audition.tracker import AuditionTracker
        from llm_council.audition.types import AuditionCriteria, AuditionState

        tracker = AuditionTracker()

        # Create model ready to graduate from SHADOW to PROBATION
        for _ in range(12):
            tracker.record_session(mc.OPENAI_BALANCED, success=True)

        # Manually adjust first_seen to meet min_days requirement
        status = tracker.get_status(mc.OPENAI_BALANCED)
        status.first_seen = datetime.now(UTC) - timedelta(days=5)
        tracker._cache[mc.OPENAI_BALANCED] = status

        criteria = AuditionCriteria()
        transitions = tracker.check_transitions(criteria)

        assert len(transitions) == 1
        model_id, from_state, to_state = transitions[0]
        assert model_id == mc.OPENAI_BALANCED
        assert from_state == AuditionState.SHADOW
        assert to_state == AuditionState.PROBATION

    def test_check_transitions_applies_state_changes(self):
        """check_transitions applies state changes to cached models."""
        from llm_council.audition.tracker import AuditionTracker
        from llm_council.audition.types import AuditionCriteria, AuditionState

        tracker = AuditionTracker()

        # Create model ready to graduate
        for _ in range(12):
            tracker.record_session(mc.OPENAI_BALANCED, success=True)

        status = tracker.get_status(mc.OPENAI_BALANCED)
        status.first_seen = datetime.now(UTC) - timedelta(days=5)
        tracker._cache[mc.OPENAI_BALANCED] = status

        criteria = AuditionCriteria()
        tracker.check_transitions(criteria)

        # Verify state was updated
        updated = tracker.get_status(mc.OPENAI_BALANCED)
        assert updated.state == AuditionState.PROBATION


class TestAuditionTrackerGetAllStatuses:
    """Test AuditionTracker.get_all_statuses()."""

    def test_get_all_statuses_returns_all_tracked(self):
        """get_all_statuses returns list of all tracked models."""
        from llm_council.audition.tracker import AuditionTracker

        tracker = AuditionTracker()
        tracker.record_session(mc.OPENAI_HIGH, success=True)
        tracker.record_session(mc.ANTHROPIC_HIGH, success=True)
        tracker.record_session(mc.GOOGLE_HIGH, success=True)

        all_statuses = tracker.get_all_statuses()
        model_ids = {s.model_id for s in all_statuses}

        assert len(all_statuses) == 3
        assert mc.OPENAI_HIGH in model_ids
        assert mc.ANTHROPIC_HIGH in model_ids
        assert mc.GOOGLE_HIGH in model_ids


class TestAuditionTrackerPersistence:
    """Test JSONL persistence."""

    def test_persistence_round_trip(self):
        """Status survives persistence to/from JSONL."""
        from llm_council.audition.tracker import AuditionTracker
        from llm_council.audition.types import AuditionState

        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "audition.jsonl"

            # Create tracker with persistence
            tracker1 = AuditionTracker(store_path=str(store_path))
            tracker1.record_session(mc.OPENAI_BALANCED, success=True)
            tracker1.record_session(mc.OPENAI_BALANCED, success=True)
            tracker1.record_session(mc.OPENAI_BALANCED, success=False)

            # Create new tracker from same file
            tracker2 = AuditionTracker(store_path=str(store_path))

            status = tracker2.get_status(mc.OPENAI_BALANCED)
            assert status is not None
            assert status.model_id == mc.OPENAI_BALANCED
            assert status.state == AuditionState.SHADOW
            assert status.session_count == 3
            assert status.consecutive_failures == 1

    def test_persistence_creates_file(self):
        """Recording session creates store file."""
        from llm_council.audition.tracker import AuditionTracker

        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "audition.jsonl"
            assert not store_path.exists()

            tracker = AuditionTracker(store_path=str(store_path))
            tracker.record_session(mc.OPENAI_BALANCED, success=True)

            assert store_path.exists()


class TestModuleExports:
    """Test module exports."""

    def test_audition_tracker_exported(self):
        """AuditionTracker is exported from module."""
        from llm_council.audition import AuditionTracker

        assert AuditionTracker is not None

    def test_get_audition_tracker_exported(self):
        """get_audition_tracker is exported from module."""
        from llm_council.audition import get_audition_tracker

        assert callable(get_audition_tracker)
