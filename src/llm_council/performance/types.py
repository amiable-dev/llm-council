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
        latency_ms: Response latency in milliseconds, or None when the
            entry point did not measure it (schema 1.1.0+)
        borda_score: Normalized Borda score (0-1) from peer review, or None
            when peer review did not rank this model (schema 1.1.0+)
        parse_success: Whether the model's ranking parsed, or None when peer
            review never ranked this model (schema 1.1.0+)
        reasoning_tokens_used: Optional reasoning tokens (for o1/o3 models)
    """

    schema_version: str = "1.1.0"
    session_id: str = ""
    model_id: str = ""
    timestamp: str = ""
    # #692: nullable since schema 1.1.0, for the same reason as the two
    # fields below. A recorded 0 ms is a claim that the model answered
    # instantly; it would land in the p50/p95 percentiles that decide
    # whether a model fits a tier's time budget.
    latency_ms: Optional[int] = None
    # #692: nullable since schema 1.1.0. `None` means peer review never ranked
    # this model — a partial or timed-out run. `0.0` means it WAS ranked, last.
    # Collapsing the two would record a pile of bottom-scored models every time
    # a run was cut short, and the performance index those scores feed decides
    # which models get selected next.
    borda_score: Optional[float] = None
    # #692 gate: tri-state. `None` means peer review never saw this model,
    # which is the normal case for a partial run now that unranked models
    # are recorded. Defaulting those to True inflated the parse-success
    # rate with models that never had the chance to parse anything.
    parse_success: Optional[bool] = None
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
        # Handle potential missing fields from older schema versions.
        #
        # NO MIGRATION, deliberately (#692 gate round 3). A 1.0.0 record
        # carrying a literal `latency_ms: 0` or `borda_score: 0.0` is
        # indistinguishable from a genuine measurement of zero, because at
        # the time it was written those fields could not be null — the
        # information needed to tell them apart was never recorded. Guessing
        # which historical zeros "meant" unknown would fabricate exactly the
        # data this schema change exists to stop fabricating. Old records are
        # read as written; only new ones can be honest about absence.
        return cls(
            schema_version=data.get("schema_version", "1.0.0"),
            session_id=data.get("session_id", ""),
            model_id=data.get("model_id", ""),
            timestamp=data.get("timestamp", ""),
            # #692 gate: NO zero defaults here. Writing nullable fields and
            # then defaulting them back to 0 on read would have undone the
            # whole point of schema 1.1.0 — an absent latency became "answered
            # instantly" and an absent score became "ranked last" the moment
            # the record was loaded. Absent stays absent.
            latency_ms=data.get("latency_ms"),
            borda_score=data.get("borda_score"),
            parse_success=data.get("parse_success"),
            reasoning_tokens_used=data.get("reasoning_tokens_used"),
            cost_usd=data.get("cost_usd"),  # ADR-011: absent in older records
        )


@dataclass
class ModelPerformanceIndex:
    """Aggregated performance for a model across sessions.

    Built from historical ModelSessionMetric records with rolling window decay.

    Attributes:
        model_id: Full model identifier
        sample_size: Number of records for this model — ALL of them, including
            records that carry no quality signal. Deliberately divergent from
            `confidence_level`, which counts only records with a Borda score
            (#692): since consult began recording models peer review never
            reached, a raw count could carry a model to HIGH confidence on
            rows containing nothing. So `sample_size=120` alongside
            `confidence_level='INSUFFICIENT'` is possible and correct — it
            means 120 observations exist and few of them scored anything.
        mean_borda_score: Weighted mean Borda score (0-1)
        p50_latency_ms: Median latency, or None when no record measured it
        p95_latency_ms: 95th percentile latency, or None when unmeasured
        parse_success_rate: Proportion of successful parses (0-1), or None
            when no record carried a parse signal
        confidence_level: Statistical confidence tier based on sample size
            - INSUFFICIENT: <10 samples
            - PRELIMINARY: 10-30 samples
            - MODERATE: 30-100 samples
            - HIGH: 100+ samples
    """

    model_id: str
    sample_size: int
    mean_borda_score: float
    # #692 gate round 2: Optional, because a model whose records carry no
    # measured latency has an UNKNOWN p50, not a p50 of zero — and a zero here
    # reads as "answered instantly" to the tier-budget decisions downstream.
    # Same for a parse-success rate computed over no parse signal at all,
    # which used to default to a confident 1.0. `mean_cost_usd` was already
    # Optional for exactly this reason; these three now match it.
    # No defaults: these precede `confidence_level`, which has none, and an
    # explicit value at every construction site is the point anyway — a
    # silently-defaulted unknown is how the zero got there in the first place.
    p50_latency_ms: Optional[int]
    p95_latency_ms: Optional[int]
    parse_success_rate: Optional[float]
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
