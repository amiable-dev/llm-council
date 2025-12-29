"""JSONL Persistence for AuditionStatus (ADR-029 Phase 3).

This module provides atomic JSONL persistence for audition status records,
following the pattern established by bias_persistence.py.

Example:
    >>> from llm_council.audition.store import append_audition_record, read_audition_records
    >>> append_audition_record(status, "~/.llm-council/audition.jsonl")
    >>> records = read_audition_records("~/.llm-council/audition.jsonl")
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .types import AuditionState, AuditionStatus

logger = logging.getLogger(__name__)

# Schema version for forward compatibility
SCHEMA_VERSION = "1.0.0"


def _status_to_dict(status: AuditionStatus) -> Dict:
    """Convert AuditionStatus to JSON-serializable dict."""
    return {
        "schema_version": SCHEMA_VERSION,
        "model_id": status.model_id,
        "state": status.state.value,
        "session_count": status.session_count,
        "first_seen": status.first_seen.isoformat() if status.first_seen else None,
        "last_seen": status.last_seen.isoformat() if status.last_seen else None,
        "consecutive_failures": status.consecutive_failures,
        "quality_percentile": status.quality_percentile,
        "quarantine_until": (
            status.quarantine_until.isoformat() if status.quarantine_until else None
        ),
        "timestamp": datetime.utcnow().isoformat(),
    }


def _dict_to_status(data: Dict) -> AuditionStatus:
    """Convert dict to AuditionStatus."""
    return AuditionStatus(
        model_id=data["model_id"],
        state=AuditionState(data["state"]),
        session_count=data.get("session_count", 0),
        first_seen=(datetime.fromisoformat(data["first_seen"]) if data.get("first_seen") else None),
        last_seen=(datetime.fromisoformat(data["last_seen"]) if data.get("last_seen") else None),
        consecutive_failures=data.get("consecutive_failures", 0),
        quality_percentile=data.get("quality_percentile"),
        quarantine_until=(
            datetime.fromisoformat(data["quarantine_until"])
            if data.get("quarantine_until")
            else None
        ),
    )


def append_audition_record(status: AuditionStatus, path: str) -> None:
    """Append an audition status record to JSONL file.

    Creates the file and parent directories if they don't exist.
    Appends atomically to prevent corruption.

    Args:
        status: AuditionStatus to persist
        path: Path to JSONL file
    """
    expanded_path = Path(os.path.expanduser(path))
    expanded_path.parent.mkdir(parents=True, exist_ok=True)

    record = _status_to_dict(status)
    line = json.dumps(record) + "\n"

    with open(expanded_path, "a") as f:
        f.write(line)

    logger.debug(f"Appended audition record for {status.model_id} to {path}")


def read_audition_records(
    path: str,
    model_id: Optional[str] = None,
) -> List[AuditionStatus]:
    """Read audition status records from JSONL file.

    Returns the most recent status for each model (or filtered model).

    Args:
        path: Path to JSONL file
        model_id: Optional model ID to filter by

    Returns:
        List of AuditionStatus, one per model (most recent state)
    """
    expanded_path = Path(os.path.expanduser(path))

    if not expanded_path.exists():
        return []

    # Track most recent status per model
    latest_by_model: Dict[str, AuditionStatus] = {}

    with open(expanded_path, "r") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)
                status = _dict_to_status(data)

                if model_id is not None and status.model_id != model_id:
                    continue

                # Keep most recent (last) record per model
                latest_by_model[status.model_id] = status

            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.warning(f"Skipping malformed record at line {line_num}: {e}")
                continue

    return list(latest_by_model.values())
