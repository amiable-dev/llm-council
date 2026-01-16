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

# File locking - use fcntl on Unix, fallback to no-op on Windows
try:
    import fcntl

    _HAS_FCNTL = True
except ImportError:
    _HAS_FCNTL = False

# Maximum file size before truncation (1MB)
MAX_METRICS_FILE_SIZE = 1024 * 1024

# Lazy import of layer_contracts to avoid circular dependency
# Used in _emit_rollback_event method


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
    min_samples: int = 10  # Minimum samples before rate calculation (cold start protection)
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
            min_samples=int(os.environ.get("LLM_COUNCIL_ROLLBACK_MIN_SAMPLES", "10")),
            disagreement_threshold=float(
                os.environ.get("LLM_COUNCIL_ROLLBACK_DISAGREEMENT_THRESHOLD", "0.08")
            ),
            escalation_threshold=float(
                os.environ.get("LLM_COUNCIL_ROLLBACK_ESCALATION_THRESHOLD", "0.15")
            ),
            error_multiplier=float(os.environ.get("LLM_COUNCIL_ROLLBACK_ERROR_MULTIPLIER", "1.5")),
            wildcard_timeout_threshold=float(
                os.environ.get("LLM_COUNCIL_ROLLBACK_WILDCARD_TIMEOUT_THRESHOLD", "0.05")
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
        """Load metrics from persistent store with file locking.

        On load error (corrupted file, permission issues), starts fresh with empty metrics.
        This is the correct 'fail-safe' behavior for rollback monitoring:
        - Empty metrics means no thresholds are breached
        - Fast path remains enabled (the default optimistic state)
        - If historical data suggests problems, we'd want to disable fast path
        - Without that data, we have no evidence to disable it
        """
        import logging

        if not os.path.exists(self.store_path):
            return

        try:
            with open(self.store_path, "r") as f:
                # Acquire shared lock for reading (Unix only)
                if _HAS_FCNTL:
                    fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                try:
                    for line in f:
                        if line.strip():
                            data = json.loads(line)
                            record = MetricRecord.from_dict(data)
                            metric_type = MetricType(record.metric_type)
                            self._metrics[metric_type].append(record)
                finally:
                    if _HAS_FCNTL:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)

            # Trim to window size
            for metric_type in self._metrics:
                self._metrics[metric_type] = self._metrics[metric_type][-self.config.window_size :]
        except (json.JSONDecodeError, IOError, ValueError) as e:
            # Log the error for observability, then start fresh
            logging.warning(
                f"Failed to load rollback metrics from {self.store_path}: {e}. "
                "Starting with empty metrics (fail-safe behavior)."
            )
            self._metrics = defaultdict(list)

    def _save_record(self, record: MetricRecord) -> None:
        """Append record to persistent store with file locking and size bounds."""
        try:
            # Check file size and truncate if needed
            if os.path.exists(self.store_path):
                file_size = os.path.getsize(self.store_path)
                if file_size > MAX_METRICS_FILE_SIZE:
                    self._truncate_file()

            with open(self.store_path, "a") as f:
                # Acquire exclusive lock for writing (Unix only)
                if _HAS_FCNTL:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    f.write(json.dumps(record.to_dict()) + "\n")
                    f.flush()
                finally:
                    # Release lock
                    if _HAS_FCNTL:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except IOError:
            pass  # Best effort persistence

    def _truncate_file(self) -> None:
        """Truncate file to keep only recent records (bounded storage).

        Uses atomic file replacement for consistency:
        1. Read all records from current file
        2. Write truncated records to temp file
        3. Atomic rename to replace main file

        Note: File locking is NOT used for truncation because:
        - The atomic rename (os.replace) guarantees readers see either
          the old or new file, never partial data
        - Holding a lock during rename is ineffective (lock is on old inode)
        - This design accepts eventual consistency which is appropriate
          for rollback metrics
        """
        import tempfile

        try:
            # Read all records from current file
            records = []
            if os.path.exists(self.store_path):
                with open(self.store_path, "r") as f:
                    for line in f:
                        if line.strip():
                            records.append(line)

            # Keep only last window_size * 5 records (reasonable history)
            max_records = self.config.window_size * 5
            if len(records) > max_records:
                records = records[-max_records:]

            # Write to temp file in same directory (for atomic rename)
            dir_path = os.path.dirname(self.store_path) or "."
            fd, temp_path = tempfile.mkstemp(dir=dir_path, suffix=".tmp")
            try:
                with os.fdopen(fd, "w") as temp_f:
                    temp_f.writelines(records)
                    temp_f.flush()
                    os.fsync(temp_f.fileno())  # Ensure data is on disk

                # Atomic rename (POSIX guarantees this is atomic)
                os.replace(temp_path, self.store_path)
            except Exception:
                # Clean up temp file on error
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
                raise
        except IOError:
            pass  # Best effort truncation

    def record(self, metric_type: MetricType, value: float) -> None:
        """Record a metric value.

        Args:
            metric_type: Type of metric
            value: Metric value (typically 1.0 or 0.0)
        """
        # Skip recording if disabled
        if not self.config.enabled:
            return

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
            Rate (0-1) of positive values, or 0.0 if below minimum samples (cold start protection)
        """
        metrics = self._metrics[metric_type]
        if not metrics:
            return 0.0

        # Cold start protection: require minimum samples before calculating rate
        # This prevents 1/1 = 100% rate from triggering immediate rollback
        if len(metrics) < self.config.min_samples:
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
            True if any threshold is breached, False if disabled
        """
        # Skip checks if monitoring is disabled
        if not self.config.enabled:
            return False

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

        # Check error rate (ADR-020: error_report_rate > baseline * 1.5)
        error_rate = self.store.get_rate(MetricType.ERROR_RATE)
        error_threshold = self._get_threshold(MetricType.ERROR_RATE)
        if error_rate > error_threshold:
            self._breached[MetricType.ERROR_RATE] = True

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
        # Lazy import to avoid circular dependency
        from llm_council.layer_contracts import LayerEventType, emit_layer_event

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
        """Get threshold for a metric type.

        Returns:
            Threshold value that triggers rollback when exceeded.
        """
        if metric_type == MetricType.SHADOW_DISAGREEMENT:
            return self.config.disagreement_threshold
        elif metric_type == MetricType.USER_ESCALATION:
            return self.config.escalation_threshold
        elif metric_type == MetricType.WILDCARD_TIMEOUT:
            return self.config.wildcard_timeout_threshold
        elif metric_type == MetricType.ERROR_RATE:
            # Per ADR-020: error_rate > baseline * error_multiplier triggers rollback
            # Using a fixed baseline of 0.05 (5% expected error rate)
            # With default multiplier of 1.5, this gives threshold of 0.075 (7.5%)
            baseline_error_rate = 0.05
            return baseline_error_rate * self.config.error_multiplier
        elif metric_type == MetricType.WILDCARD_DISAGREEMENT:
            return 0.1  # 10% wildcard disagreement threshold
        else:
            return 0.1  # Default threshold for unknown metrics


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
