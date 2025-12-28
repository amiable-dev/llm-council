# ADR-027: Frontier Tier

**Status:** ACCEPTED (Revised per Council Review 2025-12-24)
**Date:** 2025-12-24
**Decision Makers:** Engineering, Architecture
**Extends:** ADR-022 (Tier System)
**Council Review:** Reasoning tier (gpt-5.2-pro, claude-opus-4.5, gemini-3-pro-preview, grok-4.1-fast)

---

## Context

The current tier system (ADR-022) defines four confidence tiers:
- `quick` - Fast responses, low latency priority
- `balanced` - General use, balanced priorities
- `high` - Quality deliberation, proven stable models
- `reasoning` - Deep analysis with extended thinking

**Gap Identified:** There is no tier for evaluating cutting-edge, preview, or beta models before they are promoted to production use in `high` tier.

**Problem:** New models (e.g., GPT-5.2-pro, Gemini 3 Pro Preview) cannot be safely tested in council deliberations without risking production stability. The `high` tier explicitly requires proven stable models (30+ days), creating a chicken-and-egg problem.

---

## Decision

Introduce a new confidence tier called `frontier` for cutting-edge/preview model evaluation.

### Tier Definition

| Attribute | `high` | `frontier` |
|-----------|--------|------------|
| Purpose | Production deliberation | Max-capability evaluation |
| Stability | Proven (30+ days) | New/beta accepted |
| Preview models | Prohibited | Allowed |
| Rate limits | Standard | May be restricted |
| Pricing | Known/stable | May fluctuate |
| Risk tolerance | Low | High |
| **Voting Authority** | Full | Advisory only (Shadow Mode) |

### Shadow Mode (Council Recommendation)

**Critical Design Decision:** Frontier models operate in **Shadow Mode** by default.

```python
class VotingAuthority(Enum):
    FULL = "full"           # Vote counts in consensus
    ADVISORY = "advisory"   # Logged/evaluated, vote weight = 0.0
    EXCLUDED = "excluded"   # Not included in deliberation

# Default voting authority by tier
TIER_VOTING_AUTHORITY = {
    "quick": VotingAuthority.FULL,
    "balanced": VotingAuthority.FULL,
    "high": VotingAuthority.FULL,
    "reasoning": VotingAuthority.FULL,
    "frontier": VotingAuthority.ADVISORY,  # Shadow mode by default
}
```

**Rationale:** An experimental, hallucinating model could break a tie or poison the context of a production workflow. Shadow Mode ensures frontier models can be evaluated without affecting council decisions.

**Override:** Operators may explicitly enable full voting for frontier models via configuration:
```yaml
council:
  tiers:
    frontier:
      voting_authority: full  # Override shadow mode
```

### Tier Intersection: Reasoning vs Frontier

**Conflict Resolution:** Models can belong to multiple conceptual categories (e.g., `o1-preview` is both "reasoning" and "frontier").

**Precedence Rule:**
1. If user requests `frontier`, reasoning models ARE included (frontier is capability-focused)
2. If user requests `reasoning`, preview/beta models ARE excluded unless `allow_preview: true`
3. `frontier` acts as an **override flag** that permits preview models within other tier requests

```python
def resolve_tier_intersection(
    requested_tier: str,
    model_info: ModelInfo,
    allow_preview: bool = False
) -> bool:
    """Determine if model qualifies for requested tier."""
    if requested_tier == "frontier":
        # Frontier accepts all capable models including previews
        return model_info.quality_tier == QualityTier.FRONTIER

    if requested_tier == "reasoning":
        # Reasoning excludes previews by default
        if model_info.is_preview and not allow_preview:
            return False
        return model_info.supports_reasoning

    # Other tiers: standard logic
    return _standard_tier_qualification(requested_tier, model_info)
```

### Tier Weights (Revised per Council)

```python
TIER_WEIGHTS = {
    # ... existing tiers ...
    "frontier": {
        "quality": 0.85,      # INCREASED: Intelligence is the primary driver
        "diversity": 0.05,    # DECREASED: Don't rotate for rotation's sake
        "availability": 0.05, # DECREASED: Accept instability in beta
        "latency": 0.00,      # Irrelevant for capability testing
        "cost": 0.05,         # Minor guardrail against extreme pricing
    },
}
```

**Rationale (Council Feedback):**
- **Quality 85%**: When testing the frontier, you want the absolute smartest model available
- **Diversity 5%**: You often want to test *one* specific breakthrough model, not load-balance
- **Availability 5%**: Preview APIs often have aggressive rate limits or outages
- **Latency 0%**: Willing to wait for cutting-edge responses
- **Cost 5%**: Minor guardrail to prevent extreme cost surprises

### Graduation Criteria: Frontier → High

**Council Requirement:** Explicit metrics for model promotion.

```python
@dataclass
class GraduationCriteria:
    """Criteria for promoting model from frontier to high tier."""
    min_age_days: int = 30
    min_completed_sessions: int = 100
    max_error_rate: float = 0.02        # < 2% errors
    min_quality_percentile: float = 0.75  # >= 75th percentile vs high-tier baseline
    api_stability: bool = True           # No breaking changes in evaluation period
    provider_ga_status: bool = True      # Provider removed "preview/beta" label

def should_graduate(
    model_id: str,
    tracker: PerformanceTracker,
    criteria: GraduationCriteria
) -> Tuple[bool, List[str]]:
    """Check if model meets graduation criteria."""
    stats = tracker.get_model_stats(model_id)
    failures = []

    if stats.days_tracked < criteria.min_age_days:
        failures.append(f"age: {stats.days_tracked} < {criteria.min_age_days} days")

    if stats.completed_sessions < criteria.min_completed_sessions:
        failures.append(f"sessions: {stats.completed_sessions} < {criteria.min_completed_sessions}")

    if stats.error_rate > criteria.max_error_rate:
        failures.append(f"error_rate: {stats.error_rate:.1%} > {criteria.max_error_rate:.1%}")

    if stats.quality_percentile < criteria.min_quality_percentile:
        failures.append(f"quality: {stats.quality_percentile:.0%} < {criteria.min_quality_percentile:.0%}")

    return (len(failures) == 0, failures)
```

### Cost Ceiling Protection

**Council Requirement:** Prevent runaway costs from volatile preview pricing.

```python
def apply_cost_ceiling(
    model_id: str,
    model_cost: float,
    tier: str,
    high_tier_avg_cost: float
) -> Tuple[bool, Optional[str]]:
    """Check if model cost exceeds tier ceiling."""
    if tier != "frontier":
        return (True, None)

    # Frontier allows up to 5x high-tier average
    FRONTIER_COST_MULTIPLIER = 5.0
    ceiling = high_tier_avg_cost * FRONTIER_COST_MULTIPLIER

    if model_cost > ceiling:
        return (False, f"cost ${model_cost:.4f} exceeds ceiling ${ceiling:.4f}")

    return (True, None)
```

### Hard Fallback

**Council Requirement:** Define behavior when frontier model fails.

```python
async def execute_with_fallback(
    query: str,
    frontier_model: str,
    fallback_tier: str = "high"
) -> ModelResponse:
    """Execute frontier model with automatic fallback."""
    try:
        response = await query_model(frontier_model, query, timeout=300)
        return response
    except (RateLimitError, TimeoutError, APIError) as e:
        logger.warning(f"Frontier model {frontier_model} failed: {e}. Falling back to {fallback_tier}")

        # Automatic degradation to high tier
        fallback_models = get_tier_models(fallback_tier)
        return await query_model(fallback_models[0], query)
```

### Privacy & Compliance Warning

**Council Requirement:** Document data handling differences for preview models.

```markdown
**Privacy Notice:** Preview and beta models may have different data retention
policies than production models. Providers often use beta API inputs for
model training.

**Requirement:** PII must be scrubbed before sending prompts to frontier tier
unless the operator has verified the provider's data handling policy.
```

### Static Pool (Fallback)

```python
DEFAULT_TIER_MODEL_POOLS = {
    # ... existing tiers ...
    "frontier": [
        "openai/gpt-5.2-pro",
        "anthropic/claude-opus-4.5",
        "google/gemini-3-pro-preview",
        "x-ai/grok-4",
        "deepseek/deepseek-r1",
    ],
}
```

### Configuration

```yaml
council:
  tiers:
    pools:
      frontier:
        models:
          - openai/gpt-5.2-pro
          - anthropic/claude-opus-4.5
          - google/gemini-3-pro-preview
        timeout_seconds: 300
        allow_preview: true
        allow_beta: true
        voting_authority: advisory  # Shadow mode default
        cost_ceiling_multiplier: 5.0
        fallback_tier: high

    graduation:
      min_age_days: 30
      min_completed_sessions: 100
      max_error_rate: 0.02
      min_quality_percentile: 0.75
```

---

## Consequences

### Positive
- Safe environment for evaluating new models before production use
- Clear promotion path: frontier → high with explicit criteria
- Enables early adoption of cutting-edge capabilities
- Separates experimentation from production
- Shadow Mode protects council consensus from experimental failures

### Negative
- Additional tier to maintain
- Frontier results may be less reliable
- Users must understand tier semantics
- Shadow Mode means frontier responses don't influence final decisions

### Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Hallucinating model poisons consensus | Shadow Mode (advisory only) |
| Cost overruns from volatile pricing | Cost ceiling (5x high-tier avg) |
| Preview model deprecation mid-evaluation | Hard fallback to high tier |
| Data privacy with beta APIs | PII scrubbing requirement |
| Reasoning/frontier tier confusion | Explicit precedence rules |

---

## Implementation

### Files to Modify
1. `src/llm_council/config.py` - Add frontier to DEFAULT_TIER_MODEL_POOLS
2. `src/llm_council/metadata/selection.py` - Add frontier to TIER_WEIGHTS (revised values)
3. `src/llm_council/tier_contract.py` - Support frontier tier contracts
4. `src/llm_council/council.py` - Implement Shadow Mode voting authority
5. `src/llm_council/metadata/intersection.py` - NEW: Tier intersection logic
6. `src/llm_council/metadata/types.py` - Add `is_preview`, `supports_reasoning` fields
7. `src/llm_council/frontier_fallback.py` - Add event emission for fallbacks

### Validation
- [x] Tests for `select_tier_models(tier="frontier")`
- [x] Tests for frontier tier weights
- [x] Tests for frontier tier contract creation
- [x] Tests for Shadow Mode voting (Issue #110, #111)
- [x] Tests for graduation criteria (Issue #112)
- [x] Tests for cost ceiling (Issue #113)
- [x] Tests for hard fallback (Issue #114)
- [x] Document frontier tier in CLAUDE.md

### Gap Remediation (Peer Review 2025-12-24)
- [x] Tier intersection logic (Issue #119) - `resolve_tier_intersection()` in `metadata/intersection.py`
- [x] Shadow votes integration (Issue #117) - Wired into `run_council_with_fallback`, events emitted
- [x] Fallback wrapper integration (Issue #118) - Event emission in `execute_with_fallback_detailed`

### Observability

```python
# Metrics to emit
frontier.model.selected{model_id}
frontier.model.shadow_vote{model_id, agreed_with_consensus}
frontier.model.fallback_triggered{model_id, reason}
frontier.model.cost_ceiling_exceeded{model_id}
frontier.graduation.candidate{model_id}
frontier.graduation.promoted{model_id}
```

---

## References

- [ADR-022: Tiered Model Selection](./ADR-022-tiered-model-selection.md)
- [ADR-026: Dynamic Model Intelligence](./ADR-026-dynamic-model-intelligence.md)
