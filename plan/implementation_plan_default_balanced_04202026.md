# Implementation Plan - Change Default Tier to 'balanced'

Change the default confidence tier from `high` to `balanced` across the configuration system and update all dependent tests. This will reduce default query latency and cost while maintaining a consistent experience.

## User Review Required

> [!IMPORTANT]
> This is a breaking change for users/tests that rely on the default being the highest-quality models. Default query response times will decrease, and costs will be lower.

## Proposed Changes

### Core Configuration

#### [MODIFY] [unified_config.py](file:///c:/git_projects/llm-council/src/llm_council/unified_config.py)
- Update `TierConfig.default` value from `"high"` to `"balanced"`.
- Update `CouncilConfig.models` default factory to use `BALANCED` constants:
    - `model_constants.OPENAI_BALANCED`
    - `model_constants.GOOGLE_BALANCED`
    - `model_constants.ANTHROPIC_BALANCED`
    - `model_constants.QWEN_BALANCED`

### Tests (Breaking Changes)

Multiple test files need updates to reflect the new default:

#### [MODIFY] [test_unified_config.py](file:///c:/git_projects/llm-council/tests/test_unified_config.py)
- Update assertions where `config.tiers.default == "high"` to `"balanced"`.
- Update `test_load_config_with_nonexistent_file` and others.

#### [MODIFY] [test_verify_tier_support.py](file:///c:/git_projects/llm-council/tests/test_verify_tier_support.py)
- Update tests that verify default tool behavior (previously assumed `high`).

#### [MODIFY] [test_tier_model_pools.py](file:///c:/git_projects/llm-council/tests/test_tier_model_pools.py)
- Update `test_high_tier_is_default_equivalent` (rename or update logic to check balanced).

#### [MODIFY] [test_frontier_fallback.py](file:///c:/git_projects/llm-council/tests/test_frontier_fallback.py)
- Update `test_default_fallback_tier_is_high` (unless frontier specifically should still fallback to high).

---

## Verification Plan

### Automated Tests
- Run full test suite: `uv run pytest tests/`
- Specifically monitor:
    - `tests/test_unified_config.py`
    - `tests/test_verify_tier_support.py`
    - `tests/test_tier_model_pools.py`

### Manual Verification
- Verify `llm-council config dump` shows the new defaults.
- Verify through the MCP tool that a query without `confidence` specified uses the balanced models in logs.
