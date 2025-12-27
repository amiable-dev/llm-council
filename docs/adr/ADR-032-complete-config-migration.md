# ADR-032: Complete Configuration Migration & config.py Deletion

**Status:** APPROVED
**Date:** 2025-12-27
**Context:** Post-ADR-031 (EvaluationConfig), enables Issue #149
**Depends On:** ADR-013 (Secure API Keys), ADR-024 (Unified Routing), ADR-031 (Configuration Modernization)
**Council Review:** 2025-12-27 (High Tier, 4/4 models)

## Context

ADR-031 successfully migrated evaluation-related configuration (rubric, safety, bias) to `unified_config.py`. However, `config.py` still contains ~500 lines of configuration across multiple domains:

**Remaining Imports (15 files):**
```
council.py          → COUNCIL_MODELS, CHAIRMAN_MODEL, SYNTHESIS_MODE, EXCLUDE_SELF_VOTES, etc.
openrouter.py       → OPENROUTER_API_KEY, OPENROUTER_API_URL
tier_contract.py    → TIER_MODEL_POOLS, get_tier_timeout
cache.py            → CACHE_ENABLED, CACHE_TTL, CACHE_DIR
mcp_server.py       → COUNCIL_MODELS, CHAIRMAN_MODEL
telemetry.py        → TELEMETRY_ENABLED, TELEMETRY_LEVEL, TELEMETRY_ENDPOINT
webhooks/dispatcher → WEBHOOK_TIMEOUT, WEBHOOK_MAX_RETRIES, WEBHOOK_HTTPS_ONLY
gateway/ollama.py   → OLLAMA_HARDWARE_PROFILES
gateway/openrouter  → OPENROUTER_API_KEY, OPENROUTER_API_URL
metadata/selection  → TIER_MODEL_POOLS
metadata/discovery  → TIER_MODEL_POOLS
triage/__init__     → COUNCIL_MODELS
evaluation.py       → COUNCIL_MODELS
gateway_adapter.py  → USE_GATEWAY_LAYER
frontier_fallback   → get_tier_models
```

This dual-system creates confusion about which config source to use.

## Decision

We will complete the migration of all `config.py` contents to `unified_config.py` and delete `config.py`, making `unified_config.py` the single source of truth.

### Design Principles

1. **Secrets Never in YAML**: API keys and secrets come exclusively from environment variables (or keychain via ADR-013 priority chain)
2. **YAML as Canonical Config**: All non-secret configuration lives in `llm_council.yaml`
3. **Environment Variable Overrides**: Every config option supports env var override for CI/CD flexibility
4. **Backwards Compatibility**: Existing env var names continue to work via `validation_alias`
5. **Fail-Fast Validation**: Pydantic validates at startup, not at usage time

### Proposed Schema Extensions

#### 1. Secrets Configuration

```python
class SecretsConfig(BaseModel):
    """Secret resolution configuration (ADR-013).

    Secrets are NEVER stored in YAML. This config controls
    the resolution priority chain.
    """
    model_config = ConfigDict(populate_by_name=True)

    # Resolution priority (ADR-013): env → keychain → .env
    resolution_priority: list[str] = Field(
        default=["environment", "keychain", "dotenv"],
        description="Secret resolution priority chain"
    )

    # Keychain service name
    keychain_service: str = Field(
        default="llm-council",
        description="Keychain service name for credential lookup"
    )

    # Whether to warn when using insecure sources
    warn_on_insecure: bool = Field(
        default=True,
        validation_alias="LLM_COUNCIL_SUPPRESS_WARNINGS",  # Inverted
    )
```

**Runtime Resolution:**
```python
def get_api_key(provider: str = "openrouter") -> Optional[str]:
    """Resolve API key using ADR-013 priority chain."""
    config = get_config()

    for source in config.secrets.resolution_priority:
        if source == "environment":
            key = os.getenv(f"{provider.upper()}_API_KEY")
            if key:
                return key
        elif source == "keychain":
            key = _get_from_keychain(config.secrets.keychain_service, provider)
            if key:
                return key
        elif source == "dotenv":
            # Already loaded via python-dotenv
            pass

    return None
```

#### 2. Council Configuration

```python
class CouncilConfig(BaseModel):
    """Core council behavior configuration."""
    model_config = ConfigDict(populate_by_name=True)

    # Default council models
    models: list[str] = Field(
        default_factory=lambda: [
            "openai/gpt-5.2-pro",
            "google/gemini-3-pro-preview",
            "anthropic/claude-opus-4.5",
            "x-ai/grok-4",
        ],
        validation_alias="LLM_COUNCIL_MODELS",
    )

    # Chairman (synthesis) model
    chairman: str = Field(
        default="google/gemini-3-pro-preview",
        validation_alias="LLM_COUNCIL_CHAIRMAN",
    )

    # Synthesis mode
    synthesis_mode: Literal["consensus", "debate"] = Field(
        default="consensus",
        validation_alias="LLM_COUNCIL_MODE",
    )

    # Self-vote exclusion
    exclude_self_votes: bool = Field(
        default=True,
        validation_alias="LLM_COUNCIL_EXCLUDE_SELF_VOTES",
    )

    # Style normalization (Stage 1.5)
    style_normalization: bool | Literal["auto"] = Field(
        default=False,
        validation_alias="LLM_COUNCIL_STYLE_NORMALIZATION",
    )

    normalizer_model: str = Field(
        default="google/gemini-2.0-flash-001",
        validation_alias="LLM_COUNCIL_NORMALIZER_MODEL",
    )

    # Stratified sampling
    max_reviewers: Optional[int] = Field(
        default=None,
        validation_alias="LLM_COUNCIL_MAX_REVIEWERS",
    )
```

#### 3. Tier Pools Configuration

```python
class TierPoolsConfig(BaseModel):
    """Per-tier model pool configuration (ADR-022)."""
    model_config = ConfigDict(populate_by_name=True)

    quick: list[str] = Field(
        default_factory=lambda: [
            "openai/gpt-4o-mini",
            "anthropic/claude-3-5-haiku-20241022",
            "google/gemini-2.0-flash-001",
        ],
        validation_alias="LLM_COUNCIL_MODELS_QUICK",
    )

    balanced: list[str] = Field(
        default_factory=lambda: [
            "openai/gpt-4o",
            "anthropic/claude-3-5-sonnet-20241022",
            "google/gemini-2.5-pro-preview",
        ],
        validation_alias="LLM_COUNCIL_MODELS_BALANCED",
    )

    high: list[str] = Field(
        default_factory=lambda: [
            "openai/gpt-4o",
            "anthropic/claude-opus-4.5",
            "google/gemini-3-pro-preview",
            "x-ai/grok-4",
        ],
        validation_alias="LLM_COUNCIL_MODELS_HIGH",
    )

    reasoning: list[str] = Field(
        default_factory=lambda: [
            "openai/gpt-5.2-pro",
            "anthropic/claude-opus-4.5",
            "google/gemini-3-pro-preview",
            "x-ai/grok-4.1-fast",
        ],
        validation_alias="LLM_COUNCIL_MODELS_REASONING",
    )

    frontier: list[str] = Field(
        default_factory=lambda: [
            "openai/gpt-5.2-pro",
            "anthropic/claude-opus-4.5",
            "google/gemini-3-pro-preview",
            "x-ai/grok-4",
            "deepseek/deepseek-r1",
        ],
        validation_alias="LLM_COUNCIL_MODELS_FRONTIER",
    )

    def get_models(self, tier: str) -> list[str]:
        """Get models for a tier, with 'high' as fallback."""
        return getattr(self, tier, self.high)
```

#### 4. Timeout Configuration

```python
class TierTimeoutConfig(BaseModel):
    """Timeout configuration for a single tier."""
    total: int = Field(description="Total timeout in seconds")
    per_model: int = Field(description="Per-model timeout in seconds")

class TimeoutsConfig(BaseModel):
    """Tier-sovereign timeout configuration (ADR-012)."""
    model_config = ConfigDict(populate_by_name=True)

    quick: TierTimeoutConfig = Field(
        default_factory=lambda: TierTimeoutConfig(total=30, per_model=20)
    )
    balanced: TierTimeoutConfig = Field(
        default_factory=lambda: TierTimeoutConfig(total=90, per_model=45)
    )
    high: TierTimeoutConfig = Field(
        default_factory=lambda: TierTimeoutConfig(total=180, per_model=90)
    )
    reasoning: TierTimeoutConfig = Field(
        default_factory=lambda: TierTimeoutConfig(total=600, per_model=300)
    )
    frontier: TierTimeoutConfig = Field(
        default_factory=lambda: TierTimeoutConfig(total=600, per_model=300)
    )

    # Global multiplier for emergency adjustments
    multiplier: float = Field(
        default=1.0,
        validation_alias="LLM_COUNCIL_TIMEOUT_MULTIPLIER",
    )

    def get_timeout(self, tier: str) -> TierTimeoutConfig:
        """Get timeout for tier with multiplier applied."""
        base = getattr(self, tier, self.high)
        return TierTimeoutConfig(
            total=int(base.total * self.multiplier),
            per_model=int(base.per_model * self.multiplier),
        )
```

#### 5. Cache Configuration

```python
class CacheConfig(BaseModel):
    """Response caching configuration."""
    model_config = ConfigDict(populate_by_name=True)

    enabled: bool = Field(
        default=False,
        validation_alias="LLM_COUNCIL_CACHE",
    )

    ttl_seconds: int = Field(
        default=0,  # 0 = infinite
        validation_alias="LLM_COUNCIL_CACHE_TTL",
    )

    directory: Path = Field(
        default_factory=lambda: Path.home() / ".cache" / "llm-council",
        validation_alias="LLM_COUNCIL_CACHE_DIR",
    )
```

#### 6. Telemetry Configuration

```python
class TelemetryConfig(BaseModel):
    """Opt-in telemetry configuration (ADR-001)."""
    model_config = ConfigDict(populate_by_name=True)

    level: Literal["off", "anonymous", "debug"] = Field(
        default="off",
        validation_alias="LLM_COUNCIL_TELEMETRY",
    )

    endpoint: str = Field(
        default="https://ingest.llmcouncil.ai/v1/events",
        validation_alias="LLM_COUNCIL_TELEMETRY_ENDPOINT",
    )

    @property
    def enabled(self) -> bool:
        return self.level != "off"
```

### Updated UnifiedConfig Root

```python
class UnifiedConfig(BaseModel):
    """Complete unified configuration for LLM Council."""
    model_config = ConfigDict(populate_by_name=True)

    # Existing (from ADR-024, ADR-026, ADR-030, ADR-031)
    tiers: TierConfig = Field(default_factory=TierConfig)
    triage: TriageConfig = Field(default_factory=TriageConfig)
    gateways: GatewayConfig = Field(default_factory=GatewayConfig)
    model_intelligence: ModelIntelligenceConfig = Field(default_factory=ModelIntelligenceConfig)
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)

    # New (ADR-032)
    secrets: SecretsConfig = Field(default_factory=SecretsConfig)
    council: CouncilConfig = Field(default_factory=CouncilConfig)
    tier_pools: TierPoolsConfig = Field(default_factory=TierPoolsConfig)
    timeouts: TimeoutsConfig = Field(default_factory=TimeoutsConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    telemetry: TelemetryConfig = Field(default_factory=TelemetryConfig)
```

### YAML Configuration Example

```yaml
# llm_council.yaml - Complete configuration example

# Secrets are resolved from environment (never in YAML)
secrets:
  resolution_priority:
    - environment
    - keychain
    - dotenv
  keychain_service: llm-council
  warn_on_insecure: true

# Core council configuration
council:
  models:
    - openai/gpt-5.2-pro
    - google/gemini-3-pro-preview
    - anthropic/claude-opus-4.5
    - x-ai/grok-4
  chairman: google/gemini-3-pro-preview
  synthesis_mode: consensus
  exclude_self_votes: true
  style_normalization: false
  max_reviewers: null

# Per-tier model pools
tier_pools:
  quick:
    - openai/gpt-4o-mini
    - anthropic/claude-3-5-haiku-20241022
    - google/gemini-2.0-flash-001
  balanced:
    - openai/gpt-4o
    - anthropic/claude-3-5-sonnet-20241022
    - google/gemini-2.5-pro-preview
  high:
    - openai/gpt-4o
    - anthropic/claude-opus-4.5
    - google/gemini-3-pro-preview
    - x-ai/grok-4
  reasoning:
    - openai/gpt-5.2-pro
    - anthropic/claude-opus-4.5
    - google/gemini-3-pro-preview
    - x-ai/grok-4.1-fast
  frontier:
    - openai/gpt-5.2-pro
    - anthropic/claude-opus-4.5
    - google/gemini-3-pro-preview
    - deepseek/deepseek-r1

# Tier timeouts
timeouts:
  quick:
    total: 30
    per_model: 20
  balanced:
    total: 90
    per_model: 45
  high:
    total: 180
    per_model: 90
  reasoning:
    total: 600
    per_model: 300
  frontier:
    total: 600
    per_model: 300
  multiplier: 1.0

# Response caching
cache:
  enabled: false
  ttl_seconds: 0
  directory: ~/.cache/llm-council

# Telemetry (opt-in)
telemetry:
  level: "off"
  endpoint: https://ingest.llmcouncil.ai/v1/events

# Evaluation config (ADR-031)
evaluation:
  rubric:
    enabled: true
    weights:
      accuracy: 0.35
      completeness: 0.25
      conciseness: 0.20
      clarity: 0.20
  safety:
    enabled: true
    score_cap: 0.0
  bias:
    audit_enabled: true
    persistence_enabled: false

# Gateways (ADR-024)
gateways:
  default: openrouter
  providers:
    openrouter:
      base_url: https://openrouter.ai/api/v1
      timeout_seconds: 120
    ollama:
      base_url: http://localhost:11434
      timeout_seconds: 120
```

### Migration Strategy: Big Bang (Per Council)

Given the test-only deployment context, the council recommended a **single atomic refactor** to avoid "split-brain" configuration states.

**Single PR Structure:**

```
Commit 1: Add new schema sections
├── SecretsConfig (metadata-only, no resolution logic)
├── CouncilConfig (models, chairman, synthesis_mode, etc.)
├── TierPoolsConfig (quick, balanced, high, reasoning, frontier)
├── TimeoutsConfig (per-tier timeouts with multiplier)
├── CacheConfig (enabled, ttl, directory)
├── TelemetryConfig (level, endpoint)
└── ModelList type with auto-detection validator

Commit 2: Add helper functions
├── get_api_key() - ADR-013 resolution (env → keychain → dotenv)
├── parse_model_list() - Auto-detection (comma vs JSON)
└── dump_effective_config() - Debug helper with secret redaction

Commit 3: Migrate all 15 import sites
├── council.py, openrouter.py, tier_contract.py
├── cache.py, mcp_server.py, telemetry.py
├── webhooks/dispatcher.py, gateway/*.py
├── metadata/selection.py, metadata/discovery.py
├── triage/__init__.py, evaluation.py
├── gateway_adapter.py, frontier_fallback.py
└── __init__.py re-exports

Commit 4: Delete config.py, update docs
├── Remove config.py
├── Update CLAUDE.md
├── Update llm_council.yaml schema
└── Close Issue #149
```

**Rollback Strategy:** Keep `config.py` renamed to `config.py.backup` for 1 week post-merge.

### Environment Variable Compatibility Matrix

| Current Env Var | New Config Path | Notes |
|-----------------|-----------------|-------|
| `OPENROUTER_API_KEY` | Runtime resolution | Never in config |
| `LLM_COUNCIL_MODELS` | `council.models` | Comma-separated |
| `LLM_COUNCIL_CHAIRMAN` | `council.chairman` | |
| `LLM_COUNCIL_MODE` | `council.synthesis_mode` | |
| `LLM_COUNCIL_MODELS_QUICK` | `tier_pools.quick` | Comma-separated |
| `LLM_COUNCIL_MODELS_BALANCED` | `tier_pools.balanced` | Comma-separated |
| `LLM_COUNCIL_MODELS_HIGH` | `tier_pools.high` | Comma-separated |
| `LLM_COUNCIL_MODELS_REASONING` | `tier_pools.reasoning` | Comma-separated |
| `LLM_COUNCIL_TIMEOUT_MULTIPLIER` | `timeouts.multiplier` | |
| `LLM_COUNCIL_CACHE` | `cache.enabled` | |
| `LLM_COUNCIL_TELEMETRY` | `telemetry.level` | |

### Key Questions for Council Review

1. **Secrets Handling**: Is the proposed `SecretsConfig` with resolution priority chain the right abstraction? Or should secrets remain purely runtime with no schema representation?

2. **List Parsing**: For env vars containing model lists (e.g., `LLM_COUNCIL_MODELS=gpt-4,claude-3`), should we:
   - (a) Use comma-separation (current behavior)
   - (b) Use JSON array syntax (`["gpt-4", "claude-3"]`)
   - (c) Support both with auto-detection

3. **Nested Env Var Overrides**: For nested configs like `timeouts.quick.total`, should we support:
   - (a) Flattened: `LLM_COUNCIL_TIMEOUT_QUICK=30`
   - (b) Dotted: `LLM_COUNCIL_TIMEOUTS_QUICK_TOTAL=30`
   - (c) Both with priority rules

4. **YAML vs Environment Precedence**: Currently env vars override YAML. Should we:
   - (a) Keep this (env wins) - good for CI/CD overrides
   - (b) Reverse it (YAML wins) - good for explicit configuration
   - (c) Add a flag to control precedence

5. **Migration Urgency**: Given test-only deployment, should we:
   - (a) Big Bang: All phases in one PR
   - (b) Phased: 3 PRs over ~1 week

## Council Review Summary

### Decisions Made

| Question | Decision | Rationale |
|----------|----------|-----------|
| **Secrets Handling** | Simplify to metadata-only | Don't put resolution logic in schema. Schema declares *which* secrets exist, not *how* to find them. Resolution logic stays in code. |
| **List Parsing** | Option (c) - Auto-detection | Support both comma-separated and JSON arrays. Check if string starts with `[` → parse as JSON, otherwise split by comma. |
| **Nested Env Vars** | Option (a) - Flattened names | Use `LLM_COUNCIL_TIMEOUT_QUICK=30` not dotted paths. Aligns with 12-Factor App and Docker/K8s conventions. |
| **YAML vs Env Precedence** | Keep env → YAML (non-configurable) | **Unanimous.** Follows 12-Factor App principles. Making this configurable introduces debugging complexity. |
| **Migration Strategy** | Option (a) - Big Bang | **Strong majority (3/4).** Test-only deployment = low blast radius. Avoids "split-brain" configuration states. |

### Revised SecretsConfig (Per Council)

The original proposal put resolution logic in the schema. Council recommended: **declare which secrets exist, not how to find them**.

```python
class SecretsConfig(BaseModel):
    """Declares WHICH secrets the system expects (validation), not HOW to find them.

    Resolution logic (env → keychain → dotenv) stays in get_api_key() function.
    This enables startup validation: "you're missing ANTHROPIC_API_KEY".
    """
    model_config = ConfigDict(populate_by_name=True)

    # Which secrets are required for operation
    required_providers: list[str] = Field(
        default=["openrouter"],
        description="Providers that must have API keys configured"
    )

    # Keychain service name (for ADR-013 keychain lookup)
    keychain_service: str = Field(
        default="llm-council",
    )
```

### List Parsing Implementation (Per Council)

```python
from pydantic import BeforeValidator
from typing import Annotated
import json

def parse_model_list(value: str | list[str]) -> list[str]:
    """Parse environment variable as list with auto-detection."""
    if isinstance(value, list):
        return value
    value = value.strip()
    if value.startswith('['):
        return json.loads(value)  # JSON array
    return [item.strip() for item in value.split(',') if item.strip()]

ModelList = Annotated[list[str], BeforeValidator(parse_model_list)]
```

### Key Council Insights

1. **"Configuration should define *what* is needed, not logic for *how* to find it"** - Resolution chains belong in code, not YAML
2. **Use `pydantic-settings`** - Handles env → dotenv resolution automatically
3. **Flattened env vars for high-level overrides only** - Not every nested field needs an env override
4. **Replace, don't merge** - When env var overrides a list, it replaces entirely (no merging)
5. **Add config dump for debugging** - `dump_effective_config(redact_secrets=True)` for troubleshooting

### Dissenting Opinion (Minority)

**Grok-4** preferred **phased migration** for safety, even in test environments. The counterargument: phased migration requires maintaining backward-compatibility code for a week, which adds complexity and risk of "split-brain" bugs where different parts of the system use different config sources.

## Consequences

### Pros
- Single source of truth for all configuration
- Pydantic validation at startup for all config
- IDE autocomplete and type checking everywhere
- Clear separation: secrets (env only) vs config (YAML primary)
- No more confusion about which config file to use
- Enables clean module boundary for `llm_council` package

### Cons
- ~500 lines of new Pydantic models
- Need to migrate 15 files
- Risk of regression in env var handling
- May break custom integrations relying on `config.py` imports

## Implementation Checklist

- [ ] Add `SecretsConfig` to unified_config.py
- [ ] Add `CouncilConfig` to unified_config.py
- [ ] Add `TierPoolsConfig` to unified_config.py
- [ ] Add `TimeoutsConfig` to unified_config.py
- [ ] Add `CacheConfig` to unified_config.py
- [ ] Add `TelemetryConfig` to unified_config.py
- [ ] Update `UnifiedConfig` root with new sections
- [ ] Add `get_api_key()` helper with ADR-013 resolution
- [ ] Write tests for each new config section
- [ ] Migrate council.py imports
- [ ] Migrate openrouter.py imports
- [ ] Migrate tier_contract.py imports
- [ ] Migrate cache.py imports
- [ ] Migrate mcp_server.py imports
- [ ] Migrate telemetry.py imports
- [ ] Migrate webhooks/dispatcher.py imports
- [ ] Migrate gateway/ollama.py imports
- [ ] Migrate gateway/openrouter.py imports
- [ ] Migrate metadata/selection.py imports
- [ ] Migrate metadata/discovery.py imports
- [ ] Migrate triage/__init__.py imports
- [ ] Migrate evaluation.py imports
- [ ] Migrate gateway_adapter.py imports
- [ ] Migrate frontier_fallback.py imports
- [ ] Update llm_council.yaml schema
- [ ] Update CLAUDE.md documentation
- [ ] Delete config.py
- [ ] Close Issue #149
- [ ] Run full test suite
