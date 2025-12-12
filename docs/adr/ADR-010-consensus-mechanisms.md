# ADR-010: Consensus Mechanism - Normalized Score Averaging

**Status:** Proposed (Revised)
**Date:** 2024-12-12
**Deciders:** LLM Council (Unanimous on revision)
**Technical Story:** Select the optimal ranking aggregation for 3-5 LLM reviewers

## Context and Problem Statement

The council currently uses **Normalized Borda Count** to aggregate peer rankings:
- Each reviewer ranks all responses (1st, 2nd, 3rd...)
- Points assigned: 1st = (N-1)/(N-1) = 1.0, last = 0
- Self-votes excluded to prevent bias
- Average Borda score determines final ranking

**Critical insight:** We also collect 1-10 scores from each reviewer, but currently discard this data by converting to ranks.

### The Real Problems (Not Theoretical Voting Issues)

| Problem | Description |
|---------|-------------|
| **LLM biases** | Models prefer verbose responses, familiar styles |
| **Score calibration** | GPT scores harshly (avg 6), Claude generously (avg 8) |
| **Small sample size** | 3-5 voters means high statistical noise |
| **Close decisions** | Need to know when top responses are effectively tied |

### Why Ranks Are Wrong

Converting scores to ranks **deletes information**:

```
Scenario A: Scores [10, 9.9, 2] → Ranks [1, 2, 3]
Scenario B: Scores [6, 3, 1]   → Ranks [1, 2, 3]
```

In Scenario A, the top two are effectively tied. In Scenario B, there's a clear winner. Rank-based methods (Borda, Schulze) treat these identically.

## Decision Drivers

* **Simplicity**: Minimize implementation and maintenance cost
* **Use available data**: We already collect scores - use them
* **Handle calibration**: Different LLMs score differently
* **Detect ties**: Know when decisions are too close to call
* **Solve actual problems**: LLM biases, not strategic voting

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

**Chosen: Normalized Score Averaging**

After critical re-evaluation, the council **unanimously rejected** the complex tiered architecture (Schulze + Bradley-Terry + Buckets) as "engineering theater" - solving theoretical problems we don't have while ignoring our actual challenges.

### Why Complex Voting Methods Are Wrong Here

| Method | What It Solves | Why It's Irrelevant |
|--------|---------------|---------------------|
| **Schulze** | Strategic voting, clone attacks | LLMs don't strategize |
| **Bradley-Terry** | Uncertainty from limited pairwise data | We have full scores already |
| **Condorcet methods** | Rock-paper-scissors cycles | Quality is transitive in LLM evals |

With 3-5 voters, Schulze is **more sensitive to noise** than Borda, not less. A single outlier can flip pairwise majorities unpredictably.

### The Recommended Mechanism

**Normalized Score Averaging with Confidence-Based Tie Detection**

```python
import numpy as np
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Tuple

@dataclass
class AggregateResult:
    model: str
    mean_score: float      # Normalized mean (z-score scale)
    std_error: float       # Standard error of mean
    vote_count: int
    is_tied_with_next: bool = False

def aggregate_scores(
    scores_by_reviewer: Dict[str, Dict[str, float]],
    exclude_self_votes: bool = True
) -> List[AggregateResult]:
    """
    Aggregate reviewer scores using z-score normalization.

    Args:
        scores_by_reviewer: {reviewer_model: {candidate_model: score}}
        exclude_self_votes: Whether to exclude self-evaluations

    Returns:
        List of results sorted by mean score (best first)
    """
    # Step 1: Z-normalize per reviewer (fixes calibration bias)
    normalized = {}
    for reviewer, scores in scores_by_reviewer.items():
        # Exclude self-vote if configured
        if exclude_self_votes:
            scores = {k: v for k, v in scores.items() if k != reviewer}

        if not scores:
            continue

        values = list(scores.values())
        mean = np.mean(values)
        std = np.std(values)

        # Fallback if no variance (all same score)
        if std < 0.001:
            normalized[reviewer] = {k: 0.0 for k in scores}
        else:
            normalized[reviewer] = {
                k: (v - mean) / std for k, v in scores.items()
            }

    # Step 2: Aggregate normalized scores per candidate
    candidate_scores = defaultdict(list)
    for reviewer, scores in normalized.items():
        for candidate, score in scores.items():
            candidate_scores[candidate].append(score)

    # Step 3: Calculate mean, standard error, and rank
    results = []
    for candidate, scores in candidate_scores.items():
        n = len(scores)
        mean = np.mean(scores)
        std_error = np.std(scores) / np.sqrt(n) if n > 1 else 0

        results.append(AggregateResult(
            model=candidate,
            mean_score=round(mean, 3),
            std_error=round(std_error, 3),
            vote_count=n
        ))

    # Sort by mean score (highest first)
    results.sort(key=lambda x: -x.mean_score)

    # Step 4: Flag statistical ties (overlapping 95% confidence intervals)
    for i in range(len(results) - 1):
        curr, next_ = results[i], results[i + 1]
        # 95% CI uses ~1.96 * std_error
        curr_lower = curr.mean_score - 1.96 * curr.std_error
        next_upper = next_.mean_score + 1.96 * next_.std_error

        if curr_lower < next_upper:
            results[i].is_tied_with_next = True

    return results
```

### How This Solves Our Actual Problems

| Problem | Solution |
|---------|----------|
| **Score calibration** | Z-normalization: harsh reviewer (avg 6) and generous reviewer (avg 8) both center to 0 |
| **LLM biases** | Normalization spreads preferences; biases become noise that averages out |
| **Small sample size** | Standard error tells you when N is too small to decide |
| **Close decisions** | Overlapping confidence intervals explicitly flag ties |

### Configuration

```python
# config.py additions
DEFAULT_RANKING_METHOD = "normalized_scores"  # "borda", "normalized_scores"
DEFAULT_TIE_THRESHOLD = 1.96  # Z-score for 95% confidence interval
DEFAULT_FALLBACK_TO_BORDA = True  # Use Borda as tiebreaker
```

### Example Output

```json
{
  "rankings": [
    {"model": "gpt-4o", "mean_score": 0.82, "std_error": 0.15, "tied": false},
    {"model": "claude-opus", "mean_score": 0.45, "std_error": 0.22, "tied": true},
    {"model": "gemini-pro", "mean_score": 0.31, "std_error": 0.18, "tied": false}
  ],
  "interpretation": "gpt-4o is the clear winner. claude-opus and gemini-pro are statistically tied."
}
```

### Migration Path

1. **Phase 1**: Collect scores alongside ranks (already done)
2. **Phase 2**: Implement normalized score averaging in parallel with Borda
3. **Phase 3**: Compare results, validate on historical data
4. **Phase 4**: Switch default to normalized scores
5. **Phase 5**: Keep Borda as optional tiebreaker

### What to Invest In Instead

The council recommends spending the "complexity budget" saved from not implementing Schulze on:

1. **Better prompts**: Explicitly instruct reviewers to "penalize unnecessary verbosity"
2. **Bias audits**: Track correlation between scores and response length
3. **Rubrics**: Score on specific criteria (accuracy, conciseness, helpfulness) not holistic vibes
4. **Response order randomization**: Mitigate positional bias

## Consequences

### Positive
- **Simpler**: ~30 lines vs. hundreds for Schulze
- **Uses all data**: Scores contain magnitude information ranks discard
- **Built-in confidence**: Know when decisions are uncertain
- **Interpretable**: "Model A scored 0.8σ above mean" is clear
- **Handles calibration**: Z-scores fix harsh/generous reviewers automatically

### Negative
- Requires scores (we already have them)
- Z-scores can be unstable with very low variance (handled by fallback)

### Risks
- If all reviewers give identical scores, z-normalization fails → fallback to Borda
- Systematic biases (all LLMs prefer verbosity) still need prompt engineering to fix

## Complexity Comparison

| Method | Implementation | Solves Calibration? | Detects Ties? | Uses Score Magnitude? |
|--------|---------------|---------------------|---------------|----------------------|
| Borda | Simple | No | Poorly | No |
| Schulze | Complex | No | No | No |
| **Normalized Scores** | Simple | **Yes** | **Yes** | **Yes** |

## References

- [ADR-007: Council Scoring Methodology](./ADR-007-scoring-methodology.md)
- [Inter-rater reliability and z-score normalization](https://en.wikipedia.org/wiki/Standard_score)
- [Why Condorcet methods fail for small electorates](https://plato.stanford.edu/entries/voting-methods/)
