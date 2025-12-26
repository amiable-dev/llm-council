"""TDD Tests for ADR-030 Metrics Adapter.

Tests are written FIRST (RED phase) per TDD methodology.

The MetricsAdapter bridges internal LayerEvents to external metrics backends
(Prometheus, StatsD) for observability dashboards.
"""

import time
from unittest.mock import MagicMock, patch, call
from typing import Dict, Any

import pytest


class TestMetricsConfig:
    """Test MetricsConfig in unified_config.py."""

    def test_metrics_config_exists(self):
        """MetricsConfig should exist in unified_config."""
        from llm_council.unified_config import MetricsConfig

        config = MetricsConfig()
        assert config is not None

    def test_metrics_config_default_disabled(self):
        """Metrics export should be disabled by default."""
        from llm_council.unified_config import MetricsConfig

        config = MetricsConfig()
        assert config.enabled is False

    def test_metrics_config_default_backend(self):
        """Default backend should be 'none'."""
        from llm_council.unified_config import MetricsConfig

        config = MetricsConfig()
        assert config.backend == "none"

    def test_metrics_config_statsd_settings(self):
        """Should have StatsD configuration settings."""
        from llm_council.unified_config import MetricsConfig

        config = MetricsConfig()
        assert hasattr(config, "statsd_host")
        assert hasattr(config, "statsd_port")
        assert hasattr(config, "statsd_prefix")

    def test_metrics_config_default_statsd_host(self):
        """Default StatsD host should be localhost."""
        from llm_council.unified_config import MetricsConfig

        config = MetricsConfig()
        assert config.statsd_host == "localhost"

    def test_metrics_config_default_statsd_port(self):
        """Default StatsD port should be 8125."""
        from llm_council.unified_config import MetricsConfig

        config = MetricsConfig()
        assert config.statsd_port == 8125

    def test_metrics_config_default_statsd_prefix(self):
        """Default StatsD prefix should be 'llm_council'."""
        from llm_council.unified_config import MetricsConfig

        config = MetricsConfig()
        assert config.statsd_prefix == "llm_council"

    def test_metrics_config_prometheus_settings(self):
        """Should have Prometheus configuration settings."""
        from llm_council.unified_config import MetricsConfig

        config = MetricsConfig()
        assert hasattr(config, "prometheus_port")

    def test_metrics_config_default_prometheus_port(self):
        """Default Prometheus port should be 9090."""
        from llm_council.unified_config import MetricsConfig

        config = MetricsConfig()
        assert config.prometheus_port == 9090

    def test_metrics_config_custom_values(self):
        """MetricsConfig should accept custom values."""
        from llm_council.unified_config import MetricsConfig

        config = MetricsConfig(
            enabled=True,
            backend="statsd",
            statsd_host="metrics.example.com",
            statsd_port=8126,
            statsd_prefix="council",
            prometheus_port=9091,
        )
        assert config.enabled is True
        assert config.backend == "statsd"
        assert config.statsd_host == "metrics.example.com"
        assert config.statsd_port == 8126
        assert config.statsd_prefix == "council"
        assert config.prometheus_port == 9091


class TestMetricsConfigInObservability:
    """Test MetricsConfig in ObservabilityConfig."""

    def test_observability_config_has_metrics(self):
        """ObservabilityConfig should have metrics field."""
        from llm_council.unified_config import ObservabilityConfig

        config = ObservabilityConfig()
        assert hasattr(config, "metrics")

    def test_observability_default_metrics(self):
        """ObservabilityConfig should have default MetricsConfig."""
        from llm_council.unified_config import MetricsConfig, ObservabilityConfig

        config = ObservabilityConfig()
        assert isinstance(config.metrics, MetricsConfig)
        assert config.metrics.enabled is False


class TestMetricsBackend:
    """Test MetricsBackend abstract interface."""

    def test_metrics_backend_protocol_exists(self):
        """MetricsBackend protocol should exist."""
        from llm_council.observability.metrics_adapter import MetricsBackend

        assert MetricsBackend is not None

    def test_metrics_backend_has_emit_counter(self):
        """MetricsBackend should have emit_counter method."""
        from llm_council.observability.metrics_adapter import MetricsBackend

        assert hasattr(MetricsBackend, "emit_counter")

    def test_metrics_backend_has_emit_gauge(self):
        """MetricsBackend should have emit_gauge method."""
        from llm_council.observability.metrics_adapter import MetricsBackend

        assert hasattr(MetricsBackend, "emit_gauge")

    def test_metrics_backend_has_emit_histogram(self):
        """MetricsBackend should have emit_histogram method."""
        from llm_council.observability.metrics_adapter import MetricsBackend

        assert hasattr(MetricsBackend, "emit_histogram")


class TestStatsDBackend:
    """Test StatsD metrics backend."""

    def test_statsd_backend_exists(self):
        """StatsDBackend should exist."""
        from llm_council.observability.metrics_adapter import StatsDBackend

        assert StatsDBackend is not None

    def test_statsd_backend_emit_counter(self):
        """StatsDBackend should emit counters."""
        from llm_council.observability.metrics_adapter import StatsDBackend

        with patch("socket.socket") as mock_socket:
            mock_instance = MagicMock()
            mock_socket.return_value = mock_instance

            backend = StatsDBackend(host="localhost", port=8125, prefix="test")
            backend.emit_counter("circuit_breaker_open", 1, {"model_id": "openai/gpt-4o"})

            # Should have sent data to socket
            assert mock_instance.sendto.called

    def test_statsd_backend_formats_metric_name(self):
        """StatsDBackend should format metric names with prefix and tags."""
        from llm_council.observability.metrics_adapter import StatsDBackend

        with patch("socket.socket") as mock_socket:
            mock_instance = MagicMock()
            mock_socket.return_value = mock_instance

            backend = StatsDBackend(host="localhost", port=8125, prefix="llm_council")
            backend.emit_counter("circuit_breaker_open", 1, {"model_id": "openai/gpt-4o"})

            # Check that the metric was formatted correctly
            call_args = mock_instance.sendto.call_args
            data = call_args[0][0].decode("utf-8")
            assert "llm_council" in data
            assert "circuit_breaker_open" in data


class TestPrometheusBackend:
    """Test Prometheus metrics backend."""

    def test_prometheus_backend_exists(self):
        """PrometheusBackend should exist."""
        from llm_council.observability.metrics_adapter import PrometheusBackend

        assert PrometheusBackend is not None

    def test_prometheus_backend_emit_counter(self):
        """PrometheusBackend should emit counters."""
        from llm_council.observability.metrics_adapter import PrometheusBackend

        backend = PrometheusBackend(prefix="test")
        # Should not raise
        backend.emit_counter("circuit_breaker_open", 1, {"model_id": "openai/gpt-4o"})


class TestNoOpBackend:
    """Test NoOp metrics backend (for when metrics are disabled)."""

    def test_noop_backend_exists(self):
        """NoOpBackend should exist."""
        from llm_council.observability.metrics_adapter import NoOpBackend

        assert NoOpBackend is not None

    def test_noop_backend_does_nothing(self):
        """NoOpBackend should accept calls but do nothing."""
        from llm_council.observability.metrics_adapter import NoOpBackend

        backend = NoOpBackend()
        # Should not raise
        backend.emit_counter("test", 1, {})
        backend.emit_gauge("test", 1.0, {})
        backend.emit_histogram("test", 1.0, {})


class TestMetricsAdapter:
    """Test MetricsAdapter that bridges events to metrics."""

    def test_metrics_adapter_exists(self):
        """MetricsAdapter should exist."""
        from llm_council.observability.metrics_adapter import MetricsAdapter

        assert MetricsAdapter is not None

    def test_metrics_adapter_handles_circuit_breaker_open(self):
        """MetricsAdapter should handle L4_CIRCUIT_BREAKER_OPEN events."""
        from llm_council.observability.metrics_adapter import MetricsAdapter, NoOpBackend
        from llm_council.layer_contracts import LayerEvent, LayerEventType

        mock_backend = MagicMock()
        adapter = MetricsAdapter(backend=mock_backend)

        event = LayerEvent(
            event_type=LayerEventType.L4_CIRCUIT_BREAKER_OPEN,
            data={
                "model_id": "openai/gpt-4o",
                "failure_rate": 0.30,
                "cooldown_seconds": 1800,
            },
        )

        adapter.handle_event(event)

        # Should have emitted counter for circuit open
        mock_backend.emit_counter.assert_called()
        call_args = mock_backend.emit_counter.call_args
        assert "circuit_breaker_open" in call_args[0][0]

    def test_metrics_adapter_handles_circuit_breaker_close(self):
        """MetricsAdapter should handle L4_CIRCUIT_BREAKER_CLOSE events."""
        from llm_council.observability.metrics_adapter import MetricsAdapter
        from llm_council.layer_contracts import LayerEvent, LayerEventType

        mock_backend = MagicMock()
        adapter = MetricsAdapter(backend=mock_backend)

        event = LayerEvent(
            event_type=LayerEventType.L4_CIRCUIT_BREAKER_CLOSE,
            data={
                "model_id": "openai/gpt-4o",
                "from_state": "half_open",
            },
        )

        adapter.handle_event(event)

        mock_backend.emit_counter.assert_called()
        call_args = mock_backend.emit_counter.call_args
        assert "circuit_breaker_close" in call_args[0][0]

    def test_metrics_adapter_includes_model_id_tag(self):
        """MetricsAdapter should include model_id as a tag."""
        from llm_council.observability.metrics_adapter import MetricsAdapter
        from llm_council.layer_contracts import LayerEvent, LayerEventType

        mock_backend = MagicMock()
        adapter = MetricsAdapter(backend=mock_backend)

        event = LayerEvent(
            event_type=LayerEventType.L4_CIRCUIT_BREAKER_OPEN,
            data={
                "model_id": "openai/gpt-4o",
                "failure_rate": 0.30,
            },
        )

        adapter.handle_event(event)

        call_args = mock_backend.emit_counter.call_args
        tags = call_args[0][2]  # Third argument is tags
        assert "model_id" in tags
        assert tags["model_id"] == "openai/gpt-4o"

    def test_metrics_adapter_emits_failure_rate_gauge(self):
        """MetricsAdapter should emit failure_rate as a gauge on circuit open."""
        from llm_council.observability.metrics_adapter import MetricsAdapter
        from llm_council.layer_contracts import LayerEvent, LayerEventType

        mock_backend = MagicMock()
        adapter = MetricsAdapter(backend=mock_backend)

        event = LayerEvent(
            event_type=LayerEventType.L4_CIRCUIT_BREAKER_OPEN,
            data={
                "model_id": "openai/gpt-4o",
                "failure_rate": 0.30,
            },
        )

        adapter.handle_event(event)

        # Check gauge was emitted for failure_rate
        mock_backend.emit_gauge.assert_called()
        call_args = mock_backend.emit_gauge.call_args
        assert "failure_rate" in call_args[0][0]
        assert call_args[0][1] == pytest.approx(0.30, abs=0.01)


class TestMetricsAdapterFactory:
    """Test factory function for creating MetricsAdapter."""

    def test_get_metrics_adapter_exists(self):
        """get_metrics_adapter should exist."""
        from llm_council.observability.metrics_adapter import get_metrics_adapter

        assert get_metrics_adapter is not None

    def test_get_metrics_adapter_returns_adapter(self):
        """get_metrics_adapter should return MetricsAdapter instance."""
        from llm_council.observability.metrics_adapter import (
            MetricsAdapter,
            get_metrics_adapter,
        )

        adapter = get_metrics_adapter()
        assert isinstance(adapter, MetricsAdapter)

    def test_get_metrics_adapter_uses_config(self):
        """get_metrics_adapter should use configuration."""
        from llm_council.observability.metrics_adapter import get_metrics_adapter

        # Should not crash even with default config
        adapter = get_metrics_adapter()
        assert adapter is not None


class TestMetricsAdapterIntegration:
    """Integration tests for MetricsAdapter with emit_layer_event."""

    def test_adapter_subscribes_to_events(self):
        """MetricsAdapter should be able to subscribe to layer events."""
        from llm_council.observability.metrics_adapter import (
            MetricsAdapter,
            subscribe_metrics_adapter,
            unsubscribe_metrics_adapter,
        )

        mock_backend = MagicMock()
        adapter = MetricsAdapter(backend=mock_backend)

        # Subscribe
        subscribe_metrics_adapter(adapter)

        # Clean up
        unsubscribe_metrics_adapter(adapter)

    def test_subscribed_adapter_receives_events(self):
        """Subscribed MetricsAdapter should receive emitted events."""
        from llm_council.observability.metrics_adapter import (
            MetricsAdapter,
            subscribe_metrics_adapter,
            unsubscribe_metrics_adapter,
        )
        from llm_council.layer_contracts import (
            LayerEventType,
            emit_layer_event,
            clear_layer_events,
        )

        clear_layer_events()

        mock_backend = MagicMock()
        adapter = MetricsAdapter(backend=mock_backend)

        subscribe_metrics_adapter(adapter)

        try:
            # Emit a circuit breaker event
            emit_layer_event(
                LayerEventType.L4_CIRCUIT_BREAKER_OPEN,
                {
                    "model_id": "openai/gpt-4o",
                    "failure_rate": 0.30,
                    "cooldown_seconds": 1800,
                },
            )

            # Adapter should have received the event
            assert mock_backend.emit_counter.called
        finally:
            unsubscribe_metrics_adapter(adapter)
            clear_layer_events()


class TestEnvVarOverride:
    """Test environment variable override for metrics configuration."""

    def test_env_var_enables_metrics(self):
        """LLM_COUNCIL_METRICS_ENABLED=true should enable metrics."""
        import os
        from llm_council.observability.metrics_adapter import _is_metrics_enabled

        original = os.environ.get("LLM_COUNCIL_METRICS_ENABLED")
        try:
            os.environ["LLM_COUNCIL_METRICS_ENABLED"] = "true"
            assert _is_metrics_enabled() is True
        finally:
            if original is not None:
                os.environ["LLM_COUNCIL_METRICS_ENABLED"] = original
            else:
                os.environ.pop("LLM_COUNCIL_METRICS_ENABLED", None)

    def test_env_var_selects_backend(self):
        """LLM_COUNCIL_METRICS_BACKEND should select backend."""
        import os
        from llm_council.observability.metrics_adapter import _get_metrics_backend_type

        original = os.environ.get("LLM_COUNCIL_METRICS_BACKEND")
        try:
            os.environ["LLM_COUNCIL_METRICS_BACKEND"] = "statsd"
            assert _get_metrics_backend_type() == "statsd"
        finally:
            if original is not None:
                os.environ["LLM_COUNCIL_METRICS_BACKEND"] = original
            else:
                os.environ.pop("LLM_COUNCIL_METRICS_BACKEND", None)


class TestModuleExports:
    """Test module exports."""

    def test_exports_metrics_adapter(self):
        """MetricsAdapter should be exported."""
        from llm_council.observability.metrics_adapter import MetricsAdapter

        assert MetricsAdapter is not None

    def test_exports_get_metrics_adapter(self):
        """get_metrics_adapter should be exported."""
        from llm_council.observability.metrics_adapter import get_metrics_adapter

        assert get_metrics_adapter is not None

    def test_exports_subscribe_metrics_adapter(self):
        """subscribe_metrics_adapter should be exported."""
        from llm_council.observability.metrics_adapter import subscribe_metrics_adapter

        assert subscribe_metrics_adapter is not None

    def test_exports_unsubscribe_metrics_adapter(self):
        """unsubscribe_metrics_adapter should be exported."""
        from llm_council.observability.metrics_adapter import unsubscribe_metrics_adapter

        assert unsubscribe_metrics_adapter is not None
