# Quantifying Council Quality: CSS, DDI, and SAS

*Published: January 2026*

---

When the LLM Council returns an answer, how do you know if it's reliable?

Before v0.24.0, you had to trust the process. The three-stage deliberation system was sound—multiple models generating responses, peer review with anonymized evaluation, chairman synthesis—but the output was a black box. Either it worked or it didn't.

Now every council response includes three quality metrics that quantify *how* the council reached its conclusion:

```json
{
  "quality_metrics": {
    "tier": "core",
    "core": {
      "consensus_strength": 0.85,
      "deliberation_depth": 0.72,
      "synthesis_attribution": {
        "winner_alignment": 0.78,
        "max_source_alignment": 0.82,
        "hallucination_risk": 0.18,
        "grounded": true
      }
    },
    "warnings": []
  }
}
```

This post explains what these metrics mean and when to act on them.

## The Problem: Trust Without Evidence

Multi-model systems promise better answers through deliberation. But deliberation quality varies:

- **Unanimous agreement** on a wrong answer is worse than healthy debate
- **Copy-paste synthesis** defeats the purpose of having multiple perspectives
- **Shallow reviews** that say "looks good" provide no signal

Without metrics, you can't distinguish between a carefully deliberated answer and a rubber-stamped consensus.

## The Solution: Three Complementary Metrics

ADR-036 introduces three metrics that exploit the multi-stage structure of the council:

| Metric | Stage | Question Answered |
|--------|-------|-------------------|
| **CSS** (Consensus Strength Score) | Stage 2 | Did reviewers agree on quality? |
| **DDI** (Deliberation Depth Index) | Stages 1+2 | Was the deliberation thorough? |
| **SAS** (Synthesis Attribution Score) | Stage 3 | Is the synthesis grounded in sources? |

Each metric is a float in `[0.0, 1.0]`. Higher is generally better, but interpretation depends on context.

### Quick Decision Guide

| CSS | SAS | DDI | Interpretation |
|-----|-----|-----|----------------|
| High | High | Any | Trust the answer |
| High | Low | Any | Consensus but check for hallucination |
| Low | High | High | Genuine disagreement, well-explored |
| Low | Low | Low | Retry with different models/prompt |

While these metrics measure different aspects, they're not independent. Deep deliberation (high DDI) often produces clearer consensus (high CSS), but not always—genuine disagreement can be thoroughly explored.

## Consensus Strength Score (CSS)

CSS measures how much reviewers agreed during Stage 2 peer evaluation.

### How It Works

During Stage 2, each model ranks all anonymized responses. CSS analyzes the aggregate rankings:

```python
def consensus_strength_score(
    aggregate_rankings: List[Tuple[str, float]],
    stage2_results: Optional[List[dict]] = None,
) -> float:
    """
    CSS = (winner_margin * 0.4) + (ordering_clarity * 0.4) + (non_tie_factor * 0.2)
    """
```

**Three components:**

1. **Winner Margin (40%)**: How far ahead is #1 from #2? A dominant winner means clear agreement.

2. **Ordering Clarity (40%)**: Are positions evenly spread or clustered? Clear ordering (1, 2, 3, 4) indicates consistent evaluations.

3. **Non-Tie Factor (20%)**: How many unique positions exist? Ties indicate disagreement.

### Interpretation

| CSS | Meaning | Recommendation |
|-----|---------|----------------|
| 0.85+ | Strong consensus | High confidence in synthesis |
| 0.70-0.84 | Moderate consensus | Synthesis reliable, note minority views |
| 0.50-0.69 | Weak consensus | Consider `include_dissent=true` |
| <0.50 | Significant disagreement | Use `verdict_type="debate"` mode |

### Example: Strong Consensus

```python
# All reviewers agree: model_a is clearly best, others ordered consistently
aggregate_rankings = [
    ("model_a", 1.0),  # Dominant winner (everyone ranked first)
    ("model_b", 3.5),  # Pack clustered behind
    ("model_c", 3.5),
    ("model_d", 4.0),
]
css = consensus_strength_score(aggregate_rankings)
# css ≈ 0.78 - Strong consensus on the winner
```

### Example: Split Consensus

```python
# 2-2 split: reviewers disagree on which response is best
aggregate_rankings = [
    ("model_a", 1.5),  # Tied for 1st-2nd
    ("model_b", 1.5),
    ("model_c", 3.5),  # Tied for 3rd-4th
    ("model_d", 3.5),
]
css = consensus_strength_score(aggregate_rankings)
# css ≈ 0.45 - Significant disagreement
```

When CSS is low, the council couldn't agree on the best response. In these cases, `verdict_type="debate"` mode can surface the competing perspectives explicitly.

## Deliberation Depth Index (DDI)

DDI measures how thoroughly the council deliberated—diversity of thought plus rigor of review.

### How It Works

```python
def deliberation_depth_index_sync(
    stage1_responses: List[str],
    stage2_rankings: List[dict],
) -> Tuple[float, dict]:
    """
    DDI = (diversity * 0.35) + (coverage * 0.35) + (richness * 0.30)
    """
```

**Three components:**

1. **Response Diversity (35%)**: How different were the Stage 1 responses? Measured via Jaccard dissimilarity on tokenized content.

2. **Review Coverage (35%)**: What percentage of models completed their Stage 2 evaluation? Coverage < 1.0 indicates model failures.

3. **Critique Richness (30%)**: How substantive were the reviews? Longer, more detailed critiques suggest careful evaluation.

### Interpretation

| DDI | Meaning | What It Indicates |
|-----|---------|-------------------|
| 0.70+ | Deep deliberation | Diverse perspectives, thorough reviews |
| 0.50-0.69 | Adequate deliberation | Standard quality |
| 0.40-0.49 | Shallow deliberation | Consider adding models or reviewing prompts |
| <0.40 | Minimal deliberation | ⚠️ `shallow_deliberation` warning |

### Example: High Diversity

When models approach a problem differently:

```python
responses = [
    "The best approach uses recursion with memoization...",
    "I recommend an iterative dynamic programming solution...",
    "Consider using a mathematical formula for O(1) lookup...",
    "Here's a clean functional approach using fold..."
]
ddi, components = deliberation_depth_index_sync(responses, stage2_rankings)
# components["diversity"] ≈ 0.75 (responses have different token sets)
```

### Example: Low Diversity

When models converge on similar answers:

```python
responses = [
    "Use a hash map for O(1) lookup. Store keys and values.",
    "A hash map provides O(1) lookup time. Store key-value pairs.",
    "Hash maps offer constant time lookup. Use for key-value storage.",
    "The hash map data structure gives O(1) lookups. Keys map to values."
]
ddi, components = deliberation_depth_index_sync(responses, stage2_rankings)
# components["diversity"] ≈ 0.25 (high token overlap)
```

Low diversity isn't always bad—it can indicate genuine consensus on the correct approach. But combined with low CSS, it might suggest the models are reinforcing each other's biases.

## Synthesis Attribution Score (SAS)

SAS measures whether the Stage 3 synthesis is grounded in the Stage 1 responses.

### How It Works

```python
def synthesis_attribution_score_sync(
    synthesis: str,
    winning_responses: List[str],  # Top 1-2 ranked
    all_responses: List[str],
    grounding_threshold: float = 0.6,
) -> SynthesisAttribution:
    """
    Returns:
        winner_alignment: How well synthesis matches top responses
        max_source_alignment: Best match to any response
        hallucination_risk: 1 - max_source_alignment
        grounded: bool (max_source_alignment >= threshold)
    """
```

The score uses Jaccard similarity between synthesis and source responses. If the synthesis introduces content not present in any source, hallucination risk increases.

### Interpretation

| SAS Field | Good Value | Warning |
|-----------|------------|---------|
| `winner_alignment` | >0.5 | Synthesis follows ranking |
| `max_source_alignment` | >0.6 | Synthesis grounded in sources |
| `hallucination_risk` | <0.4 | Low novel content |
| `grounded` | `true` | No `synthesis_not_grounded` warning |

### Example: Well-Grounded Synthesis

```python
winning_response = "Use async/await for concurrent I/O operations..."
synthesis = "The council recommends using async/await patterns for concurrent I/O..."

sas = synthesis_attribution_score_sync(synthesis, [winning_response], all_responses)
# sas.winner_alignment ≈ 0.72
# sas.grounded = True
```

### Example: Hallucination Risk

```python
winning_response = "Use async/await for concurrent operations..."
synthesis = "The council recommends Redis pub/sub with worker pools..."  # Not mentioned!

sas = synthesis_attribution_score_sync(synthesis, [winning_response], all_responses)
# sas.max_source_alignment ≈ 0.25
# sas.hallucination_risk ≈ 0.75
# sas.grounded = False
# warnings = ["hallucination_risk", "synthesis_not_grounded"]
```

When `grounded=False`, the chairman may have introduced content not supported by the deliberation. This doesn't mean the synthesis is wrong—the chairman might be adding valuable context—but it warrants review.

## Warnings System

Quality metrics automatically generate warnings when thresholds are crossed:

```python
warnings: List[str] = []

if css < 0.5:
    warnings.append("low_consensus")

if ddi < 0.4:
    warnings.append("shallow_deliberation")

if sas.hallucination_risk > 0.4:
    warnings.append("hallucination_risk")

if not sas.grounded:
    warnings.append("synthesis_not_grounded")
```

An empty `warnings` array means the council session met all quality thresholds.

## What to Do About Low Scores

When metrics indicate problems, here's how to respond:

| Low Metric | Likely Cause | Remediation |
|------------|--------------|-------------|
| CSS | Models disagree on best answer | Add a fourth model, use `verdict_type="debate"`, or increase response diversity |
| DDI | Similar responses or terse reviews | Increase temperature, add more models, or review prompts for specificity |
| SAS | Chairman added unsupported content | Enable `include_dissent=true` to see minority views, or review synthesis prompt |

**Example: Low CSS + High DDI**

This combination means thorough exploration of genuinely different perspectives—a "healthy debate." The synthesis may not represent unanimous agreement, so consider surfacing minority views:

```python
result = await consult_council(
    query="Should I use microservices or monolith?",
    include_dissent=True  # Surface minority opinions
)
```

## Visual Display in MCP

When using the MCP tool, quality metrics display as visual progress bars:

```
### Quality Metrics
- **Consensus Strength**: 0.85 [████████░░]
- **Deliberation Depth**: 0.72 [███████░░░]
- **Synthesis Grounded**: Yes (risk: 0.18)
```

This makes quality visible at a glance during interactive sessions.

## Configuration

Quality metrics are enabled by default. To disable:

```bash
export LLM_COUNCIL_QUALITY_METRICS=false
```

Or in `llm_council.yaml`:

```yaml
quality:
  enabled: false
```

## Tier System

The current implementation is **Tier 1 (Core)**, available in the open source release. Future tiers will add:

| Tier | Metrics |
|------|---------|
| **Core** (OSS) | CSS, DDI, SAS |
| **Standard** (Paid) | + Temporal Consistency, Cross-Model Calibration |
| **Enterprise** (Paid) | + DeepEval/RAGAS integration, Golden datasets |

Tier 2/3 infrastructure is designed but implementations are reserved for future releases.

## Performance Impact

Quality metrics add minimal overhead to council deliberation:

| Component | Time Added | When |
|-----------|------------|------|
| CSS calculation | <5ms | After Stage 2 |
| DDI calculation | <10ms | After Stages 1+2 |
| SAS calculation | <15ms | After Stage 3 |
| **Total** | **<30ms** | Post-synthesis |

All calculations happen locally after existing stages complete—no additional LLM API calls. The deliberation itself (Stage 1-3) dominates latency at 10-40 seconds; quality metrics are negligible.

## Technical Notes

### Jaccard Similarity: Limitations

Phase 1 uses Jaccard similarity on tokenized text. This measures *lexical* overlap, not *semantic* meaning:

```python
def _jaccard_similarity(text1: str, text2: str) -> float:
    tokens1 = set(text1.lower().split())
    tokens2 = set(text2.lower().split())
    if not tokens1 or not tokens2:
        return 0.0
    intersection = tokens1 & tokens2
    union = tokens1 | tokens2
    return len(intersection) / len(union)
```

**Known limitation**: "The code is buggy" and "The implementation contains errors" have low Jaccard similarity despite identical meaning. This is intentional—Jaccard is fast, offline-compatible, and dependency-free. For production workloads requiring semantic understanding, Tier 2/3 will offer embedding-based similarity via configurable providers.

**Why not embeddings for OSS?** Embeddings require either an API call (adds latency, cost, and network dependency) or a local model (adds ~500MB dependency). Jaccard keeps the core tier lightweight and works offline.

### Threshold Calibration

The interpretation thresholds (CSS 0.85+ = strong, DDI 0.70+ = deep, SAS 0.6 = grounded) are starting points derived from internal testing across ~200 council sessions. They're tunable per use case—a debate-heavy domain might lower the CSS "strong" threshold to 0.75.

### Metric Limitations

Every metric has failure modes:

- **CSS** can be high when models are confidently wrong together ("echo chamber")
- **DDI** can be gamed by verbose but shallow responses
- **SAS** token-matching misses semantic equivalence ("large" vs "big")

These metrics are *indicators*, not guarantees. High scores suggest reliability; low scores flag potential issues for human review.

### Test Coverage

Quality metrics are thoroughly tested with 44 unit tests covering:

- Edge cases (empty inputs, single responses)
- Boundary conditions (threshold values)
- Component isolation (diversity, coverage, richness)
- Integration with council pipeline

## Try It

```bash
# Upgrade to v0.24.0
pip install --upgrade llm-council-core

# Run a council query
llm-council query "What's the best way to handle async errors in Python?"

# Quality metrics appear in the response
```

Or via MCP:

```python
result = await consult_council(
    query="Explain the CAP theorem",
    confidence="high"
)
print(result["quality_metrics"])
```

---

*Quality metrics transform LLM Council from a black-box deliberation system into an observable one. When CSS, DDI, and SAS all score high, you can trust the answer. When they don't, you know exactly why.*
