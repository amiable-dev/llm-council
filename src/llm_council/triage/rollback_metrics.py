"""Rollback Metric Tracking for ADR-020 Tier 1.

Implements rollback monitoring that tracks metrics and triggers automatic
rollback when thresholds are breached.

Per ADR-020 Council-Defined Rollback Triggers:
- shadow_council_disagreement_rate > 8%
- user_escalation_rate > 15%
- error_report_rate > baseline * 1.5
"""

import json
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from llm_council.layer_contracts import (
    LayerEventType,
    emit_layer_event,
)


class MetricType(Enum):
    """Types of metrics tracked for rollback decisions."""

    SHADOW_DISAGREEMENT = "shadow_disagreement"
    USER_ESCALATION = "user_escalation"
    ERROR_RATE = "error_rate"
    WILDCARD_TIMEOUT = "wildcard_timeout"
    WILDCARD_DISAGREEMENT = "wildcard_disagreement"


@dataclass
class RollbackConfig:
    """Configuration for rollback monitoring.

    Attributes:
        enabled: Whether rollback monitoring is enabled
        window_size: Rolling window for rate calculation
        disagreement_threshold: Shadow council disagreement rate trigger (default: 8%)
        escalation_threshold: User escalation rate trigger (default: 15%)
        error_multiplier: Error rate multiplier trigger (default: 1.5x baseline)
        wildcard_timeout_threshold: Wildcard timeout rate trigger (default: 5%)
    """

    enabled: bool = True
    window_size: int = 100
    disagreement_threshold: float = 0.08
    escalation_threshold: float = 0.15
    error_multiplier: float = 1.5
    wildcard_timeout_threshold: float = 0.05

    @classmethod
    def from_env(cls) -> "RollbackConfig":
        """Create config from environment variables."""
        enabled_str = os.environ.get("LLM_COUNCIL_ROLLBACK_ENABLED", "true")
        enabled = enabled_str.lower() in ("true", "1", "yes")

        return cls(
            enabled=enabled,
            window_size=int(os.environ.get("LLM_COUNCIL_ROLLBACK_WINDOW", "100")),
            disagreement_threshold=float(
                os.environ.get("LLM_COUNCIL_ROLLBACK_DISAGREEMENT_THRESHOLD", "0.08")
            ),
            escalation_threshold=float(
                os.environ.get("LLM_COUNCIL_ROLLBACK_ESCALATION_THRESHOLD", "0.15")
            ),
        )


@dataclass
class MetricRecord:
    """A single metric record.

    Attributes:
        metric_type: Type of metric
        value: Metric value (1.0 = event occurred, 0.0 = event did not occur)
        timestamp: Unix timestamp
    """

    metric_type: str
    value: float
    timestamp: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MetricRecord":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class RollbackEvent:
    """A rollback trigger event.

    Attributes:
        metric_type: Type of metric that triggered
        current_rate: Current rate of the metric
        threshold: Threshold that was exceeded
        window_size: Window size used for calculation
        timestamp: Unix timestamp
    """

    metric_type: MetricType
    current_rate: float
    threshold: float
    window_size: int
    timestamp: float

    @property
    def is_breach(self) -> bool:
        """Check if this event represents a threshold breach."""
        return self.current_rate > self.threshold


class RollbackMetricStore:
    """Store for rollback metrics.

    Tracks metrics over a rolling window and calculates rates.
    """

    def __init__(
        self,
        config: Optional[RollbackConfig] = None,
        store_path: Optional[str] = None,
    ):
        """Initialize store.

        Args:
            config: Rollback configuration
            store_path: Path to JSONL file for persistence
        """
        self.config = config or RollbackConfig.from_env()

        if store_path is None:
            store_dir = Path.home() / ".llm-council"
            store_dir.mkdir(parents=True, exist_ok=True)
            store_path = str(store_dir / "rollback_metrics.jsonl")

        self.store_path = store_path
        self._metrics: Dict[MetricType, List[MetricRecord]] = defaultdict(list)

        # Load existing metrics
        self._load()

    def _load(self) -> None:
        """Load metrics from persistent store."""
        if not os.path.exists(self.store_path):
            return

        try:
            with open(self.store_path, "r") as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        record = MetricRecord.from_dict(data)
                        metric_type = MetricType(record.metric_type)
                        self._metrics[metric_type].append(record)

            # Trim to window size
            for metric_type in self._metrics:
                self._metrics[metric_type] = self._metrics[metric_type][-self.config.window_size :]
        except (json.JSONDecodeError, IOError, ValueError):
            # Start fresh on error
            self._metrics = defaultdict(list)

    def _save_record(self, record: MetricRecord) -> None:
        """Append record to persistent store."""
        try:
            with open(self.store_path, "a") as f:
                f.write(json.dumps(record.to_dict()) + "\n")
        except IOError:
            pass  # Best effort persistence

    def record(self, metric_type: MetricType, value: float) -> None:
        """Record a metric value.

        Args:
            metric_type: Type of metric
            value: Metric value (typically 1.0 or 0.0)
        """
        record = MetricRecord(
            metric_type=metric_type.value,
            value=value,
            timestamp=time.time(),
        )

        self._metrics[metric_type].append(record)

        # Maintain rolling window
        if len(self._metrics[metric_type]) > self.config.window_size:
            self._metrics[metric_type] = self._metrics[metric_type][-self.config.window_size :]

        # Persist
        self._save_record(record)

    def get_recent_metrics(self, metric_type: MetricType) -> List[MetricRecord]:
        """Get recent metrics of a type.

        Args:
            metric_type: Type of metric to get

        Returns:
            List of recent MetricRecords
        """
        return list(self._metrics[metric_type])

    def get_rate(self, metric_type: MetricType) -> float:
        """Calculate rate for a metric type.

        Args:
            metric_type: Type of metric

        Returns:
            Rate (0-1) of positive values
        """
        metrics = self._metrics[metric_type]
        if not metrics:
            return 0.0

        positive_count = sum(1 for m in metrics if m.value > 0.5)
        return positive_count / len(metrics)


class RollbackMonitor:
    """Monitor for rollback thresholds.

    Checks metric rates against thresholds and emits events
    when thresholds are breached.
    """

    def __init__(self, config: Optional[RollbackConfig] = None):
        """Initialize monitor.

        Args:
            config: Rollback configuration
        """
        self.config = config or RollbackConfig.from_env()
        self.store = RollbackMetricStore(config)
        self._breached: Dict[MetricType, bool] = {}

    def check_thresholds(self) -> bool:
        """Check if any thresholds are breached.

        Returns:
            True if any threshold is breached
        """
        self._breached = {}

        # Check shadow disagreement
        disagreement_rate = self.store.get_rate(MetricType.SHADOW_DISAGREEMENT)
        if disagreement_rate > self.config.disagreement_threshold:
            self._breached[MetricType.SHADOW_DISAGREEMENT] = True

        # Check user escalation
        escalation_rate = self.store.get_rate(MetricType.USER_ESCALATION)
        if escalation_rate > self.config.escalation_threshold:
            self._breached[MetricType.USER_ESCALATION] = True

        # Check wildcard timeout
        timeout_rate = self.store.get_rate(MetricType.WILDCARD_TIMEOUT)
        if timeout_rate > self.config.wildcard_timeout_threshold:
            self._breached[MetricType.WILDCARD_TIMEOUT] = True

        return len(self._breached) > 0

    def get_breached_thresholds(self) -> Dict[MetricType, bool]:
        """Get dictionary of breached thresholds.

        Returns:
            Dict mapping MetricType to breach status
        """
        return dict(self._breached)

    def check_and_emit_events(self) -> List[RollbackEvent]:
        """Check thresholds and emit events for breaches.

        Returns:
            List of RollbackEvents for breaches
        """
        events = []

        if self.check_thresholds():
            for metric_type, is_breached in self._breached.items():
                if is_breached:
                    rate = self.store.get_rate(metric_type)
                    threshold = self._get_threshold(metric_type)

                    event = RollbackEvent(
                        metric_type=metric_type,
                        current_rate=rate,
                        threshold=threshold,
                        window_size=self.config.window_size,
                        timestamp=time.time(),
                    )
                    events.append(event)

                    # Emit layer event
                    emit_layer_event(
                        LayerEventType.L2_DELIBERATION_ESCALATION,
                        {
                            "type": "rollback_trigger",
                            "metric": metric_type.value,
                            "rate": rate,
                            "threshold": threshold,
                        },
                        layer_from="L2",
                        layer_to="L1",
                    )

        return events

    def _get_threshold(self, metric_type: MetricType) -> float:
        """Get threshold for a metric type."""
        if metric_type == MetricType.SHADOW_DISAGREEMENT:
            return self.config.disagreement_threshold
        elif metric_type == MetricType.USER_ESCALATION:
            return self.config.escalation_threshold
        elif metric_type == MetricType.WILDCARD_TIMEOUT:
            return self.config.wildcard_timeout_threshold
        else:
            return 0.1  # Default threshold


# Global monitor instance
_rollback_monitor: Optional[RollbackMonitor] = None


def get_rollback_monitor() -> RollbackMonitor:
    """Get global rollback monitor instance."""
    global _rollback_monitor
    if _rollback_monitor is None:
        _rollback_monitor = RollbackMonitor()
    return _rollback_monitor


def should_disable_fast_path() -> bool:
    """Check if fast path should be disabled due to rollback triggers.

    Returns:
        True if fast path should be disabled
    """
    monitor = get_rollback_monitor()
    return monitor.check_thresholds()


def record_shadow_disagreement(is_disagreement: bool) -> None:
    """Record a shadow sampling result.

    Args:
        is_disagreement: Whether fast path disagreed with council
    """
    monitor = get_rollback_monitor()
    monitor.store.record(
        MetricType.SHADOW_DISAGREEMENT,
        1.0 if is_disagreement else 0.0,
    )


def record_user_escalation(was_escalated: bool) -> None:
    """Record a user escalation.

    Args:
        was_escalated: Whether user manually escalated
    """
    monitor = get_rollback_monitor()
    monitor.store.record(
        MetricType.USER_ESCALATION,
        1.0 if was_escalated else 0.0,
    )


def record_error(had_error: bool) -> None:
    """Record an error occurrence.

    Args:
        had_error: Whether an error occurred
    """
    monitor = get_rollback_monitor()
    monitor.store.record(
        MetricType.ERROR_RATE,
        1.0 if had_error else 0.0,
    )
