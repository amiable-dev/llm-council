# ADR-022: Tiered Model Selection for Confidence Levels

**Status:** Phase 1 Implemented (Council: Conditional Approval)
**Date:** 2025-12-22
**Decision Makers:** Engineering, Architecture
**Council Review:** Completed - All 4 models responded
**Layer Assignment:** Layer 1 - Tier Selection (per ADR-024)

---

## Layer Context (ADR-024)

This ADR operates at **Layer 1** in the unified routing architecture:

| Layer | ADR | Responsibility |
|-------|-----|----------------|
| **L1** | **ADR-022** | **Tier Selection (quick/balanced/high/reasoning)** |
| L2 | ADR-020 | Query Triage & Model Selection |
| L3 | Core | Council Execution (Stage 1-3) |
| L4 | ADR-023 | Gateway Routing |

**Interaction Rules:**
- Layer 1 creates `TierContract` defining allowed models, timeouts, and constraints
- Layer 1 supports explicit tier selection (user specifies) or auto mode (defers to Layer 2)
- Tier escalation is explicit and logged; never silent
- Layer 1 outputs `TierContract` to Layer 2

---

## Context

The LLM Council currently uses the same set of high-capability models (GPT-5.2-pro, Claude Opus 4.5, Gemini 3 Pro, Grok-4) regardless of the confidence level selected. This creates inefficiencies:

### Current State

| Confidence Level | Models Used | Timeout | Actual Need |
|------------------|-------------|---------|-------------|
| **quick** | First 2 of default council | 30s | Fast models needed |
| **balanced** | First 3 of default council | 90s | Mid-tier models sufficient |
| **high** | All 4 default models | 180s | Full capability justified |
| **reasoning** | All 4 default models | 600s | Deep reasoning required |

### Problems

1. **Latency mismatch**: Quick/balanced tiers use slow reasoning models, defeating the purpose
2. **Cost inefficiency**: GPT-5.2-pro costs ~10x more than GPT-4o-mini for simple queries
3. **Timeout pressure**: Heavy models often timeout even in "quick" mode
4. **Wasted capability**: Simple factual queries don't benefit from reasoning models

### Related Work

- **ADR-012**: Established tier-sovereign timeout architecture
- **ADR-020**: Proposed Not Diamond integration for intelligent routing
  - Tier 1 triage could classify query complexity
  - Dynamic model selection based on query requirements

---

## Decision

Implement **Tier-Appropriate Model Pools** where each confidence level uses models optimized for its latency and capability requirements.

### Proposed Model Tiers

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  QUICK TIER (30s budget)                                                     │
│  Goal: Fast responses for simple queries                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│  Models: GPT-4o-mini, Claude Haiku 3.5, Gemini 2.0 Flash                    │
│  Characteristics: <5s latency, low cost, good for factual/simple tasks      │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  BALANCED TIER (90s budget)                                                  │
│  Goal: Good quality with reasonable latency                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│  Models: GPT-4o, Claude Sonnet 3.5, Gemini 1.5 Pro                          │
│  Characteristics: 10-20s latency, moderate cost, good reasoning             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  HIGH TIER (180s budget)                                                     │
│  Goal: Full council deliberation                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│  Models: GPT-4o, Claude Opus 4.5, Gemini 3 Pro, Grok-4                      │
│  Characteristics: 20-60s latency, higher cost, full capability              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  REASONING TIER (600s budget)                                                │
│  Goal: Deep reasoning for complex problems                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│  Models: GPT-5.2-pro, Claude Opus 4.5, o1-preview, DeepSeek-R1              │
│  Characteristics: 60-300s latency, highest cost, chain-of-thought           │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Configuration

```python
# config.py
TIER_MODEL_POOLS = {
    "quick": [
        "openai/gpt-4o-mini",
        "anthropic/claude-3-5-haiku-20241022",
        "google/gemini-2.0-flash-001",
    ],
    "balanced": [
        "openai/gpt-4o",
        "anthropic/claude-3-5-sonnet-20241022",
        "google/gemini-1.5-pro",
    ],
    "high": [
        "openai/gpt-4o",
        "anthropic/claude-opus-4-5-20250514",
        "google/gemini-3-pro",
        "x-ai/grok-4",
    ],
    "reasoning": [
        "openai/gpt-5.2-pro",
        "anthropic/claude-opus-4-5-20250514",
        "openai/o1-preview",
        "deepseek/deepseek-r1",
    ],
}

# Environment override pattern
# LLM_COUNCIL_MODELS_QUICK="model1,model2,model3"
# LLM_COUNCIL_MODELS_BALANCED="model1,model2,model3"
```

### Integration with ADR-020 (Not Diamond)

The tiered model selection complements Not Diamond integration:

| ADR-020 Component | Interaction with ADR-022 |
|-------------------|--------------------------|
| **Tier 1 Triage** | Not Diamond classifies complexity → selects appropriate tier |
| **Tier 3 Wildcard** | Wildcard selection from tier-appropriate pool |
| **Routing** | Use tier as input signal to Not Diamond router |

```python
# Combined approach
async def route_query(query: str, confidence: str = "auto") -> Response:
    if confidence == "auto":
        # Not Diamond determines appropriate tier
        complexity = await not_diamond.classify_complexity(query)
        confidence = complexity_to_tier(complexity)

    models = TIER_MODEL_POOLS[confidence]
    timeout_config = get_tier_timeout(confidence)

    return await run_council(query, models=models, **timeout_config)
```

---

## Alternatives Considered

### Alternative 1: Single Model Pool (Status Quo)

**Current approach**: Use same models for all tiers, just vary count and timeout.

**Rejected because**:
- Wastes resources on simple queries
- Fast tiers often timeout with slow models
- No cost optimization

### Alternative 2: User-Specified Models Only

**Approach**: Let users specify exact models per query.

**Rejected because**:
- Poor UX for most use cases
- Requires deep model knowledge
- No sensible defaults

### Alternative 3: Dynamic Selection Per Query

**Approach**: Analyze each query and select models dynamically.

**Partially adopted**: This is what Not Diamond provides. ADR-022 provides sensible defaults while ADR-020 enables dynamic override.

---

## Implementation Phases

### Phase 1: Default Tier Pools - COMPLETE
- [x] Add `TIER_MODEL_POOLS` to config.py
- [x] Update `run_council_with_fallback()` to use tier-appropriate models
- [x] Add environment variable overrides
- [x] Create `TierContract` dataclass with `create_tier_contract()` factory
- [x] Update `consult_council` MCP tool to use tier contracts
- [x] Add tier info to response metadata

### Phase 2: MCP Integration - COMPLETE (merged into Phase 1)
- [x] Update `consult_council` tool to use tier pools
- [x] Add `models` parameter for explicit override
- [x] Metadata includes tier information

### Phase 3: Auto-Tier Selection (Future, with ADR-020)
- [ ] Integrate Not Diamond complexity classification
- [ ] Add `confidence="auto"` mode
- [ ] Implement fallback when classification unavailable

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Quality degradation in quick tier | Medium | High | Clear documentation, user can override |
| Model availability varies | Medium | Medium | Fallback to next-tier models |
| Configuration complexity | Low | Medium | Sensible defaults, simple override syntax |
| Cost savings not realized | Low | Medium | Metrics tracking per tier |

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Quick tier P50 latency | <5s | Time to first response |
| Quick tier cost | -80% vs current | Compare to reasoning-model cost |
| Balanced tier completion rate | >95% | Responses within timeout |
| User satisfaction | No degradation | Quality ratings per tier |

---

## Configuration Options

```bash
# Per-tier model pools (comma-separated)
LLM_COUNCIL_MODELS_QUICK="openai/gpt-4o-mini,anthropic/claude-3-5-haiku-20241022"
LLM_COUNCIL_MODELS_BALANCED="openai/gpt-4o,anthropic/claude-3-5-sonnet-20241022"
LLM_COUNCIL_MODELS_HIGH="openai/gpt-4o,anthropic/claude-opus-4-5-20250514,google/gemini-3-pro"
LLM_COUNCIL_MODELS_REASONING="openai/gpt-5.2-pro,anthropic/claude-opus-4-5-20250514,openai/o1-preview"

# Auto-tier selection (requires Not Diamond, ADR-020)
LLM_COUNCIL_AUTO_TIER=true|false  # default: false
```

---

## Open Questions for Council Review

1. **Should quick tier skip peer review entirely?** Fast models + peer review may still exceed 30s budget.

2. **Is 3 models sufficient for quick/balanced tiers?** Reduces latency but also diversity of perspective.

3. **Should reasoning tier include non-reasoning models?** Claude Opus provides good reasoning without o1's latency.

4. **How should tier selection interact with Not Diamond routing?** Use Not Diamond for intra-tier selection only, or let it override tier entirely?

---

---

## Council Review Summary

**Status:** CONDITIONAL APPROVAL (Requires modifications)

**Reviewed by**: Claude Opus 4.5 (142s), Grok-4 (143s), GPT-5.2-pro (144s), Gemini 3 Pro (155s)

**Council Verdict**: All 4 models responded with unanimous agreement on core principles.

---

### Consensus Answers to Key Questions

#### 1. Should the quick tier skip peer review entirely?

**Verdict: No - implement lightweight "sanity check" instead**

Skipping peer review entirely creates unacceptable risk of confident-but-wrong responses. The council recommends:

- **Lead + Critic Topology**: 3 models generate in parallel, aggregator selects best, single "critic" does safety/hallucination check
- **Budget Allocation**: ~15-20s generation, ~5-8s review, ~5s synthesis
- **Escalation on Failure**: If critic flags issues, escalate to balanced tier rather than attempting repair

```python
class QuickTierPeerReview:
    async def quick_review(self, response, context) -> ReviewResult:
        review = await self.fast_model.complete(
            checks=["factual_red_flags", "logical_consistency", "query_alignment"],
            max_tokens=200,
            timeout_seconds=6
        )
        return ReviewResult(
            approved=review.no_red_flags,
            escalate=review.confidence < 0.7
        )
```

#### 2. Is 3 models sufficient for quick/balanced tiers?

**Verdict: Yes, with mandatory diversity constraints**

| Tier | Model Count | Constraint |
|------|-------------|------------|
| Quick | 3 | Speed dominant; escalation path exists |
| Balanced | 4-5 | Sweet spot for diversity within 60s budget |
| High | 5-7 | Quality dominant; can parallelize efficiently |
| Reasoning | 3-4 | Quality over quantity; expensive models |

**Hard requirement**: Never allow all models from same provider. Minimum 2 vendors for quick tier, 3 for balanced+.

#### 3. Should reasoning tier include non-reasoning models?

**Verdict: Yes - as complementary roles, not primary reasoners**

Reasoning models (o1) have known failure modes: overthinking, getting lost in reasoning chains. Non-reasoning models provide grounding.

```python
REASONING_TIER_COMPOSITION = {
    "primary_reasoning": ["o1", "gpt-5.2-pro", "deepseek-r1"],
    "complementary_non_reasoning": ["claude-opus-4.5"],
    "minimum_reasoning_ratio": 0.6,  # At least 60% reasoning models
    "required_non_reasoning": 1,      # At least 1 for perspective
}
```

**Roles for non-reasoning models**:
- Editor/rewriter for clarity
- Adversarial critic for edge cases
- Safety/policy review
- "Did we actually answer the question?" check

#### 4. Tier selection vs Not Diamond routing?

**Verdict: Tier defines constraints; Not Diamond optimizes within constraints**

```
User Query → Tier Selection (ADR-022) → Tier Pool
                    │                        │
                    └─────────┬──────────────┘
                              ▼
               Not Diamond Routing (ADR-020)
               [Input: Query + Tier Pool]
               [Output: Ranked models from pool]
               [Constraint: Must stay in pool]
```

**Override rules**:
- Not Diamond can *recommend* escalation, not force it
- Escalation requires explicit logging and user notification
- Never silently pick reasoning-tier model when user requested quick

#### 5. Underestimated risks?

| Risk | Severity | Mitigation |
|------|----------|------------|
| **Tail latency/retry blowups** | High | P95 constraints, not averages; hard deadlines |
| **Model pool staleness** | High | Weekly fitness evaluation; dynamic pool updates |
| **Failure mode correlation** | High | Cross-provider diversity; failure mode tagging |
| **Prompt/schema portability** | Medium | Model Abstraction Layer with per-model adapters |
| **Escalation spirals** | Medium | Track escalation rate as first-class metric |
| **Quality cliff at tier boundaries** | Medium | Soft tier boundaries with blending |
| **Tier gaming** | Medium | Monitor escalation rate and complexity mismatch |

---

### Architectural Recommendations from Council

#### 1. Define a Tier Contract Object

```python
@dataclass
class TierContract:
    tier: str  # quick|balanced|high|reasoning
    deadline_ms: int
    token_budget: int
    max_attempts: int
    requires_peer_review: bool
    requires_verifier: bool
    allowed_pools: List[str]
    override_policy: Dict[str, bool]  # can_escalate, can_deescalate
```

#### 2. Latency Constraints at P95, Not Averages

```python
def validate_model_for_tier(model, tier, recent_latencies) -> bool:
    p95 = np.percentile(recent_latencies, 95)
    p99 = np.percentile(recent_latencies, 99)
    model_budget = tier.latency_budget_seconds * 0.6

    return p95 <= model_budget and p99 <= model_budget * 1.5
```

#### 3. Aggregator Must Scale with Tier

| Tier | Aggregator | Rationale |
|------|------------|-----------|
| Quick | gpt-4o-mini | Speed-matched |
| Balanced | gpt-4o | Quality-matched |
| Reasoning | claude-opus | Can understand o1 outputs |

**Warning**: Do not use a "mini" model to aggregate reasoning model outputs.

#### 4. Prompt Transpiler for Reasoning Models

- Standard models: Full system prompt + persona
- Reasoning models (o1): Strip system prompt; convert persona to user-message constraint

---

### Implementation Revision (Council-Informed)

| Phase | Original | Council Revision |
|-------|----------|------------------|
| Phase 1 | Default tier pools | Add P95 latency validation + diversity constraints |
| Phase 2 | MCP integration | Add lightweight verifier for quick tier |
| Phase 3 | Auto-tier selection | Add soft tier boundaries + escalation logging |

### Rollback Triggers

```yaml
automatic_rollback:
  quick_tier:
    - escalation_rate > 30%
    - p95_latency > 35s
  balanced_tier:
    - quality_score_drop > 10%
    - timeout_rate > 15%
  all_tiers:
    - single_provider_failure_cascade
    - aggregator_discarding_correct_answers
```

---

## References

### Related ADRs (Unified Routing Architecture)
- [ADR-020: Not Diamond Integration Strategy](./ADR-020-not-diamond-integration-strategy.md) - Layer 2 (Query Triage)
- [ADR-023: Multi-Router Gateway Support](./ADR-023-multi-router-gateway-support.md) - Layer 4 (Gateway Routing)
- [ADR-024: Unified Routing Architecture](./ADR-024-unified-routing-architecture.md) - Coordination layer

### Other References
- [ADR-012: MCP Server Reliability](./ADR-012-mcp-server-reliability.md)
- [OpenRouter Model Pricing](https://openrouter.ai/models)
