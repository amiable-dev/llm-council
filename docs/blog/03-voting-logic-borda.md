# Why Majority Vote Fails for LLM Councils

**With 4 voters, Schulze method is more noise-sensitive than Borda count. Here's why we chose simplicity over theoretical elegance.**

---

When you have millions of voters, sophisticated voting methods shine. Arrow's impossibility theorem, Condorcet cycles, strategic voting—these are real concerns for national elections.

When you have 4 LLMs voting on response quality, they're irrelevant. Different problems dominate.

## The Small Electorate Problem

With 4-5 reviewers, statistical noise overwhelms theoretical correctness:

```
Reviewer Rankings:
  GPT-4:    [A, B, C, D]
  Claude:   [B, A, C, D]
  Gemini:   [A, C, B, D]
  Grok:     [A, B, C, D]

Majority winner: None (A:3, B:1 first-place votes)
Condorcet winner: A (beats all others head-to-head)
Borda winner: A (best average rank)
```

All three methods agree here. But change two votes:

```
New rankings:
  GPT-4:    [A, B, C, D]
  Claude:   [B, C, A, D]
  Gemini:   [C, A, B, D]
  Grok:     [A, B, C, D]

Pairwise comparisons:
  A vs B: A wins 2-2 (tie) → recount: A=2, B=2
  B vs C: B wins 3-1
  C vs A: C wins 2-2 (tie) → depends on tiebreaker

Result: No clear Condorcet winner. With slight noise, cycles emerge.
```

Schulze method handles cycles elegantly—but the "solution" encodes random noise, not signal. Borda ignores pairwise comparisons entirely and gives a stable answer based on average rank.

## Why Borda Count Works for Us

Borda count assigns points by position:
- 1st place: N-1 points
- 2nd place: N-2 points
- Last place: 0 points

```python
def calculate_borda_points(ranking: List[str]) -> Dict[str, int]:
    """Borda count: 1st=3pts, 2nd=2pts, 3rd=1pt, 4th=0pts."""
    n = len(ranking)
    return {model: n - 1 - position for position, model in enumerate(ranking)}
```

**Why it works for LLM councils:**

1. **Rewards consensus**: A response ranked 2nd by everyone beats one ranked 1st by half and last by half.

2. **Stable under noise**: Single reviewer changes cause small score shifts, not complete ranking inversions.

3. **LLMs don't strategize**: Condorcet methods defend against "burying" strategies that LLMs don't employ.

4. **Uses full ranking**: Unlike plurality (first-place only), Borda uses every reviewer's complete preference order.

## Self-Vote Exclusion and Average Rank

Models show self-preference bias. In testing, GPT-4 consistently ranked GPT-4 responses first. Claude preferred Claude-style responses.

We exclude self-votes from the aggregation. But this creates a problem: with self-vote exclusion, some models receive 3 votes and some receive 4. Sum-of-points would be unfair.

**Solution**: Use **average rank position** instead of sum of points.

```python
def calculate_aggregate_rankings(
    stage2_results: List[Dict],
    label_to_model: Dict[str, Dict],
    exclude_self_votes: bool = True
) -> List[Tuple[str, float]]:
    """Aggregate peer rankings using average position (lower = better)."""
    positions = defaultdict(list)

    for result in stage2_results:
        reviewer = result["model"]

        for position, label in enumerate(result["parsed_ranking"]):
            candidate = label_to_model[label]["model"]

            # Skip self-votes: GPT-4 can't vote for GPT-4
            if exclude_self_votes and reviewer == candidate:
                continue

            # Track position (1-indexed: 1st, 2nd, 3rd...)
            positions[candidate].append(position + 1)

    # Average position (lower is better)
    return sorted(
        [(model, sum(pos) / len(pos)) for model, pos in positions.items()],
        key=lambda x: x[1]  # Sort ascending: lower avg position = better
    )
```

With self-vote exclusion, each model receives 3 votes (from peers) instead of 4 (including self). Averaging normalizes for this difference.

## Edge Cases

### Ties

When two models have identical average positions, we use tiebreakers:

1. **Win count**: Model with more #1 rankings wins
2. **Alphabetical**: Deterministic fallback

```python
sorted_models = sorted(
    results.items(),
    key=lambda x: (x[1].avg_position, -x[1].win_count, x[0])  # Lower position first
)
```

### Partial Rankings

If a reviewer only ranks their top 3:

```python
# Reviewer ranking: [A, B, C]  # D not ranked

# Option 1: Skip unranked (what we do)
# D gets no vote from this reviewer

# Option 2: Assign last-place tie (alternative)
# D gets position 4
```

We chose Option 1. Silence isn't necessarily "worst"—it might mean "couldn't evaluate."

### Abstentions

If a model abstains entirely ("I cannot rank these responses"):

```python
if result.get("abstained"):
    continue  # Skip this reviewer entirely
```

The remaining reviewers determine the outcome. With 4 models and 1 abstention, you still have 3 valid votes.

## What We Considered and Rejected

### Schulze Method (Beatpath)

Schulze finds the "strongest path" between candidates in a pairwise preference graph.

**Why we rejected it:**
- Solves strategic voting (LLMs don't strategize)
- O(N³) complexity for marginal stability gain
- More sensitive to noise with small electorates
- Harder to explain to users

### Raw Score Averaging

Use the 1-10 scores directly instead of converting to ranks.

**The calibration problem:**

```
GPT-4 scores:    [7, 6, 5, 4]  (harsh grader)
Claude scores:   [9, 9, 8, 7]  (generous grader)

Raw average: Claude's 4th place (7) = GPT's 1st place (7)?
Rank-based: Both agree A > B > C > D
```

Different models have different score distributions. Ranks are more comparable across reviewers.

### Normalized Score Averaging

Z-normalize scores per reviewer to fix calibration:

```python
# Z-score normalization
mean = np.mean(scores)
std = np.std(scores)
normalized = [(s - mean) / std for s in scores]
```

This works and we may adopt it later. But it requires scores (not just rankings), and z-normalization fails when all scores are identical.

For now, Borda on rankings is simpler and robust.

## The Algorithm

Our final implementation:

```python
@dataclass
class BordaResult:
    avg_position: float  # Average rank (lower = better)
    vote_count: int
    win_count: int       # Times ranked #1
    final_rank: int

def calculate_borda_scores(
    rankings: List[Dict],
    label_to_model: Dict[str, Dict],
    exclude_self_votes: bool = True
) -> Dict[str, BordaResult]:
    """Calculate average position scores for each model."""
    model_positions = defaultdict(list)
    model_wins = defaultdict(int)

    for ranking in rankings:
        reviewer = ranking["model"]
        parsed = ranking["parsed_ranking"]

        for position, label in enumerate(parsed):
            if label not in label_to_model:
                continue

            candidate = label_to_model[label]["model"]

            if exclude_self_votes and reviewer == candidate:
                continue

            model_positions[candidate].append(position + 1)  # 1-indexed

            if position == 0:
                model_wins[candidate] += 1

    # Calculate averages
    results = {}
    for model, positions in model_positions.items():
        results[model] = BordaResult(
            avg_position=sum(positions) / len(positions),
            vote_count=len(positions),
            win_count=model_wins[model],
            final_rank=0  # Assigned below
        )

    # Assign ranks with tiebreakers (lower avg_position = better)
    sorted_models = sorted(
        results.items(),
        key=lambda x: (x[1].avg_position, -x[1].win_count, x[0])
    )

    for rank, (model, result) in enumerate(sorted_models, 1):
        result.final_rank = rank

    return {model: result for model, result in sorted_models}
```

## Real Example

Query: "Explain the CAP theorem"

| Model | GPT-4 ranks | Claude ranks | Gemini ranks | Grok ranks | Avg Position | Final Rank |
|-------|-------------|--------------|--------------|------------|--------------|------------|
| GPT-4 | - | 2 | 1 | 2 | 1.67 | 2nd |
| Claude | 1 | - | 2 | 1 | 1.33 | **1st** |
| Gemini | 2 | 1 | - | 3 | 2.00 | 3rd |
| Grok | 3 | 3 | 3 | - | 3.00 | 4th |

Claude wins with the lowest average position (1.33), despite GPT-4 getting a #1 from Gemini. Claude was consistently ranked high by all peers (1st, 2nd, 1st), while GPT-4 was ranked 2nd twice.

This is Borda working correctly: **consensus beats polarization**.

## When to Use Something Else

Borda count isn't perfect. Consider alternatives when:

- **You have 10+ reviewers**: Schulze becomes worth the complexity
- **You collect reliable scores**: Normalized averaging uses more information
- **You need uncertainty quantification**: Bradley-Terry gives confidence intervals
- **You're building a leaderboard over time**: Elo rating systems shine

For a 4-5 model council evaluating single queries, average rank (Borda-style) is the right tool.

---

*This is post 3 of 7. Next: [The Latency Tax: Parallel Execution Patterns](./04-latency-tax-parallel.md)*

---

*LLM Council is open source: [github.com/amiable-dev/llm-council](https://github.com/amiable-dev/llm-council)*
