"""ADR-026 Phase 3: Performance Metrics JSONL Storage.

Provides JSONL-based storage for performance metric records,
following the pattern established by bias_persistence.py.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

from .types import ModelSessionMetric

logger = logging.getLogger(__name__)


def append_performance_records(
    records: List[ModelSessionMetric],
    path: Path,
) -> int:
    """Append performance records to JSONL file atomically.

    Creates the file and parent directories if they don't exist.
    Uses append mode for atomic writes.

    Args:
        records: List of ModelSessionMetric records to append
        path: Path to the JSONL file

    Returns:
        Number of records written
    """
    if not records:
        return 0

    # Create parent directory if needed
    path.parent.mkdir(parents=True, exist_ok=True)

    # Append records atomically
    with open(path, "a", encoding="utf-8") as f:
        for record in records:
            f.write(record.to_jsonl_line() + "\n")

    logger.debug(f"Appended {len(records)} performance records to {path}")
    return len(records)


def read_performance_records(
    path: Path,
    max_days: Optional[int] = None,
    model_id: Optional[str] = None,
) -> List[ModelSessionMetric]:
    """Read performance records from JSONL file with optional filtering.

    Args:
        path: Path to the JSONL file
        max_days: If set, only return records from the last N days
        model_id: If set, only return records for this model

    Returns:
        List of ModelSessionMetric records, sorted by timestamp (oldest first)
    """
    if not path.exists():
        return []

    records: List[ModelSessionMetric] = []
    cutoff_date: Optional[datetime] = None

    if max_days is not None:
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=max_days)

    with open(path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            try:
                record = ModelSessionMetric.from_jsonl_line(line)
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Skipping malformed line {line_num} in {path}: {e}")
                continue

            # Apply model_id filter
            if model_id is not None and record.model_id != model_id:
                continue

            # Apply max_days filter
            if cutoff_date is not None and record.timestamp:
                try:
                    # Parse ISO timestamp
                    record_time = datetime.fromisoformat(record.timestamp.replace("Z", "+00:00"))
                    if record_time < cutoff_date:
                        continue
                except ValueError:
                    # If timestamp can't be parsed, include the record
                    pass

            records.append(record)

    # Sort by timestamp (oldest first)
    records.sort(key=lambda r: r.timestamp or "")

    return records
