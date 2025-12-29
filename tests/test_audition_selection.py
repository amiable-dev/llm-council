"""TDD Tests for ADR-029 Phase 5: Selection Integration.

Tests are written FIRST (RED phase) per TDD methodology.
Issue: https://github.com/amiable-dev/llm-council/issues/132
"""

import pytest


class TestGetSelectionWeight:
    """Test get_selection_weight function."""

    def test_selection_weight_shadow_is_0_3(self):
        """SHADOW state has 30% weight."""
        from llm_council.audition.selection import get_selection_weight
        from llm_council.audition.types import AuditionState, AuditionStatus

        status = AuditionStatus(
            model_id="openai/gpt-5",
            state=AuditionState.SHADOW,
        )
        weight = get_selection_weight(status)
        assert weight == 0.3

    def test_selection_weight_probation_is_0_3(self):
        """PROBATION state has 30% weight."""
        from llm_council.audition.selection import get_selection_weight
        from llm_council.audition.types import AuditionState, AuditionStatus

        status = AuditionStatus(
            model_id="openai/gpt-5",
            state=AuditionState.PROBATION,
        )
        weight = get_selection_weight(status)
        assert weight == 0.3

    def test_selection_weight_evaluation_scales(self):
        """EVALUATION state weight scales from 0.3 to 1.0 based on sessions."""
        from llm_council.audition.selection import get_selection_weight
        from llm_council.audition.types import AuditionState, AuditionStatus

        # Early evaluation (25 sessions, just entered) - should be ~0.3
        early_status = AuditionStatus(
            model_id="openai/gpt-5",
            state=AuditionState.EVALUATION,
            session_count=25,
        )
        early_weight = get_selection_weight(early_status)
        assert 0.3 <= early_weight < 0.5

        # Late evaluation (49 sessions, about to graduate) - should be close to 1.0
        late_status = AuditionStatus(
            model_id="openai/gpt-5",
            state=AuditionState.EVALUATION,
            session_count=49,
        )
        late_weight = get_selection_weight(late_status)
        assert late_weight > 0.8

    def test_selection_weight_full_is_1_0(self):
        """FULL state has 100% weight."""
        from llm_council.audition.selection import get_selection_weight
        from llm_council.audition.types import AuditionState, AuditionStatus

        status = AuditionStatus(
            model_id="openai/gpt-5",
            state=AuditionState.FULL,
        )
        weight = get_selection_weight(status)
        assert weight == 1.0

    def test_selection_weight_quarantine_is_0(self):
        """QUARANTINE state has 0% weight."""
        from llm_council.audition.selection import get_selection_weight
        from llm_council.audition.types import AuditionState, AuditionStatus

        status = AuditionStatus(
            model_id="openai/gpt-5",
            state=AuditionState.QUARANTINE,
        )
        weight = get_selection_weight(status)
        assert weight == 0.0

    def test_selection_weight_none_status_is_0_3(self):
        """None status (unknown model) has 30% weight (assumed SHADOW)."""
        from llm_council.audition.selection import get_selection_weight

        weight = get_selection_weight(None)
        assert weight == 0.3


class TestSelectWithAudition:
    """Test select_with_audition function."""

    def test_select_with_audition_applies_weights(self):
        """Selection applies audition weights to scores."""
        from llm_council.audition.selection import select_with_audition
        from llm_council.audition.tracker import AuditionTracker
        from llm_council.audition.types import AuditionState, AuditionStatus

        tracker = AuditionTracker()

        # Add a FULL model and a SHADOW model with same base score
        tracker._cache["model-full"] = AuditionStatus(
            model_id="model-full",
            state=AuditionState.FULL,
        )
        tracker._cache["model-shadow"] = AuditionStatus(
            model_id="model-shadow",
            state=AuditionState.SHADOW,
        )

        # Both have same base score (0.8), but FULL should win due to weight
        scored = [("model-full", 0.8), ("model-shadow", 0.8)]

        selected = select_with_audition(scored, tracker, count=1)
        assert selected == ["model-full"]

    def test_select_with_audition_limits_seats(self):
        """Selection limits audition model seats."""
        from llm_council.audition.selection import select_with_audition
        from llm_council.audition.tracker import AuditionTracker
        from llm_council.audition.types import AuditionState, AuditionStatus

        tracker = AuditionTracker()

        # Add multiple SHADOW models with high scores
        for i in range(4):
            tracker._cache[f"shadow-{i}"] = AuditionStatus(
                model_id=f"shadow-{i}",
                state=AuditionState.SHADOW,
            )

        # All SHADOW models with varying scores
        scored = [(f"shadow-{i}", 0.9 - i * 0.1) for i in range(4)]

        # Request 4 models, but max_audition_seats=1
        selected = select_with_audition(scored, tracker, count=4, max_audition_seats=1)

        # Should only include 1 audition model
        audition_count = sum(
            1
            for m in selected
            if tracker.get_status(m) and tracker.get_status(m).state != AuditionState.FULL
        )
        assert audition_count <= 1

    def test_select_with_audition_allows_full_models(self):
        """Selection allows unlimited FULL models."""
        from llm_council.audition.selection import select_with_audition
        from llm_council.audition.tracker import AuditionTracker
        from llm_council.audition.types import AuditionState, AuditionStatus

        tracker = AuditionTracker()

        # Add multiple FULL models
        for i in range(4):
            tracker._cache[f"full-{i}"] = AuditionStatus(
                model_id=f"full-{i}",
                state=AuditionState.FULL,
            )

        scored = [(f"full-{i}", 0.9 - i * 0.1) for i in range(4)]

        # Request 4 models
        selected = select_with_audition(scored, tracker, count=4, max_audition_seats=1)

        # Should include all 4 FULL models
        assert len(selected) == 4

    def test_select_with_audition_excludes_quarantine(self):
        """Selection excludes QUARANTINE models."""
        from llm_council.audition.selection import select_with_audition
        from llm_council.audition.tracker import AuditionTracker
        from llm_council.audition.types import AuditionState, AuditionStatus

        tracker = AuditionTracker()

        tracker._cache["quarantined"] = AuditionStatus(
            model_id="quarantined",
            state=AuditionState.QUARANTINE,
        )
        tracker._cache["available"] = AuditionStatus(
            model_id="available",
            state=AuditionState.FULL,
        )

        # Quarantined has higher base score
        scored = [("quarantined", 0.95), ("available", 0.5)]

        selected = select_with_audition(scored, tracker, count=1)
        assert "quarantined" not in selected
        assert "available" in selected


class TestIsAuditioningModel:
    """Test is_auditioning_model helper."""

    def test_is_auditioning_shadow(self):
        """SHADOW is an audition state."""
        from llm_council.audition.selection import is_auditioning_model
        from llm_council.audition.types import AuditionState, AuditionStatus

        status = AuditionStatus(
            model_id="model",
            state=AuditionState.SHADOW,
        )
        assert is_auditioning_model(status) is True

    def test_is_auditioning_probation(self):
        """PROBATION is an audition state."""
        from llm_council.audition.selection import is_auditioning_model
        from llm_council.audition.types import AuditionState, AuditionStatus

        status = AuditionStatus(
            model_id="model",
            state=AuditionState.PROBATION,
        )
        assert is_auditioning_model(status) is True

    def test_is_auditioning_evaluation(self):
        """EVALUATION is an audition state."""
        from llm_council.audition.selection import is_auditioning_model
        from llm_council.audition.types import AuditionState, AuditionStatus

        status = AuditionStatus(
            model_id="model",
            state=AuditionState.EVALUATION,
        )
        assert is_auditioning_model(status) is True

    def test_is_not_auditioning_full(self):
        """FULL is NOT an audition state."""
        from llm_council.audition.selection import is_auditioning_model
        from llm_council.audition.types import AuditionState, AuditionStatus

        status = AuditionStatus(
            model_id="model",
            state=AuditionState.FULL,
        )
        assert is_auditioning_model(status) is False


class TestModuleExports:
    """Test module exports."""

    def test_get_selection_weight_exported(self):
        """get_selection_weight is exported from module."""
        from llm_council.audition import get_selection_weight

        assert callable(get_selection_weight)

    def test_select_with_audition_exported(self):
        """select_with_audition is exported from module."""
        from llm_council.audition import select_with_audition

        assert callable(select_with_audition)
