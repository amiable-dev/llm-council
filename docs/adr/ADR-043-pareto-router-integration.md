# ADR-043: OpenRouter Pareto Router Integration

**Status:** Superseded by [ADR-044](./ADR-044-compute-optimal-deliberation.md) 2026-07-03 — was Draft 2026-05-12. `openrouter/pareto-code` remains usable as an ordinary pool entry; the routing intelligence this ADR sought now comes from the in-house index (ADR-044).
**Date:** 2026-05-12
**Decision Makers:** @amiable-dev, LLM Council (Proposed)
**Extends:** ADR-022 (Tiered Model Selection), ADR-023 (Multi-Router Gateway), ADR-028 (Dynamic Candidate Discovery)
**Layer Assignment:** Layer 1 / Layer 4 (Tier Selection + Gateway Routing)

---

## Context

OpenRouter launched the **Pareto Router** (`openrouter/pareto-code`), a meta-model that automatically selects a coding model from a curated shortlist based on a single `min_coding_score` parameter (0–1). It sits on the quality/cost Pareto frontier maintained by Artificial Analysis benchmarks, includes built-in fallback cascading (primary + 2 in-tier siblings), and adds no additional fee.

### Current Architecture

LLM Council selects models via a static-pool-first approach:

```
User Request → L1: Tier Selection (ADR-022) → TierContract (static model list)
             → L2: Triage (ADR-020) → Model filtering
             → L3: Council Execution → parallel queries to named models
             → L4: Gateway Routing (ADR-023) → OpenRouter / Requesty / Direct
```

**Key characteristics:**
- Model pools are defined in `unified_config` per tier (quick/balanced/high/reasoning/frontier)
- ADR-028 added background discovery for dynamic candidate updates, but pools still require manual curation
- ADR-026 added metadata-aware scoring, but candidate sets remain operator-managed
- All council seats are filled with **specific named models**

### Problem Statement

1. **Coding model drift:** The best coding model changes frequently (new releases, benchmark updates). Static pools lag behind the frontier by days or weeks.
2. **Manual curation cost:** Each model refresh requires a registry update, config change, and redeployment.
3. **No coding specialisation signal:** The tier system uses general quality tiers, not coding-specific benchmarks. A model that excels at reasoning may underperform at code generation.
4. **Frontier tracking:** ADR-028's dynamic discovery solves availability awareness but not quality-frontier tracking. Pareto Router externalises this to Artificial Analysis benchmarks.

### Opportunity

The Pareto Router is essentially a **managed coding-model selector** that tracks the quality/cost frontier automatically. Integrating it as a council seat would mean:
- One seat always represents "the best coding model at this price tier" without manual updates
- Built-in fallback cascading at the gateway layer (aligns with ADR-023)
- Coding-specific quality signal via Artificial Analysis benchmarks

### Relationship to Existing ADRs

| ADR | Relationship |
|-----|-------------|
| **ADR-022** (Tier Selection) | Pareto `min_coding_score` maps naturally to council tiers |
| **ADR-023** (Gateway Routing) | Pareto is an OpenRouter feature — uses existing gateway path |
| **ADR-024** (Unified Routing) | Fits cleanly at L1 (tier mapping) and L4 (gateway routing) |
| **ADR-026** (Dynamic Model Intelligence) | Complementary — Pareto externalises frontier tracking for code |
| **ADR-028** (Dynamic Candidate Discovery) | Pareto is a form of delegated discovery — OpenRouter does the curation |
| **ADR-029** (Model Audition) | Pareto selections could feed the audition pipeline for evaluation |
| **ADR-039** (LLMRouter Integration) | Similar "System 1" philosophy — fast routing for known patterns |

---

## Decision

Introduce the OpenRouter Pareto Router as an **optional council seat type** alongside named models, available for coding-focused council sessions.

### Option A: Pareto as a Council Seat (Recommended)

Add `openrouter/pareto-code` as a valid model identifier in tier pools. The council treats it like any other model — it gets a seat, produces a response, participates in peer review, and the chairman synthesises across all responses including the Pareto seat.

```yaml
# unified_config.yaml
tiers:
  pools:
    balanced:
      models:
        - "anthropic/claude-sonnet-4-6"
        - "openai/gpt-5.4"
        - "openrouter/pareto-code"  # Pareto seat — auto-selects best coding model
    high:
      models:
        - "anthropic/claude-opus-4-6"
        - "openai/gpt-5.4-pro"
        - "openrouter/pareto-code"
```

**Pareto score mapping to tiers:**

| Council Tier | `min_coding_score` | Rationale |
|-------------|-------------------|-----------|
| quick       | 0.2               | Cheapest fast coder |
| balanced    | 0.5               | Mid-frontier |
| high        | 0.8               | Strong coder, not necessarily most expensive |
| reasoning   | 0.9               | Near-frontier coding capability |
| frontier    | 1.0 (omitted)     | Best available — default behaviour |

**Implementation:** The `openrouter.py` adapter detects the `openrouter/pareto-code` model ID and injects the `plugins` array with the appropriate `min_coding_score` based on the active tier. The response `model` field reveals which concrete model was selected.

```python
# openrouter.py — Pareto Router support
PARETO_TIER_SCORES = {
    "quick": 0.2,
    "balanced": 0.5,
    "high": 0.8,
    "reasoning": 0.9,
    "frontier": None,  # Omit → defaults to strongest
}

def _build_request_body(model, messages, tier=None, **kwargs):
    body = {"model": model, "messages": messages, **kwargs}
    
    if model == "openrouter/pareto-code" and tier:
        score = PARETO_TIER_SCORES.get(tier)
        if score is not None:
            body["plugins"] = [{"id": "pareto-router", "min_coding_score": score}]
    
    return body
```

### Option B: Pareto as a Wildcard Seat (Alternative)

Instead of a fixed pool member, use Pareto as the **wildcard seat** (ADR-020 concept). One council seat is always filled by the Pareto Router, ensuring diversity — the Pareto selection is unlikely to duplicate a named model already in the pool.

**Pro:** Guaranteed diversity.
**Con:** More complex — requires wildcard seat logic in triage layer.

### Option C: Pareto for Pre-Screening Only (Conservative)

Use Pareto Router outside the council — as a fast pre-screen for coding queries. If the Pareto response meets a quality bar, skip the full council. Otherwise, escalate to multi-model deliberation.

**Pro:** Latency savings for simple coding tasks.
**Con:** Bypasses the core value proposition (multi-model consensus).

---

## Recommended Approach: Option A

Option A is simplest, aligns with existing architecture, and requires minimal code change:

1. **Config change:** Add `openrouter/pareto-code` to relevant tier pools
2. **Adapter change:** ~20 lines in `openrouter.py` to inject the `plugins` array
3. **Logging:** Record the resolved concrete model from the response `model` field for observability
4. **Registry:** Add `openrouter/pareto-code` to `registry.yaml` as a meta-model entry

### Phase 1: Implementation

| Step | Change | Files |
|------|--------|-------|
| 1 | Add Pareto Router to registry as meta-model | `models/registry.yaml` |
| 2 | Detect `pareto-code` in adapter, inject plugins | `openrouter.py` |
| 3 | Log resolved model from response | `openrouter.py` |
| 4 | Add to balanced + high tier pools (not quick/reasoning initially) | Config / env |
| 5 | Add integration test | `tests/` |

### Phase 2: Observability & Evaluation

| Step | Change |
|------|--------|
| 6 | Track which concrete models Pareto selects over time (ADR-029 audition data) |
| 7 | Compare Pareto seat scores against named model seats in peer review |
| 8 | Evaluate whether Pareto selections improve or degrade council consensus quality |

### Phase 3: Expansion (If Phase 2 Positive)

| Step | Change |
|------|--------|
| 9 | Extend to quick + reasoning tiers |
| 10 | Consider Pareto as default wildcard seat for all coding consultations |
| 11 | Propose upstream: request Pareto variants for non-coding tasks (general reasoning, analysis) |

---

## Consequences

### Positive

- **Automatic frontier tracking:** One council seat always represents the current best coding model at its price tier, with no manual intervention
- **Built-in resilience:** Pareto's fallback cascading adds an extra layer of reliability at L4
- **Low implementation cost:** ~20 lines of adapter code + config change
- **Diversity benefit:** Pareto may select a model not already in the pool, increasing response diversity
- **Observability data:** Tracking Pareto's concrete model selections over time provides free market intelligence on the coding model frontier

### Negative

- **Opacity:** The council cannot predict which model will fill the Pareto seat before execution. Peer reviewers evaluate the response without knowing the model (this is actually consistent with ADR-017's anonymisation).
- **Benchmark dependency:** Quality depends on Artificial Analysis benchmarks being accurate and current. If benchmarks lag or are gamed, the Pareto seat degrades.
- **Coding only:** `pareto-code` is coding-specific. Non-coding council sessions cannot use it. If OpenRouter adds a general Pareto variant, this limitation goes away.
- **Duplicate risk:** Pareto might select a model already in the pool (e.g., selecting Claude Opus when it's already a named seat). This wastes a seat on a duplicate perspective. Mitigation: check response `model` field and log duplicates for pool tuning.

### Neutral

- No impact on council sessions that don't include `openrouter/pareto-code` in their tier pools
- No breaking changes to existing configuration
- Existing ADR-028 dynamic discovery continues to operate independently

---

## Compliance / Validation

1. **Integration test:** Mock Pareto Router response with `model` field set to a concrete model; verify adapter correctly injects `plugins` and logs the resolved model
2. **Diversity check:** After 50 coding council sessions, report how often the Pareto seat duplicated a named seat
3. **Quality comparison:** Compare average peer-review scores for Pareto seat vs named seats across coding sessions
4. **Cost tracking:** Verify Pareto selections align with tier cost expectations (ADR-011)

---

## References

- [OpenRouter Pareto Router Docs](https://openrouter.ai/docs/guides/routing/routers/pareto-router)
- [Artificial Analysis Coding Benchmarks](https://artificialanalysis.ai/)
- ADR-022: Tiered Model Selection
- ADR-023: Multi-Router Gateway Support
- ADR-024: Unified Routing Architecture
- ADR-026: Dynamic Model Intelligence
- ADR-028: Dynamic Candidate Discovery
- ADR-029: Model Audition Mechanism
- ADR-039: LLMRouter Integration
