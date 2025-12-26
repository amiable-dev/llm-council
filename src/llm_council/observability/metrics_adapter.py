"""Metrics Adapter for ADR-030 Observability.

This module bridges internal LayerEvents to external metrics backends
(StatsD, Prometheus) for observability dashboards.

Usage:
    >>> from llm_council.observability.metrics_adapter import (
    ...     get_metrics_adapter,
    ...     subscribe_metrics_adapter,
    ... )
    >>>
    >>> # Get configured adapter
    >>> adapter = get_metrics_adapter()
    >>>
    >>> # Subscribe to receive events
    >>> subscribe_metrics_adapter(adapter)
"""

import logging
import os
import socket
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# =============================================================================
# Metrics Backend Protocol
# =============================================================================


@runtime_checkable
class MetricsBackend(Protocol):
    """Protocol for metrics backends (StatsD, Prometheus, etc.)."""

    def emit_counter(self, name: str, value: int, tags: Dict[str, str]) -> None:
        """Emit a counter metric.

        Args:
            name: Metric name
            value: Counter increment value
            tags: Metric tags/labels
        """
        ...

    def emit_gauge(self, name: str, value: float, tags: Dict[str, str]) -> None:
        """Emit a gauge metric.

        Args:
            name: Metric name
            value: Gauge value
            tags: Metric tags/labels
        """
        ...

    def emit_histogram(self, name: str, value: float, tags: Dict[str, str]) -> None:
        """Emit a histogram metric.

        Args:
            name: Metric name
            value: Observation value
            tags: Metric tags/labels
        """
        ...


# =============================================================================
# NoOp Backend (for when metrics are disabled)
# =============================================================================


class NoOpBackend:
    """No-operation backend for when metrics are disabled."""

    def emit_counter(self, name: str, value: int, tags: Dict[str, str]) -> None:
        """Do nothing."""
        pass

    def emit_gauge(self, name: str, value: float, tags: Dict[str, str]) -> None:
        """Do nothing."""
        pass

    def emit_histogram(self, name: str, value: float, tags: Dict[str, str]) -> None:
        """Do nothing."""
        pass


# =============================================================================
# StatsD Backend
# =============================================================================


class StatsDBackend:
    """StatsD metrics backend.

    Sends metrics to a StatsD server over UDP.

    Example:
        backend = StatsDBackend(host="localhost", port=8125, prefix="llm_council")
        backend.emit_counter("circuit_breaker_open", 1, {"model_id": "openai/gpt-4o"})
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8125,
        prefix: str = "llm_council",
    ):
        """Initialize StatsD backend.

        Args:
            host: StatsD server host
            port: StatsD server port
            prefix: Metric name prefix
        """
        self.host = host
        self.port = port
        self.prefix = prefix
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def _format_tags(self, tags: Dict[str, str]) -> str:
        """Format tags for DogStatsD format.

        Args:
            tags: Dict of tag key-value pairs

        Returns:
            Formatted tag string like "|#key1:value1,key2:value2"
        """
        if not tags:
            return ""
        tag_pairs = [f"{k}:{v}" for k, v in tags.items()]
        return "|#" + ",".join(tag_pairs)

    def _send(self, data: str) -> None:
        """Send data to StatsD server.

        Args:
            data: StatsD formatted metric string
        """
        try:
            self._socket.sendto(
                data.encode("utf-8"),
                (self.host, self.port),
            )
        except Exception as e:
            logger.warning("Failed to send metric to StatsD: %s", e)

    def emit_counter(self, name: str, value: int, tags: Dict[str, str]) -> None:
        """Emit a counter metric.

        Args:
            name: Metric name
            value: Counter increment value
            tags: Metric tags
        """
        metric_name = f"{self.prefix}.{name}"
        tag_str = self._format_tags(tags)
        data = f"{metric_name}:{value}|c{tag_str}"
        self._send(data)

    def emit_gauge(self, name: str, value: float, tags: Dict[str, str]) -> None:
        """Emit a gauge metric.

        Args:
            name: Metric name
            value: Gauge value
            tags: Metric tags
        """
        metric_name = f"{self.prefix}.{name}"
        tag_str = self._format_tags(tags)
        data = f"{metric_name}:{value}|g{tag_str}"
        self._send(data)

    def emit_histogram(self, name: str, value: float, tags: Dict[str, str]) -> None:
        """Emit a histogram metric.

        Args:
            name: Metric name
            value: Observation value
            tags: Metric tags
        """
        metric_name = f"{self.prefix}.{name}"
        tag_str = self._format_tags(tags)
        data = f"{metric_name}:{value}|h{tag_str}"
        self._send(data)


# =============================================================================
# Prometheus Backend
# =============================================================================


class PrometheusBackend:
    """Prometheus metrics backend.

    Exposes metrics via an HTTP endpoint for Prometheus scraping.
    Uses in-memory storage for simplicity.

    Note: For production use, consider using the official prometheus_client library.
    This is a minimal implementation for basic metrics export.
    """

    def __init__(self, prefix: str = "llm_council", port: int = 9090):
        """Initialize Prometheus backend.

        Args:
            prefix: Metric name prefix
            port: HTTP server port for Prometheus scraping
        """
        self.prefix = prefix
        self.port = port
        self._counters: Dict[str, int] = {}
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = {}

    def _make_key(self, name: str, tags: Dict[str, str]) -> str:
        """Create a unique key for metric storage.

        Args:
            name: Metric name
            tags: Metric tags

        Returns:
            Unique key string
        """
        tag_str = ",".join(f'{k}="{v}"' for k, v in sorted(tags.items()))
        full_name = f"{self.prefix}_{name}".replace(".", "_")
        return f"{full_name}{{{tag_str}}}" if tags else full_name

    def emit_counter(self, name: str, value: int, tags: Dict[str, str]) -> None:
        """Emit a counter metric.

        Args:
            name: Metric name
            value: Counter increment value
            tags: Metric tags
        """
        key = self._make_key(name, tags)
        self._counters[key] = self._counters.get(key, 0) + value

    def emit_gauge(self, name: str, value: float, tags: Dict[str, str]) -> None:
        """Emit a gauge metric.

        Args:
            name: Metric name
            value: Gauge value
            tags: Metric tags
        """
        key = self._make_key(name, tags)
        self._gauges[key] = value

    def emit_histogram(self, name: str, value: float, tags: Dict[str, str]) -> None:
        """Emit a histogram metric.

        Args:
            name: Metric name
            value: Observation value
            tags: Metric tags
        """
        key = self._make_key(name, tags)
        if key not in self._histograms:
            self._histograms[key] = []
        self._histograms[key].append(value)

    def get_metrics(self) -> str:
        """Get all metrics in Prometheus text format.

        Returns:
            Prometheus-formatted metrics string
        """
        lines = []

        for key, value in self._counters.items():
            lines.append(f"{key} {value}")

        for key, value in self._gauges.items():
            lines.append(f"{key} {value}")

        for key, values in self._histograms.items():
            if values:
                count = len(values)
                total = sum(values)
                lines.append(f"{key}_count {count}")
                lines.append(f"{key}_sum {total}")

        return "\n".join(lines)


# =============================================================================
# Metrics Adapter
# =============================================================================


class MetricsAdapter:
    """Adapter that bridges LayerEvents to metrics backends.

    Subscribes to the internal event bus and translates events
    to appropriate metrics.

    Example:
        from llm_council.observability.metrics_adapter import MetricsAdapter, StatsDBackend

        backend = StatsDBackend(host="localhost", port=8125)
        adapter = MetricsAdapter(backend=backend)

        # Handle events manually or subscribe to event bus
        adapter.handle_event(event)
    """

    def __init__(self, backend: Optional[MetricsBackend] = None):
        """Initialize MetricsAdapter.

        Args:
            backend: Metrics backend to use. Defaults to NoOpBackend.
        """
        self.backend = backend or NoOpBackend()

    def handle_event(self, event: Any) -> None:
        """Handle a LayerEvent and emit appropriate metrics.

        Args:
            event: LayerEvent to handle
        """
        from ..layer_contracts import LayerEventType

        event_type = event.event_type
        data = event.data

        if event_type == LayerEventType.L4_CIRCUIT_BREAKER_OPEN:
            self._handle_circuit_breaker_open(data)
        elif event_type == LayerEventType.L4_CIRCUIT_BREAKER_CLOSE:
            self._handle_circuit_breaker_close(data)

    def _handle_circuit_breaker_open(self, data: Dict[str, Any]) -> None:
        """Handle circuit breaker open event.

        Emits:
            - counter: circuit_breaker_open_total
            - gauge: circuit_breaker_failure_rate
        """
        model_id = data.get("model_id", "unknown")
        failure_rate = data.get("failure_rate", 0.0)

        tags = {"model_id": model_id}

        # Emit counter for open events
        self.backend.emit_counter("circuit_breaker_open_total", 1, tags)

        # Emit gauge for failure rate
        self.backend.emit_gauge("circuit_breaker_failure_rate", failure_rate, tags)

        logger.debug(
            "Emitted circuit_breaker_open metrics for %s (failure_rate=%.2f)",
            model_id,
            failure_rate,
        )

    def _handle_circuit_breaker_close(self, data: Dict[str, Any]) -> None:
        """Handle circuit breaker close event.

        Emits:
            - counter: circuit_breaker_close_total
        """
        model_id = data.get("model_id", "unknown")
        from_state = data.get("from_state", "unknown")

        tags = {"model_id": model_id, "from_state": from_state}

        # Emit counter for close events
        self.backend.emit_counter("circuit_breaker_close_total", 1, tags)

        logger.debug(
            "Emitted circuit_breaker_close metrics for %s (from_state=%s)",
            model_id,
            from_state,
        )


# =============================================================================
# Configuration Helpers
# =============================================================================


def _is_metrics_enabled() -> bool:
    """Check if metrics export is enabled.

    Priority: Environment variable > Config > Default (False)

    Returns:
        True if metrics are enabled
    """
    # Check environment variable first
    env_val = os.getenv("LLM_COUNCIL_METRICS_ENABLED")
    if env_val is not None:
        return env_val.lower() in ("true", "1", "yes")

    # Check config
    try:
        from ..unified_config import get_config

        config = get_config()
        return config.observability.metrics.enabled
    except Exception:
        return False


def _get_metrics_backend_type() -> str:
    """Get the configured metrics backend type.

    Priority: Environment variable > Config > Default ("none")

    Returns:
        Backend type: "none", "statsd", or "prometheus"
    """
    # Check environment variable first
    env_val = os.getenv("LLM_COUNCIL_METRICS_BACKEND")
    if env_val and env_val.lower() in ("none", "statsd", "prometheus"):
        return env_val.lower()

    # Check config
    try:
        from ..unified_config import get_config

        config = get_config()
        return config.observability.metrics.backend
    except Exception:
        return "none"


def _create_backend() -> MetricsBackend:
    """Create the appropriate metrics backend based on configuration.

    Returns:
        Configured MetricsBackend instance
    """
    if not _is_metrics_enabled():
        return NoOpBackend()

    backend_type = _get_metrics_backend_type()

    if backend_type == "statsd":
        try:
            from ..unified_config import get_config

            config = get_config()
            return StatsDBackend(
                host=config.observability.metrics.statsd_host,
                port=config.observability.metrics.statsd_port,
                prefix=config.observability.metrics.statsd_prefix,
            )
        except Exception as e:
            logger.warning("Failed to create StatsD backend: %s", e)
            return NoOpBackend()

    elif backend_type == "prometheus":
        try:
            from ..unified_config import get_config

            config = get_config()
            return PrometheusBackend(
                prefix=config.observability.metrics.statsd_prefix,
                port=config.observability.metrics.prometheus_port,
            )
        except Exception as e:
            logger.warning("Failed to create Prometheus backend: %s", e)
            return NoOpBackend()

    return NoOpBackend()


# =============================================================================
# Factory and Subscription
# =============================================================================

# Global adapter instance
_metrics_adapter: Optional[MetricsAdapter] = None

# Subscribed adapters
_subscribed_adapters: List[MetricsAdapter] = []


def get_metrics_adapter() -> MetricsAdapter:
    """Get or create the global metrics adapter.

    Returns:
        MetricsAdapter configured based on settings
    """
    global _metrics_adapter

    if _metrics_adapter is None:
        backend = _create_backend()
        _metrics_adapter = MetricsAdapter(backend=backend)

    return _metrics_adapter


def subscribe_metrics_adapter(adapter: MetricsAdapter) -> None:
    """Subscribe a MetricsAdapter to receive layer events.

    Args:
        adapter: MetricsAdapter to subscribe
    """
    if adapter not in _subscribed_adapters:
        _subscribed_adapters.append(adapter)
        logger.debug("Subscribed metrics adapter")


def unsubscribe_metrics_adapter(adapter: MetricsAdapter) -> None:
    """Unsubscribe a MetricsAdapter from layer events.

    Args:
        adapter: MetricsAdapter to unsubscribe
    """
    if adapter in _subscribed_adapters:
        _subscribed_adapters.remove(adapter)
        logger.debug("Unsubscribed metrics adapter")


def _notify_adapters(event: Any) -> None:
    """Notify all subscribed adapters of an event.

    Args:
        event: LayerEvent to dispatch
    """
    for adapter in _subscribed_adapters:
        try:
            adapter.handle_event(event)
        except Exception as e:
            logger.warning("Metrics adapter failed to handle event: %s", e)


# =============================================================================
# Module Exports
# =============================================================================

__all__ = [
    "MetricsBackend",
    "NoOpBackend",
    "StatsDBackend",
    "PrometheusBackend",
    "MetricsAdapter",
    "get_metrics_adapter",
    "subscribe_metrics_adapter",
    "unsubscribe_metrics_adapter",
    "_is_metrics_enabled",
    "_get_metrics_backend_type",
    "_notify_adapters",
]
