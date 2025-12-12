# ADR-010: Alternative Consensus Mechanisms

**Status:** Proposed
**Date:** 2024-12-12
**Deciders:** LLM Council (Unanimous)
**Technical Story:** Evaluate and select improved ranking aggregation algorithms beyond Borda Count

## Context and Problem Statement

The council currently uses **Normalized Borda Count** to aggregate peer rankings:
- Each reviewer ranks all responses (1st, 2nd, 3rd...)
- Points assigned: 1st = (N-1)/(N-1) = 1.0, last = 0
- Self-votes excluded to prevent bias
- Average Borda score determines final ranking

While Borda is simple and interpretable, it has known limitations:
1. **Treats all rank distances equally** (1st vs 2nd same as 9th vs 10th)
2. **Not Condorcet-consistent** (may not select the pairwise majority winner)
3. **Vulnerable to strategic voting** (burying strong competitors)
4. **Doesn't capture "closeness"** well for close decisions

## Decision Drivers

* **Computational complexity**: Must work in real-time (3-10 models, sub-second)
* **Robustness**: Resistant to strategic voting and model biases
* **Tie handling**: Graceful handling of ties and abstentions
* **Interpretability**: Users should understand why a response won
* **Close decisions**: Better signal when top responses are nearly equivalent

## Considered Options

### Option A: Copeland's Method
Count pairwise wins (how many other responses each beats head-to-head).

**Pros:**
- Simple: "Response A beat 7 of 9 competitors head-to-head"
- Low complexity: O(N²R) where R = reviewers

**Cons:**
- Collapses margin information (5-4 win = 9-0 win)
- Frequently produces ties with few voters
- Worse than Borda for close decisions

**Verdict:** Good as tiebreaker, not primary mechanism.

### Option B: Schulze Method (Beatpath)
Build pairwise preference graph, find strongest paths via Floyd-Warshall.

**Pros:**
- Condorcet-consistent (respects pairwise majority)
- Clone-proof, monotonic, excellent strategic robustness
- O(N³) complexity - trivial for N≤10 (~1000 ops, sub-millisecond)
- Path strengths encode margin information

**Cons:**
- Internals (strongest paths) harder to explain
- Still purely ordinal (no score magnitude)

**Verdict:** Strong candidate for primary ranking.

### Option C: Kemeny-Young
Find ranking that minimizes total disagreement (Kendall tau distance) with all reviewers.

**Pros:**
- "Most consensus ranking" - very interpretable
- Captures nuanced trade-offs in close calls
- Hard to manipulate strategically

**Cons:**
- NP-hard: O(N!) in brute force
- N=10 → 3.6M permutations (feasible but requires optimization)
- More implementation complexity than Schulze

**Verdict:** Theoretically excellent, but Schulze achieves similar results with less complexity.

### Option D: Instant Runoff Voting (IRV)
Eliminate lowest first-preference candidate iteratively.

**Pros:**
- Intuitive for users familiar with elections
- Low complexity: O(N²R)

**Cons:**
- Non-monotonic (improving rank can hurt you)
- Ignores depth of rankings
- Designed for large electorates; fails with 3-10 voters

**Verdict:** Not recommended for this use case.

### Option E: Range/Score Voting
Use raw 1-10 scores instead of rankings.

**Pros:**
- Captures intensity of preference
- Can detect when all responses are poor
- Very interpretable: "average score 8.3/10"

**Cons:**
- Score calibration varies dramatically between models
- Vulnerable to min/max strategic voting
- Requires normalization (z-score per reviewer)

**Verdict:** Good supplementary signal, not standalone.

### Option F: Bradley-Terry Model
Probabilistic model estimating "strength" from pairwise comparisons.

**Pros:**
- Outputs probabilities and confidence intervals
- Quantifies "how close" the decision was
- Handles missing comparisons naturally
- O(N² × iterations), converges quickly

**Cons:**
- Statistical interpretation may confuse users
- Requires iterative fitting (MLE)

**Verdict:** Excellent for uncertainty quantification; use as secondary layer.

### Option G: Weighted Borda
Same as Borda, but weight votes by reviewer reliability.

**Pros:**
- Incremental improvement to current system
- Can incorporate reviewer quality signals
- Same O(NR) complexity

**Cons:**
- Weight computation creates feedback loops
- Risks entrenching biases if weights are wrong

**Verdict:** Easy upgrade path if reliability metrics available.

### Option H: Bucket Consensus (Tiers)
Group responses into quality buckets (Excellent/Good/Poor) instead of strict ordering.

**Pros:**
- Reduces noise from artificial fine-grained distinctions
- Natural for LLM outputs ("good enough" vs "bad")
- Very interpretable: "3 excellent, 2 good, 1 poor"

**Cons:**
- Loses within-tier ordering
- Bucket boundaries are arbitrary

**Verdict:** Excellent for user-facing presentation layer.

### Option I: Hybrid (Rank + Score)
Combine ordinal ranking with cardinal score magnitude.

**Pros:**
- Uses all available information
- Distinguishes "strong 2nd" from "weak 2nd"

**Cons:**
- Inherits weaknesses of both
- Requires tuning α parameter

**Verdict:** Principled but adds complexity.

## Decision Outcome

**Chosen: Tiered Architecture**

Based on council consensus, implement a layered approach:

1. **Primary Ranker: Schulze Method**
   - Best theoretical properties for small N
   - Condorcet-consistent, clone-proof
   - Replaces Borda as the core ranking algorithm

2. **Uncertainty Layer: Bradley-Terry (Optional)**
   - Quantifies confidence in rankings
   - Outputs "Response A has 70% probability of being best"
   - Helps chairman know when to hedge

3. **Presentation Layer: Bucket Consensus**
   - Convert Schulze ranking to tiers for users
   - Top 20% = Excellent, next 30% = Good, etc.
   - Matches how LLMs naturally think about quality

4. **Fallback: Borda Count**
   - Keep existing implementation as fallback
   - Use when Schulze produces unexpected results

### Rationale

The council unanimously recommended this architecture because:

1. **Schulze is proven** for small voter counts and resistant to manipulation
2. **Bradley-Terry addresses the "closeness" concern** by providing probabilistic margins
3. **Buckets improve UX** by avoiding artificial precision in rankings
4. **Borda remains available** for comparison and graceful degradation

## Implementation

### Schulze Algorithm

```python
def schulze_ranking(pairwise_matrix: list[list[int]]) -> list[int]:
    """
    Compute Schulze ranking from pairwise preference matrix.

    Args:
        pairwise_matrix[i][j] = times response i ranked above j

    Returns:
        Indices sorted by Schulze ranking (best first)
    """
    n = len(pairwise_matrix)

    # Initialize direct strengths
    strength = [[0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j and pairwise_matrix[i][j] > pairwise_matrix[j][i]:
                strength[i][j] = pairwise_matrix[i][j]

    # Floyd-Warshall for strongest paths
    for k in range(n):
        for i in range(n):
            for j in range(n):
                if i != j:
                    strength[i][j] = max(
                        strength[i][j],
                        min(strength[i][k], strength[k][j])
                    )

    # Rank by wins in strength comparison
    wins = [
        sum(1 for j in range(n) if strength[i][j] > strength[j][i])
        for i in range(n)
    ]

    return sorted(range(n), key=lambda i: -wins[i])
```

### Configuration

```python
# config.py additions
DEFAULT_RANKING_METHOD = "schulze"  # "borda", "schulze", "hybrid"
DEFAULT_SHOW_CONFIDENCE = False     # Enable Bradley-Terry confidence
DEFAULT_BUCKET_TIERS = ["Excellent", "Good", "Acceptable", "Poor"]
```

### Migration Path

1. **Phase 1**: Implement Schulze alongside Borda, run in shadow mode
2. **Phase 2**: Compare rankings, validate Schulze produces sensible results
3. **Phase 3**: Switch default to Schulze, keep Borda as option
4. **Phase 4**: Add Bradley-Terry confidence intervals (optional feature)
5. **Phase 5**: Add bucket presentation to UI

## Consequences

### Positive
- More robust rankings resistant to strategic voting
- Better identification of Condorcet winners
- Quantified confidence for close decisions
- Clearer user presentation via tiers

### Negative
- Slightly more complex than Borda
- Schulze internals harder to explain
- Additional testing needed for edge cases

### Risks
- Schulze and Borda may produce different winners (monitor during rollout)
- Bradley-Terry adds computational overhead (keep optional)

## Complexity Comparison

| Method | Time Complexity | Space | Real-time N=10? |
|--------|-----------------|-------|-----------------|
| Borda | O(NR) | O(N) | Yes |
| Copeland | O(N²R) | O(N²) | Yes |
| Schulze | O(N³) | O(N²) | Yes (~1ms) |
| Kemeny-Young | O(N!) | O(N!) | Marginal |
| Bradley-Terry | O(N² × iter) | O(N) | Yes (~10ms) |

## References

- [ADR-007: Council Scoring Methodology](./ADR-007-scoring-methodology.md)
- [Schulze Method Wikipedia](https://en.wikipedia.org/wiki/Schulze_method)
- [Social Choice Theory - Condorcet Methods](https://plato.stanford.edu/entries/voting-methods/)
