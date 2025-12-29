"""TDD tests for ADR-027: Frontier Observability.

Tests for the frontier-specific layer events.

This implements Issue #115.
"""

import pytest


class TestFrontierLayerEvents:
    """Test frontier-specific LayerEventType values."""

    def test_frontier_model_selected_exists(self):
        """FRONTIER_MODEL_SELECTED should be a valid event type."""
        from llm_council.layer_contracts import LayerEventType

        assert hasattr(LayerEventType, "FRONTIER_MODEL_SELECTED")
        assert LayerEventType.FRONTIER_MODEL_SELECTED.value == "frontier_model_selected"

    def test_frontier_shadow_vote_exists(self):
        """FRONTIER_SHADOW_VOTE should be a valid event type."""
        from llm_council.layer_contracts import LayerEventType

        assert hasattr(LayerEventType, "FRONTIER_SHADOW_VOTE")
        assert LayerEventType.FRONTIER_SHADOW_VOTE.value == "frontier_shadow_vote"

    def test_frontier_fallback_triggered_exists(self):
        """FRONTIER_FALLBACK_TRIGGERED should be a valid event type."""
        from llm_council.layer_contracts import LayerEventType

        assert hasattr(LayerEventType, "FRONTIER_FALLBACK_TRIGGERED")
        assert LayerEventType.FRONTIER_FALLBACK_TRIGGERED.value == "frontier_fallback_triggered"

    def test_frontier_cost_ceiling_exceeded_exists(self):
        """FRONTIER_COST_CEILING_EXCEEDED should be a valid event type."""
        from llm_council.layer_contracts import LayerEventType

        assert hasattr(LayerEventType, "FRONTIER_COST_CEILING_EXCEEDED")
        assert (
            LayerEventType.FRONTIER_COST_CEILING_EXCEEDED.value == "frontier_cost_ceiling_exceeded"
        )

    def test_frontier_graduation_candidate_exists(self):
        """FRONTIER_GRADUATION_CANDIDATE should be a valid event type."""
        from llm_council.layer_contracts import LayerEventType

        assert hasattr(LayerEventType, "FRONTIER_GRADUATION_CANDIDATE")
        assert LayerEventType.FRONTIER_GRADUATION_CANDIDATE.value == "frontier_graduation_candidate"

    def test_frontier_graduation_promoted_exists(self):
        """FRONTIER_GRADUATION_PROMOTED should be a valid event type."""
        from llm_council.layer_contracts import LayerEventType

        assert hasattr(LayerEventType, "FRONTIER_GRADUATION_PROMOTED")
        assert LayerEventType.FRONTIER_GRADUATION_PROMOTED.value == "frontier_graduation_promoted"


class TestFrontierEventEmission:
    """Test emitting frontier events."""

    def test_emit_frontier_model_selected(self):
        """Should be able to emit FRONTIER_MODEL_SELECTED event."""
        from llm_council.layer_contracts import (
            LayerEventType,
            emit_layer_event,
            get_layer_events,
            clear_layer_events,
        )

        clear_layer_events()

        emit_layer_event(
            LayerEventType.FRONTIER_MODEL_SELECTED,
            {"model_id": "openai/gpt-5.2-pro", "tier": "frontier"},
        )

        events = get_layer_events()
        assert len(events) == 1
        assert events[0].event_type == LayerEventType.FRONTIER_MODEL_SELECTED
        assert events[0].data["model_id"] == "openai/gpt-5.2-pro"

        clear_layer_events()

    def test_emit_frontier_shadow_vote(self):
        """Should be able to emit FRONTIER_SHADOW_VOTE event."""
        from llm_council.layer_contracts import (
            LayerEventType,
            emit_layer_event,
            get_layer_events,
            clear_layer_events,
        )

        clear_layer_events()

        emit_layer_event(
            LayerEventType.FRONTIER_SHADOW_VOTE,
            {
                "model_id": "openai/gpt-5.2-pro",
                "top_pick": "anthropic/claude-opus-4.5",
                "agreed_with_consensus": True,
            },
        )

        events = get_layer_events()
        assert len(events) == 1
        assert events[0].event_type == LayerEventType.FRONTIER_SHADOW_VOTE
        assert events[0].data["agreed_with_consensus"] is True

        clear_layer_events()

    def test_emit_frontier_fallback_triggered(self):
        """Should be able to emit FRONTIER_FALLBACK_TRIGGERED event."""
        from llm_council.layer_contracts import (
            LayerEventType,
            emit_layer_event,
            get_layer_events,
            clear_layer_events,
        )

        clear_layer_events()

        emit_layer_event(
            LayerEventType.FRONTIER_FALLBACK_TRIGGERED,
            {
                "model_id": "openai/gpt-5.2-pro",
                "reason": "timeout",
                "fallback_model": "anthropic/claude-3.5-sonnet",
            },
        )

        events = get_layer_events()
        assert len(events) == 1
        assert events[0].event_type == LayerEventType.FRONTIER_FALLBACK_TRIGGERED
        assert events[0].data["reason"] == "timeout"

        clear_layer_events()

    def test_emit_frontier_cost_ceiling_exceeded(self):
        """Should be able to emit FRONTIER_COST_CEILING_EXCEEDED event."""
        from llm_council.layer_contracts import (
            LayerEventType,
            emit_layer_event,
            get_layer_events,
            clear_layer_events,
        )

        clear_layer_events()

        emit_layer_event(
            LayerEventType.FRONTIER_COST_CEILING_EXCEEDED,
            {
                "model_id": "expensive/model",
                "model_cost": 0.050,
                "ceiling": 0.025,
            },
        )

        events = get_layer_events()
        assert len(events) == 1
        assert events[0].event_type == LayerEventType.FRONTIER_COST_CEILING_EXCEEDED
        assert events[0].data["model_cost"] == 0.050

        clear_layer_events()
