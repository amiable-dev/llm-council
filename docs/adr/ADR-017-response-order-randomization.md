# ADR-017: Response Order Randomization

**Status:** Accepted → Partially Implemented (2025-12-17) → Amended (2026-08-20, see Amendment 1)
**Date:** 2025-12-13
**Decision Makers:** Engineering
**Related:** ADR-010 (Consensus Mechanisms), ADR-015 (Bias Auditing)

---

## Context

ADR-010 recommended "response order randomization" to "mitigate positional bias." This ADR documents the existing implementation and proposes enhancements for bias tracking.

### The Problem: Position Bias

Research on LLM evaluation shows systematic position bias:

| Bias Type | Description | Typical Effect |
|-----------|-------------|----------------|
| **Primacy bias** | First response rated higher | +0.3-0.5 score points |
| **Recency bias** | Last response rated higher | +0.2-0.4 score points |
| **Middle neglect** | Middle positions underrated | -0.2-0.3 score points |

Without randomization, models presented first (or last) would have an unfair advantage regardless of quality.

### Current Implementation

Response order randomization is **already implemented** in `council.py`:

```python
async def stage2_collect_rankings(user_query: str, stage1_results: List[Dict]):
    # Randomize response order to prevent position bias
    shuffled_results = stage1_results.copy()
    random.shuffle(shuffled_results)

    # Create anonymized labels for responses (Response A, Response B, etc.)
    labels = [chr(65 + i) for i in range(len(shuffled_results))]  # A, B, C, ...
```

---

## Decision

### Status: Already Implemented

The core randomization is implemented and working. This ADR formalizes the design and proposes enhancements.

### Current Behavior

1. **Pre-shuffle**: Stage 1 responses arrive in a deterministic order (based on model list)
2. **Shuffle**: `random.shuffle()` randomizes the order before labeling
3. **Label assignment**: Labels (A, B, C...) are assigned post-shuffle
4. **Reviewer sees**: Randomized order with anonymous labels
5. **De-anonymization**: `label_to_model` mapping allows result reconstruction

### Proposed Enhancements

#### Enhancement 1: Position Tracking for Bias Auditing

Track which position each response was shown in to enable position bias analysis (ADR-015).

```python
async def stage2_collect_rankings(user_query: str, stage1_results: List[Dict]):
    shuffled_results = stage1_results.copy()
    random.shuffle(shuffled_results)

    labels = [chr(65 + i) for i in range(len(shuffled_results))]

    # Track position for bias auditing
    label_to_model = {}
    label_to_position = {}
    for i, (label, result) in enumerate(zip(labels, shuffled_results)):
        label_to_model[f"Response {label}"] = result['model']
        label_to_position[f"Response {label}"] = i  # 0 = first shown

    # ... rest of implementation ...

    return stage2_results, label_to_model, label_to_position, total_usage
```

#### Enhancement 2: Deterministic Randomization (Optional)

For reproducibility in testing/debugging, allow seeding the randomization:

```python
# config.py
RANDOM_SEED = os.getenv("LLM_COUNCIL_RANDOM_SEED")  # None for true random

# council.py
if RANDOM_SEED is not None:
    random.seed(int(RANDOM_SEED))
shuffled_results = stage1_results.copy()
random.shuffle(shuffled_results)
```

#### Enhancement 3: Per-Reviewer Randomization

Currently, all reviewers see the same order. For stronger bias mitigation, randomize per-reviewer:

```python
async def get_reviewer_perspective(reviewer: str, stage1_results: List[Dict]):
    """Generate a unique randomized order for each reviewer."""
    # Seed based on reviewer name for reproducibility
    seed = hash(reviewer) % (2**32)
    rng = random.Random(seed)

    shuffled = stage1_results.copy()
    rng.shuffle(shuffled)

    return shuffled
```

**Trade-off**: This makes cross-reviewer analysis more complex but provides stronger position bias mitigation.

---

## Alternatives Considered

### Alternative 1: No Randomization

Present responses in deterministic order (e.g., alphabetical by model).

**Rejected**: Research clearly shows position bias affects LLM evaluations.

### Alternative 2: Balanced Latin Square

Use a Latin square design where each response appears in each position an equal number of times across reviewers.

**Considered for Future**: Requires coordination across reviewers. Overkill for 3-5 reviewers but valuable for large-scale evaluations.

### Alternative 3: Counterbalancing

For each reviewer, systematically rotate the order.

**Considered for Future**: Similar to Latin square, adds complexity for marginal benefit at small scale.

---

## Implementation Status

> [!NOTE]
> **Superseded by Amendment 1 (2026-08-20).** The table below is the status as
> of 2025-12-17 and is retained for history. See
> [Amendment 1's Implementation Status](#implementation-status-updated) for the
> current one — in particular, per-reviewer randomization is now *declined*
> rather than pending, and persisted position tracking was defective until #611.

| Feature | Status (2025-12-17, historical) | Notes |
|---------|--------|-------|
| Basic randomization | ✅ Implemented | `random.shuffle()` in Stage 2 |
| Anonymous labels | ✅ Implemented | Response A, B, C... |
| Label-to-model mapping | ✅ Implemented | Enhanced format with `display_index` |
| Position tracking | ✅ Implemented (v0.3.0) | Via `display_index` in enhanced format |
| Per-reviewer randomization | ❌ Not yet | See "When More Advanced Tracking is Needed" |
| Deterministic seed option | ❌ Not yet | See "When More Advanced Tracking is Needed" |

### Position Tracking Implementation (v0.3.0)

Position tracking is now implemented via the enhanced `label_to_model` format:

```python
# Enhanced format (v0.3.0+) - includes explicit display_index
label_to_model = {
    "Response A": {"model": "openai/gpt-4", "display_index": 0},
    "Response B": {"model": "anthropic/claude-3", "display_index": 1},
    "Response C": {"model": "google/gemini-pro", "display_index": 2}
}
```

The `derive_position_mapping()` function in `bias_audit.py` extracts position data for ADR-015 bias auditing.

**INVARIANT:** Labels are assigned in lexicographic order corresponding to presentation order (A=0, B=1, etc.). This invariant MUST be maintained by any changes to the anonymization module.

---

## When More Advanced Position Tracking is Needed

Per LLM Council review, the current implementation (single-order randomization with position tracking) is sufficient for MVP. However, separate position tracking mechanisms would be needed for:

### Scenario 1: Per-Reviewer Randomization
If each reviewer sees a different order to further mitigate position bias, the current single `display_index` won't capture reviewer-specific positions.

**Solution:** Add `reviewer_position_mapping: Dict[str, Dict[str, int]]` to track per-reviewer orders.

### Scenario 2: Client-Side Shuffling
If the frontend shuffles response order for UI reasons (e.g., to prevent "first-token loading bias"), the backend `display_index` won't reflect the actual displayed order.

**Solution:** Frontend must report actual display positions back to the backend.

### Scenario 3: Dynamic/Interactive Reordering
If users can manually reorder responses, sort by criteria, or collapse/expand sections, static position tracking breaks.

**Solution:** Log position at interaction time, not at generation time.

### Scenario 4: Multi-Round Re-Presentation
If responses are re-shown in subsequent conversation turns with different ordering, initial position data becomes stale.

**Solution:** Track position per-round, not just per-session.

### Scenario 5: Non-Ordinal Labels
If anonymization evolves to use non-alphabetical labels (GUIDs, colors, random strings), the current `display_index` derivation from label letters would break.

**Solution:** Already mitigated by explicit `display_index` in enhanced format.

---

## Questions for Council Review

1. Is per-reviewer randomization worth the added complexity?
2. Should we implement Latin square balancing for larger councils?
3. How important is deterministic seeding for reproducibility?
4. Should position tracking be mandatory (for ADR-015) or optional?

---

## Council Review Feedback

**Reviewed:** 2025-12-17 (GPT-5.1, Gemini 3 Pro, Claude Sonnet 4.5, Grok 4)

### Verdict: Approved - Position Tracking Essential

The council unanimously approved ADR-017, emphasizing that position tracking is **essential** for ADR-015 bias auditing to function.

### Key Insights

> "Position bias is one of the most well-documented biases in LLM evaluation. Without position tracking, you cannot measure it, and without measuring it, you cannot prove your randomization is working."

### Approved Enhancements (Priority Order)

| Enhancement | Priority | Rationale |
|-------------|----------|-----------|
| **Position Tracking** | **P0 - Required** | Foundation for ADR-015 bias auditing |
| **Deterministic Seeding** | P1 - High | Essential for reproducible testing |
| **Per-Reviewer Randomization** | P2 - Medium | Stronger bias mitigation but adds complexity |
| **Latin Square Balancing** | P3 - Deferred | Only needed for large-scale evaluations |

### Implementation Guidance

1. **Position Tracking Must Return**: Add `label_to_position` to Stage 2 return signature
2. **Store in Metadata**: Position data should be persisted in council result metadata
3. **Seed Configuration**: Add `LLM_COUNCIL_RANDOM_SEED` environment variable for testing

### Cross-ADR Dependencies

```
ADR-017 (Position Tracking)
    │
    ├──► ADR-015 (Bias Auditing) - REQUIRES position data
    │
    └──► ADR-016 (Rubric Scoring) - BENEFITS from position analysis
```

### Code Changes Required

~~Original proposal: Add separate `label_to_position` return value.~~

**Actual Implementation (v0.3.0):** Position data embedded in enhanced `label_to_model` format:

```python
# council.py - Enhanced label_to_model format
label_to_model = {
    f"Response {label}": {"model": result['model'], "display_index": i}
    for i, (label, result) in enumerate(zip(labels, shuffled_results))
}

# bias_audit.py - Extract position mapping
def derive_position_mapping(label_to_model):
    """Supports both enhanced and legacy formats."""
    for label, value in label_to_model.items():
        if isinstance(value, dict):
            position_mapping[value["model"]] = value["display_index"]
        else:
            # Legacy fallback: derive from label letter
            position_mapping[value] = ord(label.split()[-1]) - ord('A')
```

### Status Update

**Status:** Accepted → **Partially Implemented (2025-12-17)**

- ✅ Position tracking: Implemented via `display_index`
- ✅ ADR-015 integration: `derive_position_mapping()` extracts position data
- ❌ Per-reviewer randomization: Not yet needed
- ❌ Deterministic seeding: Not yet needed

---

## Success Metrics

- Position-score correlation < 0.1 (no significant position bias)
- Rankings should be stable across multiple runs (with same content)
- Position bias auditing (ADR-015) shows balanced position distribution

---

## References

- [Position Bias in LLM Evaluation](https://arxiv.org/abs/2306.17491) - Zheng et al.
- [Judging LLM-as-a-Judge with MT-Bench](https://arxiv.org/abs/2306.05685) - Shows position bias effects
- Current implementation: `src/llm_council/council.py:574-590`

---

# Amendment 1 — Per-Reviewer Randomization: Declined (2026-08-20)

**Status:** Accepted (decision: do not implement)
**Amends:** "Enhancement 3", "Scenario 1", the Implementation Status table, and Council Review Question 1
**Issues:** [#592](https://github.com/amiable-dev/llm-council/issues/592) (rubric-criteria order — implemented separately), [#602](https://github.com/amiable-dev/llm-council/issues/602) (closed as superseded by this amendment), [#611](https://github.com/amiable-dev/llm-council/issues/611) (the defect actually worth fixing — fixed)

## Decision

**Do not implement per-reviewer response-order randomization.** Council Review Question 1 — *"Is per-reviewer randomization worth the added complexity?"* — is answered **no**, at the council's operating scale.

"Enhancement 3" and "Scenario 1" remain accurate descriptions of *how* it would be built if the scale ever changes. They are recorded here as **considered and declined**, not as pending work.

## How this was arrived at

An external report ([#592](https://github.com/amiable-dev/llm-council/issues/592)) correctly observed that `stage2_collect_rankings` shuffles once per call and sends the same prompt to every reviewer, so all reviewers see Response A/B/C in identical positions. That observation is true, and this ADR had already anticipated it.

Investigating it produced a more useful result than implementing it would have.

### The measurement instrument was broken

`BiasMetricRecord.position` was documented as *"Display position during peer review (0-indexed)"* but was populated with `enumerate()` over the reviewer's **output ranking**. `bias_amplification.position_alignment` — the metric intended to detect *"agreement that tracks display order"* — was therefore correlating reviewers' rankings against a consensus derived from those same rankings.

Measured on one session where two reviewers agreed strongly and both favoured the model displayed **last** (so display order could not explain their agreement):

| | `position_alignment` | `amplification_suspect` |
|---|---|---|
| before | **+0.993** | **True** (false positive) |
| after | **−0.993** | False |

The sign inverted: the metric reported the opposite of reality, and `llm-council bias-report --amplification` would flag clean sessions. Fixed in [#611](https://github.com/amiable-dev/llm-council/issues/611).

**This is why the ordering mattered.** Shipping per-reviewer randomization first would have been a change whose effect could not be measured, evaluated against an instrument that was inverted.

### The stated blocker did not exist

[#602](https://github.com/amiable-dev/llm-council/issues/602) asserted that a per-reviewer shuffle would *"silently corrupt"* the bias-audit subsystem. That was wrong. `BiasMetricRecord` already carries a per-`(reviewer, model)` position, and `session_agreement_decomposition` already averages positions per model, with a comment explicitly anticipating ADR-017 per-reviewer randomization added during the #437 review. The persistence layer was built for this all along.

## Why declined

1. **It decorrelates rather than cancels.** At N=4–5 reviewers, per-reviewer ordering converts a systematic position effect into noise; it does not remove it. This ADR used precisely this reasoning to defer Latin-square and counterbalancing designs as *"overkill for 3-5 reviewers but valuable for large-scale evaluations."* The same logic applies, only more weakly, to per-reviewer shuffling.

2. **Per-session bias metrics cannot resolve the difference.** CLAUDE.md is explicit that these are anomaly indicators over 4–5 data points, against roughly 30 needed for significance. A change whose benefit is invisible to the project's own instrumentation is hard to justify as anything but rigour theatre.

3. **It would dissolve the metric it is meant to help.** Once every reviewer sees a different order there is no shared display order for agreement to track; averaged per-model positions converge toward `(n−1)/2` and `position_alignment` tends to zero. That is arguably the *correct* end state, but it means the work also requires re-specifying an ADR-047 P4 metric — cost on both sides of the ledger.

4. **The confound it removes has now been made measurable instead.** With #611 fixed, a genuine shared-order effect will show up in `position_alignment` and in `aggregate_position_bias`. Detecting the bias is more valuable at this scale than pre-emptively randomising it away, because detection also tells us whether it exists at all.

## What was done instead

| Change | Status |
|---|---|
| Fix `position` to record display order ([#611](https://github.com/amiable-dev/llm-council/issues/611)) | ✅ Implemented — restores the instrument |
| Randomize **rubric-criteria** order, opt-in ([#592](https://github.com/amiable-dev/llm-council/issues/592)) | ✅ Implemented — no downstream dependents, so it shipped on its own |
| Per-reviewer **response** order ([#602](https://github.com/amiable-dev/llm-council/issues/602)) | ❌ Declined — this amendment |

## Conditions that would reopen this

Revisit if any of these becomes true:

- The council's default tier pool reaches **≥10 reviewers** (i.e. `len(tier_contract.allowed_models) >= 10` for the tier in routine use), where per-reviewer ordering starts to average out rather than merely decorrelate, and where Latin-square balancing also becomes worth reconsidering.
- Post-#611 data shows a **persistent positive `position_alignment`** across many sessions — i.e. the shared-order confound is real and material, not hypothetical.
- The council's output is used for **published benchmarking or comparative model claims**, where methodological rigour is judged independently of its effect size.

## Consequences

- **Positive:** avoids per-reviewer prompt construction in a function that already has two dispatch paths; avoids re-specifying `position_alignment`; keeps the shared-order confound observable rather than hidden.
- **Negative:** a genuine shared-order position effect, if one exists, continues to apply uniformly within a run rather than being spread across reviewers. Accepted knowingly — it is now measurable.
- **Neutral:** no effect on prompt caching either way; stage-2 prompts are a documented ADR-049 cache no-op.

## Implementation Status (updated)

| Feature | Status | Notes |
|---------|--------|-------|
| Basic randomization | ✅ Implemented | `random.shuffle()` in Stage 2, once per call |
| Anonymous labels | ✅ Implemented | Response A, B, C... |
| Label-to-model mapping | ✅ Implemented | Enhanced format with `display_index` |
| Position tracking (per-session audit) | ✅ Implemented (v0.3.0) | `derive_position_mapping` → `run_bias_audit` |
| Position tracking (persisted records) | ✅ Fixed (#611) | Was recording the ranking index; schema `1.2.0` marks the corrected semantic |
| Rubric-criteria order randomization | ✅ Implemented (#592) | Per call, opt-in; distinct from response order |
| Per-reviewer randomization | ❌ **Declined** | This amendment — see "Conditions that would reopen" |
| Deterministic seed option | ❌ Deferred | Still open on its own merits. The 2025-12-17 review rated it P1 and *"essential for reproducible testing"* — that justification is independent of per-reviewer randomization and is NOT retired by this amendment |
| Latin square balancing | ❌ Deferred | Unchanged: overkill at N=4–5 |
