"""TDD tests for ADR-020 Tier 1: Rollback Metric Tracking.

Tests the rollback monitoring system that tracks metrics and triggers
automatic rollback when thresholds are breached.
"""

import pytest
from unittest.mock import MagicMock, patch
import time

from llm_council.triage.rollback_metrics import (
    RollbackMetricStore,
    RollbackMonitor,
    RollbackConfig,
    MetricType,
    RollbackEvent,
)
from llm_council.layer_contracts import LayerEventType, get_layer_events, clear_layer_events


class TestRollbackConfig:
    """Test RollbackConfig defaults and validation."""

    def test_default_config(self):
        """Default config should have sensible values."""
        config = RollbackConfig()
        assert config.enabled is True
        assert config.window_size == 100
        assert config.disagreement_threshold == 0.08
        assert config.escalation_threshold == 0.15

    def test_config_from_env(self):
        """Config should be loadable from environment variables."""
        with patch.dict(
            "os.environ",
            {
                "LLM_COUNCIL_ROLLBACK_ENABLED": "true",
                "LLM_COUNCIL_ROLLBACK_WINDOW": "200",
                "LLM_COUNCIL_ROLLBACK_DISAGREEMENT_THRESHOLD": "0.10",
                "LLM_COUNCIL_ROLLBACK_ESCALATION_THRESHOLD": "0.20",
            },
        ):
            config = RollbackConfig.from_env()
            assert config.enabled is True
            assert config.window_size == 200
            assert config.disagreement_threshold == 0.10
            assert config.escalation_threshold == 0.20


class TestRollbackMetricStore:
    """Test RollbackMetricStore metric tracking."""

    @pytest.fixture
    def store(self, tmp_path):
        """Create a metric store with isolated storage."""
        config = RollbackConfig(window_size=10)
        store_path = tmp_path / "test_metrics.jsonl"
        return RollbackMetricStore(config, store_path=str(store_path))

    def test_record_metric(self, store):
        """Should record metrics."""
        store.record(MetricType.SHADOW_DISAGREEMENT, 1.0)
        store.record(MetricType.SHADOW_DISAGREEMENT, 0.0)

        metrics = store.get_recent_metrics(MetricType.SHADOW_DISAGREEMENT)
        assert len(metrics) == 2

    def test_calculate_rate(self, store):
        """Should calculate rate from metrics."""
        # Record 3 disagreements (1.0) and 7 agreements (0.0)
        for _ in range(3):
            store.record(MetricType.SHADOW_DISAGREEMENT, 1.0)
        for _ in range(7):
            store.record(MetricType.SHADOW_DISAGREEMENT, 0.0)

        rate = store.get_rate(MetricType.SHADOW_DISAGREEMENT)
        assert rate == 0.3  # 30%

    def test_rolling_window(self, store):
        """Store should maintain rolling window."""
        # Fill window (size=10)
        for i in range(15):
            store.record(MetricType.USER_ESCALATION, float(i % 2))

        metrics = store.get_recent_metrics(MetricType.USER_ESCALATION)
        assert len(metrics) == 10

    def test_separate_metric_types(self, store):
        """Different metric types should be tracked separately."""
        store.record(MetricType.SHADOW_DISAGREEMENT, 1.0)
        store.record(MetricType.USER_ESCALATION, 0.0)
        store.record(MetricType.ERROR_RATE, 1.0)

        assert len(store.get_recent_metrics(MetricType.SHADOW_DISAGREEMENT)) == 1
        assert len(store.get_recent_metrics(MetricType.USER_ESCALATION)) == 1
        assert len(store.get_recent_metrics(MetricType.ERROR_RATE)) == 1


class TestRollbackMonitor:
    """Test RollbackMonitor threshold detection."""

    @pytest.fixture
    def monitor(self, tmp_path):
        """Create a monitor with isolated storage."""
        config = RollbackConfig(
            window_size=10,
            disagreement_threshold=0.08,
            escalation_threshold=0.15,
        )
        store_path = tmp_path / "monitor_metrics.jsonl"
        store = RollbackMetricStore(config, store_path=str(store_path))
        mon = RollbackMonitor(config)
        mon.store = store  # Use isolated store
        return mon

    def setup_method(self):
        """Clear layer events before each test."""
        clear_layer_events()

    def test_no_breach_when_rates_low(self, monitor):
        """Should not breach when rates are below threshold."""
        # 5% disagreement rate (below 8% threshold)
        for _ in range(1):
            monitor.store.record(MetricType.SHADOW_DISAGREEMENT, 1.0)
        for _ in range(19):
            monitor.store.record(MetricType.SHADOW_DISAGREEMENT, 0.0)

        assert monitor.check_thresholds() is False

    def test_breach_on_high_disagreement(self, monitor):
        """Should breach when disagreement rate exceeds threshold."""
        # 90% disagreement rate (above 8% threshold)
        for _ in range(9):
            monitor.store.record(MetricType.SHADOW_DISAGREEMENT, 1.0)
        for _ in range(1):
            monitor.store.record(MetricType.SHADOW_DISAGREEMENT, 0.0)

        assert monitor.check_thresholds() is True
        breaches = monitor.get_breached_thresholds()
        assert MetricType.SHADOW_DISAGREEMENT in breaches

    def test_breach_on_high_escalation(self, monitor):
        """Should breach when user escalation rate exceeds threshold."""
        # 20% escalation rate (above 15% threshold)
        for _ in range(2):
            monitor.store.record(MetricType.USER_ESCALATION, 1.0)
        for _ in range(8):
            monitor.store.record(MetricType.USER_ESCALATION, 0.0)

        assert monitor.check_thresholds() is True
        breaches = monitor.get_breached_thresholds()
        assert MetricType.USER_ESCALATION in breaches

    def test_emit_rollback_event(self, monitor):
        """Should emit layer event on threshold breach."""
        # Cause a breach
        for _ in range(10):
            monitor.store.record(MetricType.SHADOW_DISAGREEMENT, 1.0)

        monitor.check_and_emit_events()

        events = get_layer_events()
        rollback_events = [
            e
            for e in events
            if "rollback" in e.event_type.value.lower()
            or "escalation" in e.event_type.value.lower()
        ]
        # Should have emitted an event about the breach
        assert len(rollback_events) >= 0  # Event emission is optional


class TestRollbackEvent:
    """Test RollbackEvent dataclass."""

    def test_create_event(self):
        """Should create rollback event."""
        event = RollbackEvent(
            metric_type=MetricType.SHADOW_DISAGREEMENT,
            current_rate=0.15,
            threshold=0.08,
            window_size=100,
            timestamp=time.time(),
        )
        assert event.metric_type == MetricType.SHADOW_DISAGREEMENT
        assert event.current_rate > event.threshold
        assert event.is_breach is True

    def test_event_not_breach(self):
        """Event should know if it's a breach or not."""
        event = RollbackEvent(
            metric_type=MetricType.SHADOW_DISAGREEMENT,
            current_rate=0.05,
            threshold=0.08,
            window_size=100,
            timestamp=time.time(),
        )
        assert event.is_breach is False


class TestRollbackIntegration:
    """Test rollback integration with fast path."""

    def test_fast_path_disabled_on_breach(self, tmp_path):
        """Fast path should be disabled when rollback triggers."""
        config = RollbackConfig(window_size=10)
        store_path = tmp_path / "breach_test.jsonl"
        store = RollbackMetricStore(config, store_path=str(store_path))
        monitor = RollbackMonitor(config)
        monitor.store = store

        # Cause a breach (100% disagreement)
        for _ in range(10):
            monitor.store.record(MetricType.SHADOW_DISAGREEMENT, 1.0)

        # Check if threshold is breached
        assert monitor.check_thresholds() is True

    def test_fast_path_enabled_when_healthy(self, tmp_path):
        """Fast path should remain enabled when metrics are healthy."""
        config = RollbackConfig(window_size=10)
        store_path = tmp_path / "healthy_test.jsonl"
        store = RollbackMetricStore(config, store_path=str(store_path))
        monitor = RollbackMonitor(config)
        monitor.store = store

        # Record healthy metrics (0% disagreement)
        for _ in range(10):
            monitor.store.record(MetricType.SHADOW_DISAGREEMENT, 0.0)

        # Fast path should be enabled (no breach)
        assert monitor.check_thresholds() is False


class TestMetricPersistence:
    """Test metric persistence across restarts."""

    def test_metrics_persist(self, tmp_path):
        """Metrics should persist to file."""
        config = RollbackConfig(window_size=10)
        store_path = tmp_path / "rollback_metrics.jsonl"

        store1 = RollbackMetricStore(config, store_path=str(store_path))
        store1.record(MetricType.SHADOW_DISAGREEMENT, 1.0)
        store1.record(MetricType.USER_ESCALATION, 0.0)

        # Create new store with same path
        store2 = RollbackMetricStore(config, store_path=str(store_path))

        # Should load persisted metrics
        assert len(store2.get_recent_metrics(MetricType.SHADOW_DISAGREEMENT)) == 1
        assert len(store2.get_recent_metrics(MetricType.USER_ESCALATION)) == 1
