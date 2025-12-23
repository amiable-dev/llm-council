# ADR-025: Future Integration Capabilities

**Status:** APPROVED WITH MODIFICATIONS
**Date:** 2025-12-23
**Decision Makers:** Engineering, Architecture
**Council Review:** Completed - Reasoning Tier (4/4 models: GPT-4o, Gemini-3-Pro, Claude Opus 4.5, Grok-4)

---

## Context

### Industry Landscape Analysis (December 2025)

The AI/LLM industry has undergone significant shifts in 2025. This ADR assesses whether LLM Council's current architecture aligns with these developments and proposes a roadmap for future integrations.

#### 1. Agentic AI is the Dominant Paradigm

2025 has been declared the "Year of the Agent" by industry analysts:

| Metric | Value |
|--------|-------|
| Market size (2024) | $5.1 billion |
| Projected market (2030) | $47 billion |
| Annual growth rate | 44% |
| Enterprise adoption (2025) | 25% deploying AI agents |

**Key Frameworks Emerged:**
- LangChain - Modular LLM application framework
- AutoGen (Microsoft) - Multi-agent conversation framework
- OpenAI Agents SDK - Native agent development
- n8n - Workflow automation with LLM integration
- Claude Agent SDK - Anthropic's agent framework

**Implications for LLM Council:**
- Council deliberation is a form of multi-agent consensus
- Our 3-stage process (generate → review → synthesize) maps to agent workflows
- Opportunity to position as "agent council" for high-stakes decisions

#### 2. MCP Has Become the Industry Standard

The Model Context Protocol (MCP) has achieved widespread adoption:

| Milestone | Date |
|-----------|------|
| Anthropic announces MCP | November 2024 |
| OpenAI adopts MCP | March 2025 |
| Google confirms Gemini support | April 2025 |
| Donated to Linux Foundation | December 2025 |

**November 2025 Spec Features:**
- Parallel tool calls
- Server-side agent loops
- Task abstraction for long-running work
- Enhanced capability declarations

**LLM Council's Current MCP Status:**
- ✅ MCP server implemented (`mcp_server.py`)
- ✅ Tools: `consult_council`, `council_health_check`
- ✅ Progress reporting during deliberation
- ❓ Missing: Parallel tool call support, task abstraction

#### 3. Local LLM Adoption is Accelerating

Privacy and compliance requirements are driving on-premises LLM deployment:

**Drivers:**
- GDPR, HIPAA compliance requirements
- Data sovereignty concerns
- Reduced latency for real-time applications
- Cost optimization for high-volume usage

**Standard Tools:**
- **Ollama**: De facto standard for local LLM hosting
  - Simple API: `http://localhost:11434/v1/chat/completions`
  - OpenAI-compatible format
  - Supports Llama, Mistral, Mixtral, Qwen, etc.

- **LiteLLM**: Unified gateway for 100+ providers
  - Acts as AI Gateway/Proxy
  - Includes Ollama support
  - Cost tracking, guardrails, load balancing

**LLM Council's Current Local LLM Status:**
- ❌ No native Ollama support
- ❌ No LiteLLM integration
- ✅ Gateway abstraction exists (could add OllamaGateway)

#### 4. Workflow Automation Integrates LLMs Natively

Workflow tools now treat LLMs as first-class citizens:

**n8n Capabilities (2025):**
- Direct Ollama node for local LLMs
- AI Agent node for autonomous workflows
- 422+ app integrations
- RAG pipeline templates
- MCP server connections

**Integration Patterns:**
```
Trigger → LLM Decision → Action → Webhook Callback
```

**LLM Council's Current Workflow Status:**
- ✅ HTTP REST API (`POST /v1/council/run`)
- ✅ Health endpoint (`GET /health`)
- ❌ No webhook callbacks (async notifications)
- ❌ No streaming API for real-time progress

---

## Current Capabilities Assessment

### Gateway Layer (ADR-023)

| Gateway | Status | Description |
|---------|--------|-------------|
| OpenRouterGateway | ✅ Complete | 100+ models via single key |
| RequestyGateway | ✅ Complete | BYOK with analytics |
| DirectGateway | ✅ Complete | Anthropic, OpenAI, Google direct |
| **OllamaGateway** | ✅ Complete | Local LLM support via LiteLLM (ADR-025a) |
| **LiteLLMGateway** | ❌ Deferred | Integrated into OllamaGateway per council recommendation |

### External Integrations

| Integration | Status | Gap |
|-------------|--------|-----|
| MCP Server | ✅ Complete | Consider task abstraction |
| HTTP API | ✅ Complete | Webhooks and SSE added (ADR-025a) |
| CLI | ✅ Complete | None |
| Python SDK | ✅ Complete | None |
| Webhooks | ✅ Complete | Event-based with HMAC (ADR-025a) |
| SSE Streaming | ✅ Complete | Real-time events (ADR-025a) |
| n8n | ⚠️ Indirect | Example template needed |
| NotebookLM | ❌ N/A | Third-party tool |

### Agentic Capabilities

| Capability | Status | Notes |
|------------|--------|-------|
| Multi-model deliberation | ✅ Core feature | Our primary value |
| Peer review (bias reduction) | ✅ Stage 2 | Anonymized review |
| Consensus synthesis | ✅ Stage 3 | Chairman model |
| Fast-path routing | ✅ ADR-020 | Single-model optimization |
| Local execution | ✅ Complete | OllamaGateway via LiteLLM (ADR-025a) |

---

## Proposed Integration Roadmap

### Priority Assessment

| Integration | Priority | Effort | Impact | Rationale |
|-------------|----------|--------|--------|-----------|
| OllamaGateway | **HIGH** | Medium | High | Privacy/compliance demand |
| Webhook callbacks | **MEDIUM** | Low | Medium | Workflow tool integration |
| Streaming API | **MEDIUM** | Medium | Medium | Real-time UX |
| LiteLLM integration | LOW | Low | Medium | Alternative to native gateway |
| Enhanced MCP | LOW | Medium | Low | Spec still evolving |

### Phase 1: Local LLM Support (OllamaGateway)

**Objective:** Enable fully local council execution

**Implementation:**
```python
# src/llm_council/gateway/ollama.py
class OllamaGateway(BaseRouter):
    """Gateway for local Ollama models."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        default_timeout: float = 120.0,
    ):
        self.base_url = base_url
        self.default_timeout = default_timeout

    async def complete(self, request: GatewayRequest) -> GatewayResponse:
        # Ollama uses OpenAI-compatible format
        endpoint = f"{self.base_url}/v1/chat/completions"
        # ... implementation
```

**Model Identifier Format:**
```
ollama/llama3.2
ollama/mistral
ollama/mixtral
ollama/qwen2.5
```

**Configuration:**
```bash
# Use Ollama for all council models
LLM_COUNCIL_DEFAULT_GATEWAY=ollama
LLM_COUNCIL_OLLAMA_BASE_URL=http://localhost:11434

# Or mix cloud and local
LLM_COUNCIL_MODEL_ROUTING='{"ollama/*": "ollama", "anthropic/*": "direct"}'
```

**Fully Local Council Example:**
```yaml
# llm_council.yaml
council:
  tiers:
    pools:
      local:
        models:
          - ollama/llama3.2
          - ollama/mistral
          - ollama/qwen2.5
        timeout_seconds: 300
        peer_review: standard

  chairman: ollama/mixtral

  gateways:
    default: ollama
    providers:
      ollama:
        enabled: true
        base_url: http://localhost:11434
```

### Phase 2: Workflow Integration (Webhooks)

**Objective:** Enable async notifications for n8n and similar tools

**API Extension:**
```python
class CouncilRequest(BaseModel):
    prompt: str
    models: Optional[List[str]] = None
    # New fields
    webhook_url: Optional[str] = None
    webhook_events: List[str] = ["complete", "error"]
    async_mode: bool = False  # Return immediately, notify via webhook
```

**Webhook Payload:**
```json
{
  "event": "council.complete",
  "request_id": "uuid",
  "timestamp": "2025-12-23T10:00:00Z",
  "result": {
    "stage1": [...],
    "stage2": [...],
    "stage3": {...}
  }
}
```

**Events:**
- `council.started` - Deliberation begins
- `council.stage1.complete` - Individual responses collected
- `council.stage2.complete` - Peer review complete
- `council.complete` - Final synthesis ready
- `council.error` - Execution failed

### Phase 3: LiteLLM Alternative Path

**Objective:** Leverage existing gateway ecosystem instead of building native

**Approach:**
Instead of building OllamaGateway, point DirectGateway at LiteLLM proxy:

```bash
# LiteLLM acts as unified gateway
export LITELLM_PROXY_URL=http://localhost:4000

# DirectGateway routes through LiteLLM
LLM_COUNCIL_DIRECT_ENDPOINT=http://localhost:4000/v1/chat/completions
```

**Trade-offs:**

| Approach | Pros | Cons |
|----------|------|------|
| Native OllamaGateway | Simpler, no dependencies | Only supports Ollama |
| LiteLLM integration | 100+ providers, cost tracking | External dependency |

**Recommendation:** Implement OllamaGateway first (simpler), document LiteLLM as alternative.

---

## Open Questions for Council Review

### 1. Local LLM Priority

> Should OllamaGateway be the top priority given the industry trend toward local/private LLM deployment?

**Context:** Privacy regulations (GDPR, HIPAA) and data sovereignty concerns are driving enterprises to on-premises LLM deployment. Ollama has become the de facto standard.

### 2. LiteLLM vs Native Gateway

> Should we integrate with LiteLLM (100+ provider support) or build a native Ollama gateway?

**Trade-offs:**
- LiteLLM: Instant access to 100+ providers, maintained by external team, adds dependency
- Native: Simpler, no dependencies, but only supports Ollama initially

### 3. Webhook Architecture

> What webhook patterns best support n8n and similar workflow tools?

**Options:**
- A) Simple POST callback with full result
- B) Event-based with granular stage notifications
- C) WebSocket for real-time streaming
- D) Server-Sent Events (SSE) for progressive updates

### 4. Fully Local Council Feasibility

> Is there demand for running the entire council locally (all models + chairman via Ollama)?

**Considerations:**
- Hardware requirements (multiple concurrent models)
- Quality trade-offs (local vs cloud models)
- Use cases (air-gapped environments, development/testing)

### 5. Agentic Positioning

> Should LLM Council position itself as an "agent council" for high-stakes agentic decisions?

**Opportunity:** Multi-agent systems need consensus mechanisms. LLM Council's deliberation could serve as a "jury" for agent decisions requiring human-level judgment.

---

## Implementation Timeline

| Phase | Scope | Duration | Dependencies |
|-------|-------|----------|--------------|
| Phase 1a | OllamaGateway basic | 1 sprint | None |
| Phase 1b | Fully local council | 1 sprint | Phase 1a |
| Phase 2 | Webhook callbacks | 1 sprint | None |
| Phase 3 | LiteLLM docs | 0.5 sprint | None |

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Local council execution | Works with Ollama | Integration tests pass |
| Webhook delivery | <1s latency | P95 latency measurement |
| n8n integration | Documented workflow | Example template works |
| Council quality (local) | >80% agreement with cloud | A/B comparison |

---

## References

- [Top 9 AI Agent Frameworks (Dec 2025)](https://www.shakudo.io/blog/top-9-ai-agent-frameworks)
- [n8n LLM Agents Guide](https://blog.n8n.io/llm-agents/)
- [n8n Local LLM Guide](https://blog.n8n.io/local-llm/)
- [One Year of MCP (Nov 2025)](https://blog.modelcontextprotocol.io/posts/2025-11-25-first-mcp-anniversary/)
- [LiteLLM Gateway](https://github.com/BerriAI/litellm)
- [Ollama API Integration](https://collabnix.com/ollama-api-integration-building-production-ready-llm-applications/)
- [Open Notebook (NotebookLM alternative)](https://github.com/lfnovo/open-notebook)
- [ADR-023: Multi-Router Gateway Support](./ADR-023-multi-router-gateway-support.md)
- [ADR-024: Unified Routing Architecture](./ADR-024-unified-routing-architecture.md)

---

## Council Review

**Status:** APPROVED WITH ARCHITECTURAL MODIFICATIONS
**Date:** 2025-12-23
**Tier:** High (Reasoning)
**Sessions:** 3 deliberation sessions conducted
**Final Session:** Full council (4/4 models responded)

| Model | Status | Latency |
|-------|--------|---------|
| GPT-4o | ✓ ok | 15.8s |
| Gemini-3-Pro-Preview | ✓ ok | 31.6s |
| Claude Opus 4.5 | ✓ ok | 48.5s |
| Grok-4 | ✓ ok | 72.6s |

---

### Executive Summary

The full Council **APPROVES** the strategic direction of ADR-025, specifically the shift toward **Privacy-First (Local)** and **Agentic Orchestration**. However, significant architectural modifications are required:

1. **"Jury Mode" is the Killer Feature** - Every reviewer identified this as the primary differentiator
2. **Unified Gateway Approach** - Strong dissent (Gemini/Claude) against building proprietary native gateway
3. **Scope Reduction Required** - Split into ADR-025a (Committed) and ADR-025b (Exploratory)
4. **Quality Degradation Notices** - Required for local model usage

---

### Council Verdicts by Question

#### 1. Local LLM Priority: **YES - TOP PRIORITY** (Unanimous)

Both models agree that **OllamaGateway must be the top priority**.

**Rationale:**
- Addresses immediate enterprise requirements for privacy (GDPR/HIPAA)
- Avoids cloud costs and API rate limits
- The $5.1B → $47B market growth in agentic AI relies heavily on secure, offline capabilities
- This is a foundational feature for regulated sectors (healthcare, finance)

**Council Recommendation:** Proceed immediately with OllamaGateway implementation.

#### 2. Integration Strategy: **UNIFIED GATEWAY** (Split Decision)

**Significant Dissent on Implementation Approach:**

| Model | Position |
|-------|----------|
| GPT-4o | Native gateway for control |
| Grok-4 | Native gateway, LiteLLM as optional module |
| **Gemini** | **DISSENT**: Use LiteLLM as engine, not custom build |
| **Claude** | **DISSENT**: Start with LiteLLM as bridge, build native when hitting limitations |

**Gemini's Argument (Strong Dissent):**
> "Do not build a proprietary Native Gateway. In late 2025, maintaining a custom adapter layer for the fragmenting model market is a waste of resources. Use LiteLLM as the engine for your 'OllamaGateway' - it already standardizes headers for Ollama, vLLM, OpenAI, and Anthropic."

**Claude's Analysis:**

| Factor | Native Gateway | LiteLLM |
|--------|---------------|---------|
| Maintenance burden | Higher | Lower |
| Dependency risk | None | Medium |
| Feature velocity | Self-controlled | Dependent |
| Initial dev time | ~40 hours | ~8 hours |

**Chairman's Synthesis:** Adopt a **Unified Gateway** approach:
- Wrap LiteLLM *inside* the Council's "OllamaGateway" interface
- Satisfies user need for "native" experience without maintenance burden
- Move LiteLLM from LOW to CORE priority

#### 3. Webhook Architecture: **HYBRID B + D (EVENT-BASED + SSE)** (Unanimous)

Strong agreement that **Event-based granular notifications** combined with **SSE for streaming** is the superior choice.

**Reasoning:**
- Simple POSTs (Option A) lack flexibility for multi-stage processes
- WebSockets (Option C) are resource-heavy (persistent connections)
- **Event-based (B):** Enables granular lifecycle tracking
- **SSE (D):** Lightweight unidirectional streaming, perfect for text generation

**Chairman's Decision:** Implement Event-Based Webhooks as default, with optional SSE for real-time token streaming.

**Recommended Webhook Events:**
```
council.deliberation_start
council.stage1.complete
model.vote_cast
council.stage2.complete
consensus.reached
council.complete
council.error
```

**Payload Requirements:** Include timestamps, error codes, and metadata for n8n integration.

#### 4. Fully Local Council: **YES, WITH HARDWARE DOCUMENTATION** (Unanimous)

Both models support this but urge caution regarding hardware realities.

**Assessment:** High-value feature for regulated industries (healthcare/finance).

**Hardware Requirements (Council Consensus):**

| Profile | Hardware | Models Supported | Use Case |
|---------|----------|------------------|----------|
| **Minimum** | 8+ core CPU, 16GB RAM, SSD | Quantized 7B (Llama 3.X, Mistral) | Development/testing |
| **Recommended** | Apple M-series Pro/Max, 32GB unified | Quantized 7B-13B models | Small local council |
| **Professional** | 2x NVIDIA RTX 4090/5090, 64GB+ RAM | 70B models via offloading | Full production council |
| **Enterprise** | Mac Studio 64GB+ or multi-GPU server | Multiple concurrent 70B | Air-gapped deployments |

**Chairman's Note:** Documentation must clearly state that a "Local Council" implies quantization (4-bit or 8-bit) for most users.

**Recommendation:** Document as an "Advanced" deployment scenario. Make "Local Mode" optional/configurable with cloud fallbacks.

#### 5. Agentic Positioning: **YES - "JURY" CONCEPT** (Unanimous)

All four models enthusiastically support positioning LLM Council as a consensus mechanism for agents.

**Strategy:**
- Differentiate from single-agent tools (like Auto-GPT)
- Offer "auditable consensus" for high-stakes tasks
- Position as "ethical decision-making" layer
- Integrate with MCP for standardized context sharing

**Unique Value Proposition:** Multi-agent systems need reliable consensus mechanisms. Council deliberation can serve as a "jury" for decisions requiring human-level judgment.

**Jury Mode Verdict Types (Gemini's Framework):**

| Verdict Type | Use Case | Output |
|--------------|----------|--------|
| **Binary** | Go/no-go decisions | Single approved/rejected verdict |
| **Constructive Dissent** | Complex tradeoffs | Majority + minority opinion recorded |
| **Tie-Breaker** | Deadlocked decisions | Chairman casts deciding vote with rationale |

---

#### 6. Quality Degradation Notices: **REQUIRED** (Claude)

Claude (Evelyn) emphasized that local model usage requires explicit quality warnings:

**Requirement:** When using local models (Ollama), the council MUST:
1. Detect when local models are in use
2. Display quality degradation warning in output
3. Offer cloud fallback option when quality thresholds not met
4. Log quality metrics for comparison

**Example Warning:**
```
⚠️ LOCAL COUNCIL MODE
Using quantized local models. Response quality may be degraded compared to cloud models.
Models: ollama/llama3.2 (4-bit), ollama/mistral (4-bit)
For higher quality, set LLM_COUNCIL_DEFAULT_GATEWAY=openrouter
```

---

#### 7. Scope Split Recommendation: **ADR-025a vs ADR-025b**

The council recommends splitting this ADR to separate committed work from exploratory:

**ADR-025a (Committed) - Ship in v0.13.x:**
- OllamaGateway implementation
- Event-based webhooks
- Hardware documentation
- Basic local council support

**ADR-025b (Exploratory) - Research/RFC Phase:**
- Full "Jury Mode" agentic framework
- MCP task abstraction
- LiteLLM alternative path
- Multi-council federation

**Rationale:** Prevents scope creep while maintaining ambitious vision. Core functionality ships fast; advanced features get proper RFC process.

---

### Council-Revised Implementation Order

The models align on the following critical path:

| Phase | Scope | Duration | Priority |
|-------|-------|----------|----------|
| **Phase 1** | Native OllamaGateway | 4-6 weeks | **IMMEDIATE** |
| **Phase 2** | Event-Based Webhooks + SSE | 3-4 weeks | HIGH |
| **Phase 3** | MCP Server Enhancement | 2-3 weeks | **MEDIUM-HIGH** |
| **Phase 4** | Streaming API | 2-3 weeks | MEDIUM |
| **Phase 5** | Fully Local Council Mode | 3-4 weeks | MEDIUM |
| **Phase 6** | LiteLLM (optional) | 4-6 weeks | LOW |

**Total Timeline:** 3-6 months depending on team size.

#### Chairman's Detailed Roadmap (12-Week Plan)

**Phase 1 (Weeks 1-4): core-native-gateway**
- Build `OllamaGateway` adapter with OpenAI-compatible API
- Define Council Hardware Profiles (Low/Mid/High)
- *Risk Mitigation:* Pin Ollama API versions for stability

**Phase 2 (Weeks 5-8): connectivity-layer**
- Implement Event-based Webhooks with granular lifecycle events
- Implement SSE for token streaming (lighter than WebSockets)
- *Risk Mitigation:* API keys + localhost binding by default

**Phase 3 (Weeks 9-12): interoperability**
- Implement basic MCP Server capability (Council as callable tool)
- Release "Jury Mode" marketing and templates
- Agentic positioning materials

---

### Risks & Considerations Identified

#### Security Risks (Grok-4)
- **Webhooks:** Introduce injection risks; implement HMAC signatures and rate limiting immediately
- **Local Models:** Must be sandboxed to prevent poisoning attacks
- **Authentication:** Webhook endpoints need token validation

#### Performance Risks (Grok-4)
- A fully local council may crush consumer hardware
- "Local Mode" needs to be optional/configurable
- Consider model sharding or async processing for large councils

#### Compliance Risks (GPT-4o)
- Ensure data protection standards maintained even in local deployments
- Document compliance certifications (SOC 2) for enterprise users

#### Scope Creep (GPT-4o)
- Do not let "Agentic" features distract from core Gateway stability
- Maintain iterative development with MVPs

#### Ecosystem Risks (Grok-4)
- MCP is Linux Foundation-managed; monitor for breaking changes
- Ollama's rapid evolution might require frequent updates
- Add integration tests for n8n/Ollama to catch regressions

#### Ethical/Legal Risks (Grok-4)
- Agentic positioning could enable misuse in sensitive areas
- Include human-in-the-loop options as safeguards
- Ensure compliance with evolving AI transparency regulations

---

### Council Recommendations Summary

| Decision | Verdict | Confidence | Dissent |
|----------|---------|------------|---------|
| OllamaGateway priority | **TOP PRIORITY** | High | None |
| Native vs LiteLLM | **Unified Gateway** (wrap LiteLLM) | Medium | Gemini/Claude favor LiteLLM-first |
| Webhook architecture | **Hybrid B+D (Event + SSE)** | High | None |
| MCP Enhancement | **MEDIUM-HIGH** (new) | High | None |
| Fully local council | **Yes, with hardware docs** | High | None |
| Agentic positioning | **Yes, as "Jury Mode"** | High | None |
| Quality degradation notices | **Required for local** | High | None |
| Scope split (025a/025b) | **Recommended** | High | None |

**Chairman's Closing Ruling:** Proceed with ADR-025 utilizing the Unified Gateway approach (LiteLLM wrapped in native interface). Revise specifications to include:
1. Strict webhook payload definitions with HMAC authentication
2. Dedicated workstream for hardware benchmarking
3. Quality degradation notices for local model usage
4. Scope split into ADR-025a (committed) and ADR-025b (exploratory)

---

### Architectural Principles Established

1. **Privacy First:** Local deployment is a foundational capability, not an afterthought
2. **Lean Dependencies:** Prefer native implementations over external dependencies
3. **Progressive Enhancement:** Start with event-based webhooks, add streaming later
4. **Hardware Transparency:** Document requirements clearly for local deployments
5. **Agentic Differentiation:** Position as consensus mechanism for multi-agent systems

---

### Action Items

Based on council feedback (3 deliberation sessions, 4 models):

**ADR-025a (Committed - v0.13.x):**
- [x] **P0:** Implement OllamaGateway with OpenAI-compatible API format (wrap LiteLLM) ✅ *Completed 2025-12-23*
- [x] **P0:** Add model identifier format `ollama/model-name` ✅ *Completed 2025-12-23*
- [x] **P0:** Implement quality degradation notices for local model usage ✅ *Completed 2025-12-23*
- [x] **P0:** Define Council Hardware Profiles (Minimum/Recommended/Professional/Enterprise) ✅ *Completed 2025-12-23*
- [x] **P1:** Implement event-based webhook system with HMAC authentication ✅ *Completed 2025-12-23*
- [x] **P1:** Implement SSE for real-time token streaming ✅ *Completed 2025-12-23*
- [x] **P1:** Document hardware requirements for fully local council ✅ *Completed 2025-12-23*
- [ ] **P2:** Create n8n integration example/template

**ADR-025b (Exploratory - RFC Phase):**
- [ ] **P1:** Enhance MCP Server capability (Council as callable tool by other agents)
- [ ] **P2:** Add streaming API support
- [ ] **P2:** Design "Jury Mode" verdict types (Binary, Constructive Dissent, Tie-Breaker)
- [ ] **P2:** Release "Jury Mode" positioning materials and templates
- [ ] **P3:** Document LiteLLM as alternative deployment path
- [ ] **P3:** Prototype "agent jury" governance layer concept
- [ ] **P3:** Investigate multi-council federation architecture

---

## Supplementary Council Review: Configuration Alignment

**Date:** 2025-12-23
**Status:** APPROVED WITH MODIFICATIONS
**Council:** Reasoning Tier (3/4 models: Claude Opus 4.5, Gemini-3-Pro, Grok-4)
**Issue:** [#81](https://github.com/amiable-dev/llm-council/issues/81)

### Problem Statement

The initial ADR-025a implementation added Ollama and Webhook configuration to `config.py` (module-level constants) but did NOT integrate with `unified_config.py` (ADR-024's YAML-first configuration system). This created architectural inconsistency:

- Users cannot configure Ollama/Webhooks via YAML
- Configuration priority chain (YAML > ENV > Defaults) is broken for ADR-025a features
- `GatewayConfig.validate_gateway_name()` rejects "ollama" as invalid

### Council Decisions

| Question | Decision | Rationale |
|----------|----------|-----------|
| **Schema Design** | Consolidate under `gateways.providers.ollama` | Ollama is a gateway provider, not a top-level entity |
| **Duplication** | Single location only | Reject top-level `OllamaConfig` to avoid split-brain configuration |
| **Backwards Compat** | Deprecate `config.py` immediately | Use `__getattr__` bridge with `DeprecationWarning` |
| **Webhook Scope** | Policy in config, routing in runtime | `timeout`/`retries` in YAML; `url`/`secret` runtime-only (security) |
| **Feature Flags** | Explicit `enabled` flags | Follow ADR-020 pattern for clarity |

### Approved Schema

```python
# unified_config.py additions

class OllamaProviderConfig(BaseModel):
    """Ollama provider config - lives inside gateways.providers."""
    enabled: bool = True
    base_url: str = Field(default="http://localhost:11434")
    timeout_seconds: float = Field(default=120.0, ge=1.0, le=3600.0)
    hardware_profile: Optional[Literal[
        "minimum", "recommended", "professional", "enterprise"
    ]] = None

class WebhookConfig(BaseModel):
    """Webhook system config - top-level like ObservabilityConfig."""
    enabled: bool = False  # Opt-in
    timeout_seconds: float = Field(default=5.0, ge=0.1, le=60.0)
    max_retries: int = Field(default=3, ge=0, le=10)
    https_only: bool = True
    default_events: List[str] = Field(
        default_factory=lambda: ["council.complete", "council.error"]
    )
```

### Approved YAML Structure

```yaml
council:
  gateways:
    default: openrouter
    fallback_chain: [openrouter, ollama]
    providers:
      ollama:
        enabled: true
        base_url: http://localhost:11434
        timeout_seconds: 120.0
        hardware_profile: recommended

  webhooks:
    enabled: false
    timeout_seconds: 5.0
    max_retries: 3
    https_only: true
    default_events:
      - council.complete
      - council.error
```

### Implementation Tasks

- [x] Create GitHub issue #81 for tracking
- [ ] Add `OllamaProviderConfig` to unified_config.py
- [ ] Add `WebhookConfig` to unified_config.py
- [ ] Update `GatewayConfig` validator to include "ollama"
- [ ] Add env var overrides in `_apply_env_overrides()`
- [ ] Add deprecation bridge to config.py with `__getattr__`
- [ ] Update OllamaGateway to accept config object
- [ ] Write TDD tests for new config models

### Architectural Principles Reinforced

1. **Single Source of Truth:** `unified_config.py` is the authoritative configuration layer (ADR-024)
2. **YAML-First:** Environment variables are overrides, not primary configuration
3. **No Secrets in Config:** Webhook `url` and `secret` remain runtime-only
4. **Explicit over Implicit:** Feature flags use explicit `enabled` fields

---

## Gap Remediation: EventBridge and Webhook Integration

**Date:** 2025-12-23
**Status:** COMPLETED
**Issue:** [#82](https://github.com/amiable-dev/llm-council/issues/82), [#83](https://github.com/amiable-dev/llm-council/issues/83)

### Problem Statement

Peer review (LLM Antigravity) identified critical gaps in the ADR-025a implementation at 60% readiness:

| Gap | Severity | Status | Description |
|-----|----------|--------|-------------|
| **Gap 1: Webhook Integration** | Critical | ✅ Fixed | WebhookDispatcher existed but council.py never called it |
| **Gap 2: SSE Streaming** | Critical | ✅ Fixed | Real implementation replaces placeholder |
| **Gap 3: Event Bridge** | Critical | ✅ Fixed | No bridge connected LayerEvents to WebhookDispatcher |

### Council-Approved Solution

The reasoning tier council approved the following approach:

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Event Bridge Design | Hybrid Pub/Sub | Async queue for production, sync mode for testing |
| Webhook Triggering | Hierarchical Config | Request-level > Global-level > Defaults |
| SSE Streaming Scope | Stage-Level Events | Map-Reduce pattern prevents token streaming until Judge phase |
| Breaking Changes | Backward Compatible | Optional kwargs to existing functions |

### Implementation

#### 1. EventBridge Class (`src/llm_council/webhooks/event_bridge.py`)

```python
@dataclass
class EventBridge:
    webhook_config: Optional[WebhookConfig] = None
    mode: DispatchMode = DispatchMode.SYNC
    request_id: Optional[str] = None

    async def start(self) -> None
    async def emit(self, event: LayerEvent) -> None
    async def shutdown(self) -> None
```

#### 2. Event Mapping (LayerEvent → WebhookPayload)

| LayerEventType | WebhookEventType |
|----------------|------------------|
| L3_COUNCIL_START | council.deliberation_start |
| L3_STAGE_COMPLETE (stage=1) | council.stage1.complete |
| L3_STAGE_COMPLETE (stage=2) | council.stage2.complete |
| L3_COUNCIL_COMPLETE | council.complete |
| L3_MODEL_TIMEOUT | council.error |

#### 3. Council Integration

```python
async def run_council_with_fallback(
    user_query: str,
    ...
    *,
    webhook_config: Optional[WebhookConfig] = None,  # NEW
) -> Dict[str, Any]:
    # EventBridge lifecycle
    event_bridge = EventBridge(webhook_config=webhook_config)
    try:
        await event_bridge.start()
        await event_bridge.emit(LayerEvent(L3_COUNCIL_START, ...))
        # ... stages emit their events ...
        await event_bridge.emit(LayerEvent(L3_COUNCIL_COMPLETE, ...))
    finally:
        await event_bridge.shutdown()
```

### Test Coverage

- **24 unit tests** for EventBridge (`tests/test_event_bridge.py`)
- **11 integration tests** for webhook integration (`tests/test_webhook_integration.py`)
- **931 total tests** passing after integration

### Files Modified

| File | Action | Description |
|------|--------|-------------|
| `src/llm_council/webhooks/event_bridge.py` | CREATE | EventBridge class with async queue |
| `src/llm_council/webhooks/__init__.py` | MODIFY | Export EventBridge, DispatchMode |
| `src/llm_council/council.py` | MODIFY | Add webhook_config param, emit events |
| `tests/test_event_bridge.py` | CREATE | Unit tests for EventBridge |
| `tests/test_webhook_integration.py` | CREATE | Integration tests |

### GitHub Issues

- [#82](https://github.com/amiable-dev/llm-council/issues/82): EventBridge implementation ✅
- [#83](https://github.com/amiable-dev/llm-council/issues/83): Webhook integration ✅
- [#84](https://github.com/amiable-dev/llm-council/issues/84): SSE streaming ✅

### Phase 3: SSE Streaming (Completed)

SSE streaming implementation completed with:
- Real `_council_runner.py` implementation using EventBridge
- `/v1/council/stream` SSE endpoint in http_server.py
- 18 TDD tests (14 pass, 4 skip when FastAPI not installed)
- Stage-level events: deliberation_start → stage1.complete → stage2.complete → complete

---

## Implementation Status Summary

| Feature | Status | Issue |
|---------|--------|-------|
| OllamaGateway | ✅ Complete | - |
| Quality degradation notices | ✅ Complete | - |
| Hardware profiles | ✅ Complete | - |
| Webhook infrastructure | ✅ Complete | - |
| EventBridge | ✅ Complete | #82 |
| Council webhook integration | ✅ Complete | #83 |
| SSE streaming | ✅ Complete | #84 |
| n8n integration example | ❌ Pending | - |

**ADR-025a Readiness:** 100% (was 60% before gap remediation)

---

## ADR-025b Council Validation: Jury Mode Features

**Date:** 2025-12-23
**Status:** VALIDATED WITH SCOPE MODIFICATIONS
**Council:** Reasoning Tier (4/4 models: Claude Opus 4.5, Gemini-3-Pro, GPT-4o, Grok-4)
**Consensus Level:** High
**Primary Author:** Claude Opus 4.5 (ranked #1)

### Executive Summary

> "The core value of ADR-025b is transforming the system from a **'Summary Generator'** to a **'Decision Engine.'** Prioritize features that enforce structured, programmatic outcomes (Binary Verdicts, MCP Schemas) and cut features that add architectural noise (Federation)."

### Council Verdicts by Feature

| Original Feature | Original Priority | Council Verdict | New Priority |
|------------------|-------------------|-----------------|--------------|
| MCP Enhancement | P1 | **DEPRIORITIZE** | P3 |
| Streaming API | P2 | **REMOVE** | N/A |
| Jury Mode Design (Binary) | P2 | **COMMIT** | **P1** |
| Jury Mode Design (Tie-Breaker) | P2 | **COMMIT** | **P1** |
| Jury Mode Design (Constructive Dissent) | P2 | **COMMIT (minimal)** | P2 |
| Jury Mode Materials | P2 | **COMMIT** | P2 |
| LiteLLM Documentation | P3 | **COMMIT** | P2 |
| Federation RFC | P3 | **REMOVE** | N/A |

### Key Architectural Findings

#### 1. Streaming API: Architecturally Impossible (Unanimous)

Token-level streaming is fundamentally incompatible with the Map-Reduce deliberation pattern:

```
User Request
    ↓
Stage 1: N models generate (parallel, 10-30s) → No tokens yet
    ↓
Stage 2: N models review (parallel, 15-40s) → No tokens yet
    ↓
Stage 3: Chairman synthesizes → Tokens ONLY HERE
```

**Resolution:** Existing SSE stage-level events (`council.stage1.complete`, etc.) are the honest representation. Do not implement token streaming.

#### 2. Constructive Dissent: Option B (Extract from Stage 2)

The council evaluated four approaches:

| Option | Description | Verdict |
|--------|-------------|---------|
| A | Separate synthesis from lowest-ranked | **REJECT** (cherry-picking) |
| **B** | Extract dissenting points from Stage 2 | **ACCEPT** |
| C | Additional synthesis pass | **REJECT** (latency cost) |
| D | Not worth implementing | **REJECT** (real demand) |

**Implementation:** Extract outlier evaluations (score < median - 1 std) from existing Stage 2 data. Only surface when Borda spread > 2 points.

#### 3. Federation: Removed for Scope Discipline

| Issue | Impact |
|-------|--------|
| Latency explosion | 3-9x (45-90 seconds per call) |
| Governance complexity | Debugging nested decisions impossible |
| Scope creep | Diverts from core positioning |

#### 4. MCP Enhancement: Existing Tools Sufficient

Current `consult_council` tool adequately supports agent-to-council delegation. Enhancement solves theoretical problem (context passing) better addressed via documentation.

### Jury Mode Implementation

#### Binary Verdict Mode

Transforms chairman synthesis into structured decision output:

```python
class VerdictType(Enum):
    SYNTHESIS = "synthesis"      # Default (current behavior)
    BINARY = "binary"            # approved/rejected
    TIE_BREAKER = "tie_breaker"  # Chairman decides on deadlock

@dataclass
class VerdictResult:
    verdict_type: VerdictType
    verdict: str                        # "approved"|"rejected"|synthesis
    confidence: float                   # 0.0-1.0
    rationale: str
    dissent: Optional[str] = None       # Minority opinion
    deadlocked: bool = False
    borda_spread: float = 0.0
```

#### Use Cases Enabled

| Verdict Type | Use Case | Output |
|--------------|----------|--------|
| **Binary** | CI/CD gates, policy enforcement, compliance checks | `{verdict: "approved"/"rejected", confidence, rationale}` |
| **Tie-Breaker** | Deadlocked decisions, edge cases | Chairman decision with explicit rationale |
| **Constructive Dissent** | Architecture reviews, strategy decisions | Majority + minority opinion |

### Revised ADR-025b Action Items

**Committed (v0.14.x):**
- [x] **P1:** Implement Binary verdict mode (VerdictType enum, VerdictResult dataclass) ✅ *Completed 2025-12-23*
- [x] **P1:** Implement Tie-Breaker mode with deadlock detection ✅ *Completed 2025-12-23*
- [x] **P2:** Implement Constructive Dissent extraction from Stage 2 ✅ *Completed 2025-12-23*
- [x] **P2:** Create Jury Mode positioning materials and examples ✅ *README updated 2025-12-23*
- [ ] **P2:** Document LiteLLM as alternative deployment path

**Exploratory (RFC):**
- [ ] **P3:** Document MCP context-rich invocation patterns

**Removed:**
- ~~P2: Streaming API~~ (architecturally impossible)
- ~~P3: Federation RFC~~ (scope creep)

### Architectural Principles Established

1. **Decision Engine > Summary Generator:** Jury Mode enforces structured outputs
2. **Honest Representation:** Stage-level events reflect true system state
3. **Minimal Complexity:** Extract dissent from existing data, don't generate
4. **Scope Discipline:** Remove features that add noise without value
5. **Backward Compatibility:** Verdict typing is opt-in, synthesis remains default

### Council Evidence

| Model | Latency | Key Contribution |
|-------|---------|------------------|
| Claude Opus 4.5 | 58.5s | 3-analyst deliberation framework, Option B recommendation |
| Gemini-3-Pro | 31.2s | "Decision Engineering" framing, verdict schema |
| Grok-4 | 74.8s | Scope assessment, MCP demotion validation |
| GPT-4o | 18.0s | Selective feature promotion |

**Consensus Points:**
1. Streaming is architecturally impossible (4/4)
2. Federation is scope creep (4/4)
3. Binary + Tie-Breaker are high-value/low-effort (4/4)
4. MCP enhancement is overprioritized (3/4)
5. Constructive Dissent via extraction is correct approach (3/4)

---

## ADR-025b Implementation Status

**Date:** 2025-12-23
**Status:** COMPLETE (Core Features)
**Tests:** 1021 passing

### Files Created/Modified

| File | Action | Description |
|------|--------|-------------|
| `src/llm_council/verdict.py` | CREATE | VerdictType enum, VerdictResult dataclass |
| `src/llm_council/dissent.py` | CREATE | Constructive Dissent extraction from Stage 2 |
| `src/llm_council/council.py` | MODIFY | verdict_type, include_dissent parameters |
| `src/llm_council/mcp_server.py` | MODIFY | verdict_type, include_dissent in consult_council |
| `src/llm_council/http_server.py` | MODIFY | verdict_type, include_dissent in CouncilRequest |
| `tests/test_verdict.py` | CREATE | TDD tests for verdict functionality |
| `tests/test_dissent.py` | CREATE | TDD tests for dissent extraction |
| `README.md` | MODIFY | Jury Mode section added |

### Feature Summary

| Feature | Status | GitHub Issue |
|---------|--------|--------------|
| Binary Verdict Mode | ✅ Complete | #85 (closed) |
| Tie-Breaker Mode | ✅ Complete | #86 (closed) |
| Constructive Dissent | ✅ Complete | #87 (closed) |
| Jury Mode Documentation | ✅ Complete | #88 (closed) |

### API Changes

**New Parameters:**
- `verdict_type`: "synthesis" | "binary" | "tie_breaker"
- `include_dissent`: boolean (extract minority opinions from Stage 2)

**New Response Fields:**
- `metadata.verdict`: VerdictResult object (when verdict_type != synthesis)
- `metadata.dissent`: string (when include_dissent=True in synthesis mode)

### Test Coverage

- **verdict.py**: 8 tests
- **dissent.py**: 15 tests
- **Total test suite**: 1021 tests passing

### ADR-025 Overall Status

| Phase | Scope | Status |
|-------|-------|--------|
| ADR-025a | Local LLM + Webhooks + SSE | ✅ Complete (100%) |
| ADR-025b | Jury Mode Features | ✅ Complete (Core Features) |

**Remaining Work:**
- P2: Document LiteLLM as alternative deployment path
- P3: Document MCP context-rich invocation patterns
