# Implementation Plan: Phase 3 - Test Suite Centralization Coverage

The goal of this phase is to refactor the `tests/` directory to eliminate hardcoded model identifiers (e.g., `"openai/gpt-4o"`) and replace them with constants from `src/llm_council/model_constants.py`. This ensures that changing a model version in one place updates all test mocks and assertions.

## 🎯 Objectives
- Replace ~900+ occurrences of hardcoded model strings across ~60-120 test files.
- Ensure 100% test pass rate on localized/offline tests.
- Maintain test isolation by using constants for both actual logic and mock setup.

## 🏗️ Batch Strategy

We will process tests in groups to manage the large volume of changes.

### Batch 1: Core & Configuration Tests
Targeting shared test setup and configuration validation.
- `tests/test_unified_config.py`
- `tests/test_model_centralization.py` (Verify it's already updated)
- `tests/test_tier_model_pools.py`
- `tests/test_tier_intersection.py`

### Batch 2: Gateway & Provider Tests
Targeting tests that mock external providers (OpenRouter, Littellm, Ollama).
- `tests/test_gateway_router.py`
- `tests/test_gateway_ollama.py`
- `tests/test_gateway_openrouter.py`
- `tests/test_litellm_adapter.py`
- `tests/test_openrouter_client.py`

### Batch 3: Metadata & Selection Tests
Targeting intelligence and discovery logic.
- `tests/test_discovery.py`
- `tests/test_selection_metadata.py`
- `tests/test_static_registry.py`
- `tests/test_registry.py`

### Batch 4: Feature-Specific Tests
Targeting Audition, Triage, and Reasoning features.
- `tests/test_triage_wildcard.py`
- `tests/test_triage_types.py`
- `tests/test_triage_prompt_optimizer.py`
- `tests/test_shadow_voting.py`
- `tests/test_shadow_integration.py`
- `tests/test_reasoning_tracker.py`

### Batch 5: Remaining Unit & Integration Tests
Refactoring all other files identified by grep search.

---

## 🛠️ Refactoring Pattern

**Before:**
```python
import pytest
from unittest.mock import MagicMock

def test_something():
    mock = MagicMock()
    mock.model = "openai/gpt-4o-mini"
    assert mock.model == "openai/gpt-4o-mini"
```

**After:**
```python
import pytest
from unittest.mock import MagicMock
from llm_council import model_constants

def test_something():
    mock = MagicMock()
    mock.model = model_constants.OPENAI_QUICK
    assert mock.model == model_constants.OPENAI_QUICK
```

---

## ✅ Verification Plan

1. **Static Audit:** Run `grep -rE "(openai|anthropic|google|ollama)/" tests/` to confirm zero hits (excluding comments/docs where appropriate).
2. **Automated Tests:** Run `pytest tests/` after each batch.
3. **Guardrail Test:** Implement `tests/test_centralization_enforcement.py` to regex-scan `src/` and `tests/`.

## ⚠️ Risks
- **Test Fragility:** Some tests might rely on specific string patterns or length.
- **Provider-Specific Logic:** Some tests legacy-mock specific provider IDs that might not perfectly map to a "Tier" constant. In these cases, we use specific version constants like `model_constants.OPENAI_O1`.
