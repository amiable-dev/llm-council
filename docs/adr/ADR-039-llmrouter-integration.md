# ADR-038: One-Click Deployment Strategy

**Status:** Superseded by [ADR-044](./ADR-044-compute-optimal-deliberation.md) 2026-07-03 — was Draft 2025-12-30. The in-house performance index (ADR-026 P3, wired by ADR-044 P1) provides the routing signal this ADR outsourced to NVIDIA LLMRouter.
**Date:** 2025-12-30
**Decision Makers:** @amiable-dev, LLM Council (High Tier)
**Supersedes:** -
**Superseded By:** -

---

## Context

[LLMRouter](https://github.com/NVIDIA/LLMRouter) is an ML-based model routing system that selects the optimal single model for each query based on learned patterns. It implements 16+ routing algorithms (KNN, SVM, MLP, Matrix Factorization, etc.) and requires supervised training.

llm-council takes a fundamentally different approach: multi-model deliberation with anonymized peer review and chairman synthesis. It requires no training and optimizes for quality through diversity.

These systems are **complementary, not competing**:

| Dimension | LLMRouter | llm-council |
|-----------|-----------|-------------|
| **Core Question** | "Which model is best for this query?" | "How can multiple models validate each other?" |
| **Philosophy** | Selective routing via ML | Deliberative consensus via peer review |
| **Optimization Target** | Cost-quality tradeoff | Quality through diversity |
| **Training** | Required (supervised) | None (inference-only) |
| **Latency** | Low (single model call) | Higher (3-stage deliberation) |

An integration could combine the strengths of both: fast routing for routine queries, deliberative validation for complex/uncertain ones.

## Decision

Propose a **"System 1 / System 2" hybrid architecture** that integrates LLMRouter with llm-council:

- **System 1 (LLMRouter)**: Fast, pattern-based routing for common queries
- **System 2 (llm-council)**: Careful, multi-perspective deliberation for complex/uncertain queries

The integration follows the **Sovereign Systems principle**: each system remains fully functional without the other. Integration adds value but creates no hard dependencies.

### Integration Options

Four integration options were analyzed, reviewed by the LLM Council using reasoning tier deliberation:

#### Option 1: LLMRouter as Tier Selection Layer (P3)
Use LLMRouter's ML to dynamically select which models participate in each tier.

```python
def select_tier_models(tier: str, query: str) -> List[str]:
    if USE_LLMROUTER_SELECTION:
        router = get_llmrouter(tier)
        candidates = router.route_batch([{"query": query}], top_k=tier.council_size)
        return [c["model_name"] for c in candidates]
    else:
        return STATIC_TIER_POOLS[tier]
```

**Assessment**: High effort, medium value, high risk. Requires training data and adds complexity.

#### Option 2: Council as Verification Layer (P0 - Recommended)
When LLMRouter's confidence is low, escalate to llm-council for multi-model validation.

```python
def route_with_validation(self, query: dict) -> dict:
    result = self.route_single(query)

    if result.get("confidence", 1.0) < VALIDATION_THRESHOLD:
        council_result = consult_council(
            query["query"],
            confidence="balanced",
            verdict_type="synthesis"
        )
        result["response"] = council_result["synthesis"]
        result["validated_by_council"] = True

    return result
```

**Assessment**: Low effort, high value, low risk. Clean API boundary, no shared codebase.

#### Option 3: Unified Model Intelligence Layer (P2)
Merge LLMRouter's model metadata with llm-council's ADR-026 dynamic selection into shared intelligence layer.

```
Shared Model Intelligence:
├── Model Registry (capabilities, pricing, latency)
├── Performance Tracking (internal quality scores)
├── Availability Monitoring (circuit breakers)
└── Selection Algorithms (weighted scoring)
```

**Assessment**: Medium effort, medium value, low risk.

#### Option 4: Council-Informed Training (P1)
Use llm-council's peer review results as training signal for LLMRouter.

```python
def extract_training_signal(session: CouncilSession) -> RoutingLabel:
    winner = session.aggregate_rankings[0]
    return {
        "query": session.query,
        "embedding": get_embedding(session.query),
        "best_model": winner.model_id,
        "performance": winner.borda_score
    }
```

**Assessment**: Medium effort, high value, medium risk. Creates self-improving feedback loop.

### Recommended Approach

Based on council deliberation, prioritize:

1. **Phase 1 (P0)**: Implement Option 2 - Confidence-based escalation
2. **Phase 2 (P1)**: Implement Option 4 - Training data export from council sessions
3. **Phase 3 (P2)**: Evaluate Option 3 - Shared model registry

### Novel Patterns from Council Deliberation

The council surfaced additional integration patterns:

**Adaptive Council Sizing**: Use router confidence to dynamically size the council rather than binary escalation.

```
Query Complexity → Council Size
Simple          → 2 models (quick tier)
Medium          → 3 models (balanced tier)
Complex         → 5 models (high tier)
Ambiguous       → 7 models (reasoning tier)
```

**Two-Dimensional Gating**: Gate on both router confidence AND query complexity.

```
                    Query Complexity
                    Low        High
Router         ┌─────────┬──────────┐
Confidence     │ Single  │ Council  │
High           │ Model   │ Balanced │
               ├─────────┼──────────┤
Low            │ Council │ Council  │
               │ Quick   │ High     │
               └─────────┴──────────┘
```

**Self-Healing Feedback Loop**: When router confidently routes to Model A but council ranks Model B higher, flag for router retraining.

## Implementation

### Phase 1: Confidence-Based Escalation

```python
# New module: src/llm_council/integrations/llmrouter.py

from llm_council import consult_council

class LLMRouterBridge:
    """Bridge for LLMRouter confidence-based escalation to llm-council."""

    def __init__(
        self,
        confidence_threshold: float = 0.7,
        escalation_tier: str = "balanced",
    ):
        self.confidence_threshold = confidence_threshold
        self.escalation_tier = escalation_tier

    async def maybe_escalate(
        self,
        query: str,
        router_confidence: float,
        router_response: str,
    ) -> dict:
        """Escalate to council if router confidence is below threshold."""
        if router_confidence >= self.confidence_threshold:
            return {
                "response": router_response,
                "source": "router",
                "escalated": False,
            }

        council_result = await consult_council(
            query,
            confidence=self.escalation_tier,
            verdict_type="synthesis",
        )

        return {
            "response": council_result["synthesis"],
            "source": "council",
            "escalated": True,
            "router_confidence": router_confidence,
            "council_metadata": council_result.get("metadata"),
        }
```

### Phase 2: Training Data Export

```python
# New module: src/llm_council/integrations/training_export.py

@dataclass
class RoutingLabel:
    """Training label for LLMRouter from council session."""
    query: str
    query_hash: str  # For deduplication
    best_model: str
    borda_score: float
    council_agreement: float  # Consensus strength
    timestamp: datetime

def export_session_for_training(
    session_id: str,
    query: str,
    aggregate_rankings: List[dict],
) -> RoutingLabel:
    """Export council session as LLMRouter training label."""
    winner = aggregate_rankings[0]

    # Calculate agreement (how close was the vote?)
    scores = [r["average_position"] for r in aggregate_rankings]
    agreement = 1.0 - (scores[1] - scores[0]) / len(scores) if len(scores) > 1 else 1.0

    return RoutingLabel(
        query=query,
        query_hash=hashlib.sha256(query.encode()).hexdigest()[:16],
        best_model=winner["model"],
        borda_score=winner.get("borda_score", 0),
        council_agreement=agreement,
        timestamp=datetime.utcnow(),
    )
```

### Configuration

```yaml
# llm_council.yaml addition
integrations:
  llmrouter:
    enabled: false
    confidence_threshold: 0.7
    escalation_tier: "balanced"
    training_export:
      enabled: false
      output_path: "./data/routing_labels/"
      min_agreement: 0.6  # Only export high-agreement sessions
```

## Consequences

### Positive

- **Best of both worlds**: Fast routing for routine queries, deliberation for complex ones
- **Cost-effective**: Council only invoked when router is uncertain
- **Self-improving**: Council sessions provide training signal for router
- **No lock-in**: Either system works independently
- **Clean boundaries**: API-only integration, no shared codebase

### Negative

- **Latency variance**: Escalated queries have significantly higher latency
- **Two systems to maintain**: Operational complexity if both deployed
- **Metric alignment uncertainty**: Council rankings may not correlate with task metrics
- **Training data cost**: Council sessions are expensive to generate training data

### Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Council rankings don't predict task performance | Phase 2 validation on held-out tasks before deployment |
| Escalation threshold miscalibrated | A/B testing with adjustable threshold |
| Training data insufficient | Active learning: prioritize uncertain queries |
| Integration complexity | Start with loose coupling, tighten only where proven valuable |

## Anti-Patterns to Avoid

1. **Full Assimilation**: Don't merge codebases - they serve different use cases
2. **Forcing Fit**: Don't make llm-council do single-model routing
3. **Over-Engineering**: Start with loose coupling, tighten only where proven valuable
4. **Training Dependency**: Don't require LLMRouter training for llm-council to work

## Council Dissent

One model raised concerns about evaluation metric alignment:

> "Council rankings optimize for response quality as judged by LLMs. Router training typically optimizes for task metrics (accuracy, F1). These may diverge—a response could be 'well-written but wrong' or 'correct but poorly explained.' The feedback loop assumes council rankings correlate with downstream task performance, which should be validated empirically."

This dissent informs Phase 2 validation requirements.

## References

- [LLMRouter GitHub](https://github.com/NVIDIA/LLMRouter)
- [ADR-022: Tiered Model Selection](ADR-022-tiered-model-selection.md)
- [ADR-024: Unified Routing Architecture](ADR-024-unified-routing-architecture.md)
- [ADR-026: Dynamic Model Intelligence](ADR-026-dynamic-model-intelligence.md)
- Research: RouteLLM (ICLR 2025), RouterDC (NeurIPS 2024), AutoMix (NeurIPS 2024)
