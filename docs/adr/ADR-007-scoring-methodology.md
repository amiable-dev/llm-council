# ADR-007: Council Scoring Methodology

**Status:** Proposed
**Date:** 2024-11-29
**Deciders:** LLM Council
**Technical Story:** Define the scoring algorithm for aggregating peer rankings into leaderboard positions

## Context and Problem Statement

The council collects rankings from multiple LLM reviewers. We need a robust methodology to:

1. Aggregate individual rankings into a final score
2. Handle ties, abstentions, and partial rankings
3. Produce consistent leaderboard positions
4. Be resistant to gaming/manipulation
5. Scale across different council sizes

Current implementation uses Borda Count, but we need to formalize edge cases.

## Decision Drivers

* **Robustness**: Handle missing votes, ties, abstentions gracefully
* **Fairness**: No systematic bias toward any model
* **Interpretability**: Users should understand why Model X ranks higher
* **Resistance to Gaming**: Hard to manipulate rankings
* **Consistency**: Same inputs should always produce same outputs

## Considered Options

### Option A: Simple Average Rank
Average the position each model receives across all reviewers.

**Formula:** `Score = Σ(position) / N`

**Pros:**
- Simple to understand
- Easy to compute

**Cons:**
- Sensitive to outliers
- Doesn't capture magnitude of preference
- Abstentions break the math

### Option B: Borda Count (Current)
Assign points based on position: 1st = (N-1) points, last = 0.

**Formula:** `Score = Σ(N - 1 - position) / votes_received`

**Pros:**
- Well-established in voting theory
- Handles different council sizes naturally
- Rewards consensus

**Cons:**
- Sensitive to number of candidates
- Doesn't use raw scores

### Option C: Borda Count + Score Weighting (Hybrid)
Combine Borda position with raw reviewer scores.

**Formula:** `Score = α * normalized_borda + (1-α) * normalized_raw_score`

**Pros:**
- Uses all available information
- Captures both ranking and magnitude
- More nuanced than pure Borda

**Cons:**
- Raw scores poorly calibrated across models
- More complex to explain
- Requires tuning α parameter

### Option D: Elo Rating System
Treat each pairwise comparison as a "match" and compute Elo ratings.

**Pros:**
- Excellent for tracking skill over time
- Well-understood in competitive domains
- Handles transitive preferences well

**Cons:**
- Complex to implement correctly
- Requires match history (not just single queries)
- May be overkill for this use case

## Decision Outcome

**Chosen option: Option B (Borda Count)** with formalized edge case handling.

### Rationale
1. Borda Count is proven and well-understood
2. LLMs are better at relative ranking than absolute scoring
3. Raw scores are poorly calibrated across different reviewers
4. Simpler to explain to users
5. Matches our current implementation (minimal changes)

## Formalized Algorithm

### Core Borda Calculation

```python
def calculate_borda_score(
    rankings: List[Dict],  # List of reviewer rankings
    label_to_model: Dict[str, str],  # Map labels to model names
    exclude_self_votes: bool = True
) -> Dict[str, BordaResult]:
    """
    Calculate Borda scores for each model.

    Returns dict mapping model -> BordaResult with:
        - borda_score: float (average Borda points)
        - vote_count: int
        - win_count: int (times ranked #1)
        - final_rank: int
    """
    N = len(label_to_model)  # Number of candidates
    model_points = defaultdict(list)
    model_wins = defaultdict(int)

    for ranking in rankings:
        reviewer = ranking['model']
        parsed = ranking['parsed_ranking']

        # Skip abstentions
        if parsed.get('abstained'):
            continue

        ranking_list = parsed.get('ranking', [])

        for position, label in enumerate(ranking_list):
            if label not in label_to_model:
                continue

            author_model = label_to_model[label]

            # Exclude self-votes if configured
            if exclude_self_votes and reviewer == author_model:
                continue

            # Borda points: 1st = (N-1), last = 0
            points = (N - 1) - position
            model_points[author_model].append(points)

            if position == 0:
                model_wins[author_model] += 1

    # Calculate averages and rank
    results = {}
    for model, points in model_points.items():
        results[model] = BordaResult(
            borda_score=sum(points) / len(points) if points else 0,
            vote_count=len(points),
            win_count=model_wins[model]
        )

    # Assign final ranks (handle ties)
    sorted_models = sorted(
        results.items(),
        key=lambda x: (-x[1].borda_score, -x[1].win_count, x[0])  # Tiebreaker: wins, then alphabetical
    )

    current_rank = 1
    prev_score = None
    for i, (model, result) in enumerate(sorted_models):
        if prev_score is not None and result.borda_score < prev_score:
            current_rank = i + 1
        result.final_rank = current_rank
        prev_score = result.borda_score

    return {model: result for model, result in sorted_models}
```

### Edge Case Handling

| Edge Case | Handling | Rationale |
|-----------|----------|-----------|
| **Self-vote** | Exclude from aggregation | Prevents self-preference bias |
| **Abstention** | Skip entirely | Don't penalize models for reviewer refusals |
| **Partial ranking** | Use available positions only | Some reviewers may only rank top 3 |
| **Tie in scores** | Use win_count as tiebreaker | More #1 votes = higher rank |
| **Tie in wins** | Alphabetical by model name | Deterministic ordering |
| **No votes received** | Score = 0, rank = last | Model must have at least 1 vote |
| **Single reviewer** | Return rankings as-is | Mark as "low confidence" |
| **Score/rank mismatch** | Trust ranking, ignore scores | Ranking is more reliable |

### Score/Rank Mismatch Resolution (Issue #13)

When a reviewer's ranking order doesn't match their scores:
```
Ranking: [A, B, C]
Scores: {A: 7, B: 9, C: 5}  # B scored higher but ranked 2nd
```

**Resolution:** Always use the explicit ranking order. Scores are supplementary.

```python
def resolve_mismatch(parsed_ranking: Dict) -> List[str]:
    """
    If ranking and scores conflict, trust ranking.
    Scores are only used for display/debugging.
    """
    ranking = parsed_ranking.get('ranking', [])
    scores = parsed_ranking.get('scores', {})

    if ranking:
        return ranking  # Always prefer explicit ranking

    # Fallback: derive ranking from scores
    if scores:
        sorted_scores = sorted(scores.items(), key=lambda x: -x[1])
        return [label for label, _ in sorted_scores]

    return []
```

### Confidence Indicators

Add confidence metadata to help users interpret results:

```python
@dataclass
class LeaderboardEntry:
    model: str
    borda_score: float
    final_rank: int
    vote_count: int
    win_count: int
    confidence: str  # "high", "medium", "low"

def calculate_confidence(vote_count: int, total_possible: int) -> str:
    coverage = vote_count / total_possible
    if coverage >= 0.8:
        return "high"
    elif coverage >= 0.5:
        return "medium"
    else:
        return "low"
```

## Leaderboard Aggregation (Cross-Query)

For the public leaderboard, aggregate across all telemetry:

```sql
-- Aggregate Borda scores across all queries in time window
SELECT
    model,
    category,
    -- Use mean of means (each query contributes equally)
    AVG(borda_score) as aggregate_borda,
    SUM(vote_count) as total_votes,
    SUM(win_count) as total_wins,
    COUNT(DISTINCT event_id) as appearances
FROM event_rankings er
JOIN telemetry_events te ON er.event_id = te.event_id
WHERE te.timestamp > NOW() - INTERVAL '30 days'
GROUP BY model, category
ORDER BY aggregate_borda DESC;
```

## Consequences

### Positive
- Clear, deterministic algorithm
- Handles all edge cases explicitly
- Resistant to score manipulation (uses rankings)
- Consistent with existing implementation

### Negative
- Doesn't use raw scores (potentially useful signal)
- May not capture close decisions well

### Risks
- Borda Count can favor "safe" answers that don't offend any reviewer
- May need to revisit if gaming is detected

## Links

- [Issue #13: Score/rank mismatch](https://github.com/amiable-dev/llm-council/issues/13)
