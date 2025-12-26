"""Observability module for LLM Council.

Provides metrics export, tracing, and monitoring capabilities.
"""

from .metrics_adapter import (
    MetricsAdapter,
    MetricsBackend,
    NoOpBackend,
    StatsDBackend,
    PrometheusBackend,
    get_metrics_adapter,
    subscribe_metrics_adapter,
    unsubscribe_metrics_adapter,
    _is_metrics_enabled,
    _get_metrics_backend_type,
)

__all__ = [
    "MetricsAdapter",
    "MetricsBackend",
    "NoOpBackend",
    "StatsDBackend",
    "PrometheusBackend",
    "get_metrics_adapter",
    "subscribe_metrics_adapter",
    "unsubscribe_metrics_adapter",
    "_is_metrics_enabled",
    "_get_metrics_backend_type",
]
