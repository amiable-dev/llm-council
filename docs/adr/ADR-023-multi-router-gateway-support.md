# ADR-023: Multi-Router Gateway Support (OpenRouter, Requesty, Direct APIs)

**Status:** COMPLETE (All Gateways Implemented v0.12.2)
**Date:** 2025-12-22
**Decision Makers:** Engineering, Architecture
**Council Review:** Completed - All 4 models responded (Reasoning Tier)
**Layer Assignment:** Layer 4 - Gateway Routing (per ADR-024)

---

## Layer Context (ADR-024)

This ADR operates at **Layer 4** in the unified routing architecture:

| Layer | ADR | Responsibility |
|-------|-----|----------------|
| L1 | ADR-022 | Tier Selection (quick/balanced/high/reasoning) |
| L2 | ADR-020 | Query Triage & Model Selection |
| L3 | Core | Council Execution (Stage 1-3) |
| **L4** | **ADR-023** | **Gateway Routing** |

**Interaction Rules:**
- Layer 4 receives resolved model IDs and `CanonicalMessage` from Layer 3
- Gateway selection is based on model → gateway mapping
- Gateway fallback is for infrastructure failures only (timeout, 5xx, rate limit)
- Gateway failures NEVER trigger tier escalation (per ADR-024 council decision)
- All gateways exhausted → raise `TransportFailure` with clear error

---

## Terminology Note

This ADR uses **"gateway routing"** to describe infrastructure-level decisions about *which API endpoint* services a model request. This is distinct from:
- **Model selection/triage** (ADR-020): Semantic decisions about *which model* to use based on query complexity
- **Tier selection** (ADR-022): Choosing model pools based on confidence level

The term "routing" in this ADR always refers to gateway/provider selection, not model selection.

---

## Context

LLM Council currently has a hardcoded dependency on OpenRouter as the sole gateway for model access. While OpenRouter provides excellent multi-model access, this creates several limitations:

### Current Architecture Limitations

```python
# config.py - Hardcoded OpenRouter dependency
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_API_KEY = _get_api_key()  # Single key, single provider
```

| Issue | Impact |
|-------|--------|
| **Single Point of Failure** | OpenRouter outage = complete council failure |
| **No Gateway Choice** | Users cannot leverage Requesty, direct APIs, or other routers |
| **Cost Optimization Limited** | Cannot route to cheaper gateways for specific models |
| **BYOK Constraints** | No support for using personal API keys directly |
| **Enterprise Deployment** | Some organizations cannot use third-party routers |

### Gateway Comparison: OpenRouter vs Requesty

Based on comprehensive documentation review, here is a detailed comparison:

| Feature | OpenRouter | Requesty |
|---------|------------|----------|
| **Base URL** | `https://openrouter.ai/api/v1` | `https://router.requesty.ai/v1` |
| **Model Count** | "Hundreds" | 300+ |
| **API Compatibility** | OpenAI-compatible | OpenAI + Anthropic compatible |
| **Pricing Model** | Credit-based, passthrough | Passthrough + usage-based |
| **Smart Routing** | Basic failover | Latency-based + load balancing |
| **Auto-Failover** | Yes (implicit) | Yes (configurable chains) |
| **Caching** | Not documented | Auto-caching with toggle |
| **BYOK** | No | Yes (bring your own keys) |
| **Cost Analytics** | Basic dashboard | Rich analytics + budgets |
| **Enterprise Features** | Limited | RBAC, SSO, SOC2 |
| **Claude Code Integration** | Via OpenAI SDK | Native integration |

### Requesty Unique Capabilities

1. **Fallback Chains**: Configurable retry policies with exponential backoff
   ```
   Claude Sonnet (Anthropic) → Claude Sonnet (Bedrock) → GPT-4o
   ```

2. **BYOK (Bring Your Own Keys)**: Use existing API credentials through gateway
   ```
   Route through Requesty for analytics/failover while using own Anthropic key
   ```

3. **Cost Tracking**: Real-time budget management per user/project/API key
   ```yaml
   budget_alerts:
     - threshold: 50%
       action: notify
     - threshold: 100%
       action: block_requests
   ```

4. **MCP Gateway**: Native integration with Model Context Protocol servers

### OpenRouter Unique Capabilities

1. **Community Rankings**: Leaderboard visibility for apps
2. **Established Ecosystem**: Wider third-party integration support
3. **Credit System**: Pre-pay with known balance

---

## Decision

Implement a **Router Abstraction Layer** that supports multiple gateways with per-model routing configuration.

### Proposed Architecture

#### Combined Architecture with ADR-020 (Model Selection Layer)

This ADR operates at **Layer 2** (Gateway Routing) while ADR-020 operates at **Layer 0** (Query Triage). They compose as follows:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           USER REQUEST                                       │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│              LAYER 0: QUERY TRIAGE & MODEL SELECTION (ADR-020)              │
├─────────────────────────────────────────────────────────────────────────────┤
│  • Complexity classification (simple/medium/complex)                         │
│  • Prompt optimization (per-model adaptation)                                │
│  • Dynamic wildcard seat selection (Not Diamond)                             │
│  • Output: ResolvedModelId(s) + optimized prompts                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      LAYER 1: COUNCIL EXECUTION                              │
├─────────────────────────────────────────────────────────────────────────────┤
│  • Stage 1: Parallel model queries                                           │
│  • Stage 2: Anonymized peer review                                           │
│  • Stage 3: Chairman synthesis                                               │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│              LAYER 2: GATEWAY ROUTING (THIS ADR - ADR-023)                   │
├─────────────────────────────────────────────────────────────────────────────┤
│  Gateway Abstraction Layer                                                    │
│  ├── Input: ResolvedModelId + CanonicalMessage[]                            │
│  ├── Gateway selection based on model → gateway mapping                      │
│  ├── BYOK credential injection                                               │
│  └── Fallback chain on infrastructure failure                                │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
         ┌──────────────────────────┼──────────────────────────┐
         ▼                          ▼                          ▼
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│   OpenRouter    │      │    Requesty     │      │   Direct API    │
│   Gateway       │      │    Gateway      │      │   Gateway       │
├─────────────────┤      ├─────────────────┤      ├─────────────────┤
│ • Established   │      │ • BYOK support  │      │ • No middleman  │
│ • Wide support  │      │ • Smart routing │      │ • Lowest latency│
│ • Credit model  │      │ • Cost tracking │      │ • Full control  │
└─────────────────┘      └─────────────────┘      └─────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        LLM PROVIDER APIs                                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Execution Order

The correct execution order when both ADR-020 and ADR-023 are enabled:

1. **Triage (ADR-020)**: Analyze query complexity, decide fast-path vs full council
2. **Model Selection (ADR-020)**: Resolve dynamic models (e.g., `dynamic:not-diamond` → `deepseek/deepseek-v3`)
3. **Gateway Selection (ADR-023)**: Map resolved model ID to gateway
4. **API Call (ADR-023)**: Execute with fallback chain on failure

### Router Interface

```python
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

@dataclass
class RouterConfig:
    name: str
    base_url: str
    api_key_env: str
    timeout: float = 120.0
    retry_policy: Optional[Dict] = None
    extra_headers: Optional[Dict[str, str]] = None

class BaseRouter(ABC):
    """Abstract base for all AI gateway routers."""

    def __init__(self, config: RouterConfig):
        self.config = config

    @abstractmethod
    async def query(
        self,
        model: str,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> Dict[str, Any]:
        """Execute a query through this router."""
        pass

    @abstractmethod
    def normalize_model_id(self, model: str) -> str:
        """Convert model ID to router-specific format."""
        pass

    @abstractmethod
    def supports_model(self, model: str) -> bool:
        """Check if this router supports the given model."""
        pass
```

### Built-in Router Implementations

```python
# routers/openrouter.py
class OpenRouterGateway(BaseRouter):
    DEFAULT_CONFIG = RouterConfig(
        name="openrouter",
        base_url="https://openrouter.ai/api/v1/chat/completions",
        api_key_env="OPENROUTER_API_KEY",
    )

# routers/requesty.py
class RequestyGateway(BaseRouter):
    DEFAULT_CONFIG = RouterConfig(
        name="requesty",
        base_url="https://router.requesty.ai/v1/chat/completions",
        api_key_env="REQUESTY_API_KEY",
    )

    # Requesty-specific: BYOK configuration
    def with_byok(self, provider_key_env: str) -> "RequestyGateway":
        """Configure BYOK mode for this gateway."""
        pass

# routers/direct.py
class DirectAPIGateway(BaseRouter):
    """Direct API access to providers (Anthropic, OpenAI, Google)."""

    PROVIDER_CONFIGS = {
        "anthropic": RouterConfig(
            name="anthropic-direct",
            base_url="https://api.anthropic.com/v1/messages",
            api_key_env="ANTHROPIC_API_KEY",
        ),
        "openai": RouterConfig(
            name="openai-direct",
            base_url="https://api.openai.com/v1/chat/completions",
            api_key_env="OPENAI_API_KEY",
        ),
        "google": RouterConfig(
            name="google-direct",
            base_url="https://generativelanguage.googleapis.com/v1/models",
            api_key_env="GOOGLE_API_KEY",
        ),
    }
```

### Configuration Schema

```python
# config.py additions
@dataclass
class GatewayConfig:
    """Multi-router configuration (ADR-023)."""

    # Default router for all models
    default_router: str = "openrouter"  # openrouter | requesty | direct

    # Per-model router overrides
    # Format: {"model_prefix": "router_name"}
    # Example: {"anthropic/": "requesty", "openai/": "direct"}
    model_routing: Dict[str, str] = field(default_factory=dict)

    # Fallback chain when primary router fails
    fallback_chain: List[str] = field(default_factory=lambda: ["openrouter"])

    # BYOK configuration (Requesty-specific)
    byok_enabled: bool = False
    byok_keys: Dict[str, str] = field(default_factory=dict)
    # Example: {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}
```

### Environment Variable Configuration

```bash
# Primary router selection
LLM_COUNCIL_ROUTER=openrouter|requesty|direct  # default: openrouter

# API keys per router
OPENROUTER_API_KEY=sk-or-...
REQUESTY_API_KEY=sk-req-...
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=...

# Per-model routing (JSON format)
LLM_COUNCIL_MODEL_ROUTING='{"anthropic/": "requesty", "openai/": "direct"}'

# Fallback chain
LLM_COUNCIL_FALLBACK_CHAIN=openrouter,requesty,direct

# BYOK mode (Requesty)
LLM_COUNCIL_BYOK=true
LLM_COUNCIL_BYOK_KEYS='{"anthropic": "ANTHROPIC_API_KEY"}'
```

---

## Use Cases Enabled

### 1. Enterprise Deployment (Direct APIs Only)

Organizations that cannot use third-party routers due to compliance:

```bash
LLM_COUNCIL_ROUTER=direct
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
```

### 2. Cost Optimization (Requesty with BYOK)

Leverage Requesty analytics while using existing API agreements:

```bash
LLM_COUNCIL_ROUTER=requesty
REQUESTY_API_KEY=sk-req-...
LLM_COUNCIL_BYOK=true
LLM_COUNCIL_BYOK_KEYS='{"anthropic": "ANTHROPIC_API_KEY"}'
```

### 3. High Availability (Fallback Chain)

Router failover for maximum reliability:

```bash
LLM_COUNCIL_ROUTER=openrouter
LLM_COUNCIL_FALLBACK_CHAIN=openrouter,requesty,direct
```

### 4. Hybrid Routing (Per-Model Optimization)

Route different models through optimal gateways:

```bash
LLM_COUNCIL_ROUTER=openrouter
LLM_COUNCIL_MODEL_ROUTING='{
  "anthropic/claude": "requesty",
  "openai/": "direct",
  "google/": "openrouter"
}'
```

---

## Migration Strategy

### Phase 1: Abstraction Layer (Week 1-2)

1. Create `BaseRouter` abstract class
2. Refactor existing `openrouter.py` to implement `OpenRouterGateway`
3. Add `RouterRegistry` for runtime router selection
4. Maintain 100% backward compatibility

```python
# Backward-compatible usage
from llm_council.openrouter import query_model  # Still works

# New usage
from llm_council.routers import get_router
router = get_router("openrouter")
await router.query(model, messages)
```

### Phase 2: Requesty Integration - COMPLETE (v0.12.2, Issue #66)

1. [x] Implement `RequestyGateway` with BYOK support
2. [x] Add fallback chain logic (integrated with GatewayRouter)
3. [x] Implement per-model routing
4. [x] 20 TDD tests for RequestyGateway

### Phase 3: Direct API Support - COMPLETE (v0.12.2, Issue #67)

1. [x] Implement `DirectGateway` for Anthropic, OpenAI, Google
2. [x] Handle provider-specific message formats (OpenAI, Anthropic, Google)
3. [x] Add Anthropic Messages API support (differs from OpenAI format)
4. [x] 24 TDD tests for DirectGateway

### Phase 4: Configuration UI (Future)

1. `llm-council config router` CLI command
2. Interactive router selection and testing
3. Key validation per router

---

## Potential Issues and Mitigations

### Issue 1: Message Format Incompatibility

**Problem**: Anthropic Messages API differs from OpenAI Chat Completions format.

**Mitigation**: Router-specific message transformers:

```python
class AnthropicTransformer:
    def transform_messages(self, messages: List[Dict]) -> Dict:
        # Convert OpenAI format to Anthropic format
        system = next((m["content"] for m in messages if m["role"] == "system"), None)
        user_messages = [m for m in messages if m["role"] != "system"]
        return {
            "system": system,
            "messages": user_messages
        }
```

### Issue 2: Inconsistent Model IDs

**Problem**: Model IDs vary across routers (`anthropic/claude-3-opus` vs `claude-3-opus`).

**Mitigation**: Canonical model ID registry with per-router mappings:

```python
MODEL_ID_MAP = {
    "claude-opus-4.5": {
        "openrouter": "anthropic/claude-opus-4-5-20250514",
        "requesty": "anthropic/claude-opus-4.5",
        "direct": "claude-3-opus-20240229",  # Anthropic native
    }
}
```

### Issue 3: Feature Parity Gaps

**Problem**: Some routers support features others don't (e.g., Requesty caching).

**Mitigation**: Feature capability flags per router:

```python
@dataclass
class RouterCapabilities:
    supports_streaming: bool = True
    supports_tool_calling: bool = True
    supports_caching: bool = False  # Requesty-only
    supports_byok: bool = False     # Requesty-only
    supports_fallback_chains: bool = False  # Requesty-only
```

### Issue 4: Authentication Complexity

**Problem**: Multiple API keys to manage.

**Mitigation**: Leverage existing ADR-013 keychain support + clear validation:

```python
async def validate_router_config() -> List[str]:
    """Return list of configuration warnings/errors."""
    issues = []
    router = get_default_router()

    if not router.has_valid_key():
        issues.append(f"Missing API key for {router.name}")

    for model in COUNCIL_MODELS:
        if not get_router_for_model(model).supports_model(model):
            issues.append(f"Router {router.name} doesn't support {model}")

    return issues
```

### Issue 5: Latency Overhead from Router Switching

**Problem**: Fallback chain adds latency on failures.

**Mitigation**: Parallel probing + circuit breaker pattern:

```python
class CircuitBreaker:
    def __init__(self, failure_threshold: int = 3, reset_timeout: int = 60):
        self.failures = 0
        self.last_failure = None
        self.is_open = False

    async def call(self, router: BaseRouter, *args, **kwargs):
        if self.is_open and time.time() - self.last_failure < self.reset_timeout:
            raise CircuitOpenError(f"{router.name} circuit is open")

        try:
            result = await router.query(*args, **kwargs)
            self.failures = 0
            self.is_open = False
            return result
        except Exception as e:
            self.failures += 1
            self.last_failure = time.time()
            if self.failures >= self.failure_threshold:
                self.is_open = True
            raise
```

---

## Alternatives Considered

### Alternative 1: Requesty-Only Migration

**Approach**: Replace OpenRouter with Requesty as sole gateway.

**Rejected because**:
- Breaks existing user configurations
- Loses OpenRouter's established ecosystem
- Creates new single point of failure

### Alternative 2: Configuration-Only (No Abstraction)

**Approach**: Just add environment variable for API URL.

**Rejected because**:
- Doesn't handle format differences between APIs
- No structured fallback support
- No per-model routing capability

### Alternative 3: Plugin Architecture

**Approach**: External router plugins loaded at runtime.

**Rejected because**:
- Over-engineered for 3-4 known routers
- Adds complexity for users
- Security implications of loading external code

---

## Open Questions for Council Review

1. **Should BYOK be a first-class feature or Requesty-specific?**
   - BYOK could apply to direct APIs too (already "BYO" by definition)
   - Standardize BYOK interface across all routers?

2. **How should router health be surfaced in MCP health checks?**
   - Current `council_health_check` only checks OpenRouter
   - Should it check all configured routers or just the default?

3. **What's the right default for new installations?**
   - OpenRouter (established, wide support) vs Requesty (more features)
   - Should default depend on detected API keys?

4. **Should fallback chains be automatic or explicit?**
   - Auto-fallback improves reliability but may surprise users
   - Explicit requires more configuration but is predictable

5. **How to handle cost tracking across multiple routers?**
   - ADR-011 (cost tracking) assumes single provider
   - Need unified cost model or per-router tracking?

---

## Integration with ADR-020 (Not Diamond)

This section documents how ADR-023 (Gateway Routing) integrates with ADR-020 (Not Diamond Integration Strategy).

### Layering Model

| Layer | ADR | Responsibility | Output |
|-------|-----|----------------|--------|
| **Layer 0** | ADR-020 | Query triage, model selection | ResolvedModelId + optimized prompt |
| **Layer 1** | Core | Council execution (Stage 1-3) | Model responses |
| **Layer 2** | ADR-023 | Gateway routing, BYOK, fallback | API call results |

### Key Integration Points

#### 1. Dynamic Model Resolution

When ADR-020's wildcard seat dynamically selects a model (e.g., `dynamic:not-diamond` → `deepseek/deepseek-v3`), gateway routing applies to the **resolved** model ID.

```python
# ADR-020 resolves dynamic model
resolved_model = await not_diamond.select_model(query)  # "deepseek/deepseek-v3"

# ADR-023 routes resolved model to gateway
gateway = get_gateway_for_model(resolved_model)  # OpenRouter
response = await gateway.complete(resolved_model, messages)
```

**Requirement**: If ADR-020 dynamically selects a model not explicitly mapped in ADR-023 config, the default gateway is used.

#### 2. Canonical Format Pipeline

The canonical formats are related but serve different purposes:

```
User Prompt
    ↓
[ADR-020] Canonical Task Spec (for optimization decisions)
    ↓
[ADR-020] Optimized Prompt (model-specific)
    ↓
[ADR-023] CanonicalMessage (gateway-agnostic wire format)
    ↓
[ADR-023] Gateway-specific format (OpenAI/Anthropic/etc)
```

ADR-023's `CanonicalMessage` is the **output** of any prompt optimization performed by ADR-020.

#### 3. Failure Handling Separation

| Failure Type | Handler | Behavior |
|--------------|---------|----------|
| **Infrastructure failure** (timeout, 5xx, rate limit) | ADR-023 Fallback Chain | Retry via next gateway |
| **Low-confidence triage** | ADR-020 Confidence Gate | Escalate to full council |
| **Model returns poor result** | Neither (application layer) | Future enhancement |

Gateway fallback is **independent** of ADR-020's confidence-gated triage:

```
Triage → Single Model Fast Path
              │
              ▼
         Gateway A fails → [ADR-023] Try Gateway B
                                │
                                ▼
                          Gateway B fails → [ADR-023] Try Gateway C
                                                │
                                                ▼
                                          All gateways exhausted
                                                │
                                                ▼
                          [ADR-023] Raise TransportFailure exception
                                                │
                                                ▼
                          [Application] May escalate to full council
```

### Configuration Interaction

Both ADRs have independent configuration, but a unified config schema is recommended:

```yaml
# Recommended: llm_council_config.yaml
council:
  # ADR-020 concerns
  triage:
    mode: confidence_gated
    prompt_optimization: true
    wildcard:
      enabled: true
      selector: not_diamond
      api_key: ${NOT_DIAMOND_API_KEY}

  # ADR-023 concerns
  gateways:
    default: openrouter
    model_routing:
      "anthropic/*": requesty
      "deepseek/*": openrouter
    fallback_chain: [openrouter, requesty, direct]
    byok:
      enabled: true
      keys:
        anthropic: ${ANTHROPIC_API_KEY}
```

---

## Out of Scope

This ADR covers **gateway routing** (which API endpoint services a model). It does NOT cover:

| Concern | Responsible ADR |
|---------|-----------------|
| Query triage / complexity classification | ADR-020 |
| Model selection (which model to use) | ADR-020 |
| Not Diamond integration | ADR-020 |
| Prompt optimization | ADR-020 |
| Tier selection (quick/balanced/high) | ADR-022 |

**Not Diamond** operates at a higher layer (query triage) and its output (selected models) feeds INTO the gateway routing layer defined here. Not Diamond is NOT a gateway type.

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Backward compatibility | 100% | Existing configs work unchanged |
| Router switching latency | <50ms | Overhead of router selection |
| Fallback success rate | >95% | Failed requests recovered by fallback |
| Configuration complexity | <5 env vars for common cases | User survey |
| Enterprise adoption | Enable blocked deployments | Customer feedback |

---

---

## Council Review Summary

**Status:** ACCEPT WITH MODIFICATIONS

### Initial Review (2025-12-22)

**Reviewed by**: Gemini 3 Pro (32s), Claude Opus 4.5 (82s), Grok-4 (89s), GPT-5.2-pro (129s)

**Council Verdict**: All 4 models responded with unanimous agreement that the Router Abstraction Layer is architecturally correct. However, significant modifications are required before implementation.

### Harmonization Review (2025-12-22)

**Reviewed by**: Gemini 3 Pro (34s), Claude Opus 4.5 (65s), Grok-4 (78s), GPT-5.2-pro (153s)

**Harmonization Verdict**: ADR-020 and ADR-023 are **architecturally compatible**. Required changes are documentation-level, not design-level:
- **ADR-020** is the "Brain" (Decision Layer) - model selection, triage, prompt optimization
- **ADR-023** is the "Nervous System" (Transport Layer) - gateway routing, failover, BYOK

**Key Consensus**:
1. Terminology: ADR-023 uses "gateway routing"; ADR-020 uses "model selection/triage"
2. Not Diamond is a meta-layer, NOT a gateway type
3. Execution order: Triage → Model Selection → Gateway Selection → API Call
4. Canonical formats: Keep separate but coordinated (Task Spec → CanonicalMessage pipeline)
5. Failure handling: Infrastructure failures (ADR-023) vs competence failures (ADR-020) are orthogonal

---

### Consensus Answers to Key Questions

#### 1. Should BYOK be a first-class feature or Requesty-specific?

**Verdict: First-Class, Standardized Feature**

The Council unanimously rejects limiting BYOK to Requesty. "Direct API" usage is inherently BYOK.

**Recommendation**: Implement a standardized `CredentialManager` interface:

```python
from abc import ABC, abstractmethod
from enum import Enum
from dataclasses import dataclass

class KeyManagementModel(Enum):
    PROVIDER_KEYS = "provider"    # Router manages keys (OpenRouter default)
    USER_KEYS = "user"            # User provides their own keys
    HYBRID = "hybrid"             # Router can use either

@dataclass
class KeyConfiguration:
    model: KeyManagementModel
    user_keys: dict[str, str] | None = None
    model_key_overrides: dict[str, str] | None = None

class BaseRouter(ABC):
    @property
    @abstractmethod
    def supported_key_models(self) -> list[KeyManagementModel]:
        """What key management approaches does this router support?"""
        pass

    @abstractmethod
    def configure_keys(self, config: KeyConfiguration) -> None:
        """Configure key management for this router."""
        pass
```

#### 2. How should router health be surfaced in MCP health checks?

**Verdict: Tiered Health Model**

Checking every router on every heartbeat is rejected due to latency and rate-limit risks.

| Health Tier | Behavior |
|-------------|----------|
| **Tier 1 (Fast/Default)** | Validate config + connectivity to default router only |
| **Tier 2 (Diagnostic)** | On-demand `health_check(deep=True)` that probes all configured gateways |

```python
@dataclass
class RouterHealth:
    router_id: str
    status: HealthStatus  # healthy | degraded | unhealthy
    latency_ms: float | None
    last_check: datetime
    circuit_open: bool = False
    consecutive_failures: int = 0

@dataclass
class GatewayHealthReport:
    overall_status: HealthStatus
    default_router: RouterHealth
    fallback_routers: list[RouterHealth]
```

#### 3. What's the right default for new installations?

**Verdict: OpenRouter Strict Default + "Auto" Opt-in**

To ensure backward compatibility, OpenRouter must remain the default.

**Smart Detection** (opt-in via `LLM_COUNCIL_ROUTER=auto`):
1. If `REQUESTY_API_KEY` present → Requesty
2. Else if `OPENROUTER_API_KEY` present → OpenRouter
3. Else if direct provider keys present → Direct
4. Else → Fail fast with clear configuration error

**Key Principle**: Defaults should be predictable. Auto-detection should *inform*, not *decide*.

```
INFO: Detected Anthropic and OpenAI API keys. Consider LLM_COUNCIL_ROUTER=direct for lowest latency.
INFO: Using default router: openrouter
```

#### 4. Should fallback chains be automatic or explicit?

**Verdict: Explicit Configuration Only (Safety First)**

Automatic fallback is deemed too risky:
- Silently falling back from GPT-4 to a different model changes agent behavior
- Can cause hallucinations that are hard to debug
- May violate enterprise constraints (data residency, vendor allowlists)

**Fallback Policy Configuration**:

```python
@dataclass
class FallbackPolicy:
    behavior: FallbackBehavior = FallbackBehavior.EXPLICIT
    fallback_chain: list[str] = field(default_factory=list)

    # Trigger conditions
    fallback_on_rate_limit: bool = True
    fallback_on_timeout: bool = True
    fallback_on_server_error: bool = True  # 5xx

    # Never fallback on user errors (should surface immediately)
    fallback_on_auth_error: bool = False  # 401/403
    fallback_on_invalid_request: bool = False  # 400
    fallback_on_content_filter: bool = False
```

#### 5. How to handle cost tracking across multiple routers?

**Verdict: Unified Data Model with Router-Specific Adapters**

```python
@dataclass
class UnifiedCostRecord:
    """Router-agnostic cost representation."""
    timestamp: datetime
    model: str
    router: str
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    router_reported_cost: Decimal | None = None
    pricing_source: str = "calculated"  # or "router_reported"
```

**Key insight**: Prefer router-reported costs when available, fall back to calculated costs using a maintained pricing table, always record both for reconciliation.

---

### Critical Risks Identified (Question 6)

The Council identified **Message Format Divergence** as the highest underestimated risk.

| Risk | Severity | Mitigation |
|------|----------|------------|
| **Message Format Divergence** | HIGH | Define Canonical Internal Message Format with per-router transformers |
| **Feature Parity Leaks** | HIGH | `RouterCapabilities` flags; skip incompatible fallbacks |
| **Compliance/Data Routing** | HIGH | Explicit allowlists, region locks, "no aggregator" mode |
| **Streaming Behavior Inconsistency** | MEDIUM | Define streaming contract with clear chunk semantics |
| **Rate Limit Semantic Differences** | MEDIUM | Explicit `RateLimitInfo` abstraction |
| **Testing Matrix Explosion** | HIGH | Conformance test suite with recorded fixtures |
| **Circuit Breaker in Distributed Deployments** | MEDIUM | Local breakers with jitter; optional shared state (Redis) |
| **Secret Handling/Leakage** | MEDIUM | Strict redaction, structured secret objects |

**Canonical Message Format Required**:

```python
@dataclass
class CanonicalMessage:
    """Internal representation—routers transform to/from this."""
    role: str  # system, user, assistant, tool
    content: list['ContentBlock']
    tool_calls: list['ToolCall'] = field(default_factory=list)
    tool_call_id: str | None = None

@dataclass
class ContentBlock:
    type: str  # text, image, tool_use, tool_result
    text: str | None = None
    image_url: str | None = None
    tool_use: dict[str, Any] | None = None
```

---

### Interface Redesign (Question 7)

**Verdict: Interface is too minimal—add capabilities discovery and health probing**

```python
class BaseRouter(ABC):
    @property
    @abstractmethod
    def router_id(self) -> str:
        """Unique identifier for this router."""
        pass

    @property
    @abstractmethod
    def capabilities(self) -> RouterCapabilities:
        """What this router supports."""
        pass

    @abstractmethod
    async def complete(
        self,
        messages: list[CanonicalMessage],
        model: str,
        **kwargs
    ) -> 'CompletionResponse':
        """Synchronous completion."""
        pass

    @abstractmethod
    async def complete_stream(
        self,
        messages: list[CanonicalMessage],
        model: str,
        **kwargs
    ) -> AsyncIterator['StreamChunk']:
        """Streaming completion."""
        pass

    async def health_check(self, deep: bool = False) -> RouterHealth:
        """Tiered health check."""
        pass

    def validate_request(self, request: CanonicalRequest) -> bool:
        """Pre-flight check for context limits and feature support."""
        pass

@dataclass
class RouterCapabilities:
    supports_streaming: bool = True
    supports_tools: bool = True
    supports_vision: bool = True
    supports_json_mode: bool = True
    supports_byok: bool = False
    requires_byok: bool = False
    provides_cost_in_response: bool = False
    max_context_window: int | None = None
```

---

### Additional Architectural Recommendations

#### 1. Configuration File Support

Environment variables become unwieldy. Support YAML configuration:

```yaml
# llm_council_routing.yaml
default_router: openrouter

routers:
  openrouter:
    api_key: ${OPENROUTER_API_KEY}

  requesty:
    api_key: ${REQUESTY_API_KEY}

  direct:
    providers:
      anthropic:
        api_key: ${ANTHROPIC_API_KEY}
      openai:
        api_key: ${OPENAI_API_KEY}

fallback:
  behavior: explicit
  chain: [openrouter, direct]

model_routing:
  "anthropic/*": direct
  "openai/*": direct
```

#### 2. Circuit Breaker Defaults

```python
@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5
    failure_window_seconds: int = 60
    reset_timeout_seconds: int = 30
    half_open_max_failures: int = 1
```

#### 3. MockRouter for Testing

```python
@dataclass
class MockRouter(BaseRouter):
    """For testing—supports programmed responses and failure injection."""
    responses: dict[str, MockResponse] = field(default_factory=dict)
    failure_rate: float = 0.0
    calls: list[dict] = field(default_factory=list)  # For assertions
```

---

### Implementation Revision (Council-Informed)

| Phase | Original | Council Revision |
|-------|----------|------------------|
| Phase 1 | Abstraction Layer | Add Canonical Message Schema + `RouterCapabilities` |
| Phase 2 | Requesty Integration | Add standardized `CredentialManager` (not Requesty-specific) |
| Phase 3 | Direct API Support | Include Message Transformers for each provider |
| Phase 4 | Configuration UI | Add YAML config support, validation tools |

### Actions Required Before Approval

1. **Define Canonical Message Format Specification**
2. **Add configuration file support alongside env vars**
3. **Expand `BaseRouter` interface with capabilities and health_check**
4. **Specify circuit breaker defaults**
5. **Include MockRouter in implementation for testing**
6. **Document migration path explicitly**
7. **Update ADR-011 for multi-router cost tracking**
8. **[Harmonization] Clarify terminology: use "gateway routing" consistently**
9. **[Harmonization] Document integration with ADR-020 (completed in this revision)**
10. **[Harmonization] Define unified config schema for both ADR-020 and ADR-023**

### Rollback Triggers

```yaml
automatic_rollback:
  - backward_compatibility_break_detected
  - fallback_error_rate > 10%
  - config_validation_failure_rate > 5%
  - latency_overhead > 100ms
```

---

## References

### Related ADRs (Unified Routing Architecture)
- [ADR-020: Not Diamond Integration Strategy](./ADR-020-not-diamond-integration-strategy.md) - Layer 2 (Query Triage)
- [ADR-022: Tiered Model Selection](./ADR-022-tiered-model-selection.md) - Layer 1 (Tier Selection)
- [ADR-024: Unified Routing Architecture](./ADR-024-unified-routing-architecture.md) - Coordination layer

### Other References
- [ADR-013: Secure API Key Handling](./ADR-013-secure-api-key-handling.md)
- [OpenRouter Documentation](https://openrouter.ai/docs/quickstart)
- [Requesty Documentation](https://docs.requesty.ai/quickstart)
