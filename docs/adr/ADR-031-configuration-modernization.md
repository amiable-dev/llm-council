# ADR-031: Configuration Modernization & Cleanup

**Status:** APPROVED
**Date:** 2025-12-26
**Context:** Post-ADR-024 (Unified Routing) & ADR-030 (Scoring Extensions)
**Council Review:** 2025-12-26 (Reasoning Tier, 4/4 models, 2 rounds)

## Deployment Context

**Important:** This project is currently only deployed in our **test environment**. There are no production deployments or external consumers of the `config.py` API. This context informed the council's decision to recommend a Big Bang refactor over phased deprecation.

## Context

The `llm-council` project is currently in a "hybrid" state regarding configuration:

1. **Strict/Modern (`unified_config.py`):** Uses Pydantic for validation, hierarchical structure (e.g., `model_intelligence.scoring`), and ADR-024 architecture.
2. **Legacy (`config.py`):** Uses flat global variables, loose validation, and manual `os.getenv` lookups.

This split creates confusion:
* Developers ask "Which config file do I use?"
* Some features (ADR-016 Rubric Scoring) exist in `config.py` but are missing from the `UnifiedConfig` schema, making them invisible to the modern system.
* `llm_council.yaml` contains "dead" sections (like `scoring:`) that don't map to anything in `UnifiedConfig`.

There are currently **36 imports** from the legacy `config.py` across the codebase.

## Decision

We will standardize on **UnifiedConfig** as the single source of truth and **immediately delete** `config.py` via a Big Bang refactor.

### Migration Strategy: Big Bang Refactor

The council unanimously recommended **Option A: Big Bang Refactor** given our test-only deployment context.

**Rationale:**
> *"A shim is strictly a risk-management artifact designed to decouple internal changes from external consumers or production stability requirements. Since neither of those constraints exists here, implementing a shim would be over-engineering."*

| Approach | PRs | Time to Clean State | Complexity Added |
|----------|-----|---------------------|------------------|
| **Big Bang** ✓ | 1 | ~1 day | None |
| Phased/Shim | 2+ | 4-6 weeks | Temporary debt |

### 1. Migrate Missing Features to `UnifiedConfig`

We will move the following legacy `config.py` sections into `UnifiedConfig` schemas:

* **Rubric Scoring (ADR-016):**
    * `evaluation.rubric.enabled` (bool)
    * `evaluation.rubric.weights` (dict[str, float])
* **Safety Gate (ADR-016):**
    * `evaluation.safety.enabled` (bool)
    * `evaluation.safety.score_cap` (float)
* **Bias Auditing (ADR-015):**
    * `evaluation.bias.audit_enabled` (bool)
    * `evaluation.bias.persistence_enabled` (bool)

### 2. Schema Design

The council recommended `evaluation.*` over `scoring.*` because rubric scoring, safety gates, and bias auditing are all **evaluation-time behaviors**, not just scoring calculations.

```python
from pydantic import BaseModel, Field, field_validator

class RubricConfig(BaseModel):
    """Rubric-based multi-dimensional scoring (ADR-016)."""
    enabled: bool = Field(default=False, validation_alias="RUBRIC_SCORING_ENABLED")
    weights: dict[str, float] = Field(default_factory=lambda: {
        "accuracy": 0.35,
        "completeness": 0.25,
        "conciseness": 0.20,
        "clarity": 0.20,
    })

    @field_validator('weights')
    @classmethod
    def validate_weights(cls, v):
        if v and any(x < 0 for x in v.values()):
            raise ValueError("Weights cannot be negative")
        if v and abs(sum(v.values()) - 1.0) > 0.01:
            raise ValueError("Weights must sum to 1.0")
        return v

class SafetyConfig(BaseModel):
    """Safety gate for harmful content detection (ADR-016)."""
    enabled: bool = Field(default=False, validation_alias="SAFETY_GATE_ENABLED")
    score_cap: float = Field(default=0.0, ge=0.0, le=1.0)

class BiasConfig(BaseModel):
    """Per-session and cross-session bias auditing (ADR-015/018)."""
    audit_enabled: bool = Field(default=False, validation_alias="BIAS_AUDIT_ENABLED")
    persistence_enabled: bool = Field(default=False)
    length_correlation_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    position_variance_threshold: float = Field(default=2.0, ge=0.0)

class EvaluationConfig(BaseModel):
    """Evaluation-time configuration for scoring, safety, and bias."""
    rubric: RubricConfig = Field(default_factory=RubricConfig)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    bias: BiasConfig = Field(default_factory=BiasConfig)
```

**Key Design Decisions:**
- Use `validation_alias` for legacy environment variable compatibility
- Semantic validation (weights sum to 1.0, non-negative values)
- Sensible defaults matching current behavior

### 3. Implementation Plan

```
Pre-Merge:
├── [ ] Announce in team channel: "Merging config modernization"
├── [ ] Add EvaluationConfig to unified_config.py
├── [ ] Migrate all 36 import sites
├── [ ] Run full test suite
├── [ ] Update documentation

The PR Should Include:
├── [ ] Modified: unified_config.py (add EvaluationConfig)
├── [ ] Modified: 36 files with updated imports
├── [ ] Deleted: config.py (or gutted to re-export only)
├── [ ] Modified: CLAUDE.md

Post-Merge:
├── [ ] Notify team: "Migration complete, see ADR-031"
├── [ ] Be available for questions (~1 day)
└── [ ] Done
```

### 4. Environment Variable Compatibility

The only compatibility layer needed is `validation_alias` for environment variables. This ensures CI pipelines and local `.env` files continue to work:

| Legacy Env Var | New Config Path |
|----------------|-----------------|
| `RUBRIC_SCORING_ENABLED` | `evaluation.rubric.enabled` |
| `SAFETY_GATE_ENABLED` | `evaluation.safety.enabled` |
| `BIAS_AUDIT_ENABLED` | `evaluation.bias.audit_enabled` |

### 5. Cleanup `llm_council.yaml`

The YAML file will be updated to match the new schema:

```yaml
council:
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
      score_cap: 0.5
    bias:
      audit_enabled: true
      persistence_enabled: false
```

## Council Review Summary

### Round 1 (Initial Review)
- **Recommendation:** Phased deprecation with shim
- **Rationale:** Protect external consumers, minimize production risk

### Round 2 (Re-Review with Test-Only Context)
- **Recommendation Changed:** Big Bang refactor
- **Rationale:** No external consumers, no production deployment = shim provides zero value
- **Vote:** Unanimous (4/4 models)

### Key Council Insights

1. **Shim adds complexity for zero benefit** in test-only context
2. **`validation_alias` is sufficient** for env var compatibility
3. **"Fail Fast" is better DX** than deprecation warnings for internal teams
4. **Delete `config.py` immediately** to prevent regression

### Council Rankings (Round 2)

| Model | Borda Score |
|-------|-------------|
| openai/gpt-5.2-pro | 0.833 |
| google/gemini-3-pro-preview | 0.5 |
| anthropic/claude-opus-4.5 | 0.333 |
| x-ai/grok-4.1-fast | 0.111 |

## Consequences

### Pros
* Single Source of Truth
* Strong validation (weights sum to 1.0, non-negative) via Pydantic
* Clear documentation generated from schema
* IDE autocomplete and type checking
* Semantic validation catches errors at startup
* No temporary technical debt (shim)
* Clean codebase immediately

### Cons
* Requires refactoring 36 imports (one-time, ~2 hours)
* All developers must pull latest after merge

## Implementation Checklist

- [x] Add `EvaluationConfig` to `unified_config.py`
- [x] Add `validation_alias` for legacy env vars
- [x] Add semantic validators (weights, bounds)
- [x] Migrate evaluation-related import sites (bias_audit.py, bias_persistence.py, bias_aggregation.py, council.py)
- [ ] ~~Delete or gut `config.py`~~ **Deferred** - Non-evaluation imports remain (COUNCIL_MODELS, gateway config, telemetry, etc.)
- [ ] Update `llm_council.yaml` schema
- [x] Update `CLAUDE.md` documentation
- [x] Run full test suite (1898 tests pass)
- [x] Create atomic commits (`ddca934`)

### Implementation Notes

**Scope Clarification:** ADR-031 focused specifically on **evaluation config** (rubric, safety, bias). The full config.py deletion requires migrating ~15 additional files with non-evaluation config (council membership, gateway config, telemetry, etc.) which is deferred to a future effort.

**Files Migrated:**
- `src/llm_council/bias_audit.py` - Uses `get_config().evaluation.bias.*`
- `src/llm_council/bias_persistence.py` - Uses helper functions `_get_bias_*`
- `src/llm_council/bias_aggregation.py` - Uses `_get_bias_store_path()`
- `src/llm_council/council.py` - Uses `eval_config = get_config().evaluation`

**Pattern Used:**
```python
# Helper function pattern (bias_persistence.py)
def _get_bias_persistence_enabled() -> bool:
    try:
        return get_config().evaluation.bias.persistence_enabled
    except Exception:
        return False

# Direct access pattern (council.py)
eval_config = get_config().evaluation
if eval_config.rubric.enabled:
    weights = eval_config.rubric.weights
```
