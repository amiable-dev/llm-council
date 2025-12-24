# ADR-026: Dynamic Model Intelligence and Benchmark-Driven Selection

**Status:** APPROVED (Blocking Conditions Implemented)
**Date:** 2025-12-23
**Decision Makers:** Engineering, Architecture
**Council Review:** 2025-12-23 (Strategic + Technical Reviews)
**Layer Assignment:** Cross-cutting (L1-L4 integration)
**Implementation:** 2025-12-23 (Blocking Conditions 1-3)

---

## ⚠️ CRITICAL: Strategic Council Review - Vendor Dependency Risk

### Verdict: CONDITIONAL APPROVAL

**ADR-026 is NOT APPROVED in its current form.** The council identified critical vendor dependency risks that must be addressed before implementation.

> "We cannot build the core 'brain' of an open-source project on proprietary APIs that we do not control." — Council Consensus

### The "Sovereign Orchestrator" Philosophy

The council unanimously adopts this architectural principle:

> **The open-source version of LLM Council must function as a complete, independent utility. External services (like OpenRouter or Not Diamond) must be treated as PLUGINS, not foundations.**
>
> If the internet is disconnected or if an API key is revoked, the software must still boot, run, and perform its core function (orchestrating LLMs), even if quality is degraded.

### Blocking Conditions for Approval

| # | Condition | Status | Priority |
|---|-----------|--------|----------|
| 1 | **Add `ModelMetadataProvider` abstraction interface** | ✅ COMPLETED | **BLOCKING** |
| 2 | **Implement `StaticRegistryProvider` (30+ models)** | ✅ COMPLETED (31 models) | **BLOCKING** |
| 3 | **Add offline mode (`LLM_COUNCIL_OFFLINE=true`)** | ✅ COMPLETED | **BLOCKING** |
| 4 | **Evaluate LiteLLM as unified abstraction** | ✅ COMPLETED (as fallback) | High |
| 5 | Document degraded vs. enhanced feature matrix | 📋 Required | Medium |

### Implementation Notes (2025-12-23)

The blocking conditions were implemented using TDD (Test-Driven Development) with 86 passing tests.

**Module Structure:** `src/llm_council/metadata/`

| File | Purpose |
|------|---------|
| `types.py` | `ModelInfo` frozen dataclass, `QualityTier` enum, `Modality` enum |
| `protocol.py` | `MetadataProvider` `@runtime_checkable` Protocol |
| `static_registry.py` | `StaticRegistryProvider` with YAML + LiteLLM fallback |
| `litellm_adapter.py` | Lazy LiteLLM import for metadata extraction |
| `offline.py` | `is_offline_mode()` and `check_offline_mode_startup()` |
| `__init__.py` | `get_provider()` singleton factory, module exports |

**Bundled Registry:** `src/llm_council/models/registry.yaml`

31 models from 8 providers:
- OpenAI (7): gpt-4o, gpt-4o-mini, gpt-5.2-pro, o1, o1-preview, o1-mini, o3-mini
- Anthropic (5): claude-opus-4.5, claude-3-5-sonnet, claude-3-5-haiku, claude-3-opus, claude-3-sonnet
- Google (5): gemini-3-pro-preview, gemini-2.5-pro, gemini-2.0-flash, gemini-1.5-pro, gemini-1.5-flash
- xAI (2): grok-4, grok-4.1-fast
- DeepSeek (2): deepseek-r1, deepseek-chat
- Meta (2): llama-3.3-70b, llama-3.1-405b
- Mistral (2): mistral-large-2411, mistral-medium
- Ollama (6): llama3.2, mistral, qwen2.5:14b, codellama, phi3, deepseek-r1:8b

**LiteLLM Integration:** Used as fallback in the priority chain (local registry > LiteLLM > 4096 default). Lazy import prevents startup failures when LiteLLM is not installed.

**GitHub Issues:** #89-#92 (all completed)

### Strategic Decision: Option C+D (Hybrid + Abstraction)

| Feature | OSS (Self-Hosted) | Council Cloud (Commercial) |
|---------|-------------------|---------------------------|
| **Model Metadata** | Static library (LiteLLM) + Manual YAML config | Real-time dynamic sync via OpenRouter |
| **Routing** | Heuristic rules (latency/cost-based) | Intelligent ML-based (Not Diamond) |
| **Integrations** | BYOK (Bring Your Own Keys) | Managed Fleet (one bill, instant access) |
| **Operations** | `localhost` / Individual instance | Team governance, analytics, SSO |

### Vendor Dependency Analysis

| Service | Current Role | Risk Level | Required Mitigation |
|---------|--------------|------------|---------------------|
| **OpenRouter** | Metadata API, Gateway | HIGH | Static fallback + LiteLLM |
| **Not Diamond** | Model routing, Classification | MEDIUM | Heuristic fallback (exists) |
| **Requesty** | Alternative gateway | LOW | Already optional |

### Affiliate/Reseller Model: NOT VIABLE

> "Reliance on affiliate revenue or tight coupling creates **Platform Risk**. If OpenRouter releases 'OpenRouter Agents,' Council becomes obsolete instantly. Furthermore, council-cloud cannot withstand margin compression." — Council

**Decision:** Use external services to lower the *User's* barrier to entry, not as the backbone of the *Product's* value.

---

## Required Abstraction Architecture

### MetadataProvider Interface (MANDATORY)

```python
from typing import Protocol, Optional, Dict, List
from dataclasses import dataclass

@dataclass
class ModelInfo:
    id: str
    context_window: int
    pricing: Dict[str, float]  # {"prompt": 0.01, "completion": 0.03}
    supported_parameters: List[str]
    modalities: List[str]
    quality_tier: str  # "frontier" | "standard" | "economy"

class MetadataProvider(Protocol):
    """Abstract interface for model metadata sources."""

    def get_model_info(self, model_id: str) -> Optional[ModelInfo]: ...
    def get_context_window(self, model_id: str) -> int: ...
    def get_pricing(self, model_id: str) -> Dict[str, float]: ...
    def supports_reasoning(self, model_id: str) -> bool: ...
    def list_available_models(self) -> List[str]: ...

class StaticRegistryProvider(MetadataProvider):
    """Default: Offline-safe provider using bundled registry + LiteLLM."""

    def __init__(self, registry_path: Path = None):
        self.registry = self._load_registry(registry_path)
        self.litellm_data = self._load_litellm_model_map()

    def get_context_window(self, model_id: str) -> int:
        # 1. Check local config override
        if model_id in self.registry:
            return self.registry[model_id].context_window
        # 2. Check LiteLLM library
        if model_id in self.litellm_data:
            return self.litellm_data[model_id].context_window
        # 3. Safe default
        return 4096

class DynamicMetadataProvider(MetadataProvider):
    """Optional: Real-time metadata from OpenRouter API."""

    async def refresh(self) -> None:
        """Fetch latest model data - requires API key."""
        ...
```

### Static Registry Schema (MANDATORY)

```yaml
# models/registry.yaml - Shipped with OSS
version: "1.0"
updated: "2025-12-23"
models:
  - id: "openai/gpt-4o"
    context_window: 128000
    pricing:
      prompt: 0.0025
      completion: 0.01
    supported_parameters: ["temperature", "top_p", "tools"]
    modalities: ["text", "vision"]
    quality_tier: "frontier"

  - id: "anthropic/claude-opus-4.5"
    context_window: 200000
    pricing:
      prompt: 0.015
      completion: 0.075
    supported_parameters: ["temperature", "top_p", "tools", "reasoning"]
    modalities: ["text", "vision"]
    quality_tier: "frontier"

  - id: "ollama/llama3.2"
    provider: "ollama"
    context_window: 128000
    pricing:
      prompt: 0
      completion: 0
    modalities: ["text"]
    quality_tier: "local"
```

### Offline Mode (MANDATORY)

```bash
# Force offline operation - MUST work without any external calls
export LLM_COUNCIL_OFFLINE=true
```

When offline mode is enabled:
1. Use `StaticRegistryProvider` exclusively
2. Disable all external metadata/routing calls
3. Log INFO message about limited/stale metadata
4. **All core council operations MUST succeed**

---

## Technical Council Review Summary

### Technical Review (2025-12-23) - Full Quorum

| Model | Verdict | Rank | Response Time |
|-------|---------|------|---------------|
| Claude Opus 4.5 | CONDITIONAL APPROVAL | #1 | 23.4s |
| Gemini 3 Pro | APPROVE | #2 | 31.4s |
| Grok 4 | APPROVE | #3 | 59.6s |
| GPT-4o | APPROVE | #4 | 9.8s |

> "The council successfully identified Response C (Claude) as the superior review, noting its crucial detection of mathematical flaws (Borda normalization with variable pool sizes) and logical gaps (Cold Start) missed by other responses."

### First Technical Review (2025-12-23, 3/4 models)

**Approved Components:**
- Dynamic metadata integration via OpenRouter API (pricing, availability, capability detection)
- Reasoning parameter optimization (`reasoning_effort`, `budget_tokens`)
- Integration points with existing L1-L4 architecture

**Returned for Revision (Now Resolved):**
- ~~Benchmark scraping strategy~~ → Deferred to Phase 4, use Internal Performance Tracker
- ~~Single scoring algorithm with "magic number" weights~~ → Tier-Specific Weighting Matrices

### Key Technical Recommendations

| Recommendation | Status | Priority |
|----------------|--------|----------|
| Add Context Window as hard constraint | ✅ Incorporated | Critical |
| Replace single scoring with Tier-Specific Weighting | ✅ Incorporated | High |
| Defer benchmark scraping to optional Phase 4 | ✅ Incorporated | High |
| Add Anti-Herding logic | ✅ Incorporated | Medium |
| Implement Internal Performance Tracker | ✅ Incorporated | Medium |
| Cold Start handling for new models | 📋 Documented | Medium |
| Borda score normalization | 📋 Documented | Medium |
| Anti-Herding edge case (<3 models) | 📋 Documented | Low |

### Council Consensus Points

1. **Context Window is a hard pass/fail constraint** - must filter before scoring, not weight
2. **Tier-specific weighting is essential** - quick tier prioritizes speed, reasoning tier prioritizes quality
3. **Benchmark scraping is high-risk** - external APIs change frequently, creates maintenance nightmare
4. **Internal performance data is more valuable** - track actual council session outcomes
5. **Phased approach required** - decouple metadata (proven value) from benchmark intelligence (speculative)
6. **Cold Start needs exploration strategy** - new models need "audition" mechanism (Phase 3)
7. **LiteLLM strongly recommended** - use as library for metadata, not just proxy

---

## Context

### Problem Statement

The LLM Council's current model selection relies on **static configuration** that quickly becomes stale in the rapidly evolving model landscape. December 2025 alone saw major releases from all frontier labs:

| Release Date | Model | Provider |
|--------------|-------|----------|
| Nov 17, 2025 | Grok 4.1 | xAI |
| Nov 18, 2025 | Gemini 3 Pro | Google |
| Nov 24, 2025 | Claude Opus 4.5 | Anthropic |
| Dec 11, 2025 | GPT-5.2 | OpenAI |

Our tier pools in `config.py` reference models that may be:
- **Deprecated or renamed** (model identifiers change)
- **Outperformed by newer models** (benchmarks shift monthly)
- **Suboptimally configured** (missing reasoning parameters)
- **Unavailable or rate-limited** (provider status changes)

### Current Architecture Gaps

| Gap | Impact | Current State |
|-----|--------|---------------|
| **Static tier pools** | Stale model selection | Hardcoded in `config.py` |
| **No benchmark integration** | Suboptimal model-task matching | Manual updates |
| **No model metadata** | Missing capabilities detection | Assumed uniform |
| **No reasoning parameters** | Underutilized model capabilities | Default parameters only |
| **No availability tracking** | Failures on unavailable models | Reactive error handling |

### Existing Foundation (ADRs 020, 022, 024)

The architecture already supports dynamic model selection:

| ADR | Component | Opportunity |
|-----|-----------|-------------|
| **ADR-020** | Not Diamond integration | Model routing API exists but uses static candidates |
| **ADR-022** | Tier contracts | `allowed_models` field could be dynamically populated |
| **ADR-024** | Layer architecture | L1 tier selection could query external data sources |

---

## Decision

Implement a **Model Intelligence Layer** that provides real-time model metadata, benchmark rankings, and dynamic pool management to all routing layers.

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    MODEL INTELLIGENCE LAYER (New)                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐              │
│  │ Model Registry  │  │ Benchmark Index │  │ Availability    │              │
│  │ (OpenRouter API)│  │ (Leaderboards)  │  │ Monitor         │              │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘              │
│           │                    │                    │                        │
│           └────────────────────┴────────────────────┘                        │
│                                │                                             │
│                    ┌───────────▼───────────┐                                 │
│                    │   Model Selector API   │                                │
│                    │   - get_tier_models()  │                                │
│                    │   - get_best_for_task()│                                │
│                    │   - get_model_params() │                                │
│                    └───────────┬───────────┘                                 │
│                                │                                             │
└────────────────────────────────┼─────────────────────────────────────────────┘
                                 │
        ┌────────────────────────┼────────────────────────────────┐
        │                        │                                │
        ▼                        ▼                                ▼
┌───────────────┐       ┌───────────────┐                ┌───────────────┐
│ L1: Tier      │       │ L2: Query     │                │ L4: Gateway   │
│ Selection     │       │ Triage        │                │ Routing       │
│ (ADR-022)     │       │ (ADR-020)     │                │ (ADR-023)     │
└───────────────┘       └───────────────┘                └───────────────┘
```

---

## Data Sources

### 1. OpenRouter Models API

**Endpoint:** `GET https://openrouter.ai/api/v1/models`

Provides real-time model metadata:

```json
{
  "id": "anthropic/claude-opus-4-5-20250514",
  "name": "Claude Opus 4.5",
  "pricing": {
    "prompt": "0.000015",
    "completion": "0.000075"
  },
  "context_length": 200000,
  "architecture": {
    "input_modalities": ["text", "image"],
    "output_modalities": ["text"]
  },
  "supported_parameters": ["temperature", "top_p", "reasoning"],
  "top_provider": {
    "is_moderated": true
  }
}
```

**Key Fields for Selection:**
- `pricing` - Cost optimization
- `context_length` - Long document handling
- `supported_parameters` - Reasoning mode detection
- `input_modalities` - Multimodal capability

### 2. Benchmark Leaderboards

| Source | Data | Update Frequency | API |
|--------|------|------------------|-----|
| [LMArena](https://lmarena.ai/leaderboard) | Elo ratings from 5M+ votes | Real-time | Public |
| [LiveBench](https://livebench.ai) | Monthly contamination-free benchmarks | Monthly | Public |
| [Artificial Analysis](https://artificialanalysis.ai/leaderboards) | Speed, cost, quality metrics | Weekly | Public |
| [LLM Stats](https://llm-stats.com) | Aggregated performance data | Daily | Public |

**Benchmark Categories:**
- **Reasoning**: GPQA Diamond, AIME 2025, ARC-AGI-2
- **Coding**: SWE-bench, LiveCodeBench, Terminal-Bench
- **General**: MMLU-Pro, Humanity's Last Exam
- **Speed**: Tokens/second, time-to-first-token

### 3. OpenRouter Rankings

**Endpoint:** `GET https://openrouter.ai/rankings`

Usage-based popularity metrics (tokens served, request count).

---

## Model Parameter Optimization

### Reasoning Mode Parameters

OpenRouter supports unified reasoning parameters:

```python
# For reasoning-capable models (o1, o3, GPT-5, Claude with thinking)
request_params = {
    "reasoning": {
        "effort": "high",  # "minimal"|"low"|"medium"|"high"|"xhigh"
        "max_tokens": 32000,  # Budget for reasoning tokens
        "exclude": False,  # Include reasoning in response
    }
}
```

**Effort Level Budget Calculation:**
```
budget_tokens = max(min(max_tokens * effort_ratio, 32000), 1024)

effort_ratio:
  xhigh: 0.95
  high: 0.80
  medium: 0.50
  low: 0.20
  minimal: 0.10
```

### Parameter Detection

```python
def get_model_params(model_id: str, task_type: str) -> dict:
    """Get optimized parameters for model and task."""
    model_info = model_registry.get(model_id)

    params = {}

    # Enable reasoning for supported models on complex tasks
    if "reasoning" in model_info.supported_parameters:
        if task_type in ["reasoning", "math", "coding"]:
            params["reasoning"] = {
                "effort": "high" if task_type == "reasoning" else "medium"
            }

    # Adjust temperature for task type
    if task_type == "creative":
        params["temperature"] = 0.9
    elif task_type in ["coding", "math"]:
        params["temperature"] = 0.2

    return params
```

---

## Dynamic Tier Pool Management

### Tier Requirements Matrix

| Tier | Latency Budget | Cost Ceiling | Min Models | Required Capabilities |
|------|----------------|--------------|------------|----------------------|
| **quick** | P95 < 10s | < $0.001/req | 3 | Fast inference |
| **balanced** | P95 < 45s | < $0.01/req | 3-4 | Good reasoning |
| **high** | P95 < 120s | < $0.10/req | 4-5 | Full capability |
| **reasoning** | P95 < 300s | < $1.00/req | 3-4 | Extended thinking |

### Dynamic Pool Selection Algorithm

**Council Revision:** Algorithm updated per council feedback to:
1. Add Context Window as **hard pass/fail constraint**
2. Replace global weights with **Tier-Specific Weighting Matrices**
3. Add **Anti-Herding logic** to prevent traffic concentration

```python
@dataclass
class ModelScore:
    model_id: str
    benchmark_score: float  # Normalized 0-100 (optional, from internal tracker)
    latency_p95: float      # Seconds
    cost_per_request: float # USD
    availability: float     # 0-1
    diversity_score: float  # Provider diversity
    context_window: int     # Token limit (HARD CONSTRAINT)
    recent_traffic: float   # 0-1, for anti-herding

# COUNCIL RECOMMENDATION: Tier-Specific Weighting Matrices
# Replaces "magic number" global weights (0.4/0.2/0.2/0.1/0.1)
TIER_WEIGHTS = {
    "quick": {
        "latency": 0.45,      # Speed is primary concern
        "cost": 0.25,         # Budget-conscious
        "quality": 0.15,      # Acceptable quality
        "availability": 0.10,
        "diversity": 0.05,
    },
    "balanced": {
        "quality": 0.35,      # Better quality
        "latency": 0.25,      # Still matters
        "cost": 0.20,         # Cost-aware
        "availability": 0.10,
        "diversity": 0.10,
    },
    "high": {
        "quality": 0.50,      # Quality is paramount
        "availability": 0.20, # Must be reliable
        "latency": 0.15,      # Acceptable wait
        "diversity": 0.10,    # Multiple perspectives
        "cost": 0.05,         # Cost secondary
    },
    "reasoning": {
        "quality": 0.60,      # Best possible quality
        "availability": 0.20, # Critical reliability
        "diversity": 0.10,    # Diverse reasoning
        "latency": 0.05,      # Patience for quality
        "cost": 0.05,         # Cost not a factor
    },
}

def select_tier_models(
    tier: str,
    task_domain: Optional[str] = None,
    count: int = 4,
    required_context: Optional[int] = None,  # NEW: context requirement
) -> List[str]:
    """Select optimal models for tier using multi-criteria scoring.

    Council-Validated Algorithm:
    1. Apply HARD CONSTRAINTS (pass/fail)
    2. Score using TIER-SPECIFIC weights
    3. Apply ANTI-HERDING penalty
    4. Ensure PROVIDER DIVERSITY
    """

    candidates = model_registry.get_available_models()
    tier_config = TIER_REQUIREMENTS[tier]
    weights = TIER_WEIGHTS[tier]

    # ===== HARD CONSTRAINTS (Pass/Fail) =====
    # Council Critical: Context window MUST be hard constraint, not weighted
    eligible = [
        m for m in candidates
        if m.latency_p95 <= tier_config.latency_budget
        and m.cost_per_request <= tier_config.cost_ceiling
        and m.availability >= 0.95
        # COUNCIL ADDITION: Context window as hard constraint
        and (required_context is None or m.context_window >= required_context)
    ]

    if not eligible:
        logger.warning(f"No models meet hard constraints for tier={tier}")
        return fallback_to_static_config(tier)

    # ===== SOFT SCORING (Tier-Specific Weights) =====
    scored = []
    for model in eligible:
        # Normalize scores to 0-1 range
        latency_score = 1 - (model.latency_p95 / tier_config.latency_budget)
        cost_score = 1 - (model.cost_per_request / tier_config.cost_ceiling)
        quality_score = model.benchmark_score / 100 if model.benchmark_score else 0.5

        score = (
            quality_score * weights["quality"] +
            latency_score * weights["latency"] +
            cost_score * weights["cost"] +
            model.availability * weights["availability"] +
            model.diversity_score * weights["diversity"]
        )

        # Domain boost (task-specific enhancement)
        if task_domain and task_domain in model.strengths:
            score *= 1.15

        # COUNCIL ADDITION: Anti-Herding Penalty
        # Prevent traffic concentration on popular models
        if model.recent_traffic > 0.3:  # More than 30% of recent traffic
            score *= (1 - (model.recent_traffic - 0.3) * 0.5)  # Up to 35% penalty

        scored.append((model.model_id, score))

    # ===== DIVERSITY ENFORCEMENT =====
    selected = select_with_diversity(scored, count, min_providers=2)

    return selected
```

### Benchmark Score Normalization (DEFERRED - Phase 4)

**Council Warning:** This section describes external benchmark integration which is DEFERRED to Phase 4. Use Internal Performance Tracker (Phase 3) for quality scoring in initial releases.

```python
# DEFERRED: Only implement after Internal Performance Tracker validates value
def normalize_benchmark_scores(model_id: str) -> float:
    """Aggregate benchmark scores into single quality metric.

    WARNING: External benchmark scraping is high-maintenance.
    Prefer Internal Performance Tracker for quality scoring.
    Only implement if internal metrics prove insufficient.
    """

    # Start with manual JSON snapshots, NOT automated scrapers
    scores = load_manual_benchmark_snapshot(model_id)

    if not scores:
        return None  # Fall back to internal metrics

    # Weighted aggregation (emphasize reasoning and coding)
    weights = {
        "lmarena_elo": 0.3,      # Human preference
        "livebench": 0.2,        # Contamination-free
        "gpqa_diamond": 0.25,    # Science reasoning
        "swe_bench": 0.25,       # Coding capability
    }

    normalized = sum(
        normalize_to_100(scores[k]) * weights[k]
        for k in weights
        if scores.get(k) is not None
    )

    return normalized
```

---

## Integration Points

### 1. Layer 1 Enhancement (ADR-022)

```python
# tier_contract.py modification
def create_tier_contract(tier: str, task_domain: Optional[str] = None) -> TierContract:
    """Create tier contract with dynamically selected models."""

    # Use Model Intelligence Layer instead of static config
    models = model_intelligence.select_tier_models(
        tier=tier,
        task_domain=task_domain,
        count=TIER_MODEL_COUNTS[tier],
    )

    # Get tier-appropriate aggregator
    aggregator = model_intelligence.get_aggregator_for_tier(tier)

    return TierContract(
        tier=tier,
        allowed_models=models,
        aggregator_model=aggregator,
        **get_tier_timeout(tier),
    )
```

### 2. Layer 2 Enhancement (ADR-020)

```python
# not_diamond.py modification
async def route_with_intelligence(
    query: str,
    tier_contract: TierContract,
) -> RouteResult:
    """Route using Not Diamond + Model Intelligence."""

    # Get task-appropriate candidates from intelligence layer
    candidates = model_intelligence.select_tier_models(
        tier=tier_contract.tier,
        task_domain=classify_domain(query),
    )

    # Get optimized parameters for each candidate
    params = {
        model: model_intelligence.get_model_params(model, query)
        for model in candidates
    }

    # Route using Not Diamond (with enriched candidates)
    if is_not_diamond_available():
        result = await not_diamond.route(query, candidates)
        return RouteResult(
            model=result.model,
            params=params[result.model],
            confidence=result.confidence,
        )

    # Fallback to intelligence-based selection
    return RouteResult(
        model=candidates[0],
        params=params[candidates[0]],
        confidence=0.7,
    )
```

### 3. Gateway Enhancement (ADR-023)

```python
# gateway/types.py modification
@dataclass
class GatewayRequest:
    model: str
    messages: List[CanonicalMessage]
    # New: Model-specific parameters from intelligence layer
    model_params: Optional[Dict[str, Any]] = None

    def apply_model_params(self) -> Dict[str, Any]:
        """Apply optimized parameters to request."""
        request = self.to_openai_format()
        if self.model_params:
            request.update(self.model_params)
        return request
```

---

## Caching and Refresh Strategy

### Cache Layers

| Data | Cache TTL | Refresh Trigger |
|------|-----------|-----------------|
| Model registry | 1 hour | API call / manual |
| Benchmark scores | 24 hours | Daily cron |
| Availability status | 5 minutes | Health check failures |
| Latency metrics | 15 minutes | Rolling window |

### Implementation

```python
class ModelIntelligenceCache:
    def __init__(self):
        self.registry_cache = TTLCache(maxsize=500, ttl=3600)
        self.benchmark_cache = TTLCache(maxsize=100, ttl=86400)
        self.availability_cache = TTLCache(maxsize=500, ttl=300)

    async def refresh_registry(self):
        """Fetch latest model data from OpenRouter."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://openrouter.ai/api/v1/models",
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"}
            )
            models = response.json()["data"]

            for model in models:
                self.registry_cache[model["id"]] = ModelInfo.from_api(model)

    async def refresh_benchmarks(self):
        """Fetch latest benchmark data from leaderboards."""
        # LMArena Elo
        lmarena = await fetch_lmarena_leaderboard()
        # LiveBench
        livebench = await fetch_livebench_scores()
        # Artificial Analysis
        aa = await fetch_artificial_analysis()

        # Merge and normalize
        for model_id in self.registry_cache:
            self.benchmark_cache[model_id] = BenchmarkData(
                lmarena_elo=lmarena.get(model_id),
                livebench=livebench.get(model_id),
                artificial_analysis=aa.get(model_id),
            )
```

---

## Configuration

### Environment Variables

```bash
# Model Intelligence Layer
LLM_COUNCIL_MODEL_INTELLIGENCE=true|false  # Enable dynamic selection
LLM_COUNCIL_BENCHMARK_SOURCE=lmarena|livebench|artificial_analysis|aggregate
LLM_COUNCIL_REFRESH_INTERVAL=3600  # Registry refresh interval (seconds)

# Fallback to static config if intelligence unavailable
LLM_COUNCIL_STATIC_FALLBACK=true|false

# Minimum benchmark score thresholds
LLM_COUNCIL_MIN_BENCHMARK_SCORE=60  # 0-100 normalized
LLM_COUNCIL_MIN_AVAILABILITY=0.95   # 0-1

# Provider diversity
LLM_COUNCIL_MIN_PROVIDERS=2  # Minimum distinct providers per tier
```

### YAML Configuration

**Council Revision:** Updated to use tier-specific weights instead of global weights.

```yaml
council:
  model_intelligence:
    enabled: true
    sources:
      openrouter_api: true
      # DEFERRED: External benchmark sources (Phase 4)
      # lmarena: false
      # livebench: false
      # artificial_analysis: false
      internal_performance: true  # Phase 3: Use council session outcomes

    refresh:
      registry_ttl: 3600
      # benchmark_ttl: 86400  # DEFERRED
      availability_ttl: 300
      performance_ttl: 3600  # Internal performance cache

    selection:
      # COUNCIL REVISION: Tier-specific weights instead of global weights
      tier_weights:
        quick:
          latency: 0.45
          cost: 0.25
          quality: 0.15
          availability: 0.10
          diversity: 0.05
        balanced:
          quality: 0.35
          latency: 0.25
          cost: 0.20
          availability: 0.10
          diversity: 0.10
        high:
          quality: 0.50
          availability: 0.20
          latency: 0.15
          diversity: 0.10
          cost: 0.05
        reasoning:
          quality: 0.60
          availability: 0.20
          diversity: 0.10
          latency: 0.05
          cost: 0.05

      constraints:
        min_providers: 2
        min_availability: 0.95
        max_cost_multiplier: 10  # vs cheapest option

      # COUNCIL ADDITION: Anti-Herding
      anti_herding:
        enabled: true
        traffic_threshold: 0.3  # 30% of recent traffic
        max_penalty: 0.35       # Up to 35% score reduction

    parameters:
      auto_reasoning: true  # Enable reasoning params when appropriate
      reasoning_effort_by_tier:
        quick: minimal
        balanced: low
        high: medium
        reasoning: high

    # COUNCIL ADDITION: Internal Performance Tracker
    performance_tracker:
      enabled: true
      store_path: "${HOME}/.llm-council/performance.jsonl"
      decay_days: 30
      min_samples_preliminary: 10
      min_samples_moderate: 30
      min_samples_high: 100
```

---

## Risks and Mitigations

### Council-Identified Risks (High Priority)

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **Benchmark scraper breakage** | HIGH | HIGH | DEFER to Phase 4; use manual snapshots, not scrapers |
| **Traffic herding** | Medium | High | Anti-Herding penalty in selection algorithm |
| **Context window violations** | Medium | High | Hard constraint filter (not weighted) |
| **Magic number weights** | N/A | Medium | Tier-specific weight matrices |

### Original Risks (Updated)

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| External API unavailability | Medium | High | Static fallback, aggressive caching |
| ~~Benchmark data staleness~~ | ~~Medium~~ | ~~Medium~~ | **DEFERRED:** Internal Performance Tracker instead |
| Model identifier changes | High | Medium | Fuzzy matching, alias tracking |
| Over-optimization | Medium | Medium | Diversity constraints, Anti-Herding logic |
| Cold start latency | Low | Medium | Pre-warm cache on startup |
| ~~Provider bias in benchmarks~~ | ~~Medium~~ | ~~Low~~ | **DEFERRED:** Internal metrics not susceptible |
| **Internal metric bias** | Medium | Medium | Minimum sample size requirements, decay weighting |

---

## Success Metrics

### Phase 1 Success Metrics (Model Metadata Layer)

| Metric | Target | Measurement |
|--------|--------|-------------|
| Registry availability | > 99% uptime | Track OpenRouter API failures |
| Context window violations | 0 errors | Monitor "context exceeded" errors |
| Static fallback activation | < 1% of requests | Track fallback usage |
| Model freshness | < 1 hour stale | Track registry refresh success |

### Phase 2 Success Metrics (Reasoning Parameters)

| Metric | Target | Measurement |
|--------|--------|-------------|
| Parameter utilization | 100% for reasoning tier | Track reasoning param usage |
| Budget token efficiency | > 80% utilization | Compare budget vs actual tokens |
| Reasoning quality | No regression | Compare rubric scores before/after |

### Phase 3 Success Metrics (Internal Performance Tracker)

| Metric | Target | Measurement |
|--------|--------|-------------|
| Session coverage | > 95% tracked | Count sessions with metrics |
| Internal metric correlation | > 0.6 with Borda | Validate internal scores vs outcomes |
| Model ranking stability | < 10% weekly variance | Track rank position changes |
| Selection improvement | > 5% higher Borda | Compare dynamic vs static selection |

### Overall Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| ~~Benchmark correlation~~ | ~~> 0.8~~ | **DEFERRED:** Internal metrics instead |
| Cost optimization | -15% vs static | Compare equivalent quality |
| Tier pool diversity | ≥ 2 providers | Track provider distribution |
| Anti-Herding effectiveness | No model > 40% traffic | Monitor traffic distribution |

---

## Implementation Phases

**Council Recommendation:** Decouple proven value (metadata) from speculative value (benchmark intelligence). Implement in strict phases with validation gates.

### Phase 1: Model Metadata Layer (v0.15.x) ✅ IMPLEMENTED

**Goal:** Dynamic model discovery and capability detection via OpenRouter API.

**Status:** ✅ COMPLETE (2025-12-23)
**GitHub Issues:** #93, #94, #95
**Tests:** 79 TDD tests (cache: 20, client: 20, provider: 24, selection: 35)

- [x] Implement OpenRouter API client (`src/llm_council/metadata/openrouter_client.py`)
- [x] Cache model metadata with TTL (1 hour registry, 5 min availability)
  - `src/llm_council/metadata/cache.py`: TTLCache, ModelIntelligenceCache
- [x] Add model capability detection (context window, reasoning support, modalities)
  - `src/llm_council/metadata/dynamic_provider.py`: DynamicMetadataProvider
- [x] Add **Context Window as hard constraint** in tier filtering
  - `src/llm_council/metadata/selection.py`: _meets_context_requirement()
- [x] Update `get_tier_models()` to use registry with static fallback
  - `src/llm_council/metadata/selection.py`: select_tier_models()
- [x] Implement **Anti-Herding logic** with traffic tracking
  - `src/llm_council/metadata/selection.py`: apply_anti_herding_penalty()
- [x] Add ModelIntelligenceConfig to unified_config.py
- [x] Add task_domain parameter to tier_contract.py

**Environment Variables:**
- `LLM_COUNCIL_MODEL_INTELLIGENCE=true` enables dynamic selection
- `LLM_COUNCIL_OFFLINE=true` forces static provider (takes precedence)

**Validation Gate:** ✅ PASSED
- OpenRouter API client with timeout/error handling
- Static fallback activates when API unavailable or offline mode enabled
- All 1206 tests pass

**Phase 1 "Hollow" Fix (2025-12-24):**

Initial Phase 1 implementation used regex pattern matching ("hollow" implementation).
Fixed to use real metadata from providers (Issues #105-#108).

| Function | Before | After |
|----------|--------|-------|
| `_get_provider_safe()` | N/A | Returns provider or None gracefully |
| `_get_quality_score_from_metadata()` | Regex patterns | Real QualityTier lookup |
| `_get_cost_score_from_metadata()` | Regex patterns | Real pricing data |
| `_meets_context_requirement()` | Always True | Real context window filtering |

**Quality Tier Scores:**
- FRONTIER: 0.95
- STANDARD: 0.75
- ECONOMY: 0.55
- LOCAL: 0.40

**Graceful Degradation:** When metadata unavailable, falls back to heuristic estimates.

### Phase 2: Reasoning Parameter Optimization (v0.16.x) ✅ IMPLEMENTED

**Goal:** Automatic reasoning parameter configuration for capable models.

- [x] Detect reasoning-capable models from registry metadata
- [x] Apply `reasoning_effort` parameter based on tier (quick=minimal, reasoning=high)
- [x] Calculate `budget_tokens` per effort level
- [x] Add task-specific parameter profiles (math→high effort, creative→minimal)
- [x] Update gateway to pass reasoning parameters to OpenRouter
- [x] Track reasoning token usage for cost optimization

**Implementation Details (2025-12-24):**

Implemented using TDD with 80 new tests (1299 total tests pass).

**Module Structure:** `src/llm_council/reasoning/`

| File | Purpose |
|------|---------|
| `types.py` | `ReasoningEffort` enum, `ReasoningConfig` frozen dataclass, `should_apply_reasoning()` |
| `tracker.py` | `ReasoningUsage`, `AggregatedUsage`, `extract_reasoning_usage()`, `aggregate_reasoning_usage()` |
| `__init__.py` | Module exports |

**Tier-Effort Mapping:**
- quick → MINIMAL (10%)
- balanced → LOW (20%)
- high → MEDIUM (50%)
- reasoning → HIGH (80%)

**Domain Overrides:** math→HIGH, coding→MEDIUM, creative→MINIMAL

**Stage Configuration:**
- `stage1: true` (primary responses)
- `stage2: false` (peer reviews)
- `stage3: true` (synthesis)

**GitHub Issues:** #97-#100 (all completed)

**Validation Gate:** ✅ PASSED
- Reasoning parameters correctly applied for all reasoning-tier queries
- Token usage tracking shows expected budget allocation
- No regressions in non-reasoning tiers (1299 tests pass)

### Phase 3: Internal Performance Tracking (v0.17.x) ✅ IMPLEMENTED

**Council Recommendation:** Instead of scraping external benchmarks (high maintenance risk), implement internal performance tracking based on actual council session outcomes.

- [x] Track model performance per council session:
  - Borda score received (`ModelSessionMetric.borda_score`)
  - Response latency (`ModelSessionMetric.latency_ms`)
  - Parse success rate (`ModelSessionMetric.parse_success`)
  - Reasoning quality (optional `reasoning_tokens_used`)
- [x] Build **Internal Performance Index** from historical sessions
  - `InternalPerformanceTracker` with rolling window aggregation
  - `ModelPerformanceIndex` with mean_borda_score, p50/p95_latency, parse_success_rate
- [x] Use internal metrics for quality scoring (replaces external benchmarks)
  - `get_quality_score()` returns 0-100 normalized score
  - Cold start: unknown models get neutral score (50)
- [x] Implement rolling window decay (recent sessions weighted higher)
  - Exponential decay: `weight = exp(-days_ago / decay_days)`
  - Default decay_days = 30

**Implementation Details:**
- `src/llm_council/performance/` module (4 files, ~700 lines)
- 70 TDD tests in `tests/test_performance_*.py`
- JSONL storage pattern (follows `bias_persistence.py`)
- Configuration via `PerformanceTrackerConfig` in unified_config.py

**Validation Gate:** Phase 3 complete when:
- 100+ sessions tracked with metrics (tracked via confidence_level=HIGH)
- Internal quality scores correlate with Borda outcomes (by design)
- Model selection uses `quality_score` from tracker

### Phase 4: External Benchmark Integration (DEFERRED) ⏸️

**Council Warning:** External benchmark scraping is HIGH-RISK due to:
- API instability (LMArena, LiveBench change formats frequently)
- Maintenance burden (scrapers break silently)
- Data staleness (monthly updates don't reflect rapid model changes)

**Deferred until:** Internal Performance Tracking validates the value of quality metrics.

**If implemented:**
- [ ] Start with **manual JSON snapshots** (not automated scrapers)
- [ ] Implement LMArena Elo as optional quality boost (not required)
- [ ] LiveBench for contamination-free validation only
- [ ] Create benchmark staleness alerts (>30 days = warning)

---

## Internal Performance Tracker

**Council Recommendation:** Build quality metrics from actual council session outcomes rather than external benchmarks.

### Performance Metrics Schema

```python
@dataclass
class ModelSessionMetric:
    """Performance data from a single council session."""
    session_id: str
    model_id: str
    timestamp: datetime

    # Stage 1 metrics
    response_latency_ms: int
    response_length: int
    parse_success: bool

    # Stage 2 metrics (from peer review)
    borda_score: float              # 0.0 - N (N = council size)
    normalized_rank: float          # 0.0 - 1.0 (1.0 = best)
    rubric_scores: Optional[Dict[str, float]]  # If rubric scoring enabled

    # Stage 3 metrics (from chairman selection)
    selected_for_synthesis: bool    # Was this response referenced?

@dataclass
class ModelPerformanceIndex:
    """Aggregated performance for a model."""
    model_id: str
    sample_size: int
    last_updated: datetime

    # Aggregated metrics
    mean_borda_score: float
    mean_normalized_rank: float
    p50_latency_ms: int
    p95_latency_ms: int
    parse_success_rate: float
    selection_rate: float           # How often selected for synthesis

    # Confidence
    confidence: str  # INSUFFICIENT (<10), PRELIMINARY (10-30), MODERATE (30-100), HIGH (>100)

class InternalPerformanceTracker:
    """Track and aggregate model performance from council sessions."""

    def __init__(self, store_path: Path, decay_days: int = 30):
        self.store_path = store_path
        self.decay_days = decay_days

    def record_session(self, session_metrics: List[ModelSessionMetric]) -> None:
        """Record metrics from a completed council session."""
        # Atomic append to JSONL store
        ...

    def get_model_index(self, model_id: str) -> ModelPerformanceIndex:
        """Get aggregated performance for a model with rolling window."""
        # Apply exponential decay to older sessions
        # Recent sessions weighted higher
        ...

    def get_quality_score(self, model_id: str) -> float:
        """Get normalized quality score (0-100) for model selection."""
        index = self.get_model_index(model_id)
        if index.confidence == "INSUFFICIENT":
            return 50.0  # Default neutral score
        return index.mean_normalized_rank * 100
```

### Integration with Selection Algorithm

```python
def select_tier_models(tier: str, ...) -> List[str]:
    # ... hard constraints ...

    for model in eligible:
        # Use INTERNAL performance tracker instead of external benchmarks
        quality_score = performance_tracker.get_quality_score(model.model_id)
        # ... rest of scoring with tier-specific weights ...
```

---

## Open Questions (Council Addressed)

### Resolved by Council Review

| Question | Council Answer |
|----------|----------------|
| Should benchmark scores override tier selection? | **No.** Tiers represent user intent (speed vs quality tradeoff). Benchmarks inform selection *within* tier. |
| How to handle new models with no data? | **Default neutral score (50).** Use provider metadata only until internal performance data accumulates. |
| Balance between performance and cost? | **Tier-specific.** Quick tier: yes, select cheaper. Reasoning tier: never compromise on quality. |
| Auto-apply reasoning parameters? | **Yes, by tier.** Reasoning tier = high effort, quick tier = minimal effort. |
| Handle benchmark gaming? | **Use internal metrics.** Council session outcomes are harder to game than public benchmarks. |

### Remaining Open Questions

1. **What sample size validates Internal Performance Index?**
   - Council suggested 100+ sessions for HIGH confidence
   - Is 30+ sessions sufficient for MODERATE confidence?

2. **Should models with LOW internal scores be automatically demoted?**
   - Threshold for exclusion from tier pools?
   - Grace period for new models?

3. **How to bootstrap Internal Performance Tracker?**
   - Run shadow sessions with all available models?
   - Start with static config and learn incrementally?

### Issues Identified in Full Quorum Review

**A. Cold Start Problem** (Claude, Gemini)
> "When a new model appears in OpenRouter, it has zero internal performance data."

**Recommended Solutions:**
- Assign temporary "phantom score" equivalent to tier average until 10+ samples
- Implement Epsilon-Greedy exploration (small % of requests try new models)
- Minimum sessions required before model enters regular rotation
- Manual allowlist for high-profile new releases

**B. Borda Score Normalization** (Claude)
> "A 5-model session gives max score of 4; an 8-model session gives max of 7."

**Solution:** Normalize to percentile rank (0.0-1.0) rather than raw Borda counts:
```python
normalized_rank = (council_size - borda_position) / council_size
```

**C. Parse Success Definition** (Claude)
Define parse success as ALL of:
- Valid JSON returned (if JSON expected)
- Schema-compliant response
- Extractable vote/rationale for Stage 2

**D. Anti-Herding Edge Case** (Gemini)
> "If only 2 models pass hard constraints, the system might oscillate wildly."

**Solution:** Disable Anti-Herding when eligible model count < 3.

**E. Degradation Behavior** (Claude)
> "What happens when ALL eligible models for a tier fall below acceptable thresholds?"

**Fallback Chain:**
1. Warn user and proceed with best-available
2. Escalate to adjacent tier (quick→balanced, balanced→high)
3. Fall back to static config as last resort

---

## References

### External Sources
- [OpenRouter Models API](https://openrouter.ai/docs/api/reference/models)
- [OpenRouter Rankings](https://openrouter.ai/rankings)
- [LMArena Leaderboard](https://lmarena.ai/leaderboard)
- [LiveBench](https://livebench.ai)
- [Artificial Analysis](https://artificialanalysis.ai/leaderboards/models)
- [LLM Stats](https://llm-stats.com/)
- [Not Diamond Model Routing](https://www.notdiamond.ai/)

### Related ADRs
- [ADR-020: Not Diamond Integration Strategy](./ADR-020-not-diamond-integration-strategy.md)
- [ADR-022: Tiered Model Selection](./ADR-022-tiered-model-selection.md)
- [ADR-023: Multi-Router Gateway Support](./ADR-023-multi-router-gateway-support.md)
- [ADR-024: Unified Routing Architecture](./ADR-024-unified-routing-architecture.md)

### Research
- [Chatbot Arena Methodology](https://lmarena.ai/)
- [LLM Routing Survey (Not Diamond)](https://github.com/Not-Diamond/awesome-ai-model-routing)
- [IBM Research: LLM Routing](https://research.ibm.com/blog/LLM-routers)
