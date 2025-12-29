"""ADR-018 Phase 1: Cross-session bias data persistence.

This module provides JSONL-based storage for bias metric records,
enabling cross-session aggregation for statistically meaningful bias detection.

Key components:
- BiasMetricRecord: Dataclass for individual bias measurements
- ConsentLevel: Privacy consent levels aligned with ADR-001
- JSONL append/read operations for efficient storage
- Session-to-records conversion for council.py integration
"""

import hashlib
import hmac
import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

# Import version from package
try:
    from llm_council import __version__
except ImportError:
    __version__ = "unknown"

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration (loaded from unified_config - ADR-031)
# =============================================================================

from .unified_config import get_config


def _get_bias_persistence_enabled() -> bool:
    """Get bias persistence enabled flag from unified config."""
    try:
        return get_config().evaluation.bias.persistence_enabled
    except Exception:
        return False


def _get_bias_store_path() -> Path:
    """Get bias store path from unified config."""
    try:
        path_str = get_config().evaluation.bias.store_path
        return Path(path_str).expanduser()
    except Exception:
        return Path.home() / ".llm-council" / "bias_metrics.jsonl"


def _get_bias_consent_level() -> int:
    """Get bias consent level from unified config as integer."""
    try:
        consent_str = get_config().evaluation.bias.consent_level
        consent_map = {"OFF": 0, "LOCAL_ONLY": 1, "ANONYMOUS": 2, "ENHANCED": 3, "RESEARCH": 4}
        return consent_map.get(consent_str, 1)
    except Exception:
        return 1  # LOCAL_ONLY default


# Hash secret from environment
BIAS_HASH_SECRET = os.getenv("LLM_COUNCIL_HASH_SECRET", "default-dev-secret-do-not-use-in-prod")


# =============================================================================
# ConsentLevel Enum
# =============================================================================


class ConsentLevel(Enum):
    """ADR-018: Unified consent model aligned with council-cloud ADR-001.

    Levels:
        OFF (0): No telemetry or storage
        LOCAL_ONLY (1): Local JSONL storage only
        ANONYMOUS (2): + Cloud rankings transmission
        ENHANCED (3): + Cloud bias summary transmission
        RESEARCH (4): + Query hashes for similarity grouping
    """

    OFF = 0
    LOCAL_ONLY = 1
    ANONYMOUS = 2
    ENHANCED = 3
    RESEARCH = 4


# =============================================================================
# BiasMetricRecord Dataclass
# =============================================================================


@dataclass
class BiasMetricRecord:
    """Single bias metric record for JSONL storage.

    One record per (session, model, reviewer) combination.
    Schema versioned for future compatibility.

    Attributes:
        schema_version: Semver version string for schema compatibility
        session_id: UUID identifying the council session
        timestamp: ISO 8601 timestamp of the session
        consent_level: Privacy consent level (0-4)
        reviewer_id: Model that gave the score
        model_id: Model being scored
        position: Display position during peer review (0-indexed)
        response_length_chars: Character count of the response
        score_value: Numeric score given by reviewer
        score_scale: Scale description (e.g., "1-10")
        council_config_version: Package version for model drift tracking
        query_hash: Optional HMAC hash for query grouping (RESEARCH only)
        query_metadata: Optional metadata about the query
    """

    schema_version: str = "1.1.0"
    session_id: str = ""
    timestamp: str = ""
    consent_level: int = 1  # LOCAL_ONLY default
    reviewer_id: str = ""
    model_id: str = ""
    position: int = 0
    response_length_chars: int = 0
    score_value: float = 0.0
    score_scale: str = "1-10"
    council_config_version: str = "0.1.0"
    query_hash: Optional[str] = None
    query_metadata: Optional[Dict[str, Any]] = None

    def to_jsonl_line(self) -> str:
        """Serialize to single JSONL line.

        Returns:
            JSON string without newlines, suitable for JSONL append.
        """
        return json.dumps(asdict(self), default=str)

    @classmethod
    def from_jsonl_line(cls, line: str) -> "BiasMetricRecord":
        """Deserialize from JSONL line.

        Args:
            line: JSON string representing a record

        Returns:
            BiasMetricRecord instance
        """
        data = json.loads(line)
        # Handle potential missing fields from older schema versions
        return cls(
            schema_version=data.get("schema_version", "1.0.0"),
            session_id=data.get("session_id", ""),
            timestamp=data.get("timestamp", ""),
            consent_level=data.get("consent_level", 1),
            reviewer_id=data.get("reviewer_id", ""),
            model_id=data.get("model_id", ""),
            position=data.get("position", 0),
            response_length_chars=data.get("response_length_chars", 0),
            score_value=data.get("score_value", 0.0),
            score_scale=data.get("score_scale", "1-10"),
            council_config_version=data.get("council_config_version", ""),
            query_hash=data.get("query_hash"),
            query_metadata=data.get("query_metadata"),
        )


# =============================================================================
# Query Hashing (Privacy)
# =============================================================================


def hash_query_if_enabled(
    query: str,
    consent_level: ConsentLevel,
) -> Optional[str]:
    """Generate HMAC hash for query grouping (opt-in only).

    Only generates hash at RESEARCH consent level.
    Uses LLM_COUNCIL_HASH_SECRET env var or default dev secret.

    Args:
        query: The query text to hash
        consent_level: Current consent level

    Returns:
        16-character hex hash if RESEARCH consent, None otherwise
    """
    if consent_level != ConsentLevel.RESEARCH:
        return None

    # Use first 100 chars to limit what's hashed
    query_sample = query[:100]

    # HMAC with deployment-specific secret
    secret = os.getenv("LLM_COUNCIL_HASH_SECRET", "default-dev-secret-do-not-use-in-prod")
    hash_bytes = hmac.new(secret.encode(), query_sample.encode(), hashlib.sha256).hexdigest()

    # Truncate to 16 chars
    return hash_bytes[:16]


# =============================================================================
# JSONL Storage Operations
# =============================================================================


def append_bias_records(
    records: List[BiasMetricRecord],
    store_path: Optional[Path] = None,
) -> int:
    """Append records to JSONL store (atomic append).

    Creates directory and file if needed.
    Each record is written as a single line.

    Args:
        records: List of BiasMetricRecord to append
        store_path: Path to JSONL file (default from config)

    Returns:
        Number of records written
    """
    if not records:
        return 0

    if store_path is None:
        store_path = _get_bias_store_path()

    # Ensure directory exists
    store_path.parent.mkdir(parents=True, exist_ok=True)

    # Append records atomically (one line at a time)
    with open(store_path, "a") as f:
        for record in records:
            f.write(record.to_jsonl_line() + "\n")

    return len(records)


def read_bias_records(
    store_path: Optional[Path] = None,
    max_sessions: Optional[int] = None,
    max_days: Optional[int] = None,
    since: Optional[datetime] = None,
) -> List[BiasMetricRecord]:
    """Read records from JSONL store with optional filtering.

    Applies rolling window based on parameters.
    Returns records in chronological order (oldest first).

    Args:
        store_path: Path to JSONL file (default from config)
        max_sessions: Limit to last N sessions
        max_days: Limit to last N days
        since: Only records after this datetime

    Returns:
        List of BiasMetricRecord in chronological order
    """
    if store_path is None:
        store_path = _get_bias_store_path()

    if not store_path.exists():
        return []

    records = []

    with open(store_path, "r") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            try:
                record = BiasMetricRecord.from_jsonl_line(line)
                records.append(record)
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                logger.warning(f"Skipping malformed line {line_num}: {e}")
                continue

    # Filter by max_days
    if max_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_days)
        records = [r for r in records if _parse_timestamp(r.timestamp) >= cutoff]

    # Filter by since datetime
    if since is not None:
        records = [r for r in records if _parse_timestamp(r.timestamp) >= since]

    # Sort chronologically (oldest first)
    records.sort(key=lambda r: r.timestamp)

    # Filter by max_sessions (keep last N sessions)
    if max_sessions is not None:
        # Get unique session IDs in chronological order
        seen_sessions = []
        for r in reversed(records):
            if r.session_id not in seen_sessions:
                seen_sessions.append(r.session_id)
            if len(seen_sessions) >= max_sessions:
                break

        # Keep only records from these sessions
        allowed_sessions = set(seen_sessions)
        records = [r for r in records if r.session_id in allowed_sessions]

    return records


def _parse_timestamp(timestamp_str: str) -> datetime:
    """Parse ISO 8601 timestamp string to datetime.

    Handles various formats and returns epoch for invalid strings.
    """
    if not timestamp_str:
        return datetime.min.replace(tzinfo=timezone.utc)

    try:
        # Try standard ISO format
        if timestamp_str.endswith("Z"):
            timestamp_str = timestamp_str[:-1] + "+00:00"
        return datetime.fromisoformat(timestamp_str)
    except (ValueError, TypeError):
        return datetime.min.replace(tzinfo=timezone.utc)


def get_bias_store_stats(
    store_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Get statistics about the bias store.

    Args:
        store_path: Path to JSONL file (default from config)

    Returns:
        Dictionary with stats: total_records, unique_sessions,
        unique_reviewers, oldest_record, newest_record, file_size_bytes
    """
    if store_path is None:
        store_path = _get_bias_store_path()

    if not store_path.exists():
        return {
            "total_records": 0,
            "unique_sessions": 0,
            "unique_reviewers": 0,
            "oldest_record": None,
            "newest_record": None,
            "file_size_bytes": 0,
        }

    records = read_bias_records(store_path)

    if not records:
        return {
            "total_records": 0,
            "unique_sessions": 0,
            "unique_reviewers": 0,
            "oldest_record": None,
            "newest_record": None,
            "file_size_bytes": store_path.stat().st_size,
        }

    session_ids = {r.session_id for r in records}
    reviewer_ids = {r.reviewer_id for r in records}
    timestamps = [r.timestamp for r in records if r.timestamp]

    return {
        "total_records": len(records),
        "unique_sessions": len(session_ids),
        "unique_reviewers": len(reviewer_ids),
        "oldest_record": min(timestamps) if timestamps else None,
        "newest_record": max(timestamps) if timestamps else None,
        "file_size_bytes": store_path.stat().st_size,
    }


# =============================================================================
# Session-to-Records Conversion
# =============================================================================


def _get_model_from_label_value(label_value: Any) -> str:
    """Extract model string from label_to_model value.

    Handles both enhanced format (dict with 'model' key) and legacy (string).
    """
    if isinstance(label_value, dict):
        return label_value.get("model", "")
    return str(label_value)


def _get_position_from_label(label: str, label_value: Any) -> int:
    """Extract position from label_to_model entry.

    Uses display_index from enhanced format, or derives from label letter.
    """
    if isinstance(label_value, dict) and "display_index" in label_value:
        return label_value["display_index"]

    # Fall back to deriving from label letter (A=0, B=1, etc.)
    # Label format: "Response A", "Response B", etc.
    parts = label.split()
    if len(parts) >= 2:
        letter = parts[-1].upper()
        if letter.isalpha() and len(letter) == 1:
            return ord(letter) - ord("A")

    return 0


def _extract_query_metadata(query: str) -> Dict[str, Any]:
    """Extract metadata from the user query for bias analysis (ADR-018).

    Extracts:
    - category: Simple heuristic-based classification
    - token_bucket: 'short' (<50 chars), 'medium' (<200), 'long' (>200)
    - language: Defaults to 'en' (placeholder for future detection)

    Args:
        query: The user's query string (potentially sensitive)

    Returns:
        Dict with metadata fields
    """
    if not query:
        return {"category": "unknown", "token_bucket": "unknown", "language": "en"}

    # 1. Token bucket (using char length as proxy for speed/privacy)
    length = len(query)
    if length < 50:
        bucket = "short"
    elif length < 200:
        bucket = "medium"
    else:
        bucket = "long"

    # 2. Category heuristic
    query_lower = query.lower()
    category = "general"

    code_keywords = ["def", "function", "class", "import", "python", "javascript"]
    math_keywords = ["calculate", "compute", "equation", "math", "+", "="]
    creative_keywords = ["write", "story", "poem", "creative", "imagine"]

    if any(k in query_lower for k in code_keywords):
        category = "coding"
    elif any(k in query_lower for k in math_keywords):
        category = "math_reasoning"
    elif any(k in query_lower for k in creative_keywords):
        category = "creative_writing"

    return {"category": category, "token_bucket": bucket, "language": "en"}


def create_bias_records_from_session(
    session_id: str,
    stage1_results: List[Dict[str, Any]],
    stage2_results: List[Dict[str, Any]],
    label_to_model: Dict[str, Any],
    query: Optional[str] = None,
    consent_level: ConsentLevel = ConsentLevel.LOCAL_ONLY,
) -> List[BiasMetricRecord]:
    """
    Create bias metric records from a council session.

    Args:
        session_id: Unique session identifier
        stage1_results: List of model responses from Stage 1
        stage2_results: List of rankings/reviews from Stage 2
        label_to_model: Mapping of anonymous labels to model names
        query: Original user query (optional, for metadata/hashing)
        consent_level: User's privacy consent level

    Returns:
        List of BiasMetricRecord objects
    """
    records = []
    timestamp = datetime.now(timezone.utc).isoformat()

    # 1. Calculate query hash if consent allows (RESEARCH level)
    query_hash = hash_query_if_enabled(query, consent_level) if query else None

    # 2. Extract query metadata (safely, no PII)
    query_metadata = _extract_query_metadata(query) if query else None

    # Helper to get model name from label mapping
    def get_model_from_label(lbl: str) -> str:
        val = label_to_model.get(lbl)
        if isinstance(val, dict):
            return val.get("model", "")
        return str(val) if val else ""

    # Parse all rankings first
    for ranking_result in stage2_results:
        # One record per (reviewer, candidate) pair
        reviewer_id = ranking_result.get("model", "")

        parsed = ranking_result.get("parsed_ranking") or {}

        # Determine score scale
        score_scale = "1-10"

        # Process explicit scores if available
        scores = parsed.get("scores", {})
        ranked_labels = parsed.get("ranking", [])

        # Determine which labels to process (ranking list prefers order, but fallback to score keys)
        labels_to_process = ranked_labels if ranked_labels else list(scores.keys())

        for idx, label in enumerate(labels_to_process):
            model_id = get_model_from_label(label)
            if not model_id:
                continue

            # Get the score if available
            score_value = float(scores.get(label, 0.0))

            # Position is 0-indexed index in the processed list
            position = idx

            # Find usage stats if available
            # Note: We don't have per-candidate response length easily accessible here
            # without looking back at stage1_results, but we can do a quick lookup
            response_length = 0
            for r in stage1_results:
                if r.get("model") == model_id:
                    response_length = len(r.get("response", ""))
                    break

            record = BiasMetricRecord(
                schema_version="1.1.0",
                session_id=session_id,
                timestamp=timestamp,
                consent_level=consent_level.value
                if hasattr(consent_level, "value")
                else int(consent_level),
                reviewer_id=reviewer_id,
                model_id=model_id,
                position=position,
                response_length_chars=response_length,
                score_value=score_value,
                score_scale=score_scale,
                council_config_version="0.1.0",
                query_hash=query_hash,
                query_metadata=query_metadata,
            )
            records.append(record)

    return records


# =============================================================================
# High-Level Integration
# =============================================================================


def persist_session_bias_data(
    session_id: str,
    stage1_results: List[Dict[str, Any]],
    stage2_results: List[Dict[str, Any]],
    label_to_model: Dict[str, Any],
    query: Optional[str] = None,
) -> int:
    """High-level integration point for council.py.

    Called after Stage 2 completes if bias persistence is enabled.
    Respects consent_level from config.

    Args:
        session_id: UUID for the session
        stage1_results: List of {model, response} from Stage 1
        stage2_results: List of {model, parsed_ranking} from Stage 2
        label_to_model: Mapping of labels to model info
        query: Optional query text (for hashing at RESEARCH consent)

    Returns:
        Number of records persisted (0 if disabled)
    """
    if not _get_bias_persistence_enabled():
        return 0

    # Convert consent level int to enum
    try:
        consent = ConsentLevel(_get_bias_consent_level())
    except ValueError:
        consent = ConsentLevel.LOCAL_ONLY

    # Create records
    records = create_bias_records_from_session(
        session_id=session_id,
        stage1_results=stage1_results,
        stage2_results=stage2_results,
        label_to_model=label_to_model,
        query=query,
        consent_level=consent,
    )

    # Persist (store_path comes from _get_bias_store_path() via append_bias_records)
    return append_bias_records(records)
