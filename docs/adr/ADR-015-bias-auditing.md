# ADR-015: Bias Auditing and Length Correlation Tracking

**Status:** Draft (Ready for Council Review)
**Date:** 2025-12-13
**Decision Makers:** Engineering
**Related:** ADR-010 (Consensus Mechanisms), ADR-014 (Verbosity Penalty)

---

## Context

ADR-010 recommended tracking "correlation between scores and response length" as part of bias auditing. This provides empirical data to:

1. Measure the effectiveness of ADR-014 (verbosity penalty prompts)
2. Detect systematic biases in reviewer models
3. Identify reviewers that consistently favor certain patterns

### The Problem

Without metrics, we cannot:
- Know if verbosity bias exists (or how severe it is)
- Measure if our mitigations (ADR-014) are working
- Detect other systematic biases (e.g., style preferences, position bias)
- Compare reviewer reliability across models

### What to Measure

| Metric | Description | Expected Healthy Range |
|--------|-------------|------------------------|
| **Length-Score Correlation** | Pearson correlation between word count and score | -0.2 to 0.2 (weak) |
| **Position Bias** | Score variation by presentation order (A, B, C...) | < 5% difference |
| **Reviewer Calibration** | Mean and variance of scores per reviewer | Similar across reviewers |
| **Self-Vote Inflation** | Score given to own response vs. others | Should be excluded |

---

## Decision

Implement a bias auditing module that calculates and logs correlation metrics for each council session.

### Proposed Implementation

```python
# bias_audit.py
import numpy as np
from dataclasses import dataclass
from typing import Dict, List, Optional
from scipy import stats

@dataclass
class BiasAuditResult:
    """Results from bias analysis of a council session."""

    # Length bias
    length_score_correlation: float  # Pearson r
    length_score_p_value: float      # Statistical significance
    length_bias_detected: bool       # |r| > 0.3 and p < 0.05

    # Position bias (if randomization data available)
    position_score_variance: Optional[float]
    position_bias_detected: Optional[bool]

    # Reviewer calibration
    reviewer_mean_scores: Dict[str, float]
    reviewer_score_variance: Dict[str, float]
    harsh_reviewers: List[str]      # Mean score < median - 1 std
    generous_reviewers: List[str]   # Mean score > median + 1 std

    # Summary
    overall_bias_risk: str  # "low", "medium", "high"


def calculate_length_correlation(
    responses: List[Dict],
    scores: Dict[str, Dict[str, float]]
) -> tuple[float, float]:
    """
    Calculate Pearson correlation between response length and average score.

    Args:
        responses: List of {model, response} dicts
        scores: {reviewer: {candidate: score}} nested dict

    Returns:
        (correlation coefficient, p-value)
    """
    # Calculate word counts
    word_counts = {r['model']: len(r['response'].split()) for r in responses}

    # Calculate average score per response
    avg_scores = {}
    for candidate in word_counts.keys():
        candidate_scores = [
            s[candidate] for s in scores.values()
            if candidate in s
        ]
        if candidate_scores:
            avg_scores[candidate] = np.mean(candidate_scores)

    # Align data
    models = list(avg_scores.keys())
    lengths = [word_counts[m] for m in models]
    score_values = [avg_scores[m] for m in models]

    if len(models) < 3:
        return 0.0, 1.0  # Insufficient data

    r, p = stats.pearsonr(lengths, score_values)
    return r, p


def audit_reviewer_calibration(
    scores: Dict[str, Dict[str, float]]
) -> Dict[str, Dict[str, float]]:
    """
    Analyze score calibration across reviewers.

    Returns:
        {reviewer: {mean, std, count}}
    """
    calibration = {}
    for reviewer, reviewer_scores in scores.items():
        values = list(reviewer_scores.values())
        if values:
            calibration[reviewer] = {
                "mean": np.mean(values),
                "std": np.std(values),
                "count": len(values)
            }
    return calibration


def run_bias_audit(
    stage1_responses: List[Dict],
    stage2_scores: Dict[str, Dict[str, float]],
    position_mapping: Optional[Dict[str, int]] = None
) -> BiasAuditResult:
    """
    Run full bias audit on a council session.

    Args:
        stage1_responses: List of {model, response} from Stage 1
        stage2_scores: {reviewer: {candidate: score}} from Stage 2
        position_mapping: Optional {candidate: position_shown} for position bias

    Returns:
        BiasAuditResult with all metrics
    """
    # Length correlation
    r, p = calculate_length_correlation(stage1_responses, stage2_scores)
    length_bias = abs(r) > 0.3 and p < 0.05

    # Reviewer calibration
    calibration = audit_reviewer_calibration(stage2_scores)
    means = [c["mean"] for c in calibration.values()]
    median_mean = np.median(means) if means else 5.0
    std_mean = np.std(means) if len(means) > 1 else 1.0

    harsh = [r for r, c in calibration.items() if c["mean"] < median_mean - std_mean]
    generous = [r for r, c in calibration.items() if c["mean"] > median_mean + std_mean]

    # Position bias (if data available)
    position_variance = None
    position_bias = None
    if position_mapping:
        # Group scores by position
        position_scores = {}
        for reviewer, scores in stage2_scores.items():
            for candidate, score in scores.items():
                pos = position_mapping.get(candidate)
                if pos is not None:
                    position_scores.setdefault(pos, []).append(score)

        if position_scores:
            position_means = [np.mean(s) for s in position_scores.values()]
            position_variance = np.var(position_means)
            position_bias = position_variance > 0.5  # Threshold TBD

    # Overall risk assessment
    risk_factors = sum([
        length_bias,
        position_bias or False,
        len(harsh) > 0,
        len(generous) > 0
    ])
    overall_risk = "low" if risk_factors == 0 else "medium" if risk_factors <= 2 else "high"

    return BiasAuditResult(
        length_score_correlation=round(r, 3),
        length_score_p_value=round(p, 4),
        length_bias_detected=length_bias,
        position_score_variance=round(position_variance, 3) if position_variance else None,
        position_bias_detected=position_bias,
        reviewer_mean_scores={r: round(c["mean"], 2) for r, c in calibration.items()},
        reviewer_score_variance={r: round(c["std"], 2) for r, c in calibration.items()},
        harsh_reviewers=harsh,
        generous_reviewers=generous,
        overall_bias_risk=overall_risk
    )
```

### Integration with Council Pipeline

```python
# council.py additions
from llm_council.bias_audit import run_bias_audit

async def run_full_council(user_query: str, ...):
    # ... existing Stage 1, 2, 3 logic ...

    # Optional: Run bias audit
    if BIAS_AUDIT_ENABLED:
        audit_result = run_bias_audit(
            stage1_results,
            extract_scores_from_stage2(stage2_results),
            position_mapping=label_to_position  # Track original position
        )
        metadata["bias_audit"] = asdict(audit_result)

    return stage1, stage2, stage3, metadata
```

### Configuration

```python
# config.py
DEFAULT_BIAS_AUDIT_ENABLED = False  # Off by default (adds latency)
BIAS_AUDIT_ENABLED = os.getenv("LLM_COUNCIL_BIAS_AUDIT", "false").lower() == "true"

# Thresholds
LENGTH_CORRELATION_THRESHOLD = 0.3  # |r| above this = bias detected
POSITION_VARIANCE_THRESHOLD = 0.5   # Score variance by position
```

### Output Example

```json
{
  "bias_audit": {
    "length_score_correlation": 0.42,
    "length_score_p_value": 0.023,
    "length_bias_detected": true,
    "position_score_variance": 0.12,
    "position_bias_detected": false,
    "reviewer_mean_scores": {
      "openai/gpt-4": 6.2,
      "anthropic/claude": 7.8,
      "google/gemini": 7.1
    },
    "harsh_reviewers": ["openai/gpt-4"],
    "generous_reviewers": [],
    "overall_bias_risk": "medium"
  }
}
```

---

## Alternatives Considered

### Alternative 1: External Analytics Only

Log raw data and analyze offline.

**Partially Adopted**: We should log raw data for deeper analysis, but real-time metrics are valuable for immediate feedback.

### Alternative 2: Automatic Score Adjustment

Automatically adjust scores based on detected bias.

**Rejected**: Too aggressive. Better to report bias and let users decide how to respond.

### Alternative 3: Reviewer Weighting

Weight reviewers by historical calibration accuracy.

**Deferred**: Requires historical data collection first. Can be added later based on audit results.

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Adds latency to pipeline | Make audit optional, calculate asynchronously |
| False positives with small N | Require minimum sample size, show confidence |
| Overcomplicates output | Put audit in metadata, not main response |

---

## Questions for Council Review

1. Are the proposed metrics comprehensive? What's missing?
2. What thresholds should trigger bias warnings?
3. Should bias audit results affect the synthesis or just be logged?
4. Should we track reviewer reliability over time (requires persistence)?

---

## Success Metrics

- Bias audit runs without adding >100ms latency
- Length-score correlation decreases after ADR-014 implementation
- Users can identify and respond to systematic biases
