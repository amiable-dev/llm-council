# Implementation Plan (V2): 100% Model Centralization Coverage

This plan replaces the previous version with a comprehensive list of all remaining literals found during a project-wide audit. The goal is to move from "partial centralization" to a "Sovereign Constant State" where **zero** provider strings (e.g., `openai/`) exist outside of [model_constants.py](file:///c:/git_projects/llm-council/src/llm_council/model_constants.py).

## Audit Findings: The "Centralization Gap"

> [!WARNING]
> **Drift Alert:** Although the YAML is clean, the internal Python logic still contains **942 hardcoded literals**. If a model like `gpt-4o-mini` is deprecated by the provider, we currently have to edit **40+ files** instead of one.

## Proposed Changes

We will execute this in 5 logical batches to ensure CI stability at every step.

---

### Batch 1: Core Domain Contracts
These files define the "hard fallbacks" used when configuration fails or model intelligence is off.

#### [MODIFY] [tier_contract.py](file:///c:/git_projects/llm-council/src/llm_council/tier_contract.py)
*   **Gap:** Contains `_DEFAULT_TIER_MODEL_POOLS` and `TIER_AGGREGATORS` static dictionaries with hardcoded strings.
*   **Fix:** Replace strings with `model_constants.OPENAI_QUICK`, etc.

#### [MODIFY] [mcp_server.py](file:///c:/git_projects/llm-council/src/llm_council/mcp_server.py)
*   **Gap:** literals in `CONFIDENCE_CONFIGS` and fallback health-check models.
*   **Fix:** Import and use centralized constants.

#### [MODIFY] [unified_config.py](file:///c:/git_projects/llm-council/src/llm_council/unified_config.py)
*   **Gap:** Residual literals in Pydantic validators and docstring examples.
*   **Fix:** Ensure all `Field` defaults point to constants.

---

### Batch 2: Gateway & Connectivity Layer
Ensures that routers and provider adapters are not "guessing" model paths.

#### [MODIFY] Gateways
- [gateway/openrouter.py](file:///c:/git_projects/llm-council/src/llm_council/gateway/openrouter.py)
- [gateway/requesty.py](file:///c:/git_projects/llm-council/src/llm_council/gateway/requesty.py)
- [gateway/router.py](file:///c:/git_projects/llm-council/src/llm_council/gateway/router.py)
- [gateway/direct.py](file:///c:/git_projects/llm-council/src/llm_council/gateway/direct.py)
- [gateway/ollama.py](file:///c:/git_projects/llm-council/src/llm_council/gateway/ollama.py)
- [gateway/types.py](file:///c:/git_projects/llm-council/src/llm_council/gateway/types.py)

---

### Batch 3: Metadata & Selection Engine
The most complex refactor. These files handle the intelligence of which model to pick.

#### [MODIFY] Metadata Subsystem
- [metadata/static_registry.py](file:///c:/git_projects/llm-council/src/llm_council/metadata/static_registry.py)
- [metadata/litellm_adapter.py](file:///c:/git_projects/llm-council/src/llm_council/metadata/litellm_adapter.py)
- [metadata/registry.py](file:///c:/git_projects/llm-council/src/llm_council/metadata/registry.py)
- [metadata/discovery.py](file:///c:/git_projects/llm-council/src/llm_council/metadata/discovery.py)
- [metadata/types.py](file:///c:/git_projects/llm-council/src/llm_council/metadata/types.py)

---

### Batch 4: Observability & Audition
Monitoring and new model onboarding.

#### [MODIFY] Subsystems
- [audition/tracker.py](file:///c:/git_projects/llm-council/src/llm_council/audition/tracker.py)
- [audition/types.py](file:///c:/git_projects/llm-council/src/llm_council/audition/types.py)
- [reasoning/tracker.py](file:///c:/git_projects/llm-council/src/llm_council/reasoning/tracker.py)
- [observability/metrics_adapter.py](file:///c:/git_projects/llm-council/src/llm_council/observability/metrics_adapter.py)

---

### Batch 5: Test Suite Stabilization
Massive search-and-replace across 60+ test files.

#### [MODIFY] `tests/*`
*   **Strategy:** Replace literals used in `pytest.mark.parametrize` and `MagicMock` calls with their constant equivalents.
*   **Goal:** Ensure that changing a model in `model_constants.py` automatically updates all test mocks.

---

## Final Verification: The Nuclear Audit

### [NEW] `tests/test_centralization_enforcement.py`
A new test that regex-scans the entire `src/` directory. 
*   **Logic:** If any string matches `(openai|anthropic|google|...)/` and the file is NOT `model_constants.py`, the build **must fail**.

## Verification Plan

### Automated Tests
- `uv run pytest tests/` after each batch.
- Running the new `test_centralization_enforcement.py` at the very end to prove 100% coverage.

### Manual Verification
- `llm-council health` to ensure models are correctly resolved via constants.
