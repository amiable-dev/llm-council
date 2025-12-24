# ADR-026 Implementation Gap Analysis (Re-Review)

**Date:** 2025-12-24
**Auditor:** Antigravity
**Scope:** Deep-Dive Codebase Review against ADR-026

## 1. Executive Summary

**Status:** ⚠️ **PARTIALLY IMPLEMENTED** (High Risk of Runtime Error)

A second, deeper review reveals a more nuanced state than "Missing". The "Sovereign" layer is perfect. The "Intelligence" layer exists but is incomplete ("Hollow"), and the "Reasoning" layer contains a **critical crash risk**.

- **Blocking Conditions:** ✅ **COMPLETE** (Offline Safe)
- **Phase 1 (Dynamic Intelligence):** ⚠️ **HOLLOW** (Wired but using static estimates)
- **Phase 2 (Reasoning):** ❌ **BROKEN** (`reasoning.py` missing, import will crash)
- **Phase 3 (Performance):** ✅ **COMPLETE** (Tracker implemented)

## 2. Detailed Verification

### A. Blocking Conditions (Sovereign Metadata)
**Status:** ✅ **Verified Complete**
The system correctly prioritizes offline safety. `StaticRegistryProvider` and `registry.yaml` are robust.

### B. Phase 1: Dynamic Intelligence
**Status:** ⚠️ **Hollow Implementation**
The infrastructure exists but isn't fully "intelligent" yet.

| Component | Status | Finding |
|-----------|--------|---------|
| **OpenRouter Client** | ✅ Present | `src/llm_council/metadata/openrouter_client.py` |
| **Provider Factory** | ✅ Present | `src/llm_council/metadata/__init__.py` |
| **Selection Logic** | ⚠️ **Mocked** | `selection.py` uses `_estimate_quality_score` (hardcoded regex) instead of real metadata. |
| **Context Awareness** | ❌ **TODO** | `_meets_context_requirement` has a `TODO` and returns `True` always. |

### C. Phase 2: Reasoning Parameters
**Status:** ❌ **CRITICAL FAILURE**

The file `src/llm_council/tier_contract.py` attempts to import `ReasoningConfig` from `.reasoning` when intelligence is enabled:
```python
if _is_model_intelligence_enabled():
    from .reasoning import ReasoningConfig  # <--- CRASH: File does not exist
```
**Impact:** Enabling `LLM_COUNCIL_MODEL_INTELLIGENCE=true` will cause the application to crash immediately.

### D. Phase 3: Internal Performance Tracker
**Status:** ✅ **Verified Complete**
Unexpectedly, this advanced phase is fully implemented in `src/llm_council/performance/`, including `tracker.py` and JSONL storage logic.

## 3. Discrepancy Findings

The implementation is "front-heavy" (Metadata) and "back-heavy" (Performance Tracker), but the middle "Intelligence/Reasoning" layer is fragile.

**Files Missing:** `src/llm_council/reasoning.py`

## 4. Recommendations

1.  **Immediate Fix:** Create `src/llm_council/reasoning.py` to prevent crashes when intelligence is enabled.
2.  **Fill the Hollow:** Update `src/llm_council/metadata/selection.py` to use actual data from `DynamicMetadataProvider` instead of regex estimates.
3.  **Release Control:** Do NOT enable `LLM_COUNCIL_MODEL_INTELLIGENCE` by default until `reasoning.py` is fixed.
