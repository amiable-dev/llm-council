# ADR-017: Response Order Randomization

**Status:** Accepted (Already Implemented)
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

| Feature | Status |
|---------|--------|
| Basic randomization | ✅ Implemented |
| Anonymous labels | ✅ Implemented |
| Label-to-model mapping | ✅ Implemented |
| Position tracking | ❌ Not yet |
| Per-reviewer randomization | ❌ Not yet |
| Deterministic seed option | ❌ Not yet |

---

## Questions for Council Review

1. Is per-reviewer randomization worth the added complexity?
2. Should we implement Latin square balancing for larger councils?
3. How important is deterministic seeding for reproducibility?
4. Should position tracking be mandatory (for ADR-015) or optional?

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
