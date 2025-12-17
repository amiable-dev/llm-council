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
