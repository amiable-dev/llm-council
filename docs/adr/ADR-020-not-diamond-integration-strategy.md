# ADR-020: Not Diamond Integration Strategy for LLM Council Ecosystem

**Status:** Tier 1-3 Implemented (v0.12.0)
**Date:** 2025-12-19 (Updated: 2025-12-22)
**Decision Makers:** Engineering, Architecture
**Council Review:** Completed (GPT-5.2-pro, Claude Opus 4.5, Gemini 3 Pro, Grok-4)
**Layer Assignment:** Layer 2 - Query Triage & Model Selection (per ADR-024)

---

## Layer Context (ADR-024)

This ADR operates at **Layer 2** in the unified routing architecture:

| Layer | ADR | Responsibility |
|-------|-----|----------------|
| L1 | ADR-022 | Tier Selection (quick/balanced/high/reasoning) |
| **L2** | **ADR-020** | **Query Triage & Model Selection** |
| L3 | Core | Council Execution (Stage 1-3) |
| L4 | ADR-023 | Gateway Routing |

**Interaction Rules:**
- Layer 2 receives `TierContract` from Layer 1 (models MUST come from `TierContract.allowed_pools`)
- Layer 2 can RECOMMEND tier escalation, not force it
- Escalation requires explicit user notification
- Layer 2 outputs `TriageResult` to Layer 3

---

### Implementation Status

| Tier | Component | Status |
|------|-----------|--------|
| Tier 3 | Wildcard Selection | **Implemented (v0.8.0)** |
| Tier 2 | Prompt Optimization | **Implemented (v0.8.0)** |
| Tier 1 | Confidence-Gated Fast Path | **Implemented (v0.12.0)** |
| Tier 1 | Shadow Council Sampling | **Implemented (v0.12.0)** |
| Tier 1 | Rollback Metric Tracking | **Implemented (v0.12.0)** |
| Tier 1 | Not Diamond API Integration | **Implemented (v0.12.0)** - Optional, graceful fallback to heuristics |

---

## Context

Not Diamond (notdiamond.ai) offers AI optimization capabilities that could complement or enhance the LLM Council ecosystem:

### Not Diamond Capabilities

| Capability | Description |
|------------|-------------|
| **Prompt Adaptation** | Automatically optimizes prompts to improve accuracy and adapt to new models |
| **Model Routing** | Intelligent query routing based on complexity, cost, and latency preferences |
| **Custom Routers** | Train personalized routing models on evaluation datasets |
| **Multi-SDK Support** | Python, TypeScript, and REST API integrations |

### Current LLM Council Architecture

The LLM Council uses a 3-stage deliberation process:

1. **Stage 1**: Parallel queries to 4 fixed models (GPT-5.2-pro, Gemini 3 Pro, Claude Opus 4.5, Grok-4)
2. **Stage 2**: Anonymized peer review with Borda count ranking
3. **Stage 3**: Chairman synthesis of consensus response

### Integration Opportunities

| System | Potential Integration |
|--------|----------------------|
| **llm-council** (library) | Pre-council routing, prompt optimization, dynamic model selection |
| **council-cloud** (service) | Tiered routing for cost optimization, A/B testing model combinations |

---

## Decision

Implement a **Hybrid Augmentation Strategy** where Not Diamond enhances rather than replaces the council's consensus mechanism.

### Recommended Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         TIER 1: TRIAGE LAYER                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│  Not Diamond Complexity Classifier                                           │
│  ├── Simple queries → Single best model (bypass council, 70% cost savings)  │
│  ├── Medium queries → Lite council (2 models + synthesis)                   │
│  └── Complex queries → Full council (4 models + peer review)                │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         TIER 2: PROMPT OPTIMIZATION                          │
├─────────────────────────────────────────────────────────────────────────────┤
│  Not Diamond Prompt Adaptation (applied before council stage)                │
│  ├── Reduces variance between model responses                               │
│  ├── Improves consensus quality                                             │
│  └── Adapts queries to model-specific strengths                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         TIER 3: DYNAMIC COUNCIL                              │
├─────────────────────────────────────────────────────────────────────────────┤
│  3 Fixed Anchor Models + 1 Wildcard Seat                                     │
│  ├── Anchors: GPT-5.2-pro, Gemini 3 Pro, Claude Opus 4.5                   │
│  └── Wildcard: Not Diamond selects specialist (coding, math, creative)      │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Integration Points

### 1. Pre-Council Triage (council-cloud)

```python
# Pseudocode for tiered routing
async def route_query(query: str) -> CouncilResponse:
    complexity = await not_diamond.classify_complexity(query)

    if complexity == "simple":
        model = await not_diamond.route(query, optimize="cost")
        return await query_single_model(model, query)

    elif complexity == "medium":
        return await run_lite_council(query, models=2)

    else:  # complex
        return await run_full_council(query)
```

**Expected Savings**: 60-80% cost reduction on simple queries (estimated 40% of traffic)

### 2. Prompt Optimization (llm-council)

```python
# Apply before Stage 1
async def stage1_with_optimization(query: str) -> List[Response]:
    optimized = await not_diamond.adapt_prompt(
        prompt=query,
        target_models=COUNCIL_MODELS,
        metric="semantic_similarity"
    )
    return await stage1_collect_responses(optimized)
```

**Expected Benefit**: Reduced response variance, improved consensus quality

### 3. Dynamic Wildcard Selection (llm-council)

```python
# Configuration option for dynamic 4th seat
COUNCIL_MODELS = [
    "openai/gpt-5.2-pro",       # Anchor
    "google/gemini-3-pro",       # Anchor
    "anthropic/claude-opus-4.5", # Anchor
    "dynamic:not-diamond",       # Wildcard - selected per query
]
```

**Expected Benefit**: Specialized expertise without manual model selection

---

## API Integration Details

### Not Diamond Endpoints

| Endpoint | Purpose | Integration Point |
|----------|---------|-------------------|
| `POST /v2/prompt/adapt` | Prompt optimization | Pre-Stage 1 |
| `POST /v2/modelRouter/modelSelect` | Model routing | Triage layer |
| `POST /v2/pzn/trainCustomRouter` | Custom router training | council-cloud analytics |

### Authentication

```bash
export NOT_DIAMOND_API_KEY="your-key"
```

### SDK Installation

```bash
pip install notdiamond  # Python SDK
```

---

## Alternatives Considered

### Alternative 1: Full Replacement (Use Not Diamond Instead of Council)

**Rejected**: Loses the peer review consensus mechanism that provides:
- Hallucination reduction through cross-validation
- Nuanced disagreement detection
- Transparency via inspectable rankings

### Alternative 2: No Integration (Status Quo)

**Rejected**: Misses cost optimization opportunities. Current fixed council costs ~$0.08-0.15 per query regardless of complexity.

### Alternative 3: Post-Council Routing Only

**Rejected**: Doesn't address the primary cost driver (running all 4 models on every query).

---

## Implementation Phases

### Phase 1: Evaluation (2 weeks)
- [ ] A/B test Not Diamond routing accuracy vs. council consensus
- [ ] Measure latency overhead of routing layer
- [ ] Calculate cost savings on production traffic sample

### Phase 2: Triage Integration (3 weeks)
- [ ] Implement complexity classifier wrapper
- [ ] Add `LLM_COUNCIL_ROUTING_MODE` config option
- [ ] Create lite council mode (2 models)

### Phase 3: Prompt Optimization (2 weeks)
- [ ] Integrate prompt adaptation API
- [ ] Benchmark variance reduction
- [ ] Add `LLM_COUNCIL_PROMPT_OPTIMIZATION` config option

### Phase 4: Dynamic Wildcard (3 weeks)
- [ ] Implement wildcard model selection
- [ ] Train custom router on council evaluation data
- [ ] A/B test wildcard vs. fixed 4th seat

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Routing accuracy < council accuracy | Medium | High | A/B test with fallback to full council |
| Added latency from routing layer | Medium | Medium | Cache routing decisions for similar queries |
| Vendor lock-in to Not Diamond | Low | Medium | Abstract behind interface, maintain bypass option |
| Prompt optimization changes intent | Low | High | Validate optimized prompts preserve semantics |

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Cost per query (avg) | -50% | Compare pre/post monthly costs |
| Simple query latency | -60% | P50 latency for routed queries |
| Council consensus quality | No degradation | Measure disagreement rate |
| Routing accuracy | >95% | Compare routed model vs. council winner |

---

## Configuration Options

```bash
# Triage routing mode
LLM_COUNCIL_ROUTING_MODE=auto|full|lite|bypass  # default: full

# Prompt optimization
LLM_COUNCIL_PROMPT_OPTIMIZATION=true|false  # default: false

# Dynamic wildcard
LLM_COUNCIL_WILDCARD_MODEL=dynamic|<model-id>  # default: x-ai/grok-4

# Not Diamond API key (required for routing/optimization)
NOT_DIAMOND_API_KEY=<key>
```

---

## Council Review Summary

**Status:** CONDITIONAL ACCEPTANCE (Requires architectural changes to Tier 1 and Tier 2)

**Reviewed by**: GPT-5.2-pro (109s), Claude Opus 4.5 (64s), Gemini 3 Pro (31s), Grok-4 (72s)

**Council Verdict**: All 4 models responded. Unanimous agreement on:
- **Tier 3 (Wildcard)**: APPROVED - Strongest value proposition
- **Tier 2 (Prompt Optimization)**: APPROVED WITH MODIFICATIONS
- **Tier 1 (Triage)**: REDESIGN REQUIRED - Primary risk to consensus integrity

---

### Consensus Answers to Key Questions

#### 1. Does triage routing compromise consensus quality?
**Yes, significantly—if implemented as a simple filter.**

All respondents agree that pre-classifying a query as "simple" is error-prone. The council unanimously recommends:

- **Confidence-Gated Routing**: Don't route based on query complexity; route based on model's self-reported confidence AFTER attempting an answer
- **Shadow Council**: Random 5% sampling of triaged queries through full council to measure "regret rate"
- **Escalation Threshold**: Only bypass council if confidence > 0.92 AND complexity_score < 0.3

```yaml
tier_1_redesign:
  name: "Confidence-Gated Fast Path"
  flow:
    1. Route to single model via Not Diamond
    2. Model responds WITH calibrated confidence score
    3. Gate decision:
       - confidence >= 0.92 AND low_risk: Return single response
       - else: Escalate to full council
  audit: 5% shadow council sampling
  cost_savings: ~45-55% (lower but safer than 70%)
```

#### 2. Is prompt optimization valuable for multi-model scenarios?
**Yes, but only as "Translation," not "Rewriting."**

Council consensus: Apply **Per-Model Adaptation** while maintaining semantic equivalence.

- **Do**: Format prompts for model preferences (Claude's XML vs GPT's Markdown)
- **Don't**: Globally optimize prompts that may favor one model's style
- **Constraint**: Verify semantic equivalence (cosine similarity > 0.93) across adapted prompts

```python
# Council-recommended approach
class CouncilPromptOptimizer:
    def optimize(self, prompt: str, models: list) -> dict:
        canonical = self.extract_intent(prompt)  # Immutable core
        adapted = {m: self.adapt_syntax(canonical, m) for m in models}
        if not self.verify_equivalence(adapted.values()):
            return {m: prompt for m in models}  # Fallback to original
        return adapted
```

#### 3. Should the wildcard seat be domain-specialized or general?
**Domain-Specialized** (unanimous)

Adding another generalist yields diminishing returns. Council recommends:

- **Specialist Pool**: DeepSeek (code), Med-PaLM (health), o1-preview (reasoning)
- **Diversity Constraint**: Wildcard must differ from base council on model family, training methodology, or architecture
- **Fallback**: If specialist unavailable, use quantized generalist (Llama 3)

#### 4. What risks are underestimated?

| Risk | Severity | Mitigation |
|------|----------|------------|
| **Latency Stacking** | High | Pre-warm specialists, cache optimizations |
| **Router Bias/Drift** | High | Shadow evaluation, drift monitoring |
| **Correlated Failures** | Medium | Enforce diversity constraints on wildcard |
| **Aggregation Breakage** | Medium | Require consistent JSON schema from all seats |
| **Security (Prompt Injection)** | Medium | Routing decisions should not be influenced by query content |
| **Reproducibility Gaps** | Medium | Log task_spec_id, routing decision, model versions |

---

### Architectural Recommendations from Council

#### 1. Redesign Tier 1: "Confidence Circuit" (not complexity filter)

```
Request → [Single Model] → Check Confidence
   If Confidence > 90% AND Safety_Flag == False → Return Response
   Else → Forward to [Full Council]

Audit: 5% shadow sampling to measure regret rate
Rollback trigger: shadow_council_disagreement_rate > 8%
```

#### 2. Refine Tier 2: "Adapter Pattern" (not rewriting)

- Create **Canonical Task Spec** (immutable intent)
- Apply syntactic adapters per model
- Verify semantic equivalence before sending
- Monitor for consensus rate changes (either direction is suspicious)

#### 3. Harden Tier 3: "Specialist Pool" with constraints

```yaml
wildcard_configuration:
  pool:
    - code: deepseek-v3, codestral
    - reasoning: o1-preview, deepseek-r1
    - creative: claude-opus, command-r
    - multilingual: gpt-4, command-r

  constraints:
    - must_differ_from_base_council: [family, training, architecture]
    - timeout_fallback: llama-3-70b
    - max_selection_latency: 200ms
```

#### 4. Council Orchestrator Architecture

```
1. Ingress → Authenticate, rate-limit, attach tenant policy
2. Normalize → Canonical Task Spec (log task_spec_id)
3. Safety Gate → Classify risk tier, enforce allowed models
4. Triage Decision → Not Diamond + local heuristics
5. Execute → Single model OR council (3 fixed + 1 wildcard)
6. Aggregate → Structured decision with dissent summary
7. Post-process → Schema validation, emit metrics, store audit bundle
```

---

### Implementation Revision (Council-Informed)

| Phase | Original | Council Revision |
|-------|----------|------------------|
| Phase 1 | Evaluation (2 weeks) | **Tier 3 only** - Lowest risk, highest value |
| Phase 2 | Triage Integration | **Add Tier 2** - Prompt optimization with adapters |
| Phase 3 | Prompt Optimization | **Tier 1 v2** - Confidence-gated routing with heavy monitoring |
| Phase 4 | Dynamic Wildcard | **Continuous optimization** bounded by SLOs |

---

### Rollback Triggers (Council-Defined)

```yaml
automatic_rollback:
  tier_1:
    - shadow_council_disagreement_rate > 8%
    - user_escalation_rate > 15%
    - error_report_rate > baseline * 1.5
  tier_2:
    - consensus_rate_change > 10%
    - prompt_divergence > 0.2
  tier_3:
    - wildcard_timeout_rate > 5%
    - wildcard_disagreement_rate < 20%  # Not adding value if always agrees
```

---

## References

### Related ADRs (Unified Routing Architecture)
- [ADR-022: Tiered Model Selection](./ADR-022-tiered-model-selection.md) - Layer 1 (Tier Selection)
- [ADR-023: Multi-Router Gateway Support](./ADR-023-multi-router-gateway-support.md) - Layer 4 (Gateway Routing)
- [ADR-024: Unified Routing Architecture](./ADR-024-unified-routing-architecture.md) - Coordination layer

### Other References
- [Not Diamond Documentation](https://docs.notdiamond.ai/docs/what-is-not-diamond)
- [Not Diamond API Reference](https://docs.notdiamond.ai/reference/adapt_prompt_v2_prompt_adapt_post)
- [ADR-012: MCP Server Reliability](./ADR-012-mcp-server-reliability.md)
- [ADR-015: Bias Auditing](./ADR-015-bias-auditing.md)
