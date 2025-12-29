"""TDD tests for ADR-028 Phase 7: Observability (Issue #126).

Tests for discovery metrics, events, and health check functionality.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from llm_council.layer_contracts import (
    LayerEventType,
    emit_layer_event,
    get_layer_events,
    clear_layer_events,
)


class TestDiscoveryEventTypes:
    """Test discovery-specific event types in layer_contracts."""

    def test_discovery_refresh_started_event_type_exists(self):
        """LayerEventType should have DISCOVERY_REFRESH_STARTED."""
        assert hasattr(LayerEventType, "DISCOVERY_REFRESH_STARTED")
        assert LayerEventType.DISCOVERY_REFRESH_STARTED.value == "discovery_refresh_started"

    def test_discovery_refresh_complete_event_type_exists(self):
        """LayerEventType should have DISCOVERY_REFRESH_COMPLETE."""
        assert hasattr(LayerEventType, "DISCOVERY_REFRESH_COMPLETE")
        assert LayerEventType.DISCOVERY_REFRESH_COMPLETE.value == "discovery_refresh_complete"

    def test_discovery_refresh_failed_event_type_exists(self):
        """LayerEventType should have DISCOVERY_REFRESH_FAILED."""
        assert hasattr(LayerEventType, "DISCOVERY_REFRESH_FAILED")
        assert LayerEventType.DISCOVERY_REFRESH_FAILED.value == "discovery_refresh_failed"

    def test_discovery_fallback_triggered_event_type_exists(self):
        """LayerEventType should have DISCOVERY_FALLBACK_TRIGGERED."""
        assert hasattr(LayerEventType, "DISCOVERY_FALLBACK_TRIGGERED")
        assert LayerEventType.DISCOVERY_FALLBACK_TRIGGERED.value == "discovery_fallback_triggered"

    def test_discovery_stale_serve_event_type_exists(self):
        """LayerEventType should have DISCOVERY_STALE_SERVE."""
        assert hasattr(LayerEventType, "DISCOVERY_STALE_SERVE")
        assert LayerEventType.DISCOVERY_STALE_SERVE.value == "discovery_stale_serve"


class TestDiscoveryEventEmission:
    """Test that discovery operations emit appropriate events."""

    def setup_method(self):
        """Clear events before each test."""
        clear_layer_events()

    def teardown_method(self):
        """Clear events after each test."""
        clear_layer_events()

    def test_emit_discovery_refresh_started(self):
        """Should be able to emit DISCOVERY_REFRESH_STARTED event."""
        event = emit_layer_event(
            LayerEventType.DISCOVERY_REFRESH_STARTED,
            {"provider": "openrouter"},
        )

        assert event.event_type == LayerEventType.DISCOVERY_REFRESH_STARTED
        assert event.data["provider"] == "openrouter"

        events = get_layer_events()
        assert len(events) == 1
        assert events[0].event_type == LayerEventType.DISCOVERY_REFRESH_STARTED

    def test_emit_discovery_refresh_complete(self):
        """Should be able to emit DISCOVERY_REFRESH_COMPLETE event."""
        event = emit_layer_event(
            LayerEventType.DISCOVERY_REFRESH_COMPLETE,
            {
                "provider": "openrouter",
                "model_count": 50,
                "duration_ms": 1234,
            },
        )

        assert event.event_type == LayerEventType.DISCOVERY_REFRESH_COMPLETE
        assert event.data["model_count"] == 50
        assert event.data["duration_ms"] == 1234

    def test_emit_discovery_refresh_failed(self):
        """Should be able to emit DISCOVERY_REFRESH_FAILED event."""
        event = emit_layer_event(
            LayerEventType.DISCOVERY_REFRESH_FAILED,
            {
                "provider": "openrouter",
                "error": "Connection timeout",
                "attempt": 3,
            },
        )

        assert event.event_type == LayerEventType.DISCOVERY_REFRESH_FAILED
        assert event.data["error"] == "Connection timeout"
        assert event.data["attempt"] == 3

    def test_emit_discovery_fallback_triggered(self):
        """Should be able to emit DISCOVERY_FALLBACK_TRIGGERED event."""
        event = emit_layer_event(
            LayerEventType.DISCOVERY_FALLBACK_TRIGGERED,
            {
                "tier": "high",
                "reason": "insufficient_candidates",
                "dynamic_count": 1,
                "static_count": 5,
            },
        )

        assert event.event_type == LayerEventType.DISCOVERY_FALLBACK_TRIGGERED
        assert event.data["tier"] == "high"
        assert event.data["reason"] == "insufficient_candidates"


class TestRegistryMetrics:
    """Test metrics tracking in ModelRegistry."""

    def setup_method(self):
        """Reset registry before each test."""
        from llm_council.metadata.registry import _reset_registry

        _reset_registry()
        clear_layer_events()

    def teardown_method(self):
        """Reset after each test."""
        from llm_council.metadata.registry import _reset_registry

        _reset_registry()
        clear_layer_events()

    @pytest.mark.asyncio
    async def test_refresh_emits_started_event(self):
        """refresh_registry should emit DISCOVERY_REFRESH_STARTED."""
        from llm_council.metadata.registry import get_registry
        from llm_council.metadata.types import ModelInfo, QualityTier

        registry = get_registry()

        mock_provider = MagicMock()
        mock_provider.list_available_models = MagicMock(return_value=["openai/gpt-4o"])
        mock_provider.get_model_info = MagicMock(
            return_value=ModelInfo(
                id="openai/gpt-4o",
                context_window=128000,
                quality_tier=QualityTier.FRONTIER,
            )
        )

        await registry.refresh_registry(mock_provider)

        events = get_layer_events()
        started_events = [
            e for e in events if e.event_type == LayerEventType.DISCOVERY_REFRESH_STARTED
        ]
        assert len(started_events) >= 1

    @pytest.mark.asyncio
    async def test_refresh_emits_complete_event_with_duration(self):
        """refresh_registry should emit DISCOVERY_REFRESH_COMPLETE with duration."""
        from llm_council.metadata.registry import get_registry
        from llm_council.metadata.types import ModelInfo, QualityTier

        registry = get_registry()

        mock_provider = MagicMock()
        mock_provider.list_available_models = MagicMock(return_value=["openai/gpt-4o"])
        mock_provider.get_model_info = MagicMock(
            return_value=ModelInfo(
                id="openai/gpt-4o",
                context_window=128000,
                quality_tier=QualityTier.FRONTIER,
            )
        )

        await registry.refresh_registry(mock_provider)

        events = get_layer_events()
        complete_events = [
            e for e in events if e.event_type == LayerEventType.DISCOVERY_REFRESH_COMPLETE
        ]
        assert len(complete_events) == 1
        assert "duration_ms" in complete_events[0].data
        assert "model_count" in complete_events[0].data
        assert complete_events[0].data["model_count"] == 1

    @pytest.mark.asyncio
    async def test_refresh_emits_failed_event_on_error(self):
        """refresh_registry should emit DISCOVERY_REFRESH_FAILED on error."""
        from llm_council.metadata.registry import get_registry

        registry = get_registry()

        mock_provider = MagicMock()
        mock_provider.list_available_models = MagicMock(side_effect=Exception("API error"))

        await registry.refresh_registry(mock_provider, max_retries=1)

        events = get_layer_events()
        failed_events = [
            e for e in events if e.event_type == LayerEventType.DISCOVERY_REFRESH_FAILED
        ]
        assert len(failed_events) >= 1
        assert "error" in failed_events[0].data

    @pytest.mark.asyncio
    async def test_refresh_emits_stale_serve_event_after_failure(self):
        """refresh_registry should emit DISCOVERY_STALE_SERVE when serving stale data."""
        from llm_council.metadata.registry import get_registry
        from llm_council.metadata.types import ModelInfo, QualityTier

        registry = get_registry()

        # First successful refresh
        mock_provider = MagicMock()
        mock_provider.list_available_models = MagicMock(return_value=["openai/gpt-4o"])
        mock_provider.get_model_info = MagicMock(
            return_value=ModelInfo(
                id="openai/gpt-4o",
                context_window=128000,
                quality_tier=QualityTier.FRONTIER,
            )
        )
        await registry.refresh_registry(mock_provider)

        clear_layer_events()

        # Second refresh fails
        mock_provider.list_available_models = MagicMock(side_effect=Exception("API error"))
        await registry.refresh_registry(mock_provider, max_retries=1)

        events = get_layer_events()
        stale_events = [e for e in events if e.event_type == LayerEventType.DISCOVERY_STALE_SERVE]
        assert len(stale_events) >= 1
        assert stale_events[0].data["model_count"] == 1


class TestHealthCheckMetrics:
    """Test health check includes all required metrics."""

    def setup_method(self):
        """Reset registry before each test."""
        from llm_council.metadata.registry import _reset_registry

        _reset_registry()

    def teardown_method(self):
        """Reset after each test."""
        from llm_council.metadata.registry import _reset_registry

        _reset_registry()

    def test_health_status_includes_registry_size(self):
        """get_health_status should include registry_size."""
        from llm_council.metadata.registry import get_registry

        registry = get_registry()
        status = registry.get_health_status()

        assert "registry_size" in status
        assert isinstance(status["registry_size"], int)

    def test_health_status_includes_last_refresh(self):
        """get_health_status should include last_refresh."""
        from llm_council.metadata.registry import get_registry

        registry = get_registry()
        status = registry.get_health_status()

        assert "last_refresh" in status

    def test_health_status_includes_is_stale(self):
        """get_health_status should include is_stale."""
        from llm_council.metadata.registry import get_registry

        registry = get_registry()
        status = registry.get_health_status()

        assert "is_stale" in status
        assert isinstance(status["is_stale"], bool)

    def test_health_status_includes_refresh_failures(self):
        """get_health_status should include refresh_failures."""
        from llm_council.metadata.registry import get_registry

        registry = get_registry()
        status = registry.get_health_status()

        assert "refresh_failures" in status
        assert isinstance(status["refresh_failures"], int)

    def test_health_status_includes_stale_threshold(self):
        """get_health_status should include stale_threshold_minutes."""
        from llm_council.metadata.registry import get_registry

        registry = get_registry()
        status = registry.get_health_status()

        assert "stale_threshold_minutes" in status
        assert isinstance(status["stale_threshold_minutes"], int)


class TestDiscoveryFallbackEvents:
    """Test fallback events in discovery module."""

    def setup_method(self):
        """Clear events before each test."""
        clear_layer_events()

    def teardown_method(self):
        """Clear events after each test."""
        clear_layer_events()

    def test_emit_fallback_helper_exists(self):
        """emit_discovery_fallback should be exported from discovery module."""
        from llm_council.metadata.discovery import emit_discovery_fallback

        assert callable(emit_discovery_fallback)

    def test_emit_fallback_creates_event(self):
        """emit_discovery_fallback should create DISCOVERY_FALLBACK_TRIGGERED event."""
        from llm_council.metadata.discovery import emit_discovery_fallback

        emit_discovery_fallback(
            tier="high",
            reason="insufficient_candidates",
            dynamic_count=1,
            static_count=5,
        )

        events = get_layer_events()
        assert len(events) == 1
        assert events[0].event_type == LayerEventType.DISCOVERY_FALLBACK_TRIGGERED
        assert events[0].data["tier"] == "high"
        assert events[0].data["reason"] == "insufficient_candidates"
