# ADR-021: Quint Code and First Principles Framework (FPF) Integration

**Status:** Proposed
**Date:** 2025-12-19
**Decision Makers:** Engineering, Architecture
**Council Review:** Pending (GPT-5.2-pro, Claude Opus 4.5, Gemini 3 Pro, Grok-4)

---

## Context

Two complementary frameworks have emerged for structured AI-assisted reasoning:

### Quint Code (github.com/m0n0x41d/quint-code)

A structured reasoning framework for AI-assisted development that creates auditable decision trails. Implements the First Principles Framework (FPF) methodology through:

| Component | Description |
|-----------|-------------|
| **Abduction Phase** | Generate 3-5 competing hypotheses (stored in L0/) |
| **Deduction Phase** | Verify logical consistency, promote to L1/ |
| **Induction Phase** | Gather empirical evidence, promote to L2/ |
| **Trust Scoring** | Weakest-link (WLNK) assurance model |
| **Bias Detection** | Flags anchoring bias and early-hypothesis privilege |
| **Design Rationale Records** | Auditable decision artifacts with expiry conditions |

**Integration**: Works via MCP protocol with Claude Code, Cursor, Gemini CLI, Codex CLI.

### First Principles Framework (FPF) (github.com/ailev/FPF)

A transdisciplinary "Operating System for Thought" providing:

| Component | Description |
|-----------|-------------|
| **Holonic Foundation** | Everything as whole and part simultaneously |
| **Trust Formula** | Trust = ⟨F, G, R⟩ (Formality, Granularity, Reliability) |
| **Γ-Algebra** | Universal aggregation preserving invariants |
| **Bounded Contexts** | Terms hold meaning only within defined boundaries |
| **LLM Integration** | Functions as "bias-assistant" steering toward first-principles |

---

## Functional Alignment Analysis

### Conceptual Overlap with LLM Council

| Dimension | LLM Council | Quint Code/FPF | Alignment |
|-----------|-------------|----------------|-----------|
| **Multi-perspective** | 4 models provide diverse viewpoints | Multiple competing hypotheses | HIGH |
| **Quality Assurance** | Peer review + Borda count ranking | Trust scoring + WLNK model | HIGH |
| **Bias Detection** | ADR-015 bias auditing | Anchoring bias detection | HIGH |
| **Decision Artifacts** | Aggregate rankings + synthesis | Design Rationale Records | MEDIUM |
| **Temporal Validity** | Per-session (ephemeral) | Evidence decay tracking | LOW |
| **Knowledge Levels** | Flat (all responses equal) | Hierarchical (L0→L1→L2) | LOW |

### Key Differences

| Aspect | LLM Council | Quint Code/FPF |
|--------|-------------|----------------|
| **Execution Mode** | Runtime (query-time) | Development-time (persistent) |
| **Focus** | Answer synthesis | Decision documentation |
| **Verification** | Peer agreement | Logical + empirical proof |
| **Storage** | Ephemeral (per-session) | Persistent knowledge base |
| **Trust Model** | Vote aggregation | Weakest-link chain |

---

## Decision

Implement a **Bidirectional Integration** where LLM Council enhances Quint Code's hypothesis generation and Quint Code's trust model enhances council decision confidence.

### Proposed Integration Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    INTEGRATION LAYER: "Principled Council"                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────────┐          ┌──────────────────────┐                 │
│  │    QUINT CODE        │          │    LLM COUNCIL       │                 │
│  │    (Structured       │◄────────►│    (Multi-Model      │                 │
│  │     Reasoning)       │          │     Consensus)       │                 │
│  └──────────────────────┘          └──────────────────────┘                 │
│           │                                   │                              │
│           ▼                                   ▼                              │
│  ┌──────────────────────┐          ┌──────────────────────┐                 │
│  │  Abduction Phase     │          │  Stage 1: Collection │                 │
│  │  - Use council for   │◄─────────│  - Multiple models   │                 │
│  │    hypothesis gen    │          │    generate options  │                 │
│  └──────────────────────┘          └──────────────────────┘                 │
│           │                                   │                              │
│           ▼                                   ▼                              │
│  ┌──────────────────────┐          ┌──────────────────────┐                 │
│  │  Deduction Phase     │          │  Stage 2: Peer Review│                 │
│  │  - Verify logic via  │◄─────────│  - Cross-validate    │                 │
│  │    council critique  │          │    reasoning         │                 │
│  └──────────────────────┘          └──────────────────────┘                 │
│           │                                   │                              │
│           ▼                                   ▼                              │
│  ┌──────────────────────┐          ┌──────────────────────┐                 │
│  │  Trust Scoring       │─────────►│  Confidence Weights  │                 │
│  │  - WLNK model        │          │  - Apply to rankings │                 │
│  │  - Evidence chain    │          │  - Qualify synthesis │                 │
│  └──────────────────────┘          └──────────────────────┘                 │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Integration Points

### 1. Council-Powered Hypothesis Generation

Replace Quint Code's single-model abduction with council-based generation:

```python
# Current: Single model generates hypotheses
hypotheses = await model.generate_hypotheses(problem)

# Proposed: Council generates diverse hypotheses
async def council_abduction(problem: str) -> List[Hypothesis]:
    """Use LLM Council for hypothesis generation phase."""
    result = await run_council_with_fallback(
        f"Generate 3-5 competing hypotheses for: {problem}. "
        "Each hypothesis should represent a distinct approach."
    )

    # Extract hypotheses from each model's response
    hypotheses = []
    for response in result["stage1_responses"]:
        hypotheses.extend(parse_hypotheses(response))

    # Deduplicate and return with provenance
    return deduplicate_with_provenance(hypotheses)
```

**Benefits**:
- Model diversity prevents anchoring bias
- Each hypothesis comes with model provenance
- Natural competition between approaches

### 2. Council-Assisted Deduction Verification

Use peer review for logical verification:

```python
async def council_verify(hypothesis: Hypothesis) -> VerificationResult:
    """Use council peer review for logical verification."""
    result = await run_council_with_fallback(
        f"Verify logical consistency of this hypothesis:\n"
        f"{hypothesis.content}\n\n"
        "Check for: constraint violations, type errors, "
        "implicit assumptions, edge cases."
    )

    # Unanimous agreement required for L1 promotion
    if result["consensus_type"] == "unanimous":
        return VerificationResult(passed=True, level="L1")
    elif result["consensus_type"] == "majority":
        return VerificationResult(passed=True, level="L1",
                                   caveats=result["dissent_summary"])
    else:
        return VerificationResult(passed=False,
                                   reasons=result["disagreements"])
```

### 3. Trust-Weighted Council Rankings

Apply FPF's trust formula to council rankings:

```python
@dataclass
class TrustWeightedRanking:
    model: str
    raw_score: float
    trust_weight: float  # From FPF ⟨F, G, R⟩
    weighted_score: float

def apply_trust_weights(
    rankings: List[Ranking],
    evidence_chain: EvidenceChain
) -> List[TrustWeightedRanking]:
    """Apply weakest-link trust model to council rankings."""

    for ranking in rankings:
        # F = Formality (how rigorous was the evaluation)
        formality = calculate_formality(ranking.evaluation_text)

        # G = Granularity (scope of claims made)
        granularity = calculate_granularity(ranking.claims)

        # R = Reliability (evidence backing)
        reliability = evidence_chain.weakest_link_score()

        # Trust = min(F, G, R) per WLNK model
        trust = min(formality, granularity, reliability)

        ranking.trust_weight = trust
        ranking.weighted_score = ranking.raw_score * trust

    return sorted(rankings, key=lambda r: r.weighted_score, reverse=True)
```

### 4. Design Rationale Records for Council Decisions

Generate DRRs from council consensus:

```python
@dataclass
class DesignRationaleRecord:
    decision_id: str
    timestamp: datetime
    question: str
    winning_hypothesis: str
    alternatives_considered: List[str]
    evidence_chain: List[Evidence]
    council_rankings: List[Ranking]
    consensus_type: str  # unanimous, majority, split
    trust_score: float
    valid_until: datetime  # Evidence expiry

def generate_drr(council_result: CouncilResult) -> DesignRationaleRecord:
    """Convert council result to Design Rationale Record."""
    return DesignRationaleRecord(
        decision_id=f"DRR-{uuid4()}",
        timestamp=datetime.utcnow(),
        question=council_result["query"],
        winning_hypothesis=council_result["synthesis"]["response"],
        alternatives_considered=[
            r["response"] for r in council_result["stage1_responses"]
        ],
        evidence_chain=extract_evidence(council_result),
        council_rankings=council_result["aggregate_rankings"],
        consensus_type=determine_consensus_type(council_result),
        trust_score=calculate_trust(council_result),
        valid_until=calculate_expiry(council_result),
    )
```

---

## Knowledge Level Mapping

Map Quint Code's L0→L1→L2 to council consensus levels:

| Quint Level | Description | Council Equivalent |
|-------------|-------------|-------------------|
| **L0** (Raw) | Unverified hypothesis | Single model response |
| **L1** (Verified) | Logically consistent | Majority consensus |
| **L2** (Validated) | Empirically proven | Unanimous + external validation |

```python
def council_result_to_knowledge_level(result: CouncilResult) -> str:
    """Map council consensus to FPF knowledge level."""
    rankings = result["aggregate_rankings"]
    top_score = rankings[0]["score"] if rankings else 0

    if result["consensus_type"] == "unanimous" and top_score > 0.9:
        return "L2"  # High confidence, validated
    elif result["consensus_type"] in ("unanimous", "majority"):
        return "L1"  # Logically verified
    else:
        return "L0"  # Raw hypothesis
```

---

## Alternatives Considered

### Alternative 1: Replace Council with Quint Code Entirely

**Rejected**: Quint Code is development-time focused; LLM Council is runtime-focused. They serve complementary purposes.

### Alternative 2: No Integration (Use Separately)

**Rejected**: Significant synergy opportunities missed. Both systems address quality and bias but from different angles.

### Alternative 3: Quint Code as Council Pre-processor Only

**Rejected**: Loses the value of FPF's trust model for enhancing council confidence scoring.

---

## Implementation Phases

### Phase 1: Evaluation (2 weeks)
- [ ] Benchmark council-based hypothesis generation vs. single-model
- [ ] Measure diversity improvement in abduction phase
- [ ] Test trust-weighted ranking quality

### Phase 2: Council-Powered Abduction (3 weeks)
- [ ] Implement `/q1-hypothesize-council` command
- [ ] Add provenance tracking for council-generated hypotheses
- [ ] Update Quint Code's L0 storage format

### Phase 3: Trust-Weighted Rankings (2 weeks)
- [ ] Implement WLNK trust calculator for council
- [ ] Add trust scores to council metadata
- [ ] Create `LLM_COUNCIL_TRUST_MODEL=wlnk` config option

### Phase 4: DRR Generation (2 weeks)
- [ ] Implement Design Rationale Record generator
- [ ] Add DRR storage to `.quint/decisions/`
- [ ] Create decay detection for council-based decisions

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Latency increase from council in abduction | High | Medium | Cache similar hypotheses, async generation |
| Trust model complexity | Medium | Medium | Start with simplified F-G-R calculation |
| Dual system maintenance burden | Medium | High | Clear interface boundaries, optional integration |
| Knowledge level mapping mismatch | Low | Medium | Conservative defaults, explicit override option |

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Hypothesis diversity | +40% unique approaches | Compare single-model vs. council |
| Anchoring bias reduction | -60% first-hypothesis wins | Track which hypothesis wins |
| Decision confidence | +25% trust scores | Before/after trust model |
| DRR completeness | 100% decisions documented | Audit trail coverage |

---

## Configuration Options

```bash
# Enable council-based hypothesis generation
LLM_COUNCIL_QUINT_INTEGRATION=true

# Trust model for rankings
LLM_COUNCIL_TRUST_MODEL=wlnk|simple|none  # default: simple

# Generate Design Rationale Records
LLM_COUNCIL_GENERATE_DRR=true

# DRR storage location
LLM_COUNCIL_DRR_PATH=.quint/decisions/
```

---

## Council Review Summary

**Status:** APPROVE WITH MODIFICATIONS

**Reviewed by**: Gemini 3 Pro (34s), Claude Opus 4.5 (44s), Grok-4 (70s)
*GPT-5.2-pro: timeout (120s)*

**Council Verdict**: Unanimous approval with significant architectural modifications. The integration is "architecturally sound but overengineered in its current form."

---

### Consensus Analysis

#### 1. Does Council-Based Abduction Improve Hypothesis Diversity?

**Verdict: Conditionally Yes**

Council does NOT automatically guarantee diversity—models often collapse into safe consensus based on shared training data.

**Required Modifications:**
- **Role-Based Prompting**: Assign specific roles (Scientist, Historian, Logician) to different models
- **Adversarial Seeding**: Require at least one model to argue against emerging consensus
- **Model Heterogeneity**: Mix model families (GPT + Claude + Llama) rather than same-family instances
- **Diversity Metrics**: Measure semantic distance between hypotheses, not just count

```python
# Council-recommended diversity enforcement
class DiversityEnforcedCouncil:
    def generate_hypotheses(self, problem: str) -> List[Hypothesis]:
        # Assign adversarial roles
        roles = ["primary_proposer", "devil_advocate", "synthesis_agent"]

        # Enforce minimum variance via KL-divergence threshold
        hypotheses = self.collect_with_roles(problem, roles)

        if semantic_variance(hypotheses) < DIVERSITY_THRESHOLD:
            return self.force_divergence(hypotheses)

        return hypotheses
```

#### 2. Is FPF Trust Model (F-G-R) Applicable to Multi-Model Consensus?

**Verdict: Partially—Requires Reinterpretation**

| Component | Single-Model Meaning | Council Reinterpretation |
|-----------|---------------------|--------------------------|
| **Fidelity (F)** | Accuracy to source | Inter-model agreement on factual claims |
| **Groundedness (G)** | Traceability to evidence | Convergent citation of same sources |
| **Robustness (R)** | Stability under perturbation | Consistency across prompt variations |

**Critical Issue: WLNK is Problematic**

The pure Weakest-Link model `WLNK = min(F, G, R)` becomes excessively conservative in council contexts:

```
WLNK_council = min(min(F_i), min(G_i), min(R_i)) for all models i
```

This "double-minimum" means a single model's low score tanks the entire output.

**Council-Recommended Alternative: Robust Aggregate Trust (RAT)**

```python
def calculate_rat(wlnk_scores: List[float], disagreement: float) -> float:
    """Replace pure WLNK with Robust Aggregate Trust."""
    α, β, γ = 0.5, 0.3, 0.2  # Weights

    geometric_mean = prod(wlnk_scores) ** (1/len(wlnk_scores))
    median_score = median(wlnk_scores)
    min_score = min(wlnk_scores)

    coherence_bonus = 1 + 0.2 * (1 - disagreement)

    return (α * geometric_mean + β * median_score + γ * min_score) * coherence_bonus
```

**Tiered Trust Application:**
- **L0 (Facts)**: Use strict WLNK—any factual error breaks the chain
- **L1 (Inferences)**: Use weighted aggregation—allow outvoting of weak links
- **L2 (Hypotheses)**: Use RAT—preserve diversity, don't force premature consensus

#### 3. Should Knowledge Levels (L0-L2) Map to Consensus Types?

**Verdict: Yes—Strongest Part of the Proposal**

| Level | Definition | Consensus Requirement | Validation Method |
|-------|------------|----------------------|-------------------|
| **L0** | Data/Observation | Strict Unanimity (5/5) | RAG/API, not just voting |
| **L1** | Patterns/Inference | Majority Vote (4/5+) | Explicit reasoning chains |
| **L2** | Theories/Hypothesis | Plurality (3/5) | Preserve alternatives |

**Key Insight**: For L2, diversity is preferred over consensus—goal is generating options, not picking a winner prematurely.

#### 4. Risks Underestimated

| Risk | Severity | Council Mitigation |
|------|----------|-------------------|
| **Latency Cascade** | HIGH | Implement tiered invocation (not full council every query) |
| **Attribution Collapse** | HIGH | Tag every claim with model_id and consensus_score |
| **Shared Hallucination** | HIGH | Consensus ≠ Truth; add citation requirements |
| **Cost Scaling** | MEDIUM | 7× cost requires explicit thresholds |
| **Prompt Injection Amplification** | MEDIUM | Council may "launder" malicious output through consensus |

---

### Council Architectural Recommendations

#### 1. Tiered Invocation Strategy (Not Full Council by Default)

```
┌─────────────────────────────────────────────────────────┐
│                    Query Classifier                      │
│  (complexity, stakes, domain novelty)                    │
└─────────────────┬───────────────────────────────────────┘
                  │
    ┌─────────────┼─────────────┬─────────────┐
    ▼             ▼             ▼             ▼
┌───────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐
│ Fast  │   │ Verify  │   │  Full   │   │ Deep    │
│ Path  │   │ Path    │   │ Council │   │ Council │
│(1 LLM)│   │(2 LLMs) │   │(5 LLMs) │   │(5+synth)│
└───────┘   └─────────┘   └─────────┘   └─────────┘
  <2s         3-5s          8-12s        15-30s
```

**Mapping to Quint Levels:**
- **Fast Lane (L0)**: Single Model + RAG verification (facts)
- **Medium Lane (L1)**: 3-Model Vote (pattern validation)
- **Slow Lane (L2)**: Full Council + FPF scoring (hypothesis generation)

#### 2. Preserve Model Attribution in DRRs

```yaml
design_rationale_record:
  query_id: "quint-hypothesis-001"
  timestamp: "2025-12-19T14:32:00Z"

  contributions:
    - model: "claude-opus-4.5"
      role: "primary_synthesis"
      claims: ["hypothesis_A", "constraint_check_passed"]
      confidence: 0.82

    - model: "gemini-3-pro"
      role: "adversarial_reviewer"
      dissents: ["edge_case_unhandled"]
      confidence: 0.71

  weakest_link_identified: "Assumption that clocks were synced"
  trust_score:
    fidelity: 0.78
    groundedness: 0.85
    robustness: 0.71
    composite_rat: 0.77
```

#### 3. Circuit Breakers for Consensus Failure

```python
class ConsensusCircuitBreaker:
    def evaluate(self, responses: List[ModelResponse]) -> Action:

        # Irreconcilable disagreement → escalate
        if semantic_variance(responses) > DIVERGENCE_THRESHOLD:
            return Action.ESCALATE_TO_HUMAN

        # Suspicious unanimity (possible shared hallucination)
        if agreement_score(responses) > 0.98 and groundedness < 0.5:
            return Action.REQUEST_CITATIONS

        # Potential prompt injection pattern
        if anomaly_score(responses) > INJECTION_THRESHOLD:
            return Action.QUARANTINE_AND_REVIEW

        return Action.PROCEED_TO_SYNTHESIS
```

#### 4. The "Fact-Rule" Split

- **L0 (Facts)**: Do NOT use LLMs to verify facts if possible. Use deterministic code/API or RAG lookups.
- **L1/L2 (Logic/Game)**: This is the sweet spot for the LLM Council.

---

### Implementation Revision (Council-Informed)

| Phase | Original | Council Revision |
|-------|----------|------------------|
| Phase 1 | Evaluation | **Prototype L1-only council** (lowest risk) |
| Phase 2 | Council-Powered Abduction | **Benchmark diversity** with/without adversarial seeding |
| Phase 3 | Trust-Weighted Rankings | **Replace WLNK with RAT** for L1/L2 |
| Phase 4 | DRR Generation | **Implement attribution schema** before production |

---

### Rollback Triggers (Council-Defined)

```yaml
automatic_rollback:
  diversity:
    - semantic_variance < 0.3  # Hypotheses too similar
  latency:
    - p99_response_time > 15s
  trust:
    - shared_hallucination_detected: true
    - groundedness < 0.5 with consensus > 0.95
  attribution:
    - untraced_claims_ratio > 10%
```

---

## References

- [Quint Code Repository](https://github.com/m0n0x41d/quint-code)
- [First Principles Framework (FPF)](https://github.com/ailev/FPF)
- [ADR-015: Bias Auditing](./ADR-015-bias-auditing.md)
- [ADR-018: Cross-Session Bias Aggregation](./ADR-018-cross-session-bias-aggregation.md)
