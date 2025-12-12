# ADR-011: Cost Tracking and Prediction System

**Status:** Proposed
**Date:** 2024-12-12
**Deciders:** LLM Council
**Technical Story:** Design comprehensive cost tracking, prediction, and budget controls for the council system

## Context and Problem Statement

The council system uses multiple LLM calls per query (3-10 models × 3 stages), making costs unpredictable. Users need:

1. **Pre-submission estimates**: Know costs before running a query
2. **Post-submission breakdowns**: Understand where money went
3. **Budget controls**: Prevent surprise charges
4. **Optimization guidance**: Reduce costs without sacrificing quality

### Current State
- Token counts tracked per stage (stage1, stage1.5, stage2, stage3)
- OpenRouter provides usage: `{prompt_tokens, completion_tokens, total_tokens}`
- No cost calculation or prediction
- No budget enforcement

### Key Challenge: Peer Review Cost Growth
Stage 2 (peer review) input size grows as O(N × M) where:
- N = number of models
- M = average Stage 1 response length

With 5 models generating 500 tokens each, each reviewer sees ~2500+ input tokens.

## Decision Drivers

* **Accuracy**: Cost predictions should be within 20% of actuals
* **Reliability**: Never fail a query due to pricing lookup issues
* **User Safety**: Prevent runaway costs before they happen
* **Transparency**: Users understand exactly how costs are calculated
* **Extensibility**: Support future providers beyond OpenRouter

## Design Questions & Decisions

### 1. Pricing Data Source

**Question:** How to get and cache model pricing data?

**Options Considered:**
| Approach | Pros | Cons |
|----------|------|------|
| Hardcoded only | Simple, no dependencies | Stale quickly, maintenance burden |
| Dynamic API only | Always current | API failures break pricing |
| **Hybrid (chosen)** | Resilient, current when available | Slightly more complex |

**Decision: Hybrid approach with cached dynamic fetching + hardcoded fallback**

```python
class PricingService:
    def __init__(self):
        self.cache_ttl = 3600  # 1 hour
        self.fallback_prices = {
            # Per million tokens
            "openai/gpt-4o": {"input": 2.50, "output": 10.00},
            "anthropic/claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
            "google/gemini-1.5-pro": {"input": 1.25, "output": 5.00},
        }
        self._cache = {}

    async def get_price(self, model_id: str) -> dict:
        if self._is_cache_valid(model_id):
            return self._cache[model_id]

        try:
            price = await self._fetch_from_openrouter(model_id)
            self._update_cache(model_id, price)
            return price
        except APIError:
            return self.fallback_prices.get(model_id)
```

**Rationale:**
- OpenRouter prices change frequently (new models, price drops)
- API failures shouldn't break cost tracking
- Cached prices provide sub-millisecond lookups during query execution
- Fallback ensures graceful degradation

### 2. Token Estimation for Cost Prediction

**Question:** How to estimate completion tokens before a query runs?

**Options Considered:**
| Approach | Pros | Cons |
|----------|------|------|
| Simple multiplier | Easy | Ignores model/stage variance |
| Trained ML predictor | Accurate | Complex, data-hungry |
| **Historical percentiles (chosen)** | Accurate, simple | Needs bootstrap data |

**Decision: Model-specific historical percentiles with stage multipliers**

```python
class CostPredictor:
    def __init__(self):
        # Per (model, stage) completion token statistics
        self.completion_stats = {
            "openai/gpt-4o": {
                "initial_response": {"p50": 450, "p75": 680, "p95": 1200},
                "peer_review": {"p50": 580, "p75": 850, "p95": 1400},
                "synthesis": {"p50": 400, "p75": 600, "p95": 1000},
            },
            # ... other models
        }

    def estimate_query_cost(
        self,
        prompt_tokens: int,
        models: list[str],
        confidence: str = "p75"  # p50, p75, p95
    ) -> CostEstimate:
        """
        Estimate total cost for a council query.

        Returns low/expected/high range based on historical data.
        """
        estimates = []

        for stage in ["initial_response", "peer_review", "synthesis"]:
            stage_models = self._models_for_stage(stage, models)
            stage_prompt = self._estimate_stage_prompt(stage, prompt_tokens)

            for model in stage_models:
                completion = self.completion_stats[model][stage][confidence]
                price = self.pricing.get_price(model)

                cost = (
                    (stage_prompt * price["input"]) +
                    (completion * price["output"])
                ) / 1_000_000

                estimates.append(StageCostEstimate(stage, model, cost))

        total = sum(e.cost for e in estimates)
        return CostEstimate(
            low=total * 0.6,      # p25 equivalent
            expected=total,       # chosen confidence
            high=total * 1.5,     # p95 buffer
            breakdown=estimates
        )

    def update_stats(self, model: str, stage: str, actual_tokens: int):
        """Update statistics after each completion (exponential moving average)."""
        alpha = 0.1
        current = self.completion_stats[model][stage]["p50"]
        self.completion_stats[model][stage]["p50"] = (
            alpha * actual_tokens + (1 - alpha) * current
        )
```

**Rationale:**
- Different models have different verbosity (Claude verbose, GPT concise)
- Different stages have different output patterns (reviews longer than synthesis)
- Percentiles let users choose risk tolerance
- EMA updates improve accuracy over time without complex ML

### 3. Budget Enforcement Strategy

**Question:** How to handle spending limits?

**Options Considered:**
| Approach | Pros | Cons |
|----------|------|------|
| Hard reject | Safe | Frustrating UX, estimates uncertain |
| Warn only | User-friendly | Can exceed budget |
| Abort mid-query | Real-time control | Wastes spent tokens |
| **Tiered (chosen)** | Flexible, safe | More complex |

**Decision: Tiered enforcement with configurable strictness**

```python
class BudgetEnforcer:
    class Mode(Enum):
        STRICT = "strict"      # Reject if p75 estimate exceeds
        BALANCED = "balanced"  # Reject if p50 exceeds, warn if p75 exceeds
        PERMISSIVE = "permissive"  # Warn only, never reject upfront

    def pre_query_check(
        self,
        estimate: CostEstimate,
        budget_remaining: float,
        mode: Mode = Mode.BALANCED
    ) -> BudgetDecision:
        if mode == Mode.STRICT:
            if estimate.high > budget_remaining:
                return BudgetDecision.REJECT, self._suggest_cheaper(estimate)

        elif mode == Mode.BALANCED:
            if estimate.expected > budget_remaining:
                return BudgetDecision.REJECT, "Likely to exceed budget"
            elif estimate.high > budget_remaining:
                return BudgetDecision.WARN, f"May exceed (${estimate.expected:.2f} expected, up to ${estimate.high:.2f})"

        elif mode == Mode.PERMISSIVE:
            if estimate.expected > budget_remaining:
                return BudgetDecision.WARN, "Likely to exceed budget"

        return BudgetDecision.ALLOW, None

    def mid_query_check(
        self,
        spent_so_far: float,
        remaining_stages: list[str],
        budget_remaining: float
    ) -> BudgetDecision:
        """Check between stages - abort gracefully if over budget."""
        if spent_so_far > budget_remaining:
            return BudgetDecision.ABORT_GRACEFULLY, "Budget exceeded. Returning partial results."
        return BudgetDecision.CONTINUE, None
```

**Critical UX considerations:**
- **Never abort mid-completion**: Wastes tokens, creates broken responses
- **Check between stages**: Can return partial results gracefully
- **Suggest alternatives**: "Removing GPT-4 reduces estimate to $0.28"

### 4. Cost Attribution in Peer Review

**Question:** In Stage 2, each model reviews all others. How to attribute costs?

**Options Considered:**
| Approach | Pros | Cons |
|----------|------|------|
| Split among reviewed | Intuitive | Masks reviewer verbosity |
| **Reviewer only (chosen)** | Actionable, causal | Less intuitive |
| Both views | Complete | Complex |

**Decision: Primary attribution to reviewer, with cross-reference tagging**

```python
@dataclass
class CostAttribution:
    stage: str
    model: str
    tokens_in: int
    tokens_out: int
    cost: float
    reviewing_models: list[str] | None = None  # For peer review stage

    @property
    def cost_per_review_target(self) -> float | None:
        """Secondary view: split cost among reviewed responses."""
        if self.reviewing_models:
            return self.cost / len(self.reviewing_models)
        return None
```

**Rationale:**
- **Causality**: The reviewer's verbosity determines cost
- **Actionability**: "Claude's reviews cost 2x GPT's" → adjust reviewer selection
- **Simplicity**: Primary attribution is straightforward
- **Flexibility**: Can still compute "cost to be reviewed" analytically

**Example output:**
```json
{
  "model_costs": {
    "openai/gpt-4o": {
      "direct_cost": 0.0234,
      "cost_as_review_target": 0.0156,
      "breakdown": {
        "initial_response": 0.0089,
        "peer_review": 0.0102,
        "synthesis": 0.0043
      }
    }
  },
  "stage_costs": {
    "initial_response": 0.0312,
    "peer_review": 0.0847,
    "synthesis": 0.0098
  }
}
```

### 5. Where Cost Tracking Lives

**Question:** Core library, optional module, or cloud-only?

**Decision: Core library with pluggable interfaces**

```
┌─────────────────────────────────────────────────────────────────┐
│                     OPEN SOURCE CORE                            │
├─────────────────────────────────────────────────────────────────┤
│  llm_council/                                                   │
│  └── cost_tracking/                                             │
│      ├── __init__.py                                            │
│      ├── types.py          # CostEstimate, Attribution DTOs     │
│      ├── calculator.py     # Pure token→cost math               │
│      ├── predictor.py      # Estimation algorithms              │
│      ├── enforcer.py       # Budget enforcement                 │
│      └── interfaces.py     # Abstract PricingProvider           │
│                                                                 │
│  llm_council/cost_tracking/backends/                            │
│  ├── memory_storage.py     # In-memory (default)                │
│  ├── sqlite_storage.py     # Local persistence                  │
│  └── static_pricing.py     # Bundled fallback prices            │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    PAID CLOUD TIER                              │
├─────────────────────────────────────────────────────────────────┤
│  • PostgreSQL storage backend                                   │
│  • Real-time OpenRouter pricing sync                            │
│  • Cross-organization prediction models                         │
│  • Budget alerts, dashboards, admin controls                    │
│  • Cost anomaly detection                                       │
│  • Multi-tenant quotas (org/team/user)                          │
└─────────────────────────────────────────────────────────────────┘
```

**Feature Matrix:**
| Feature | Open Source | Cloud |
|---------|-------------|-------|
| Per-query cost calculation | Yes | Yes |
| Cost estimation (local history) | Yes | Yes (global models) |
| Budget warnings | Yes | Yes |
| Budget enforcement | Yes (local) | Yes (org-wide) |
| Historical dashboards | No | Yes |
| Cross-user prediction models | No | Yes |
| Cost anomaly alerts | No | Yes |

**Rationale:**
- **Safety default**: OSS users need visibility into spend
- **Transparency**: Users can see exactly how costs are calculated
- **Extensibility**: Cloud tier adds value without restricting core functionality
- **Community contribution**: Open cost logic means community can improve it

## Implementation

### API Integration

```python
# In run_full_council()
async def run_full_council(
    user_query: str,
    cost_tracker: CostTracker | None = None,
    budget_limit: float | None = None,
) -> CouncilResult:
    cost_tracker = cost_tracker or DefaultCostTracker()

    # Pre-flight cost estimation
    estimate = cost_tracker.estimate(user_query, COUNCIL_MODELS)

    # Budget check
    if budget_limit:
        decision, msg = cost_tracker.enforcer.pre_query_check(
            estimate, budget_limit
        )
        if decision == BudgetDecision.REJECT:
            raise BudgetExceededError(msg, estimate=estimate)

    # ... run stages, tracking actual costs ...

    return CouncilResult(
        answer=synthesis,
        cost_summary=cost_tracker.get_summary()
    )
```

### Configuration

```python
# config.py additions
DEFAULT_BUDGET_MODE = "balanced"  # strict, balanced, permissive
DEFAULT_COST_TRACKING = True
DEFAULT_PRICING_CACHE_TTL = 3600  # seconds
```

### Response Schema

```python
@dataclass
class CostSummary:
    total_cost: float
    currency: str = "USD"
    by_stage: dict[str, float]
    by_model: dict[str, float]
    estimate_accuracy: float  # actual / estimated
    tokens: TokenUsage

@dataclass
class TokenUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    by_stage: dict[str, dict]
```

## Consequences

### Positive
- Users can predict costs before running queries
- Budget controls prevent surprise charges
- Cost breakdowns enable optimization
- OSS users get full cost visibility

### Negative
- Adds complexity to core library
- Pricing data maintenance required
- Estimates are inherently uncertain

### Risks
- **Stale prices**: Mitigated by dynamic fetching + short TTL
- **Inaccurate estimates**: Mitigated by percentile ranges
- **Budget too strict**: Mitigated by configurable modes

## Migration Path

1. **Phase 1**: Add cost calculation (post-query only)
2. **Phase 2**: Add cost estimation (pre-query)
3. **Phase 3**: Add budget warnings
4. **Phase 4**: Add budget enforcement (opt-in)
5. **Phase 5**: Add cost dashboards in cloud tier

## References

- [ADR-009: HTTP API and Open Core Boundary](./ADR-009-http-api-open-core-boundary.md)
- [OpenRouter Pricing API](https://openrouter.ai/docs#models)
- [Token Estimation Best Practices](https://platform.openai.com/tokenizer)
