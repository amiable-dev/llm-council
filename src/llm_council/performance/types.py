"""ADR-026 Phase 3: Performance Metric Types.

Core dataclasses for tracking model performance from council sessions.
"""

import json
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional


@dataclass
class ModelSessionMetric:
    """Performance data from a single council session for one model.

    One record per (session, model) combination.
    Schema versioned for future compatibility.

    Attributes:
        schema_version: Semver version string for schema compatibility
        session_id: UUID identifying the council session
        model_id: Full model identifier (e.g., 'openai/gpt-4o')
        timestamp: ISO 8601 timestamp of the session
        latency_ms: Response latency in milliseconds
        borda_score: Normalized Borda score (0-1) from peer review
        parse_success: Whether the model's response was successfully parsed
        reasoning_tokens_used: Optional reasoning tokens (for o1/o3 models)
    """

    schema_version: str = "1.0.0"
    session_id: str = ""
    model_id: str = ""
    timestamp: str = ""
    latency_ms: int = 0
    borda_score: float = 0.0
    parse_success: bool = True
    reasoning_tokens_used: Optional[int] = None
    cost_usd: Optional[float] = None  # ADR-011 Phase 3: per-session cost (None if unknown)

    def to_jsonl_line(self) -> str:
        """Serialize to single JSONL line.

        Returns:
            JSON string without newlines, suitable for JSONL append.
        """
        return json.dumps(asdict(self), default=str)

    @classmethod
    def from_jsonl_line(cls, line: str) -> "ModelSessionMetric":
        """Deserialize from JSONL line.

        Args:
            line: JSON string representing a record

        Returns:
            ModelSessionMetric instance
        """
        data = json.loads(line)
        # Handle potential missing fields from older schema versions
        return cls(
            schema_version=data.get("schema_version", "1.0.0"),
            session_id=data.get("session_id", ""),
            model_id=data.get("model_id", ""),
            timestamp=data.get("timestamp", ""),
            latency_ms=data.get("latency_ms", 0),
            borda_score=data.get("borda_score", 0.0),
            parse_success=data.get("parse_success", True),
            reasoning_tokens_used=data.get("reasoning_tokens_used"),
            cost_usd=data.get("cost_usd"),  # ADR-011: absent in older records
        )


@dataclass
class ModelPerformanceIndex:
    """Aggregated performance for a model across sessions.

    Built from historical ModelSessionMetric records with rolling window decay.

    Attributes:
        model_id: Full model identifier
        sample_size: Number of sessions used for aggregation
        mean_borda_score: Weighted mean Borda score (0-1)
        p50_latency_ms: Median (50th percentile) latency
        p95_latency_ms: 95th percentile latency
        parse_success_rate: Proportion of successful parses (0-1)
        confidence_level: Statistical confidence tier based on sample size
            - INSUFFICIENT: <10 samples
            - PRELIMINARY: 10-30 samples
            - MODERATE: 30-100 samples
            - HIGH: 100+ samples
    """

    model_id: str
    sample_size: int
    mean_borda_score: float
    p50_latency_ms: int
    p95_latency_ms: int
    parse_success_rate: float
    confidence_level: str  # INSUFFICIENT, PRELIMINARY, MODERATE, HIGH
    # ADR-011 Phase 3: weighted mean USD cost per session (None until any
    # session recorded a known cost).
    mean_cost_usd: Optional[float] = None

    @property
    def quality_per_cost(self) -> Optional[float]:
        """Borda-per-dollar: quality earned per USD (higher is better value).

        Returns None when cost is unknown or zero (no meaningful ratio) — callers
        must treat None as "no cost-value signal", not as best or worst.
        """
        if self.mean_cost_usd is None or self.mean_cost_usd <= 0:
            return None
        return self.mean_borda_score / self.mean_cost_usd
