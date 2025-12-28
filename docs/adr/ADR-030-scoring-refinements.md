# ADR-030: Scoring Refinements

**Status:** ACCEPTED (Revised per Council Review 2025-12-24)
**Date:** 2025-12-24
**Decision Makers:** Engineering, Architecture
**Extends:** ADR-026 (Dynamic Model Intelligence)
**Council Review:** Reasoning tier (gpt-5.2-pro, claude-opus-4.5, gemini-3-pro-preview, grok-4.1-fast)

---

## Context

The current scoring implementation (ADR-026 Phase 1) has limitations identified during council review:

1. **Linear cost scoring** fails for exponential price differences
2. **Quality tier floors** need benchmark evidence
3. **No circuit breaker** for failing models

---

## Decision

### 1. Log-Ratio Cost Scoring (Council-Revised Formula)

**Council Feedback:** `log(price + 1)` is effectively linear for small values (< 0.1).

**Problem Analysis:**
```python
# Original formula behavior for typical API prices:
log(0.001 + 1) = 0.000999...  # Nearly linear
log(0.01 + 1)  = 0.00995...   # Still linear
log(0.1 + 1)   = 0.0953...    # Starting to curve
```

**Solution: Log-Ratio Normalization**

```python
import math

def get_cost_score(price: float, reference_high: float = 0.015) -> float:
    """
    Log-ratio scoring for exponential pricing differences.

    Uses log(price/reference) which properly handles small values.
    Council-recommended formula.

    Args:
        price: Cost per 1K tokens
        reference_high: Reference "expensive" price (high-tier average)

    Returns:
        Score between 0.0 (expensive) and 1.0 (cheap/free)
    """
    if price <= 0:
        return 1.0  # Free models get perfect cost score

    if reference_high <= 0:
        return 0.5  # Invalid reference, neutral score

    # Minimum price floor to avoid log(0)
    MIN_PRICE = 0.0001  # $0.0001 per 1K tokens
    effective_price = max(price, MIN_PRICE)

    # Log-ratio: how many orders of magnitude from reference?
    # log(price/ref) = log(price) - log(ref)
    # Normalized to [0, 1] where cheaper = higher score
    log_ratio = math.log10(effective_price / reference_high)

    # Map log ratio to score:
    # - price == reference_high → log_ratio = 0 → score = 0.5
    # - price == reference_high / 10 → log_ratio = -1 → score = 0.75
    # - price == reference_high * 10 → log_ratio = 1 → score = 0.25
    score = 0.5 - (log_ratio * 0.25)

    return max(0.0, min(1.0, score))


# Alternative: Exponential decay (also council-approved)
def get_cost_score_exponential(price: float, reference_high: float = 0.015) -> float:
    """
    Exponential decay scoring.

    score = exp(-price / reference_high)
    Simpler formula, natural decay curve.
    """
    if price <= 0:
        return 1.0

    decay_rate = 1.0 / reference_high
    score = math.exp(-price * decay_rate)

    return max(0.0, min(1.0, score))
```

**Comparison Table (reference_high = $0.015):**

| Price | Linear | log(price+1) | Log-Ratio | Exp Decay |
|-------|--------|--------------|-----------|-----------|
| $0.000 | 1.00 | 1.00 | 1.00 | 1.00 |
| $0.001 | 0.93 | 0.96 | 0.79 | 0.94 |
| $0.003 | 0.80 | 0.87 | 0.68 | 0.82 |
| $0.015 | 0.00 | 0.52 | 0.50 | 0.37 |
| $0.030 | -1.00* | 0.32 | 0.43 | 0.14 |
| $0.150 | -9.00* | 0.00 | 0.25 | 0.00 |

*Linear formula breaks for prices > reference

**Rationale:** Log-ratio properly reflects that the difference between $0.001 and $0.003 (3x) is as significant as between $0.010 and $0.030 (3x).

### 2. Quality Tier Scores with Benchmark Evidence (Council Requirement)

**Council Feedback:** Quality tier floors must be justified with benchmark data.

```python
# Updated with benchmark citations
QUALITY_TIER_SCORES = {
    # FRONTIER: Top-tier models (GPT-4o, Claude Opus 4, Gemini Ultra)
    # Benchmark: MMLU 87-90%, HumanEval 90%+
    QualityTier.FRONTIER: 0.95,

    # STANDARD: Strong models (GPT-4o-mini, Claude Sonnet 3.5, Gemini Pro)
    # Benchmark: MMLU 80-86%, HumanEval 85-90%
    # Justification: GPT-4o-mini matches GPT-4 (2023) on most tasks
    QualityTier.STANDARD: 0.85,  # +0.10 from original 0.75

    # ECONOMY: Cost-optimized (GPT-3.5-turbo, Claude Haiku, Gemini Flash)
    # Benchmark: MMLU 70-79%, HumanEval 70-85%
    # Justification: Flash models now rival previous-gen standards
    QualityTier.ECONOMY: 0.70,   # +0.15 from original 0.55

    # LOCAL: Self-hosted models (Llama, Mistral, Qwen)
    # Benchmark: Varies widely (MMLU 55-80%, HumanEval 40-80%)
    # Justification: Upper bound LOCAL models match ECONOMY
    QualityTier.LOCAL: 0.50,     # +0.10 from original 0.40
}

# Benchmark sources (per Council requirement)
QUALITY_TIER_BENCHMARK_SOURCES = {
    QualityTier.FRONTIER: [
        "https://openai.com/index/gpt-4o-system-card",
        "https://www.anthropic.com/news/claude-3-5-sonnet",
        "https://deepmind.google/technologies/gemini/ultra/",
    ],
    QualityTier.STANDARD: [
        "https://openai.com/index/gpt-4o-mini-advancing-cost-efficient-intelligence/",
        "https://www.anthropic.com/news/claude-3-haiku",
    ],
    QualityTier.ECONOMY: [
        "https://openai.com/blog/chatgpt-turbo",
        "https://deepmind.google/technologies/gemini/flash/",
    ],
    QualityTier.LOCAL: [
        "https://huggingface.co/spaces/HuggingFaceH4/open_llm_leaderboard",
    ],
}
```

### 3. Circuit Breaker with State Machine (Council-Revised)

**Council Feedback:**
- Lower threshold from 50% to 20-30%
- Add minimum request count before tripping
- Implement proper Closed → Open → Half-Open pattern

```python
from enum import Enum, auto
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Deque
from collections import deque
import threading


class CircuitState(Enum):
    """Standard circuit breaker states."""
    CLOSED = auto()      # Normal operation, tracking failures
    OPEN = auto()        # Tripped, rejecting requests
    HALF_OPEN = auto()   # Testing recovery, limited requests


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""
    failure_threshold: float = 0.25      # 25% failure rate (Council: 20-30%)
    min_requests: int = 5                # Minimum requests before evaluation
    window_seconds: int = 600            # 10 minute sliding window
    cooldown_seconds: int = 1800         # 30 minute cooldown when OPEN
    half_open_max_requests: int = 3      # Probes before closing
    half_open_success_threshold: float = 0.67  # 2/3 success to close


@dataclass
class CircuitBreaker:
    """
    Per-model circuit breaker with proper state machine.

    Implements standard pattern:
    - CLOSED: Normal operation, counts failures in sliding window
    - OPEN: Rejects all requests, waits for cooldown
    - HALF-OPEN: Allows limited probes, closes on success or reopens on failure
    """
    model_id: str
    config: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    state: CircuitState = CircuitState.CLOSED

    # Sliding window for CLOSED state
    _request_times: Deque[tuple[datetime, bool]] = field(
        default_factory=lambda: deque(maxlen=1000)
    )

    # Half-open tracking
    _half_open_requests: int = 0
    _half_open_successes: int = 0

    # State transition timestamps
    _opened_at: Optional[datetime] = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def is_available(self) -> tuple[bool, Optional[str]]:
        """
        Check if model is available for selection.

        Returns:
            (is_available, reason_if_unavailable)
        """
        with self._lock:
            now = datetime.utcnow()

            if self.state == CircuitState.CLOSED:
                return (True, None)

            if self.state == CircuitState.OPEN:
                # Check if cooldown has elapsed
                if self._opened_at and now >= self._opened_at + timedelta(
                    seconds=self.config.cooldown_seconds
                ):
                    self._transition_to_half_open()
                    return (True, None)  # Allow probe request

                remaining = (
                    self._opened_at + timedelta(seconds=self.config.cooldown_seconds) - now
                ).seconds if self._opened_at else 0

                return (False, f"circuit_open (cooldown: {remaining}s)")

            if self.state == CircuitState.HALF_OPEN:
                if self._half_open_requests < self.config.half_open_max_requests:
                    return (True, None)  # Allow probe
                return (False, "circuit_half_open (probes exhausted)")

            return (True, None)  # Default: available

    def record_result(self, success: bool) -> None:
        """Record request outcome and evaluate state transitions."""
        with self._lock:
            now = datetime.utcnow()

            if self.state == CircuitState.CLOSED:
                self._request_times.append((now, success))
                self._prune_old_requests(now)
                self._evaluate_closed_state()

            elif self.state == CircuitState.HALF_OPEN:
                self._half_open_requests += 1
                if success:
                    self._half_open_successes += 1
                self._evaluate_half_open_state()

    def _prune_old_requests(self, now: datetime) -> None:
        """Remove requests outside the sliding window."""
        cutoff = now - timedelta(seconds=self.config.window_seconds)
        while self._request_times and self._request_times[0][0] < cutoff:
            self._request_times.popleft()

    def _evaluate_closed_state(self) -> None:
        """Check if circuit should trip to OPEN."""
        total = len(self._request_times)

        if total < self.config.min_requests:
            return  # Not enough data to evaluate

        failures = sum(1 for _, success in self._request_times if not success)
        failure_rate = failures / total

        if failure_rate >= self.config.failure_threshold:
            self._transition_to_open(failure_rate)

    def _evaluate_half_open_state(self) -> None:
        """Check if circuit should close or reopen."""
        if self._half_open_requests >= self.config.half_open_max_requests:
            success_rate = self._half_open_successes / self._half_open_requests

            if success_rate >= self.config.half_open_success_threshold:
                self._transition_to_closed()
            else:
                self._transition_to_open(1.0 - success_rate)

    def _transition_to_open(self, failure_rate: float) -> None:
        """Trip the circuit breaker."""
        self.state = CircuitState.OPEN
        self._opened_at = datetime.utcnow()
        self._half_open_requests = 0
        self._half_open_successes = 0

        # Emit metric
        _emit_circuit_event("circuit_opened", self.model_id, failure_rate)

    def _transition_to_half_open(self) -> None:
        """Enter half-open state for recovery testing."""
        self.state = CircuitState.HALF_OPEN
        self._half_open_requests = 0
        self._half_open_successes = 0

        _emit_circuit_event("circuit_half_open", self.model_id, None)

    def _transition_to_closed(self) -> None:
        """Close the circuit (recovery complete)."""
        self.state = CircuitState.CLOSED
        self._request_times.clear()
        self._opened_at = None

        _emit_circuit_event("circuit_closed", self.model_id, None)


# Global circuit breaker registry
_circuit_breakers: dict[str, CircuitBreaker] = {}
_registry_lock = threading.Lock()


def get_circuit_breaker(model_id: str) -> CircuitBreaker:
    """Get or create circuit breaker for model."""
    with _registry_lock:
        if model_id not in _circuit_breakers:
            _circuit_breakers[model_id] = CircuitBreaker(model_id=model_id)
        return _circuit_breakers[model_id]


def check_circuit_breaker(model_id: str) -> tuple[bool, Optional[str]]:
    """
    Check if model is available (circuit not open).

    Returns:
        (is_available, unavailable_reason)
    """
    breaker = get_circuit_breaker(model_id)
    return breaker.is_available()


def _emit_circuit_event(event: str, model_id: str, failure_rate: Optional[float]) -> None:
    """Emit observability event for circuit state change."""
    import logging
    logger = logging.getLogger(__name__)

    logger.warning(
        f"Circuit breaker: {event}",
        extra={
            "event": event,
            "model_id": model_id,
            "failure_rate": failure_rate,
        }
    )
    # Metrics export: emit_layer_event() automatically notifies subscribed
    # MetricsAdapters (see observability/metrics_adapter.py)
```

### Configuration

```yaml
council:
  model_intelligence:
    scoring:
      # Cost scoring algorithm
      cost_scale: log_ratio           # 'linear', 'log_ratio', or 'exponential'
      cost_reference_high: 0.015      # Reference expensive price

      # Quality tier scores (with benchmark justification)
      quality_tier_scores:
        frontier: 0.95    # MMLU 87-90%
        standard: 0.85    # MMLU 80-86%
        economy: 0.70     # MMLU 70-79%
        local: 0.50       # MMLU 55-80%

    circuit_breaker:
      enabled: true
      failure_threshold: 0.25         # 25% (Council: 20-30%)
      min_requests: 5                 # Minimum before evaluation
      window_seconds: 600             # 10 minute window
      cooldown_seconds: 1800          # 30 minute cooldown
      half_open_max_requests: 3       # Probes before closing
      half_open_success_threshold: 0.67
```

### Environment Variables

| Variable | Type | Default | Purpose |
|----------|------|---------|---------|
| `LLM_COUNCIL_COST_SCALE` | str | log_ratio | Cost scoring algorithm |
| `LLM_COUNCIL_CIRCUIT_BREAKER` | bool | true | Enable circuit breaker |
| `LLM_COUNCIL_CIRCUIT_THRESHOLD` | float | 0.25 | Failure rate threshold |
| `LLM_COUNCIL_CIRCUIT_MIN_REQUESTS` | int | 5 | Min requests before trip |

---

## Observability (Council Requirement)

```python
# Metrics to emit
scoring.cost_score{model_id, algorithm}
scoring.quality_score{model_id, tier}
circuit.state_change{model_id, from_state, to_state, failure_rate}
circuit.request_blocked{model_id, state, cooldown_remaining}
circuit.probe_result{model_id, success}

# Structured logging
{
    "event": "circuit_state_change",
    "model_id": "openai/gpt-4o",
    "from_state": "CLOSED",
    "to_state": "OPEN",
    "failure_rate": 0.28,
    "requests_in_window": 25,
    "cooldown_seconds": 1800
}
```

---

## Consequences

### Positive
- Log-ratio accurately reflects order-of-magnitude price differences
- Quality scores backed by benchmark evidence
- Circuit breaker prevents cascading failures
- Proper state machine enables safe recovery testing
- Min-requests prevents false-positive tripping

### Negative
- Log-ratio less intuitive than linear
- Quality benchmarks may become stale
- Circuit breaker adds latency (lock contention)
- Half-open probes may fail on unlucky requests

### Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Log scoring edge cases | MIN_PRICE floor, clamp to [0, 1] |
| Circuit breaker too sensitive | min_requests requirement, configurable threshold |
| Stale quality benchmarks | Document sources, quarterly review |
| Half-open probe bias | Multiple probes (3), high success threshold (67%) |

---

## Testing Strategy

```python
class TestScoringRefinements:
    def test_log_ratio_cost_scoring(self):
        """Log-ratio properly handles order-of-magnitude differences."""
        assert get_cost_score(0.001, 0.015) > get_cost_score(0.003, 0.015)
        assert get_cost_score(0.015, 0.015) == pytest.approx(0.5, abs=0.01)

    def test_cost_score_free_models(self):
        """Free models get perfect cost score."""
        assert get_cost_score(0.0, 0.015) == 1.0

    def test_circuit_breaker_min_requests(self):
        """Circuit doesn't trip below min_requests."""
        breaker = CircuitBreaker(model_id="test")
        for _ in range(4):  # Below min_requests=5
            breaker.record_result(False)
        assert breaker.state == CircuitState.CLOSED

    def test_circuit_breaker_trips_at_threshold(self):
        """Circuit trips at failure threshold."""
        breaker = CircuitBreaker(model_id="test")
        for _ in range(3):
            breaker.record_result(True)
        for _ in range(2):
            breaker.record_result(False)  # 2/5 = 40% > 25%
        assert breaker.state == CircuitState.OPEN

    def test_circuit_breaker_half_open_recovery(self):
        """Half-open state allows recovery."""
        breaker = CircuitBreaker(model_id="test")
        breaker._transition_to_open(0.5)
        breaker._transition_to_half_open()

        for _ in range(3):
            breaker.record_result(True)  # 3/3 = 100% > 67%

        assert breaker.state == CircuitState.CLOSED

    def test_circuit_breaker_half_open_reopen(self):
        """Half-open reopens on continued failures."""
        breaker = CircuitBreaker(model_id="test")
        breaker._transition_to_half_open()

        breaker.record_result(True)
        breaker.record_result(False)
        breaker.record_result(False)  # 1/3 = 33% < 67%

        assert breaker.state == CircuitState.OPEN
```

---

## Implementation Plan

1. [x] Implement log-ratio cost scoring function (Issue #138)
2. [x] Update QUALITY_TIER_SCORES with benchmark sources (Issue #139)
3. [x] Implement CircuitBreaker class with state machine (Issue #140)
4. [x] Add circuit breaker registry (per-model) (Issue #141)
5. [x] Integrate circuit breaker with selection pipeline (Issue #142)
6. [x] Add metrics and structured logging (L4_CIRCUIT_BREAKER_OPEN/CLOSE events)
7. [x] Make all parameters configurable via YAML (ScoringConfig, CircuitBreakerConfig)
8. [x] Add comprehensive tests (126 new tests across 4 test files)

---

## References

- [ADR-026: Dynamic Model Intelligence](./ADR-026-dynamic-model-intelligence.md)
- [Circuit Breaker Pattern (Martin Fowler)](https://martinfowler.com/bliki/CircuitBreaker.html)
- [Microsoft Circuit Breaker Best Practices](https://docs.microsoft.com/en-us/azure/architecture/patterns/circuit-breaker)
