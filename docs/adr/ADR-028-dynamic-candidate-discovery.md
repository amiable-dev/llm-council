# ADR-028: Dynamic Candidate Discovery

**Status:** ACCEPTED (Revised per Council Review 2025-12-24)
**Date:** 2025-12-24
**Decision Makers:** Engineering, Architecture
**Extends:** ADR-026 (Dynamic Model Intelligence)
**Implements:** GitHub Issue #109
**Council Review:** Reasoning tier (gpt-5.2-pro, claude-opus-4.5, gemini-3-pro-preview, grok-4.1-fast)

---

## Context

ADR-026 implemented metadata-aware **scoring** but still uses static pools for candidate **discovery**.

### Current Implementation

```python
# ADR-026 Phase 1 (current)
static_pool = TIER_MODEL_POOLS.get(tier, ...)
candidates = _create_candidates_from_pool(static_pool, tier)
# Scoring uses real metadata, but candidates are static
```

**Problem:** Even with `model_intelligence.enabled=true`, the system uses static pools as candidates. New models require manual pool updates.

**Impact:** Defeats the core promise of "Dynamic Model Intelligence" - the system cannot autonomously adopt new models.

---

## Decision

Replace static pool lookup with provider-based discovery using a **background registry pattern**.

### Architecture: Registry → Filter → Score (Revised)

**Critical Council Feedback:** Discovery must NOT happen on the request path.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Dynamic Candidate Pipeline                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  CONTROL PLANE (Background)              DATA PLANE (Request Time)          │
│  ┌─────────────────────────┐            ┌──────────────────────────────┐   │
│  │     Background          │            │                              │   │
│  │     Discovery           │            │  ┌────────┐  ┌────────┐     │   │
│  │                         │            │  │Registry│─▶│ Filter │     │   │
│  │  - Cron (every 5 min)   │──update──▶ │  │ Read   │  │        │     │   │
│  │  - Provider API calls   │            │  └────────┘  └───┬────┘     │   │
│  │  - Stale-while-revalidate│           │                  │          │   │
│  └─────────────────────────┘            │                  ▼          │   │
│                                         │            ┌────────┐       │   │
│                                         │            │ Score  │       │   │
│                                         │            └────────┘       │   │
│                                         └──────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Model Registry Pattern (Council Requirement)

**Critical:** Discovery happens asynchronously. Request-time reads from cached registry.

```python
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

@dataclass
class RegistryEntry:
    """Cached model information with staleness tracking."""
    info: ModelInfo
    fetched_at: datetime
    is_deprecated: bool = False

@dataclass
class ModelRegistry:
    """
    Maintains constantly updated cache of available models.
    Updated via background task (Control Plane), read by Router (Data Plane).
    """
    _cache: Dict[str, RegistryEntry] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _last_refresh: Optional[datetime] = None
    _refresh_failures: int = 0

    async def refresh_registry(
        self,
        provider: MetadataProvider,
        max_retries: int = 3
    ) -> None:
        """
        Background refresh of model registry.
        Implements stale-while-revalidate pattern.
        """
        for attempt in range(max_retries):
            try:
                # Fetch full model list (avoid N+1)
                models = await provider.fetch_full_model_list()

                async with self._lock:
                    now = datetime.utcnow()
                    # Filter deprecated, store by ID for O(1) lookup
                    self._cache = {
                        m.id: RegistryEntry(info=m, fetched_at=now)
                        for m in models
                        if m.status != ModelStatus.DEPRECATED
                    }
                    self._last_refresh = now
                    self._refresh_failures = 0

                logger.info(f"Registry refreshed: {len(self._cache)} models")
                metrics.gauge("discovery.registry_size", len(self._cache))
                return

            except Exception as e:
                self._refresh_failures += 1
                logger.warning(
                    f"Discovery refresh failed (attempt {attempt + 1}/{max_retries}): {e}"
                )
                metrics.increment("discovery.refresh_failures")

                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff

        # All retries failed - keep stale cache (stale-while-revalidate)
        logger.error(
            f"Discovery refresh failed after {max_retries} attempts. "
            f"Serving stale registry ({len(self._cache)} models)."
        )
        metrics.increment("discovery.stale_serve")

    def get_candidates(self) -> List[ModelInfo]:
        """Read-only access to cached models. Safe for request path."""
        return [entry.info for entry in self._cache.values()]

    def get_model(self, model_id: str) -> Optional[ModelInfo]:
        """O(1) lookup by model ID."""
        entry = self._cache.get(model_id)
        return entry.info if entry else None

    @property
    def is_stale(self) -> bool:
        """Check if registry needs refresh."""
        if self._last_refresh is None:
            return True
        return datetime.utcnow() - self._last_refresh > timedelta(minutes=30)


# Singleton registry
_registry: Optional[ModelRegistry] = None

def get_registry() -> ModelRegistry:
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry
```

### Background Refresh Worker

```python
async def run_discovery_worker(
    registry: ModelRegistry,
    provider: MetadataProvider,
    interval_seconds: int = 300  # 5 minutes
) -> None:
    """
    Background worker that refreshes model registry periodically.
    Should be started at application startup.
    """
    logger.info(f"Starting discovery worker (interval: {interval_seconds}s)")

    while True:
        try:
            await registry.refresh_registry(provider)
        except Exception as e:
            logger.error(f"Discovery worker error: {e}")
            metrics.increment("discovery.worker_errors")

        await asyncio.sleep(interval_seconds)
```

### Request-Time Discovery (Reads from Registry)

```python
async def discover_tier_candidates(
    tier: str,
    registry: ModelRegistry,
    required_context: Optional[int] = None,
) -> List[ModelCandidate]:
    """
    Fast, in-memory filtering of pre-fetched candidates.
    NEVER calls external APIs - reads from cached registry.
    """
    candidates = []

    # 1. Filter from cached registry (O(n) in-memory, fast)
    all_models = registry.get_candidates()

    for info in all_models:
        if _model_qualifies_for_tier(info, tier, required_context):
            candidates.append(_create_candidate_from_info(info, tier))

    # 2. Static fallback (only if registry empty/insufficient)
    if len(candidates) < MIN_CANDIDATES_PER_TIER:
        logger.warning(
            f"Insufficient dynamic candidates for tier {tier}: "
            f"{len(candidates)} < {MIN_CANDIDATES_PER_TIER}. Using static fallback."
        )
        metrics.increment("discovery.fallback_triggered", tags={"tier": tier})

        static = _create_candidates_from_pool(TIER_MODEL_POOLS[tier], tier)
        candidates = _merge_deduplicate(dynamic=candidates, static=static)

    return candidates


def _merge_deduplicate(
    dynamic: List[ModelCandidate],
    static: List[ModelCandidate]
) -> List[ModelCandidate]:
    """
    Merge candidates with dynamic taking precedence.
    Dynamic has fresher metadata/pricing.
    """
    seen = {c.model_id for c in dynamic}
    merged = list(dynamic)

    for candidate in static:
        if candidate.model_id not in seen:
            merged.append(candidate)
            seen.add(candidate.model_id)

    return merged
```

### Tier Qualification Logic (Revised per Council)

```python
from enum import Enum, auto

class ModelStatus(Enum):
    AVAILABLE = auto()
    DEPRECATED = auto()
    PREVIEW = auto()
    BETA = auto()

def _model_qualifies_for_tier(
    info: ModelInfo,
    tier: str,
    required_context: Optional[int],
) -> bool:
    """
    Check if model meets tier requirements.
    Revised per Council feedback to address logic gaps.
    """
    # Universal Hard Constraints
    if required_context and info.context_window < required_context:
        return False

    if info.status == ModelStatus.DEPRECATED:
        return False

    # Tier-Specific Constraints
    if tier == "frontier":
        return info.quality_tier == QualityTier.FRONTIER

    elif tier == "reasoning":
        # Use normalized capability flag, not brittle string matching
        return (
            info.capabilities.reasoning  # Explicit flag
            or info.model_family in KNOWN_REASONING_FAMILIES  # e.g., {"o1", "o3", "deepseek-r1"}
        )

    elif tier == "high":
        return (
            info.quality_tier == QualityTier.FRONTIER
            and info.status == ModelStatus.AVAILABLE  # Excludes preview/beta
        )

    elif tier == "balanced":
        return (
            info.quality_tier in (QualityTier.STANDARD, QualityTier.FRONTIER)
            and info.cost_per_1k_tokens < 0.03  # Cost ceiling for balanced
        )

    elif tier == "quick":
        # FIXED: No longer returns True for all models
        # Must enforce speed or cost constraints
        return (
            info.median_latency_ms < 1500  # Fast response
            or info.cost_per_1k_tokens < 0.005  # Or very cheap
        )

    else:
        # Unknown tier - fail explicitly, don't silently return False
        raise ValueError(f"Unknown tier: {tier}")


# Known reasoning model families (avoid brittle string matching)
KNOWN_REASONING_FAMILIES = {
    "o1", "o3", "o1-mini", "o3-mini",
    "deepseek-r1", "deepseek-reasoner",
    "claude-3-opus",  # Strong reasoning capability
}
```

### Configuration

```yaml
council:
  model_intelligence:
    enabled: true

    discovery:
      enabled: true
      refresh_interval_seconds: 300  # 5 minutes
      min_candidates_per_tier: 3
      max_candidates_per_tier: 10

      # Stale-while-revalidate settings
      stale_threshold_minutes: 30
      max_refresh_retries: 3

      # Provider settings
      providers:
        openrouter:
          enabled: true
          rate_limit_rpm: 60
          timeout_seconds: 10
```

### Environment Variables

| Variable | Type | Default | Purpose |
|----------|------|---------|---------|
| `LLM_COUNCIL_DISCOVERY_ENABLED` | bool | true | Enable dynamic discovery |
| `LLM_COUNCIL_DISCOVERY_INTERVAL` | int | 300 | Refresh interval (seconds) |
| `LLM_COUNCIL_DISCOVERY_MIN_CANDIDATES` | int | 3 | Minimum candidates per tier |

---

## Observability (Council Requirement)

```python
# Metrics to emit
discovery.registry_size{provider}              # Gauge: models in registry
discovery.refresh_duration_ms{provider}        # Histogram: refresh latency
discovery.refresh_failures{provider}           # Counter: failed refreshes
discovery.stale_serve{provider}                # Counter: served stale data
discovery.fallback_triggered{tier}             # Counter: static fallback used
discovery.candidates_found{tier, source}       # Gauge: dynamic vs static

# Structured logging
{
    "event": "discovery_refresh_complete",
    "models_count": 127,
    "duration_ms": 450,
    "stale_before": false,
    "provider": "openrouter"
}
```

---

## Consequences

### Positive
- New models automatically discovered from OpenRouter API
- No manual pool updates required
- System adapts to model availability changes
- Graceful degradation to static pools
- **Zero request-time API calls** (registry pattern)

### Negative
- Dependency on external API for discovery
- Potential for unexpected model selection
- Need to validate discovery results
- Background worker adds operational complexity

### Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| API latency on request path | Background refresh, registry pattern |
| Provider API failures | Stale-while-revalidate, static fallback |
| N+1 API calls | Bulk fetch with `fetch_full_model_list()` |
| Silent exception masking | Explicit logging, metrics, alerts |
| Deprecated models selected | Filter by `ModelStatus.DEPRECATED` |
| Quick tier selects expensive models | Add latency/cost constraints |

---

## Alternatives Considered

| Alternative | Rejected Because |
|-------------|------------------|
| Synchronous discovery per request | Unacceptable latency (100-500ms per provider) |
| Periodic batch sync to database | Over-engineered for current scale |
| Static pools only | Defeats dynamic intelligence goal |
| Percentile-based cost normalization | More complex, less intuitive than constraints |

---

## Implementation Plan

1. [x] Implement `ModelRegistry` class with async lock (Phase 1, Issue #120)
2. [x] Add `run_discovery_worker()` background task (Phase 2, Issue #121)
3. [x] Integrate with application startup (Phase 6, Issue #125)
4. [x] Revise `_model_qualifies_for_tier()` with council fixes (Phase 3, Issue #122)
5. [x] Add metrics and structured logging (Phase 7, Issue #126)
6. [x] Add integration tests with mock registry (Phases 1-7)
7. [x] Add health check endpoint for registry status (Phase 7, Issue #126)

---

## Testing Strategy

```python
class TestDynamicDiscovery:
    async def test_registry_refresh_success(self):
        """Background refresh populates registry."""

    async def test_registry_stale_while_revalidate(self):
        """Failed refresh serves stale data."""

    async def test_discovery_reads_from_registry(self):
        """Request-time discovery never calls API."""

    async def test_tier_qualification_quick_has_constraints(self):
        """Quick tier rejects slow/expensive models."""

    async def test_tier_qualification_rejects_deprecated(self):
        """All tiers reject deprecated models."""

    async def test_fallback_when_registry_empty(self):
        """Static fallback used when registry empty."""

    async def test_merge_deduplicates(self):
        """Dynamic candidates take precedence over static."""
```

---

## References

- [ADR-026: Dynamic Model Intelligence](./ADR-026-dynamic-model-intelligence.md)
- [GitHub Issue #109](https://github.com/amiable-dev/llm-council/issues/109)
- [OpenRouter Models API](https://openrouter.ai/docs/api/reference/models)
