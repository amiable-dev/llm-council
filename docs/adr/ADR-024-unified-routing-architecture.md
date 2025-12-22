# ADR-024: Unified Routing Architecture

**Status:** COMPLETE (Full L1-L4 Observability Verified v0.12.1)
**Date:** 2025-12-22
**Decision Makers:** Engineering, Architecture
**Council Review:** Completed - All 4 models responded (Reasoning Tier)

---

## Context

Three recent ADRs address different aspects of "routing" in the LLM Council system:

| ADR | Focus | Key Decision |
|-----|-------|--------------|
| **ADR-020** | Query triage & model selection | Not Diamond for complexity classification, prompt optimization, wildcard seat |
| **ADR-022** | Tier-appropriate model pools | Quick/balanced/high/reasoning tiers with different model sets |
| **ADR-023** | Gateway routing | OpenRouter/Requesty/Direct API abstraction with fallback chains |

### Current Problem

These ADRs were developed independently and lack:
1. **Clear layering model**: Which decisions happen first?
2. **Unified configuration**: 15+ environment variables across the three ADRs
3. **Interaction rules**: How do escalation, tier selection, and gateway fallback compose?
4. **Single source of truth**: Developers must read 3 ADRs to understand the full picture

### Identified Conflicts and Ambiguities

| Issue | ADRs Involved | Ambiguity |
|-------|---------------|-----------|
| **Execution order** | ADR-020, ADR-022 | Does triage select tier, or does tier constrain triage? |
| **Escalation semantics** | ADR-020, ADR-022 | Confidence escalation vs tier escalation vs gateway fallback |
| **Auto-tier selection** | ADR-020, ADR-022 | Both propose automatic tier/complexity detection |
| **Model selection** | ADR-020, ADR-022 | Wildcard seat vs tier pool selection |
| **Canonical formats** | ADR-020, ADR-023 | Task Spec vs CanonicalMessage |
| **Configuration explosion** | All three | 15+ env vars, no unified schema |

---

## Decision

Establish a **Unified Routing Architecture** that defines:
1. A four-layer execution model
2. Clear interaction rules between ADRs
3. A unified configuration schema
4. Consistent terminology

### The Four-Layer Model

**Council Recommendation: Hybrid Layer Ordering**

The Council unanimously agreed on a hybrid approach:
- **Explicit tier** (user specifies quick/balanced/high/reasoning): Tier first, triage operates within constraints
- **Auto tier** (user specifies "auto"): Triage first to classify complexity, then tier selection

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           USER REQUEST                                       │
│                    (query + confidence level hint)                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                          ┌─────────┴─────────┐
                          │ confidence level? │
                          └─────────┬─────────┘
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
              [explicit]        [auto]         [bypass]
                    │               │               │
                    ▼               ▼               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  LAYER 1: TIER SELECTION (ADR-022)                                          │
│  ═══════════════════════════════════                                        │
│  Input:  User-specified confidence level OR "auto"                          │
│  Process: Select tier (quick/balanced/high/reasoning)                       │
│  Output: TierContract (model pool, timeout budget, constraints)             │
│                                                                              │
│  EXPLICIT PATH: User specifies tier directly                                │
│    → Create TierContract immediately                                         │
│    → Layer 2 operates WITHIN tier constraints                               │
│                                                                              │
│  AUTO PATH: User specifies confidence="auto"                                │
│    → Defer to Layer 2 for complexity classification                         │
│    → Layer 2 determines tier via Not Diamond                                │
│                                                                              │
│  BYPASS PATH: Debug/testing mode (requires authorization)                   │
│    → Skip Layers 1-3, direct to Layer 4                                     │
│    → Strict logging, never in production                                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  LAYER 2: QUERY TRIAGE & MODEL SELECTION (ADR-020)                          │
│  ═══════════════════════════════════════════════════                        │
│  Input:  Query + TierContract (from Layer 1)                                │
│  Process:                                                                    │
│    1. Complexity classification (if auto-tier)                              │
│    2. Fast-path decision (single model vs full council)                     │
│    3. Prompt optimization (per-model adaptation)                            │
│    4. Wildcard seat selection (specialist from tier pool)                   │
│  Output: ResolvedModelSet + OptimizedPrompts                                │
│                                                                              │
│  Constraints:                                                                │
│    - Models MUST come from TierContract.allowed_pools                       │
│    - Can RECOMMEND escalation, not force it                                 │
│    - Escalation requires explicit user notification                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  LAYER 3: COUNCIL EXECUTION (Core)                                          │
│  ═════════════════════════════════                                          │
│  Input:  ResolvedModelSet + OptimizedPrompts                                │
│  Process:                                                                    │
│    - Stage 1: Parallel queries to selected models                           │
│    - Stage 2: Anonymized peer review (tier-appropriate)                     │
│    - Stage 3: Chairman synthesis                                            │
│  Output: CouncilResponse                                                     │
│                                                                              │
│  Note: Quick tier may use lightweight "sanity check" instead of             │
│        full peer review (per ADR-022 council recommendation)                │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  LAYER 4: GATEWAY ROUTING (ADR-023)                                         │
│  ═══════════════════════════════════                                        │
│  Input:  ResolvedModelId + CanonicalMessage (per model)                     │
│  Process:                                                                    │
│    1. Map model → gateway (per MODEL_ROUTING config)                        │
│    2. Inject BYOK credentials if configured                                 │
│    3. Execute API call with fallback chain on failure                       │
│  Output: API Response                                                        │
│                                                                              │
│  Failure handling:                                                           │
│    - Infrastructure failure → try next gateway in chain                     │
│    - All gateways exhausted → raise TransportFailure                        │
│    - TransportFailure may trigger Layer 2 escalation (application policy)  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Execution Order (Definitive)

```
1. TIER SELECTION (ADR-022)
   ├── User specifies: confidence="balanced"
   └── Output: TierContract{models: [gpt-4o, sonnet, gemini-1.5-pro], timeout: 90s}

2. QUERY TRIAGE (ADR-020)
   ├── Input: query + TierContract
   ├── Complexity check → stays in balanced tier (no escalation)
   ├── Prompt optimization → per-model prompts
   ├── Wildcard selection → adds specialist from balanced pool
   └── Output: [gpt-4o, sonnet, gemini-1.5-pro, selected-specialist]

3. COUNCIL EXECUTION (Core)
   ├── Stage 1: Query all 4 models in parallel
   ├── Stage 2: Peer review
   └── Stage 3: Synthesis → CouncilResponse

4. GATEWAY ROUTING (ADR-023)
   ├── gpt-4o → OpenRouter (default)
   ├── sonnet → Requesty (per MODEL_ROUTING)
   ├── gemini-1.5-pro → OpenRouter
   └── specialist → Direct API (if configured)
```

### Escalation and Fallback Rules

Three orthogonal failure-handling mechanisms exist:

| Mechanism | Layer | Trigger | Action |
|-----------|-------|---------|--------|
| **Tier Escalation** | L1→L2 | Low confidence / complexity mismatch | Move to higher tier (quick→balanced→high) |
| **Deliberation Escalation** | L2 | Fast-path confidence < 0.92 | Single model → Full council |
| **Gateway Fallback** | L4 | Transport failure (5xx, timeout, rate limit) | Try next gateway in chain |

**Council Recommendation on Gateway Failure**: The Council unanimously agreed that gateway failures should **NEVER** automatically trigger tier escalation. Gateway failures are infrastructure issues, not query complexity issues. The correct action is:
1. Try next gateway in fallback chain
2. If all gateways exhausted → fail with clear error
3. User/application may manually retry at different tier if desired

**Interaction Rules:**

```python
# Pseudo-code for escalation interaction (Council-revised)
async def execute_query(query: str, confidence: str) -> Response:
    tier = select_tier(confidence)  # Layer 1

    try:
        # Layer 2: Triage
        triage_result = await triage_query(query, tier)

        if triage_result.escalate_tier:
            # Tier escalation (ADR-022) - only for complexity mismatch
            tier = get_next_tier(tier)
            log_escalation("tier", reason=triage_result.escalation_reason)
            triage_result = await triage_query(query, tier)

        # Layer 3: Council execution
        models = triage_result.resolved_models
        council_result = await run_council(query, models, tier.timeout)

        return council_result

    except TransportFailure as e:
        # Gateway fallback exhausted (ADR-023)
        # COUNCIL DECISION: Never auto-escalate tier on gateway failure
        # Gateway failures are infrastructure issues, not complexity issues
        log_error("gateway_exhausted", error=e, tier=tier.name)
        raise GatewayExhaustedError(
            message="All gateways failed",
            attempted_gateways=e.attempted_gateways,
            suggestion="Retry later or check gateway health"
        )
```

**Key Principles:**
1. **Tier escalation is explicit**: Never silently upgrade tier (cost implications)
2. **Gateway fallback is transparent**: Retry same model via different gateway
3. **Council escalation is autonomous**: Fast-path can escalate to full council
4. **Never cross-layer escalation without logging**: All escalations are auditable

---

## Unified Configuration Schema

### The Problem

Current configuration across three ADRs:

```bash
# ADR-020 (6 vars)
LLM_COUNCIL_ROUTING_MODE=auto|full|lite|bypass
LLM_COUNCIL_PROMPT_OPTIMIZATION=true|false
LLM_COUNCIL_WILDCARD_MODEL=dynamic|<model-id>
NOT_DIAMOND_API_KEY=...

# ADR-022 (5 vars)
LLM_COUNCIL_MODELS_QUICK=...
LLM_COUNCIL_MODELS_BALANCED=...
LLM_COUNCIL_MODELS_HIGH=...
LLM_COUNCIL_MODELS_REASONING=...
LLM_COUNCIL_AUTO_TIER=true|false

# ADR-023 (6+ vars)
LLM_COUNCIL_ROUTER=openrouter|requesty|direct
LLM_COUNCIL_MODEL_ROUTING='{...}'
LLM_COUNCIL_FALLBACK_CHAIN=...
LLM_COUNCIL_BYOK=true|false
OPENROUTER_API_KEY=...
REQUESTY_API_KEY=...
ANTHROPIC_API_KEY=...
OPENAI_API_KEY=...
```

**17+ environment variables** is unmanageable.

### The Solution: Unified YAML Configuration

```yaml
# llm_council.yaml - Unified Configuration
# Precedence: Explicit config > Environment variables > Defaults

council:
  # ==========================================================================
  # LAYER 1: Tier Selection (ADR-022)
  # ==========================================================================
  tiers:
    default: high  # Default tier when not specified

    pools:
      quick:
        models:
          - openai/gpt-4o-mini
          - anthropic/claude-3-5-haiku-20241022
          - google/gemini-2.0-flash-001
        timeout_seconds: 30
        peer_review: lightweight  # sanity check only

      balanced:
        models:
          - openai/gpt-4o
          - anthropic/claude-3-5-sonnet-20241022
          - google/gemini-1.5-pro
        timeout_seconds: 90
        peer_review: standard

      high:
        models:
          - openai/gpt-4o
          - anthropic/claude-opus-4-5-20250514
          - google/gemini-3-pro
          - x-ai/grok-4
        timeout_seconds: 180
        peer_review: standard

      reasoning:
        models:
          - openai/gpt-5.2-pro
          - anthropic/claude-opus-4-5-20250514
          - openai/o1-preview
          - deepseek/deepseek-r1
        timeout_seconds: 600
        peer_review: standard

    escalation:
      enabled: true
      notify_user: true  # Never silently escalate
      max_escalations: 2  # quick → balanced → high (stop)

  # ==========================================================================
  # LAYER 2: Query Triage (ADR-020)
  # ==========================================================================
  triage:
    enabled: false  # Opt-in; requires Not Diamond API key

    complexity_classification:
      enabled: true
      provider: not_diamond

    prompt_optimization:
      enabled: true
      verify_semantic_equivalence: true
      similarity_threshold: 0.93

    wildcard:
      enabled: true
      pool: domain_specialist  # code, reasoning, creative, multilingual
      fallback_model: null  # Use tier pool if specialist unavailable

    fast_path:
      enabled: true
      confidence_threshold: 0.92
      escalate_on_low_confidence: true

  # ==========================================================================
  # LAYER 4: Gateway Routing (ADR-023)
  # ==========================================================================
  gateways:
    default: openrouter

    providers:
      openrouter:
        enabled: true
        api_key: ${OPENROUTER_API_KEY}

      requesty:
        enabled: true
        api_key: ${REQUESTY_API_KEY}
        byok:
          enabled: false
          keys:
            anthropic: ${ANTHROPIC_API_KEY}
            openai: ${OPENAI_API_KEY}

      direct:
        enabled: true
        anthropic:
          api_key: ${ANTHROPIC_API_KEY}
        openai:
          api_key: ${OPENAI_API_KEY}
        google:
          api_key: ${GOOGLE_API_KEY}

    model_routing:
      # Route specific models to specific gateways
      "anthropic/*": requesty
      "deepseek/*": openrouter
      "openai/*": direct  # Use direct API for OpenAI

    fallback:
      enabled: true
      chain: [openrouter, requesty, direct]
      retry_on:
        - timeout
        - rate_limit
        - server_error  # 5xx
      do_not_retry_on:
        - auth_error  # 401/403
        - invalid_request  # 400
        - content_filter

  # ==========================================================================
  # Cross-Layer Settings
  # ==========================================================================
  credentials:
    # Consolidated API key references
    not_diamond: ${NOT_DIAMOND_API_KEY}
    openrouter: ${OPENROUTER_API_KEY}
    requesty: ${REQUESTY_API_KEY}
    anthropic: ${ANTHROPIC_API_KEY}
    openai: ${OPENAI_API_KEY}
    google: ${GOOGLE_API_KEY}

  observability:
    log_escalations: true
    log_gateway_fallbacks: true
    metrics_enabled: true
```

### Environment Variable Overrides

For CI/CD and simple deployments, environment variables still work:

```bash
# Tier selection
LLM_COUNCIL_DEFAULT_TIER=high
LLM_COUNCIL_TIER_ESCALATION=true

# Triage
LLM_COUNCIL_TRIAGE_ENABLED=false
LLM_COUNCIL_FAST_PATH_CONFIDENCE=0.92

# Gateway
LLM_COUNCIL_DEFAULT_GATEWAY=openrouter
LLM_COUNCIL_GATEWAY_FALLBACK_CHAIN=openrouter,requesty,direct

# API Keys (always environment variables for security)
OPENROUTER_API_KEY=...
REQUESTY_API_KEY=...
```

**Precedence**: YAML config > Environment variables > Defaults

---

## Terminology Standardization

| Concept | Term to Use | NOT to Use | Layer |
|---------|-------------|------------|-------|
| Selecting confidence level | **Tier Selection** | "routing" | L1 |
| Choosing which models to query | **Model Selection** | "routing" | L2 |
| Classifying query complexity | **Triage** | "routing" | L2 |
| Choosing which gateway/API to use | **Gateway Routing** | "model routing" | L4 |
| Moving to higher tier | **Tier Escalation** | "fallback" | L1→L2 |
| Retrying via different gateway | **Gateway Fallback** | "escalation" | L4 |
| Single model → Full council | **Deliberation Escalation** | "council escalation", "tier escalation" | L2 |

**Note**: The Council recommended renaming "Council Escalation" to "Deliberation Escalation" to avoid confusion with tier escalation and to more accurately describe the action (escalating the deliberation depth, not the council itself).

---

## Canonical Data Flow

```
┌──────────────────────────────────────────────────────────────────────────┐
│                            DATA FLOW                                      │
└──────────────────────────────────────────────────────────────────────────┘

User Query (string) + Confidence Hint (string)
    │
    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ TierContract                                                              │
│ {                                                                         │
│   tier: "balanced",                                                       │
│   allowed_models: ["gpt-4o", "sonnet", "gemini-1.5-pro"],                │
│   timeout_ms: 90000,                                                      │
│   peer_review_mode: "standard",                                           │
│   escalation_policy: {can_escalate: true, max: 2}                        │
│ }                                                                         │
└──────────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ TriageResult                                                              │
│ {                                                                         │
│   resolved_models: ["gpt-4o", "sonnet", "gemini-1.5-pro", "deepseek-v3"],│
│   optimized_prompts: {                                                    │
│     "gpt-4o": CanonicalTaskSpec,                                         │
│     "sonnet": CanonicalTaskSpec,                                         │
│     ...                                                                   │
│   },                                                                      │
│   fast_path: false,                                                       │
│   escalation_recommended: false                                           │
│ }                                                                         │
└──────────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ CanonicalMessage[] (per model)                                            │
│ {                                                                         │
│   role: "user",                                                           │
│   content: [{type: "text", text: "..."}],                                │
│   tool_calls: [],                                                         │
│   metadata: {task_id: "...", tier: "balanced"}                           │
│ }                                                                         │
└──────────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ GatewayRequest (per model)                                                │
│ {                                                                         │
│   model: "anthropic/claude-3-5-sonnet-20241022",                         │
│   gateway: "requesty",                                                    │
│   messages: [...],  // Gateway-specific format                           │
│   credentials: {api_key: "...", byok: null},                             │
│   fallback_chain: ["openrouter", "direct"]                               │
│ }                                                                         │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Council Answers to Open Questions

### 1. Layer Ordering: Tier vs Triage First?

**Council Verdict: HYBRID APPROACH**

| Scenario | Order | Rationale |
|----------|-------|-----------|
| Explicit tier (user specifies) | Tier → Triage | User intent is clear; triage operates within constraints |
| Auto tier ("auto") | Triage → Tier | Need complexity classification to determine tier |

### 2. Gateway Failure → Tier Escalation?

**Council Verdict: NEVER (Option A)**

Gateway failures are infrastructure issues, not query complexity issues. Auto-escalating tier would:
- Increase cost without addressing root cause
- Mask infrastructure problems
- Confuse the separation of concerns

Correct behavior: Exhaust fallback chain → fail with clear error → let user/app decide.

### 3. Unified YAML Configuration?

**Council Verdict: PROCEED with YAML**

Benefits outweigh costs:
- Single source of truth for complex configurations
- Better documentation and validation
- Environment variables remain for secrets and CI/CD overrides
- Schema validation catches configuration errors early

### 4. Bypass Mode for Debugging?

**Council Verdict: YES, with strict guardrails**

```yaml
bypass:
  enabled: false  # Must be explicitly enabled
  authorization: ["BYPASS_TOKEN", "admin_role"]  # Require auth
  logging: audit_all  # Every bypass logged
  environments: ["development", "staging"]  # Never production
```

**Guardrails:**
- Requires explicit authorization token or role
- All bypass requests logged to audit trail
- Hard-blocked in production environment
- Rate-limited to prevent abuse

### 5. Model Pool Staleness?

**Council Verdict: Automated with human oversight**

```python
# Weekly automated fitness check
@scheduled(weekly)
async def evaluate_model_fitness():
    for tier, models in TIER_POOLS.items():
        for model in models:
            p95_latency = await get_model_latency_p95(model, days=7)
            if p95_latency > TIER_LATENCY_BUDGETS[tier] * 0.6:
                alert(f"{model} exceeds P95 budget for {tier}")
                # Don't auto-remove; flag for human review
```

### 6. ADR Conflicts?

**Council Verdict: Architecturally compatible**

No fundamental conflicts. ADR-020, ADR-022, and ADR-023 are complementary:
- ADR-020 is the "Brain" (intelligence layer)
- ADR-022 is the "Policy" (constraints layer)
- ADR-023 is the "Nervous System" (transport layer)

ADR-024 documents how they interact; no redesign required.

---

## Observability Requirements

**Council Recommendation:** All layers must emit structured observability data.

### Required Metrics

```yaml
observability:
  metrics:
    tier_selection:
      - tier_selected (counter, by tier)
      - escalation_count (counter, by from_tier, to_tier)
      - auto_tier_classification_latency_ms (histogram)

    triage:
      - fast_path_usage (counter, by used=true/false)
      - deliberation_escalation_count (counter)
      - wildcard_selection (counter, by specialist_type)

    gateway:
      - requests_total (counter, by gateway, model)
      - latency_ms (histogram, by gateway, model)
      - errors_total (counter, by gateway, error_type)
      - fallback_triggered (counter, by from_gateway, to_gateway)
      - circuit_breaker_state (gauge, by gateway)

  logging:
    escalations: always  # Every escalation logged with reason
    fallbacks: always    # Every gateway fallback logged
    bypass: audit_all    # Bypass mode logs everything

  tracing:
    enabled: true
    propagate_context: true  # Trace across all layers
    sample_rate: 0.1  # 10% of requests traced in production
```

---

## Circuit Breaker Requirements

**Council Recommendation:** Implement circuit breakers at Layer 4 (Gateway) to prevent cascade failures.

### Circuit Breaker Configuration

```yaml
gateways:
  circuit_breaker:
    enabled: true
    thresholds:
      failure_rate: 0.5      # Open circuit if >50% failures
      slow_call_rate: 0.8    # Open if >80% calls exceed timeout
      slow_call_duration_ms: 30000
    window:
      type: sliding_window
      size: 100  # Last 100 calls
    states:
      half_open:
        permitted_calls: 10   # Allow 10 test calls
      open:
        wait_duration_ms: 60000  # Wait 1 minute before half-open
```

### Per-Gateway Circuit Breakers

```python
class GatewayCircuitBreaker:
    def __init__(self, gateway_id: str, config: CircuitBreakerConfig):
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None

    async def call(self, request: GatewayRequest) -> Response:
        if self.state == CircuitState.OPEN:
            if self.should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
            else:
                raise CircuitOpenError(self.gateway_id)

        try:
            response = await self.execute(request)
            self.on_success()
            return response
        except GatewayError as e:
            self.on_failure()
            raise

    def on_failure(self):
        self.failure_count += 1
        if self.failure_rate > self.config.failure_rate_threshold:
            self.state = CircuitState.OPEN
            log_circuit_state_change(self.gateway_id, "OPEN")
```

### Interaction with Fallback Chain

```
Gateway A [CLOSED] → try request
                   ↓ success → return
                   ↓ failure → check fallback
                              ↓
Gateway B [OPEN]   → skip (circuit open)
                              ↓
Gateway C [CLOSED] → try request
                   ↓ success → return
                   ↓ failure → exhaust chain → raise error
```

**Key Behavior:**
- Open circuits are skipped in fallback chain
- If all circuits open → fail immediately (don't wait for timeouts)
- Circuit state is per-gateway, not per-model
- Health check endpoints can preemptively test circuits

---

## Implementation Strategy

### Phase 1: Documentation Alignment - COMPLETE
- [x] Add cross-references between ADR-020, ADR-022, ADR-023
- [x] Update each ADR with layer assignment and interaction rules
- [x] Standardize terminology across all three

### Phase 2: Unified Configuration - COMPLETE
- [x] Implement `llm_council.yaml` parser with Pydantic
- [x] Add validation schema for tiers, gateways, triage
- [x] Maintain backwards compatibility with env vars
- [x] Environment variable substitution (`${VAR_NAME}` syntax)
- [x] Automatic config discovery (cwd, ~/.config/llm-council/)

### Phase 3: Layer Interfaces - COMPLETE
- [x] Define `TierContract` dataclass (already existed, verified)
- [x] Define `TriageResult` dataclass (already existed, verified)
- [x] Define `GatewayRequest` dataclass (already existed, verified)
- [x] Implement layer boundaries in code (`layer_contracts.py`)
- [x] Add validation functions for L1→L2→L3→L4 boundaries
- [x] Add observability hooks (LayerEvent, emit_layer_event)
- [x] Add boundary crossing helpers (cross_l1_to_l2, etc.)

### Phase 4: Integration Testing & Execution Wiring
- [x] Test tier escalation paths
- [x] Test gateway fallback with tier interaction
- [x] Test auto-tier selection via Not Diamond
- [x] **CRITICAL FIX (v0.11.1)**: Wire `council.py` to use `gateway_adapter`
  - Previous: `council.py` imported directly from `openrouter` (gateway layer was dead code)
  - Fixed: `council.py` now imports from `gateway_adapter` (enables CircuitBreaker, fallback)
  - Added 4 gateway wiring tests to prevent regression

### Phase 5: Full Observability Wiring (v0.12.1)
- [x] L3_COUNCIL_START and L3_COUNCIL_COMPLETE events in `council.py`
- [x] L4_GATEWAY_RESPONSE and L4_GATEWAY_FALLBACK events in `router.py`
- [x] L2_FAST_PATH_TRIGGERED event in `fast_path.py` (Issue #64)
- [x] L2_WILDCARD_SELECTED event in `wildcard.py` (Issue #65)
- [x] Gateway fallback chain iteration with circuit breaker integration

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Configuration clarity | Single source of truth | User can understand full routing from one doc |
| Env var reduction | <10 for common cases | Count required env vars for basic setup |
| Layer independence | Each ADR testable independently | Unit tests per layer |
| Escalation visibility | 100% logged | All escalations in audit trail |

---

## References

- [ADR-020: Not Diamond Integration Strategy](./ADR-020-not-diamond-integration-strategy.md)
- [ADR-022: Tiered Model Selection](./ADR-022-tiered-model-selection.md)
- [ADR-023: Multi-Router Gateway Support](./ADR-023-multi-router-gateway-support.md)
- [ADR-012: MCP Server Reliability](./ADR-012-mcp-server-reliability.md)

---

## Council Review Summary

**Status:** APPROVED WITH MODIFICATIONS

**Reviewed by**: Gemini 3 Pro (38s), Claude Opus 4.5 (66s), Grok-4 (80s), GPT-5.2-pro (144s)

**Council Verdict**: All 4 models responded. Unanimous approval with the following required modifications incorporated into this document.

---

### Consensus Recommendations (Incorporated)

#### 1. Hybrid Layer Ordering
**Verdict: Approved - Use contextual ordering**

- Explicit tier selection → Tier first, triage operates within constraints
- Auto tier selection → Triage first to classify complexity
- Added bypass path for debugging/testing scenarios

#### 2. Gateway Failure Handling
**Verdict: Option A - Never auto-escalate tier**

Gateway failures are infrastructure issues. The correct response is:
1. Exhaust fallback chain
2. Fail with clear error
3. Let user/application decide next steps

Tier escalation should only occur for complexity mismatches, not transport failures.

#### 3. YAML Configuration
**Verdict: Proceed with YAML**

Benefits (single source of truth, validation, documentation) outweigh costs (schema maintenance, parsing). Environment variables remain for secrets and simple deployments.

#### 4. Bypass Mode
**Verdict: Yes, with guardrails**

Bypass mode enabled for debugging/testing with:
- Explicit authorization required
- Audit logging of all bypass requests
- Hard-blocked in production environments
- Rate limiting to prevent abuse

#### 5. Terminology Standardization
**Verdict: Rename "Council Escalation" → "Deliberation Escalation"**

Avoids confusion between escalating the tier (resource allocation) vs escalating deliberation depth (single model → full council).

---

### Required Updates to Underlying ADRs

The Council identified specific updates needed in the underlying ADRs:

| ADR | Required Update | Priority |
|-----|-----------------|----------|
| **ADR-020** | Add constraint: models must come from `TierContract.allowed_pools` | High |
| **ADR-020** | Clarify: triage determines tier only when `confidence="auto"` | Medium |
| **ADR-022** | Document explicit vs auto tier selection policy | High |
| **ADR-022** | Add P95 latency validation for tier pool membership | Medium |
| **ADR-023** | Add circuit breaker requirement per gateway | High |
| **ADR-023** | Add canonical model identity mapping section | Medium |
| **ADR-023** | Define error taxonomy for fallback triggering | Medium |

---

### Architectural Principles Established

1. **Layer Sovereignty**: Each layer owns its decision; no layer overrides another
2. **Explicit Escalation**: All escalations are logged, user-visible, and auditable
3. **Failure Isolation**: Gateway failures don't cascade to tier changes
4. **Constraint Propagation**: Tier constraints flow down; lower layers cannot violate
5. **Observability by Default**: Every layer emits metrics, logs, and traces

---

### Rollback Triggers

```yaml
automatic_rollback:
  unified_config:
    - parse_errors > 5%
    - validation_failures > 10%
  layer_integration:
    - escalation_rate > 30%
    - cross_layer_timeout_rate > 15%
  circuit_breakers:
    - false_positive_rate > 10%  # Circuit opens when gateway is healthy
    - recovery_time > 5_minutes
```

---

### Implementation Revision (Council-Informed)

| Phase | Original | Council Revision |
|-------|----------|------------------|
| Phase 1 | Documentation Alignment | Add layer sovereignty contracts |
| Phase 2 | Unified Configuration | Add schema validation and migration tooling |
| Phase 3 | Layer Interfaces | Add observability hooks at each boundary |
| Phase 4 | Integration Testing | Add chaos engineering tests for circuit breakers |
