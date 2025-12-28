# Detecting Evaluator Bias

**GPT-4 scores harshly (avg 6.2). Claude scores generously (avg 7.8). Here's how to detect and account for it.**

---

When multiple LLMs evaluate each other's work, they don't grade on the same curve. Some models are harsh critics; others give everyone gold stars. If you don't account for this, your "consensus" is just noise.

We built a bias auditing system to detect these patterns. Here's what we learned.

## The Three Biases

### 1. Reviewer Calibration Bias

Different models have different scoring baselines:

```
GPT-4 scores:     [6, 7, 5, 6]    mean: 6.0
Claude scores:    [8, 9, 8, 7]    mean: 8.0
Gemini scores:    [7, 7, 8, 7]    mean: 7.25
```

If you average these raw scores, Claude's 4th-place candidate (score 7) ties with GPT's 1st-place candidate (score 7). That's not consensus—that's calibration noise.

**Detection:**

```python
import statistics
from typing import Dict

def audit_reviewer_calibration(
    scores: Dict[str, Dict[str, float]]
) -> Dict[str, Dict[str, float]]:
    """
    Detect harsh and generous reviewers.

    IMPORTANT: This assumes all reviewers graded the same set of responses.
    If reviewers grade different subsets, this comparison is invalid.
    """
    calibration = {}
    for reviewer, reviewer_scores in scores.items():
        values = list(reviewer_scores.values())
        calibration[reviewer] = {
            "mean": statistics.mean(values),
            "std": statistics.stdev(values) if len(values) > 1 else 0,
        }

    # Find median baseline
    all_means = [c["mean"] for c in calibration.values()]
    median_mean = statistics.median(all_means)
    std_of_means = statistics.stdev(all_means) if len(all_means) > 2 else 1

    # Flag outliers (z-score relative to other reviewers)
    for reviewer, stats in calibration.items():
        z_score = (stats["mean"] - median_mean) / std_of_means if std_of_means > 0 else 0
        stats["z_score"] = round(z_score, 2)
        stats["classification"] = (
            "harsh" if z_score < -1 else
            "generous" if z_score > 1 else
            "neutral"
        )

    return calibration
```

**Example output** (with means 6.0, 7.25, 8.0 → median 7.25, std ≈ 1.0):

```json
{
  "openai/gpt-4": {"mean": 6.0, "z_score": -1.25, "classification": "harsh"},
  "anthropic/claude": {"mean": 8.0, "z_score": 0.75, "classification": "neutral"},
  "google/gemini": {"mean": 7.25, "z_score": 0.0, "classification": "neutral"}
}
```

Note: With only 3 reviewers, you need a z-score magnitude > 1.0 to be flagged. Claude at z=0.75 is within one standard deviation of the median.

### 2. Length-Score Correlation

Verbose responses often score higher, regardless of quality:

```python
import statistics
import math
from typing import Dict, List, Tuple

def _pearson_correlation(x: List[float], y: List[float]) -> float:
    """Pure Python Pearson correlation coefficient."""
    n = len(x)
    if n < 3:
        return 0.0

    mean_x = statistics.mean(x)
    mean_y = statistics.mean(y)

    numerator = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    sum_sq_x = sum((xi - mean_x) ** 2 for xi in x)
    sum_sq_y = sum((yi - mean_y) ** 2 for yi in y)

    denominator = math.sqrt(sum_sq_x * sum_sq_y)
    if denominator == 0:
        return 0.0

    return numerator / denominator

def calculate_length_correlation(
    responses: List[Dict],
    scores: Dict[str, Dict[str, float]]
) -> Tuple[float, str]:
    """Calculate Pearson correlation between length and score."""
    # Get word counts
    word_counts = {r["model"]: len(r["response"].split()) for r in responses}

    # Get average scores per response
    avg_scores = {}
    for model in word_counts:
        model_scores = [s[model] for s in scores.values() if model in s]
        avg_scores[model] = statistics.mean(model_scores) if model_scores else 0

    # Calculate correlation
    models = list(avg_scores.keys())
    x = [word_counts[m] for m in models]
    y = [avg_scores[m] for m in models]

    if len(models) < 3:
        return 0.0, "insufficient_data"

    r = _pearson_correlation(x, y)

    interpretation = (
        "strong_positive" if r > 0.7 else
        "moderate_positive" if r > 0.3 else
        "weak" if r > -0.3 else
        "moderate_negative" if r > -0.7 else
        "strong_negative"
    )

    return round(r, 3), interpretation
```

**Healthy range:** -0.2 to 0.2 (weak correlation)

**Warning sign:** r > 0.7 means reviewers are rewarding verbosity, not quality.

### 3. Position Bias

The first response shown often gets an unfair advantage. Detecting this requires tracking the *display order* for each review session, not a fixed model-to-position mapping:

```python
from collections import defaultdict
from typing import Dict, List, Tuple

def calculate_position_bias(
    session_data: List[Dict]
) -> Tuple[float, bool]:
    """
    Detect if presentation order affects scores.

    Each session_data entry must include:
    - display_order: List[str]  # Models in order shown to reviewer
    - scores: Dict[str, float]  # Reviewer's scores for each model
    """
    position_scores = defaultdict(list)

    for session in session_data:
        display_order = session["display_order"]
        scores = session["scores"]

        for position, model in enumerate(display_order):
            if model in scores:
                position_scores[position].append(scores[model])

    if len(position_scores) < 2:
        return 0.0, False

    # Calculate mean score per position
    position_means = [
        statistics.mean(scores)
        for scores in position_scores.values()
        if scores
    ]

    # Variance of position means indicates bias
    variance = statistics.variance(position_means) if len(position_means) > 1 else 0

    # High variance = position affects scores
    bias_detected = variance > 0.5

    return round(variance, 3), bias_detected
```

If Position 0 averages 7.5 and Position 3 averages 6.2 across many sessions, you have position bias.

**Mitigation:** Randomize response order for each reviewer. Track the randomization and analyze cross-session.

## The Statistical Honesty Problem

Here's the uncomfortable truth: **with 4-5 models, single-session bias detection lacks statistical power.**

| Metric | Data Points | Minimum for Significance |
|--------|-------------|-------------------------|
| Length correlation | 4-5 pairs | 30+ pairs |
| Position bias | 1 ordering | 20+ orderings |
| Reviewer calibration | ~12 scores | 50+ scores |

A single session can detect **extreme anomalies** (r > 0.9), but cannot provide statistical proof of systematic bias. These are indicators, not evidence.

## Cross-Session Aggregation

Real insights require aggregating across sessions:

```python
import math
import statistics
from dataclasses import dataclass
from typing import List, Optional, Tuple

@dataclass
class BiasMetricRecord:
    session_id: str
    length_correlation: Optional[float]

@dataclass
class AggregatedBiasResult:
    length_correlation: float
    length_correlation_ci: Tuple[float, float]  # 95% confidence interval
    sample_size: int
    confidence_level: str  # "insufficient", "preliminary", "moderate", "high"

def run_aggregated_bias_audit(
    records: List[BiasMetricRecord],
    min_sessions: int = 10
) -> Optional[AggregatedBiasResult]:
    """Aggregate bias metrics across multiple sessions."""
    # Filter valid correlations (must be in range (-1, 1), exclusive)
    correlations = [
        r.length_correlation
        for r in records
        if r.length_correlation is not None and -1 < r.length_correlation < 1
    ]

    if len(correlations) < min_sessions:
        return AggregatedBiasResult(
            length_correlation=0,
            length_correlation_ci=(0, 0),
            sample_size=len(correlations),
            confidence_level="insufficient"
        )

    # Fisher z-transform for pooling correlations
    z_values = [0.5 * math.log((1 + r) / (1 - r)) for r in correlations]
    pooled_z = statistics.mean(z_values)
    pooled_r = (math.exp(2 * pooled_z) - 1) / (math.exp(2 * pooled_z) + 1)

    # 95% CI using Fisher z standard error
    # Note: For meta-analysis, SE = 1/sqrt(n-3) per correlation
    # With small per-session n, we use session count as proxy
    n = len(z_values)
    if n <= 3:
        # Not enough data for CI
        return AggregatedBiasResult(
            length_correlation=round(pooled_r, 3),
            length_correlation_ci=(-1, 1),
            sample_size=n,
            confidence_level="insufficient"
        )

    se = 1 / math.sqrt(n - 3)
    z_lower = pooled_z - 1.96 * se
    z_upper = pooled_z + 1.96 * se
    ci_lower = (math.exp(2 * z_lower) - 1) / (math.exp(2 * z_lower) + 1)
    ci_upper = (math.exp(2 * z_upper) - 1) / (math.exp(2 * z_upper) + 1)

    # Confidence level based on session count
    confidence = (
        "high" if n >= 50 else
        "moderate" if n >= 20 else
        "preliminary"
    )

    return AggregatedBiasResult(
        length_correlation=round(pooled_r, 3),
        length_correlation_ci=(round(ci_lower, 3), round(ci_upper, 3)),
        sample_size=n,
        confidence_level=confidence
    )
```

**Key insight:** We store bias metrics from every session to a JSONL file. After 50+ sessions, we can make statistically valid claims about reviewer behavior.

## Reviewer Profiles

Over time, you build profiles of each reviewer:

```bash
$ llm-council bias-report

=== Reviewer Profiles (50 sessions) ===

openai/gpt-4o
  Mean score: 6.2 (harsh, z=-1.3)
  Score variance: 1.8 (discriminating)
  Reliability: high (50 samples)

anthropic/claude-3-5-sonnet
  Mean score: 7.8 (generous, z=+1.1)
  Score variance: 0.9 (compressed range)
  Reliability: high (50 samples)

google/gemini-1.5-pro
  Mean score: 7.1 (neutral, z=+0.2)
  Score variance: 1.4 (balanced)
  Reliability: high (50 samples)
```

**What this tells you:**
- GPT-4 is a harsh grader (good for catching errors)
- Claude compresses scores toward the top (less discriminating)
- Gemini is your neutral baseline

## What We Don't Do

**We don't auto-adjust scores.** This was a deliberate decision:

> "If a reviewer is 'harsh,' they might simply be the domain expert holding the standard high. Automatically penalizing their scores is a UX minefield."

Instead, we:
1. **Report** bias indicators in metadata
2. **Flag** extreme anomalies
3. **Let users** decide how to respond

The bias audit is diagnostic, not corrective.

## Privacy Considerations

We never store raw queries. Bias records contain:

```json
{
  "schema_version": "1.1.0",
  "session_id": "uuid",
  "reviewer_id": "google/gemini-3-pro",
  "model_id": "anthropic/claude-opus-4.5",
  "position": 2,
  "response_length_chars": 1200,
  "score_value": 8.5,
  "query_hash": null
}
```

Query hashes are opt-in (for grouping similar queries) and use salted HMAC—you can't reverse them to get the original query.

## Practical Takeaways

1. **Expect calibration differences.** GPT and Claude don't grade the same. Use rankings, not raw scores.

2. **Watch for length bias.** If r > 0.7, your reviewers are rewarding verbosity. Add explicit instructions: "Penalize unnecessary wordiness."

3. **Randomize presentation order.** Position bias is real. Shuffle responses before each review.

4. **Aggregate across sessions.** Single-session metrics are indicators. 50+ sessions give you statistical confidence.

5. **Don't auto-correct.** Report bias, let humans decide what to do with it.

---

*This is post 5 of 7. Next: [The Accuracy Ceiling](./06-accuracy-ceiling.md)*

---

*LLM Council is open source: [github.com/amiable-dev/llm-council](https://github.com/amiable-dev/llm-council)*
