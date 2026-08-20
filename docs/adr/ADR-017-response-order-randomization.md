# ADR-017: Response Order Randomization

**Status:** Accepted → Partially Implemented (2025-12-17)
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

| Feature | Status | Notes |
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

# Amendment 1 — Per-Reviewer Randomization (2026-08-20)

**Status:** Proposed
**Amends:** "Enhancement 3", "Scenario 1", the Implementation Status table, and Council Review Question 1
**Issues:** [#592](https://github.com/amiable-dev/llm-council/issues/592) (rubric-criteria order, shipped separately), [#602](https://github.com/amiable-dev/llm-council/issues/602) (this amendment), [#611](https://github.com/amiable-dev/llm-council/issues/611) (prerequisite)

## Why this amendment exists

An external report ([#592](https://github.com/amiable-dev/llm-council/issues/592)) observed that `stage2_collect_rankings` shuffles once per council call and sends the *same* prompt to every reviewer, so all reviewers see Response A/B/C in identical positions. Any position preference a judge holds therefore applies uniformly across the council for that run rather than decorrelating across reviewers.

That observation is correct, and this ADR already anticipated it — "Enhancement 3" and "Scenario 1" describe both the change and the `reviewer_position_mapping` it would require. What the original text left open is Council Review **Question 1**: *"Is per-reviewer randomization worth the added complexity?"* This amendment answers it.

## Finding that changes the answer

Investigation for #602 surfaced a defect that must be resolved first, and that materially alters the cost/benefit.

**`BiasMetricRecord.position` does not hold the display position.** It is documented as *"Display position during peer review (0-indexed)"*, but `create_bias_records_from_session` populates it with `enumerate()` over the reviewer's **output ranking**. Demonstrated (display order alpha=0, beta=1, gamma=2; reviewer ranks C,B,A):

| model | recorded `.position` | true `display_index` |
|---|---|---|
| `m/alpha` | 2 | 0 |
| `m/beta` | 1 | 1 |
| `m/gamma` | 0 | 2 |

Consequently `bias_amplification.position_alignment` — intended as *"high agreement that tracks display order = amplification suspect"* — currently correlates the reviewers' own rankings against a consensus derived from those same rankings. It is close to a restatement of `agreement_index`, not a position-bias measure. Tracked as [#611](https://github.com/amiable-dev/llm-council/issues/611).

There are two position paths and only one is correct: the per-session audit (`derive_position_mapping` → `run_bias_audit`) uses real `display_index` values; the persisted cross-session records do not.

**This inverts part of the #602 write-up.** That issue asserted that a per-reviewer shuffle would "silently corrupt" `position_alignment`. In fact the record schema *already* carries a per-(reviewer, model) position, and `bias_amplification` *already* averages positions per model with an explicit comment anticipating ADR-017 per-reviewer randomization (added in the #437 review). The blocker is narrower than claimed, and the metric is already not measuring display order.

## Decision

**Adopt per-reviewer randomization, behind a default-off flag, and only after [#611](https://github.com/amiable-dev/llm-council/issues/611) is fixed.**

Answering Question 1 directly: **yes, but at low priority and with honest expectations.** The complexity is smaller than the original P2 rating assumed, because the persistence schema and the amplification reducer already accommodate per-reviewer positions. The *benefit* is also smaller than the framing implies — see "Calibration" below.

### Ordering (non-negotiable)

1. **#611 first.** Until `position` means display position, neither the current single-order design nor a per-reviewer design can be evaluated — there is no working instrument to measure whether randomization helps. Shipping per-reviewer randomization onto a broken measure would produce a change we cannot verify.
2. **Then per-reviewer randomization**, with the tracking contract below.

### Contract

`stage2_collect_rankings` builds one prompt for all reviewers today. Per-reviewer order requires per-reviewer prompts, which changes three things:

- **`reviewer_position_mapping: Dict[str, Dict[str, int]]`** — reviewer → model → display index, as "Scenario 1" specified. `label_to_model` remains for the single-order case and for de-anonymised display, but is no longer sufficient to describe what any given reviewer saw.
- **The INVARIANT is narrowed.** "Labels are assigned in lexicographic order corresponding to presentation order" continues to hold *per reviewer*. It ceases to hold globally for the session, and any consumer treating it as session-global must be updated. `derive_position_mapping` is such a consumer.
- **Seeded per reviewer** (`rng = random.Random(hash(reviewer))`, per Enhancement 3's sketch) so a run is reproducible and a failing case can be replayed. This subsumes the deferred "Deterministic Seeding" enhancement for stage 2.

### Flag

`evaluation.bias.per_reviewer_order` (or equivalent), **default off**, flag-off byte-identical — matching how #592's sibling change (rubric-criteria order) shipped, and the project's standing convention for behaviour-affecting changes.

## Calibration — what this does and does not buy

At the council's real scale (N=4–5 reviewers), per-reviewer randomization **decorrelates** position bias into noise; it does not cancel it. CLAUDE.md is explicit that per-session bias metrics are anomaly indicators over 4–5 data points, far below the ~30 needed for significance. This ADR used the same reasoning to defer Latin-square and counterbalancing designs as *"overkill for 3-5 reviewers but valuable for large-scale evaluations"* — that reasoning applies here too, in weaker form.

Converting a systematic bias into noise is a real improvement, and it removes a confound that is otherwise indistinguishable from genuine consensus. But it should be scoped as a **rigour improvement**, not a fix for a live defect, and it is the *weaker* of the two effects this amendment touches — #611 is the one that restores a broken measurement.

An honest secondary consequence: once every reviewer sees a different order, `position_alignment`'s threat model largely dissolves, because there is no shared display order for agreement to track. Averaged per-model positions converge toward `(n-1)/2` and the correlation tends to zero. That is the *correct* outcome, not a regression — but it means the metric's interpretation must be re-documented, and a per-reviewer within-session position/score correlation would be the more informative replacement.

## Consequences

- **Positive:** removes a shared-order confound; makes seeded reproducibility available for stage 2; forces #611's fix, which is the higher-value change.
- **Negative:** stage 2 gains per-reviewer prompt construction, which interacts with the two dispatch paths in that function; cross-reviewer analysis becomes two-level (as this ADR's original trade-off note predicted); `position_alignment` needs reinterpretation.
- **Neutral:** no effect on prompt caching — stage-2 prompts are a documented ADR-049 cache no-op, so per-reviewer prompt divergence costs no cache hits.

## Implementation Status (updated)

| Feature | Status | Notes |
|---------|--------|-------|
| Basic randomization | ✅ Implemented | `random.shuffle()` in Stage 2 |
| Anonymous labels | ✅ Implemented | Response A, B, C... |
| Label-to-model mapping | ✅ Implemented | Enhanced format with `display_index` |
| Position tracking (per-session audit) | ✅ Implemented (v0.3.0) | `derive_position_mapping` → `run_bias_audit` |
| Position tracking (persisted records) | ❌ **Defective** | Records ranking index, not display position — [#611](https://github.com/amiable-dev/llm-council/issues/611) |
| Rubric-criteria order randomization | ✅ Implemented (#592) | Per call, opt-in; distinct from response order |
| Per-reviewer randomization | 🔶 Proposed | This amendment; blocked on #611 |
| Deterministic seed option | 🔶 Proposed | Subsumed by per-reviewer seeding above |
| Latin square balancing | ❌ Deferred | Unchanged: overkill at N=4–5 |

## Open questions for review

1. Is the ordering right — is #611 genuinely a prerequisite, or could per-reviewer randomization land first and be validated some other way?
2. Should `position_alignment` be re-specified as a per-reviewer within-session correlation as part of this work, or left to a separate ADR-047 amendment?
3. Does bumping `BiasMetricRecord.schema_version` (for #611) suffice for pooled analyses, or do existing records need migration/quarantine?
4. Given the modest expected benefit at N=4–5, is this worth doing at all once #611 is fixed — or should #602 close as "won't do, superseded by #611"?
