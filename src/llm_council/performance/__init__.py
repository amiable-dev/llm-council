"""ADR-026 Phase 3: Internal Performance Tracking module.

Provides performance tracking and aggregation for council sessions,
building an Internal Performance Index from historical data.

Usage:
    from llm_council.performance import ModelSessionMetric, ModelPerformanceIndex
    from llm_council.performance import append_performance_records, read_performance_records

    # Create a metric record
    metric = ModelSessionMetric(
        session_id="sess-123",
        model_id="openai/gpt-4o",
        timestamp="2025-12-24T00:00:00Z",
        latency_ms=1500,
        borda_score=0.75,
        parse_success=True,
    )

    # Persist to JSONL
    from pathlib import Path
    append_performance_records([metric], Path("metrics.jsonl"))

    # Read back with filtering
    records = read_performance_records(Path("metrics.jsonl"), max_days=30)
"""

from .integration import get_tracker, persist_session_performance_data
from .store import append_performance_records, read_performance_records
from .tracker import InternalPerformanceTracker
from .types import ModelPerformanceIndex, ModelSessionMetric

__all__ = [
    # Types (types.py)
    "ModelSessionMetric",
    "ModelPerformanceIndex",
    # Storage (store.py)
    "append_performance_records",
    "read_performance_records",
    # Tracker (tracker.py)
    "InternalPerformanceTracker",
    # Integration (integration.py)
    "get_tracker",
    "persist_session_performance_data",
]
