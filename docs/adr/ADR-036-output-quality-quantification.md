# ADR-036: Output Quality Quantification Framework

| Field | Value |
|-------|-------|
| **Status** | Accepted |
| **Date** | 2025-12-29 |
| **Implemented** | 2026-01-03 (Phase 1) |
| **Author** | Chris (amiable-dev) |
| **Supersedes** | - |
| **Related ADRs** | ADR-015 (Bias Auditing), ADR-016 (Structured Rubric Scoring), ADR-018 (Cross-Session Bias Aggregation), ADR-025b (Jury Mode), ADR-030 (Scoring Refinements) |

---

## Context

LLM Council implements a sophisticated multi-stage peer review system where multiple LLMs deliberate to produce synthesized answers. While existing ADRs address internal mechanics (rubric scoring, bias detection, consensus mechanisms), we lack a comprehensive framework for quantifying the **accuracy and quality of the council's final output** in a way that:

1. Provides meaningful metrics to users about answer reliability
2. Enables regression testing and quality monitoring over time
3. Supports differentiated value propositions between OSS and paid tiers
4. Integrates with established LLM evaluation frameworks in the ecosystem

The current gap: users receive a synthesized answer but have limited visibility into *how confident* the council is, *how much agreement* existed, and whether the answer meets objective quality thresholds.

### Industry Context

The LLM evaluation landscape has matured significantly, with frameworks like DeepEval, RAGAS, Promptfoo, TruLens, and LangSmith providing standardized approaches to quantifying LLM output quality. Key patterns emerging:

- **LLM-as-a-Judge** has become the dominant paradigm, replacing traditional metrics (BLEU/ROUGE) that poorly capture semantic nuance
- **Multi-dimensional rubric scoring** with weighted dimensions (similar to our ADR-016)
- **Faithfulness/groundedness metrics** for RAG-style systems
- **Confidence calibration** to detect overconfident or underconfident outputs
- **Statistical aggregation** across sessions for meaningful trend analysis

LLM Council's unique architecture—where multiple LLMs already evaluate each other in Stage 2—provides inherent advantages for quality quantification that single-model systems cannot match.

---

## Decision

Implement a **three-tier Output Quality Quantification (OQQ) framework** that exposes quality metrics at increasing levels of sophistication:

### Tier 1: Core Metrics (OSS)

Available in the open-source package, included in all council responses:

#### 1.1 Consensus Strength Score (CSS)

A normalized 0.0–1.0 score indicating the level of agreement among council members during Stage 2 peer review.

**Calculation:**
```python
def consensus_strength_score(rankings: list[dict]) -> float:
    """
    Calculate consensus strength from Stage 2 rankings.
    
    High CSS (>0.8): Strong agreement, high confidence in synthesis
    Medium CSS (0.5-0.8): Moderate agreement, nuanced topic
    Low CSS (<0.5): Significant disagreement, consider debate mode
    """
    # Extract Borda scores per response
    borda_scores = aggregate_borda_scores(rankings)
    
    # Normalize to 0-1 range
    normalized = normalize_scores(borda_scores)
    
    # Calculate score spread (low spread = high consensus)
    spread = max(normalized) - min(normalized)
    
    # Invert: high spread means clear winner = high consensus
    # But also factor in clustering (are scores bunched?)
    variance = statistics.variance(normalized)
    
    # CSS formula: balance spread (clear winner) with low variance (agreement)
    css = (spread * 0.6) + ((1 - variance) * 0.4)
    
    return round(css, 3)
```

**Interpretation:**
| CSS Range | Interpretation | Recommended Action |
|-----------|---------------|-------------------|
| 0.85–1.0 | Strong consensus | High confidence in synthesis |
| 0.70–0.84 | Moderate consensus | Synthesis reliable, note minority views |
| 0.50–0.69 | Weak consensus | Consider `include_dissent=true` |
| < 0.50 | Significant disagreement | Recommend debate mode |

#### 1.2 Deliberation Depth Index (DDI)

Quantifies how thoroughly the council considered the query.

**Components:**
- **Response Diversity** (0.0–1.0): Semantic dissimilarity of Stage 1 responses
- **Review Coverage** (0.0–1.0): Percentage of valid rankings received
- **Critique Richness** (0.0–1.0): Average length/detail of Stage 2 justifications

```python
def deliberation_depth_index(
    stage1_responses: list[str],
    stage2_rankings: list[dict],
    stage2_justifications: list[str]
) -> float:
    """
    Higher DDI indicates more thorough deliberation.
    """
    # Response diversity via embedding cosine distances
    embeddings = embed_responses(stage1_responses)
    diversity = average_pairwise_distance(embeddings)
    
    # Review coverage (did all models participate in Stage 2?)
    expected_reviews = len(stage1_responses) ** 2
    actual_reviews = len(stage2_rankings)
    coverage = actual_reviews / expected_reviews
    
    # Critique richness (non-trivial justifications)
    avg_justification_tokens = mean([len(j.split()) for j in stage2_justifications])
    richness = min(1.0, avg_justification_tokens / 50)  # 50 tokens = 1.0
    
    # Weighted combination
    ddi = (diversity * 0.35) + (coverage * 0.35) + (richness * 0.30)
    
    return round(ddi, 3)
```

#### 1.3 Synthesis Attribution Score (SAS)

When using `include_details=true`, indicates how well the final synthesis traces back to peer-reviewed responses.

```python
def synthesis_attribution_score(
    synthesis: str,
    winning_responses: list[str],
    all_responses: list[str]
) -> dict:
    """
    Measures attribution of synthesis to source responses.
    """
    synthesis_embedding = embed(synthesis)
    
    # How much does synthesis align with top-ranked responses?
    winner_similarity = mean([
        cosine_similarity(synthesis_embedding, embed(r))
        for r in winning_responses
    ])
    
    # Is synthesis grounded in ANY council response?
    max_similarity = max([
        cosine_similarity(synthesis_embedding, embed(r))
        for r in all_responses
    ])
    
    # Hallucination risk: synthesis diverges from all responses
    hallucination_risk = 1.0 - max_similarity
    
    return {
        "winner_alignment": round(winner_similarity, 3),
        "max_source_alignment": round(max_similarity, 3),
        "hallucination_risk": round(hallucination_risk, 3),
        "grounded": max_similarity > 0.6
    }
```

### Tier 2: Enhanced Analytics (Paid - Standard)

Extended metrics for organizations requiring quality assurance:

#### 2.1 Temporal Consistency Score (TCS)

Track whether council responses to similar queries remain consistent over time. Requires persistence (builds on ADR-018).

```python
def temporal_consistency_score(
    current_response: str,
    historical_responses: list[tuple[str, datetime]],
    query_similarity_threshold: float = 0.85
) -> dict:
    """
    For semantically similar past queries, measure response consistency.
    """
    current_embedding = embed(current_response)
    
    similar_historical = [
        (resp, ts) for resp, ts in historical_responses
        if cosine_similarity(embed(resp), current_embedding) > query_similarity_threshold
    ]
    
    if len(similar_historical) < 3:
        return {"status": "insufficient_data", "score": None}
    
    # Calculate drift from historical consensus
    historical_mean = mean_embedding([embed(r) for r, _ in similar_historical])
    drift = 1.0 - cosine_similarity(current_embedding, historical_mean)
    
    return {
        "status": "calculated",
        "score": round(1.0 - drift, 3),
        "sample_size": len(similar_historical),
        "drift_detected": drift > 0.2
    }
```

#### 2.2 Cross-Model Calibration Report

Extends ADR-015 bias auditing with calibration curves per model.

```yaml
calibration_report:
  session_count: 147
  confidence_level: "high"  # Per ADR-018 thresholds
  
  models:
    "anthropic/claude-opus-4.5":
      mean_score_given: 7.2
      mean_score_received: 7.8
      calibration_delta: -0.6  # Tends to score harshly
      self_preference_rate: 0.12  # 12% of time ranks self #1
      
    "openai/gpt-4o":
      mean_score_given: 7.6
      mean_score_received: 7.4
      calibration_delta: +0.2
      self_preference_rate: 0.08
      
  recommendations:
    - "claude-opus-4.5 scores 0.6 points below median; consider calibration weight"
    - "Cross-session length bias: r=0.42 (moderate positive correlation)"
```

#### 2.3 Rubric Dimension Breakdown

When ADR-016 rubric scoring is enabled, expose per-dimension aggregates:

```json
{
  "rubric_breakdown": {
    "accuracy": {
      "mean": 8.2,
      "std": 0.9,
      "ceiling_applied": false
    },
    "relevance": {
      "mean": 8.7,
      "std": 0.4,
      "weight": 0.10
    },
    "completeness": {
      "mean": 7.4,
      "std": 1.2,
      "weight": 0.20,
      "flag": "high variance suggests split opinions"
    },
    "conciseness": {
      "mean": 6.8,
      "std": 0.7,
      "weight": 0.15
    },
    "clarity": {
      "mean": 8.1,
      "std": 0.5,
      "weight": 0.20
    },
    "weighted_composite": 7.73,
    "accuracy_ceiling_effect": "none"
  }
}
```

### Tier 3: Enterprise Quality Assurance (Paid - Enterprise)

Comprehensive quality pipeline with external validation:

#### 3.1 External Evaluation Framework Integration

Integrate with industry-standard evaluation frameworks for validation:

**DeepEval Integration:**
```python
from deepeval import assert_test
from deepeval.metrics import GEval, AnswerRelevancyMetric, HallucinationMetric
from deepeval.test_case import LLMTestCase

async def validate_council_output(
    query: str,
    council_response: str,
    ground_truth: Optional[str] = None,
    context: Optional[list[str]] = None
) -> dict:
    """
    Validate council output using DeepEval metrics.
    """
    test_case = LLMTestCase(
        input=query,
        actual_output=council_response,
        expected_output=ground_truth,
        retrieval_context=context
    )
    
    metrics = []
    
    # Answer relevancy (always)
    relevancy = AnswerRelevancyMetric(threshold=0.7)
    await relevancy.a_measure(test_case)
    metrics.append(("relevancy", relevancy.score, relevancy.reason))
    
    # Hallucination (if context provided)
    if context:
        hallucination = HallucinationMetric(threshold=0.5)
        await hallucination.a_measure(test_case)
        metrics.append(("hallucination_free", 1.0 - hallucination.score, hallucination.reason))
    
    # Correctness (if ground truth provided)
    if ground_truth:
        correctness = GEval(
            name="Correctness",
            criteria="Factual accuracy compared to ground truth",
            evaluation_params=["actual_output", "expected_output"],
            threshold=0.7
        )
        await correctness.a_measure(test_case)
        metrics.append(("correctness", correctness.score, correctness.reason))
    
    return {
        "validation_framework": "deepeval",
        "metrics": {name: {"score": score, "reason": reason} for name, score, reason in metrics},
        "overall_pass": all(score >= 0.7 for _, score, _ in metrics)
    }
```

**RAGAS Integration (for RAG-enhanced council queries):**
```python
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy, context_precision

async def validate_rag_council_output(
    query: str,
    council_response: str,
    retrieved_context: list[str],
    ground_truth: str
) -> dict:
    """
    For council queries that included RAG context.
    """
    dataset = Dataset.from_dict({
        "question": [query],
        "answer": [council_response],
        "contexts": [retrieved_context],
        "ground_truth": [ground_truth]
    })
    
    result = evaluate(
        dataset,
        metrics=[faithfulness, answer_relevancy, context_precision]
    )
    
    return {
        "validation_framework": "ragas",
        "metrics": result.to_dict(),
        "faithfulness_score": result["faithfulness"],
        "rag_quality_pass": result["faithfulness"] >= 0.8
    }
```

#### 3.2 Golden Dataset Regression Testing

Maintain organization-specific golden datasets for regression testing:

```yaml
# llm_council_golden.yaml
golden_datasets:
  - name: "compliance_queries"
    description: "Regulatory compliance questions with verified answers"
    queries:
      - id: "gdpr-001"
        query: "What are the key requirements for GDPR data portability?"
        ground_truth: "Article 20 requires..."
        minimum_scores:
          accuracy: 8
          completeness: 7
        required_mentions:
          - "Article 20"
          - "machine-readable format"
          - "30 days"
        forbidden_claims:
          - "automatic"  # Common hallucination
          
  - name: "technical_architecture"
    description: "Cloud architecture decision questions"
    evaluation_mode: "expert_review"  # Requires human validation
    queries:
      - id: "arch-001"
        query: "Microservices vs monolith for a 10-person startup?"
        rubric:
          - dimension: "trade_off_coverage"
            weight: 0.3
            criteria: "Mentions both approaches' pros/cons"
          - dimension: "context_awareness"
            weight: 0.3
            criteria: "Considers team size and startup constraints"
          - dimension: "actionability"
            weight: 0.4
            criteria: "Provides clear recommendation with reasoning"
```

**Regression Test Runner:**
```python
async def run_regression_suite(
    golden_dataset: str,
    council_config: CouncilConfig
) -> RegressionReport:
    """
    Run council against golden dataset and compare to historical baselines.
    """
    dataset = load_golden_dataset(golden_dataset)
    results = []
    
    for case in dataset.queries:
        # Run council
        stage1, stage2, stage3, metadata = await run_full_council(
            case.query,
            confidence=council_config.confidence_level
        )
        
        # Validate against case criteria
        validation = await validate_against_case(stage3, case)
        
        results.append({
            "case_id": case.id,
            "passed": validation.passed,
            "scores": validation.scores,
            "regressions": validation.regressions_from_baseline
        })
    
    return RegressionReport(
        dataset=golden_dataset,
        timestamp=datetime.utcnow(),
        pass_rate=sum(r["passed"] for r in results) / len(results),
        results=results,
        baseline_comparison=compare_to_baseline(results, dataset)
    )
```

#### 3.3 Continuous Quality Monitoring Dashboard

Real-time quality metrics exposed via API and webhooks:

```python
@dataclass
class QualityMonitoringEvent:
    """Emitted after each council deliberation for monitoring systems."""
    timestamp: datetime
    request_id: str
    query_hash: str  # Privacy-preserving hash
    
    # Tier 1 metrics
    consensus_strength: float
    deliberation_depth: float
    synthesis_attribution: dict
    
    # Tier 2 metrics (if enabled)
    rubric_breakdown: Optional[dict]
    bias_indicators: Optional[dict]
    
    # Tier 3 metrics (if validation enabled)
    external_validation: Optional[dict]
    
    # Alerts
    alerts: list[str]  # e.g., ["low_consensus", "hallucination_risk"]

# Webhook integration
async def emit_quality_event(event: QualityMonitoringEvent):
    """Emit to configured monitoring endpoints."""
    for webhook in config.monitoring_webhooks:
        await dispatch_webhook(webhook, event.to_dict())
```

---

## Metric Exposure Strategy

### API Response Enhancement

All council responses include a `quality_metrics` object:

```json
{
  "stage3_response": "The synthesized answer...",
  "metadata": {
    "duration_ms": 4523,
    "models_participated": ["claude-opus-4.5", "gpt-4o", "gemini-3-pro"],
    
    "quality_metrics": {
      "tier": "standard",  // "core" | "standard" | "enterprise"
      
      "core": {
        "consensus_strength": 0.82,
        "deliberation_depth": 0.74,
        "synthesis_attribution": {
          "winner_alignment": 0.89,
          "hallucination_risk": 0.08,
          "grounded": true
        }
      },
      
      "standard": {  // Paid tier only
        "rubric_breakdown": { ... },
        "calibration_notes": ["claude-opus-4.5 scored 0.5 below peer average"]
      },
      
      "enterprise": {  // Enterprise tier only
        "external_validation": {
          "deepeval_relevancy": 0.91,
          "deepeval_hallucination_free": 0.94
        },
        "regression_baseline_delta": +0.03
      }
    },
    
    "quality_alerts": []  // Empty = no concerns
  }
}
```

### CLI Quality Reports

```bash
# Per-session quality summary
llm-council quality-report --session latest

# Cross-session quality trends (requires persistence)
llm-council quality-report --sessions 50 --format json

# Regression test against golden dataset
llm-council regression-test --dataset compliance_queries --output report.html
```

### MCP Tool Enhancement

Update `consult_council` tool to accept quality options:

```python
@mcp_tool
async def consult_council(
    query: str,
    confidence: str = "high",
    include_details: bool = False,
    verdict_type: str = "synthesis",
    include_dissent: bool = False,
    # New quality options
    quality_metrics: bool = True,  # Include Tier 1 metrics
    validate_output: bool = False,  # Run external validation (Tier 3)
    ground_truth: Optional[str] = None  # For correctness validation
) -> CouncilResponse:
    ...
```

---

## OSS vs Paid Tier Differentiation

| Capability | OSS (Free) | Standard (Paid) | Enterprise (Paid) |
|------------|------------|-----------------|-------------------|
| **Consensus Strength Score** | ✅ | ✅ | ✅ |
| **Deliberation Depth Index** | ✅ | ✅ | ✅ |
| **Synthesis Attribution** | ✅ | ✅ | ✅ |
| **Per-response rubric breakdown** | ❌ | ✅ | ✅ |
| **Cross-model calibration reports** | ❌ | ✅ | ✅ |
| **Temporal consistency tracking** | ❌ | ✅ | ✅ |
| **Cross-session bias aggregation** | Basic (ADR-018) | Enhanced | Full |
| **DeepEval/RAGAS integration** | ❌ | ❌ | ✅ |
| **Golden dataset regression testing** | ❌ | ❌ | ✅ |
| **Continuous monitoring webhooks** | ❌ | ❌ | ✅ |
| **Quality SLA guarantees** | ❌ | ❌ | ✅ |
| **Historical quality data retention** | 7 days | 90 days | Unlimited |

### Value Proposition Alignment

**OSS Users (Developers, Hobbyists):**
- Get immediate feedback on answer reliability
- Core metrics sufficient for most use cases
- Builds trust and drives adoption

**Standard Tier (Teams, Small Organizations):**
- Understand *why* quality varies (rubric dimensions, calibration)
- Track quality over time for regression detection
- Justify council usage to stakeholders

**Enterprise Tier (Regulated Industries, Large Organizations):**
- External validation for audit trails
- Golden dataset integration for compliance
- SLA-backed quality guarantees
- Continuous monitoring for production systems

---

## Implementation Phases

### Phase 1: Core Metrics (OSS) — 2 weeks
- [ ] Implement `consensus_strength_score()` in `council.py`
- [ ] Implement `deliberation_depth_index()` with embedding service
- [ ] Implement `synthesis_attribution_score()` 
- [ ] Add `quality_metrics` to response metadata
- [ ] Update MCP tool schema
- [ ] Documentation and examples

### Phase 2: Enhanced Analytics — 3 weeks
- [ ] Temporal consistency tracking (extend ADR-018 persistence)
- [ ] Cross-model calibration report generation
- [ ] Rubric breakdown exposure (extend ADR-016)
- [ ] CLI `quality-report` command
- [ ] Tier gating infrastructure

### Phase 3: Enterprise Quality Assurance — 4 weeks
- [ ] DeepEval integration module
- [ ] RAGAS integration module
- [ ] Golden dataset schema and loader
- [ ] Regression test runner
- [ ] Monitoring webhook system
- [ ] Dashboard API endpoints

---

## Consequences

### Positive

1. **User Trust**: Quantified quality metrics build confidence in council outputs
2. **Regression Detection**: Quality trends surface degradation before users notice
3. **Differentiated Value**: Clear tier separation justifies paid offerings
4. **Ecosystem Alignment**: Integration with established frameworks (DeepEval, RAGAS) provides familiar patterns
5. **Auditability**: Enterprise customers can demonstrate due diligence for AI-assisted decisions

### Negative

1. **Complexity**: Additional computation per request (mitigated by optional flags)
2. **Latency**: External validation adds ~500-2000ms (Tier 3 only, async option available)
3. **Dependencies**: External frameworks introduce versioning concerns
4. **Storage**: Historical quality data requires persistence infrastructure

### Risks

1. **Metric Gaming**: Users may over-optimize for metrics rather than actual quality
   - *Mitigation*: Multiple complementary metrics, emphasize holistic interpretation
   
2. **False Confidence**: High scores on flawed queries could mislead users
   - *Mitigation*: Clear documentation of metric limitations, confidence intervals
   
3. **Framework Churn**: External evaluation frameworks evolve rapidly
   - *Mitigation*: Abstraction layer, version pinning, graceful degradation

---

## References

1. [DeepEval Documentation](https://docs.confident-ai.com/)
2. [RAGAS Metrics](https://docs.ragas.io/en/latest/concepts/metrics/)
3. [LLM-as-a-Judge: MT-Bench and Chatbot Arena](https://arxiv.org/abs/2306.05685)
4. [G-Eval: NLG Evaluation using GPT-4](https://arxiv.org/abs/2303.16634)
5. ADR-015: Per-Session Bias Audit
6. ADR-016: Structured Rubric Scoring
7. ADR-018: Cross-Session Bias Aggregation
8. ADR-025b: Jury Mode (Binary Verdicts)
9. ADR-030: Scoring Refinements

---

## Appendix A: Example Quality Report

```
╔══════════════════════════════════════════════════════════════════╗
║                  LLM Council Quality Report                       ║
║                  Session: 2025-12-29T14:32:00Z                    ║
╠══════════════════════════════════════════════════════════════════╣
║ CORE METRICS (Tier 1)                                             ║
╠═══════════════════════╦══════════╦═══════════════════════════════╣
║ Consensus Strength    ║   0.84   ║ ████████░░ Strong consensus   ║
║ Deliberation Depth    ║   0.71   ║ ███████░░░ Adequate depth     ║
║ Winner Alignment      ║   0.89   ║ █████████░ Well-grounded      ║
║ Hallucination Risk    ║   0.06   ║ █░░░░░░░░░ Low risk           ║
╠═══════════════════════╩══════════╩═══════════════════════════════╣
║ RUBRIC BREAKDOWN (Tier 2)                                         ║
╠═══════════════════════╦══════════╦═══════════════════════════════╣
║ Accuracy (35%)        ║   8.4    ║ ████████░░                    ║
║ Relevance (10%)       ║   9.1    ║ █████████░                    ║
║ Completeness (20%)    ║   7.2    ║ ███████░░░ ⚠ High variance    ║
║ Conciseness (15%)     ║   6.9    ║ ███████░░░                    ║
║ Clarity (20%)         ║   8.0    ║ ████████░░                    ║
╠═══════════════════════╬══════════╬═══════════════════════════════╣
║ Weighted Composite    ║   7.82   ║ Above baseline (+0.3)         ║
╠═══════════════════════╩══════════╩═══════════════════════════════╣
║ CALIBRATION NOTES                                                 ║
║ • claude-opus-4.5 scored 0.4 below peer average (harsh reviewer)  ║
║ • No position bias detected (variance: 0.12)                      ║
║ • Length correlation: r=0.18 (acceptable)                         ║
╠══════════════════════════════════════════════════════════════════╣
║ ALERTS: None                                                      ║
╚══════════════════════════════════════════════════════════════════╝
```

---

## Appendix B: Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_COUNCIL_QUALITY_METRICS` | Enable quality metrics in responses | `true` |
| `LLM_COUNCIL_QUALITY_TIER` | Quality tier (`core`, `standard`, `enterprise`) | `core` |
| `LLM_COUNCIL_EMBEDDING_MODEL` | Model for DDI/SAS embeddings | `text-embedding-3-small` |
| `LLM_COUNCIL_EXTERNAL_VALIDATION` | Enable DeepEval/RAGAS validation | `false` |
| `LLM_COUNCIL_GOLDEN_DATASET_PATH` | Path to golden dataset YAML | - |
| `LLM_COUNCIL_QUALITY_WEBHOOK_URL` | Monitoring webhook endpoint | - |
| `LLM_COUNCIL_QUALITY_RETENTION_DAYS` | Historical data retention | `7` (OSS) |

---

## Implementation Changelog

### Phase 1 (v0.24.0) - 2026-01-03

**Core Metrics Implemented:**

1. **Consensus Strength Score (CSS)**
   - Winner margin (40%): Gap between #1 and #2 positions
   - Ordering clarity (40%): Uniformity of position distribution
   - Non-tie factor (20%): Penalty for tied positions

2. **Deliberation Depth Index (DDI)**
   - Response diversity (35%): Jaccard-based dissimilarity
   - Review coverage (35%): Fraction of expected reviewers
   - Critique richness (30%): Token count of justifications

3. **Synthesis Attribution Score (SAS)**
   - Winner alignment: Jaccard similarity to top responses
   - Max source alignment: Best match to any response
   - Hallucination risk: 1 - max_source_alignment
   - Grounded threshold: 0.6

**Integration Points:**
- `council.py`: Quality metrics in `run_full_council()` metadata
- `mcp_server.py`: Visual display in `consult_council` output
- `unified_config.py`: Configuration support (future)

**Files:**
- `src/llm_council/quality/` - New module (6 files)
- `tests/quality/` - 44 TDD tests

**Note:** Phase 1 uses synchronous Jaccard-based calculations. Async embedding support reserved for Tier 2/3.
