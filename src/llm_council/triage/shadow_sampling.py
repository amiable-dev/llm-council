"""Shadow Council Sampling for ADR-020 Tier 1.

Implements shadow sampling that randomly samples fast-path queries through
the full council to measure "regret rate" and detect routing drift.

Per ADR-020 Council Recommendation:
- Audit: 5% shadow council sampling
- Rollback trigger: shadow_council_disagreement_rate > 8%
"""

import hashlib
import json
import os
import random
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional
import re


@dataclass
class ShadowSamplingConfig:
    """Configuration for shadow sampling.

    Attributes:
        enabled: Whether shadow sampling is enabled
        sampling_rate: Fraction of fast-path queries to sample (default: 0.05 = 5%)
        disagreement_threshold: Rate that triggers rollback (default: 0.08 = 8%)
        window_size: Rolling window for rate calculation (default: 100)
        deterministic_seed: Optional seed for deterministic sampling (testing)
    """

    enabled: bool = True
    sampling_rate: float = 0.05
    disagreement_threshold: float = 0.08
    window_size: int = 100
    deterministic_seed: Optional[int] = None
    agreement_threshold: float = 0.9  # Score below this is disagreement

    def __post_init__(self):
        """Validate configuration."""
        if not 0 <= self.sampling_rate <= 1:
            raise ValueError(f"Sampling rate must be between 0 and 1, got {self.sampling_rate}")
        if not 0 <= self.disagreement_threshold <= 1:
            raise ValueError(
                f"Disagreement threshold must be between 0 and 1, "
                f"got {self.disagreement_threshold}"
            )

    @classmethod
    def from_env(cls) -> "ShadowSamplingConfig":
        """Create config from environment variables."""
        rate_str = os.environ.get("LLM_COUNCIL_SHADOW_SAMPLING_RATE", "0.05")
        threshold_str = os.environ.get("LLM_COUNCIL_SHADOW_DISAGREEMENT_THRESHOLD", "0.08")
        window_str = os.environ.get("LLM_COUNCIL_SHADOW_WINDOW_SIZE", "100")

        return cls(
            sampling_rate=float(rate_str),
            disagreement_threshold=float(threshold_str),
            window_size=int(window_str),
        )


@dataclass
class ShadowSampleResult:
    """Result of a shadow sampling comparison.

    Attributes:
        query_hash: Hash of the query for grouping
        fast_path_model: Model used for fast path
        fast_path_response: Fast path response content
        council_consensus: Council's synthesized answer
        agreement_score: Semantic similarity score (0-1)
        timestamp: Unix timestamp of the sample
    """

    query_hash: str
    fast_path_model: str
    fast_path_response: str
    council_consensus: str
    agreement_score: float
    timestamp: float

    @property
    def is_agreement(self) -> bool:
        """Check if fast path agreed with council."""
        return self.agreement_score >= 0.9

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for persistence."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ShadowSampleResult":
        """Create from dictionary."""
        return cls(**data)


class ShadowSampler:
    """Sampler that selects queries for shadow council comparison.

    Uses random sampling with configurable rate to select which
    fast-path queries should also be run through the full council.
    """

    def __init__(self, config: Optional[ShadowSamplingConfig] = None):
        """Initialize sampler.

        Args:
            config: Sampling configuration (default: from env)
        """
        self.config = config or ShadowSamplingConfig.from_env()

        # Set up random generator
        if self.config.deterministic_seed is not None:
            self._rng = random.Random(self.config.deterministic_seed)
        else:
            self._rng = random.Random()

    def should_sample(self) -> bool:
        """Check if this request should be shadow sampled.

        Returns:
            True if request should be sampled
        """
        return self._rng.random() < self.config.sampling_rate

    def should_sample_query(self, query: str) -> bool:
        """Deterministically decide if query should be sampled.

        Uses query hash for consistent sampling of same query.

        Args:
            query: The query string

        Returns:
            True if query should be sampled
        """
        # Hash the query for deterministic sampling
        query_hash = hashlib.sha256(query.encode()).hexdigest()
        # Use first 8 chars as hex number, convert to 0-1 range
        hash_value = int(query_hash[:8], 16) / 0xFFFFFFFF

        return hash_value < self.config.sampling_rate


class DisagreementDetector:
    """Detector for measuring agreement between fast path and council.

    Uses text similarity to determine if fast path response
    agrees with council consensus.
    """

    def __init__(self, agreement_threshold: float = 0.9):
        """Initialize detector.

        Args:
            agreement_threshold: Score above which is agreement
        """
        self.agreement_threshold = agreement_threshold

    def compute_agreement(self, response_a: str, response_b: str) -> float:
        """Compute agreement score between two responses.

        Uses normalized text similarity as a proxy for semantic agreement.

        Args:
            response_a: First response
            response_b: Second response

        Returns:
            Agreement score between 0 and 1
        """
        # Normalize both responses
        norm_a = self._normalize(response_a)
        norm_b = self._normalize(response_b)

        # Exact match
        if norm_a == norm_b:
            return 1.0

        # Use Jaccard similarity on words
        words_a = set(norm_a.split())
        words_b = set(norm_b.split())

        if not words_a or not words_b:
            return 0.0

        intersection = words_a & words_b
        union = words_a | words_b

        jaccard = len(intersection) / len(union)

        # Also consider word order with n-gram overlap
        ngram_score = self._ngram_overlap(norm_a, norm_b, n=3)

        # Weighted combination
        return 0.6 * jaccard + 0.4 * ngram_score

    def _normalize(self, text: str) -> str:
        """Normalize text for comparison."""
        # Lowercase
        text = text.lower()
        # Remove extra whitespace
        text = " ".join(text.split())
        # Remove punctuation
        text = re.sub(r"[^\w\s]", "", text)
        return text

    def _ngram_overlap(self, text_a: str, text_b: str, n: int = 3) -> float:
        """Compute n-gram overlap between texts."""

        def get_ngrams(text: str, n: int) -> set:
            words = text.split()
            if len(words) < n:
                return {tuple(words)}
            return {tuple(words[i : i + n]) for i in range(len(words) - n + 1)}

        ngrams_a = get_ngrams(text_a, n)
        ngrams_b = get_ngrams(text_b, n)

        if not ngrams_a or not ngrams_b:
            return 0.0

        intersection = ngrams_a & ngrams_b
        union = ngrams_a | ngrams_b

        return len(intersection) / len(union) if union else 0.0

    def is_agreement(self, response_a: str, response_b: str) -> bool:
        """Check if responses agree.

        Args:
            response_a: First response
            response_b: Second response

        Returns:
            True if responses agree (score >= threshold)
        """
        score = self.compute_agreement(response_a, response_b)
        return score >= self.agreement_threshold


class ShadowMetricStore:
    """Store for shadow sampling metrics.

    Persists shadow sampling results and calculates disagreement rates
    over a rolling window.
    """

    def __init__(
        self,
        config: Optional[ShadowSamplingConfig] = None,
        store_path: Optional[str] = None,
    ):
        """Initialize store.

        Args:
            config: Sampling configuration
            store_path: Path to JSONL file for persistence
        """
        self.config = config or ShadowSamplingConfig.from_env()

        if store_path is None:
            store_dir = Path.home() / ".llm-council"
            store_dir.mkdir(parents=True, exist_ok=True)
            store_path = str(store_dir / "shadow_metrics.jsonl")

        self.store_path = store_path
        self._results: List[ShadowSampleResult] = []

        # Load existing results
        self._load()

    def _load(self) -> None:
        """Load results from persistent store."""
        if not os.path.exists(self.store_path):
            return

        try:
            with open(self.store_path, "r") as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        self._results.append(ShadowSampleResult.from_dict(data))

            # Keep only window_size most recent
            self._results = self._results[-self.config.window_size :]
        except (json.JSONDecodeError, IOError):
            # Start fresh on error
            self._results = []

    def _save_result(self, result: ShadowSampleResult) -> None:
        """Append result to persistent store."""
        try:
            with open(self.store_path, "a") as f:
                f.write(json.dumps(result.to_dict()) + "\n")
        except IOError:
            pass  # Best effort persistence

    def record(self, result: ShadowSampleResult) -> None:
        """Record a shadow sampling result.

        Args:
            result: Shadow sample result to record
        """
        self._results.append(result)

        # Maintain rolling window
        if len(self._results) > self.config.window_size:
            self._results = self._results[-self.config.window_size :]

        # Persist
        self._save_result(result)

    def get_recent_results(self) -> List[ShadowSampleResult]:
        """Get recent results within window.

        Returns:
            List of recent ShadowSampleResults
        """
        return list(self._results)

    def get_disagreement_rate(self) -> float:
        """Calculate disagreement rate over rolling window.

        Returns:
            Disagreement rate (0-1)
        """
        if not self._results:
            return 0.0

        disagreements = sum(1 for r in self._results if not r.is_agreement)
        return disagreements / len(self._results)

    def is_threshold_breached(self) -> bool:
        """Check if disagreement rate exceeds threshold.

        Returns:
            True if rollback should be triggered
        """
        return self.get_disagreement_rate() > self.config.disagreement_threshold


async def run_shadow_sample(
    query: str,
    fast_path_result: Any,
    tier_contract: Optional[Any] = None,
) -> Optional[ShadowSampleResult]:
    """Run shadow sampling for a fast-path query.

    Executes full council deliberation and compares with fast path result.

    Args:
        query: The user query
        fast_path_result: Result from fast path routing
        tier_contract: Optional tier contract

    Returns:
        ShadowSampleResult with comparison, or None on error
    """
    from llm_council.council import run_full_council

    try:
        # Run full council
        council_result = await run_full_council(query)

        # Extract council consensus
        council_consensus = council_result.get("stage3", {}).get("content", "")

        # Compute agreement
        detector = DisagreementDetector()
        agreement_score = detector.compute_agreement(
            fast_path_result.response or "",
            council_consensus,
        )

        # Create result
        query_hash = hashlib.sha256(query.encode()).hexdigest()[:16]
        return ShadowSampleResult(
            query_hash=query_hash,
            fast_path_model=fast_path_result.model or "unknown",
            fast_path_response=fast_path_result.response or "",
            council_consensus=council_consensus,
            agreement_score=agreement_score,
            timestamp=time.time(),
        )

    except Exception:
        return None


# Global instances
_shadow_sampler: Optional[ShadowSampler] = None
_shadow_store: Optional[ShadowMetricStore] = None


def get_shadow_sampler() -> ShadowSampler:
    """Get global shadow sampler instance."""
    global _shadow_sampler
    if _shadow_sampler is None:
        _shadow_sampler = ShadowSampler()
    return _shadow_sampler


def get_shadow_store() -> ShadowMetricStore:
    """Get global shadow metric store instance."""
    global _shadow_store
    if _shadow_store is None:
        _shadow_store = ShadowMetricStore()
    return _shadow_store
