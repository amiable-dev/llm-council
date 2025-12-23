# ADR-026 Implementation Gap Analysis

**Date:** 2025-12-23
**Auditor:** Antigravity
**Scope:** Codebase Review against ADR-026 (Dynamic Model Intelligence)

## 1. Executive Summary

**Status:** ⚠️ **PARTIALLY IMPLEMENTED**

The "Blocking Conditions" required for approval (Sovereign Metadata Layer) are **fully implemented** and robust. However, the "Phase 1" dynamic features (Live OpenRouter Integration) are **completely missing**, despite the ADR implying they are part of the current release phase.

The system is currently in a safe, offline-capable state but lacks the dynamic intelligence promised by the ADR title.

## 2. Detailed Verification

### A. Blocking Conditions (Sovereign Metadata)
**Status:** ✅ **COMPLETE**

| Requirement | Evidence | Location |
|-------------|----------|----------|
| **Metadata Protocol** | `MetadataProvider` protocol exists | `src/llm_council/metadata/protocol.py` |
| **Static Registry** | `StaticRegistryProvider` implemented | `src/llm_council/metadata/static_registry.py` |
| **Offline Mode** | `LLM_COUNCIL_OFFLINE` logic exists | `src/llm_council/metadata/offline.py` |
| **Bundled Data** | `registry.yaml` contains 30+ models | `src/llm_council/models/registry.yaml` |
| **LiteLLM Fallback** | Adapter implemented & integrated | `src/llm_council/metadata/litellm_adapter.py` |

### B. Dynamic Intelligence (Phase 1)
**Status:** ❌ **MISSING**

The following components described in the ADR are absent:

1.  **Dynamic Client:** No `src/llm_council/intelligence` directory.
2.  **OpenRouter Client:** `src/llm_council/intelligence/openrouter.py` does not exist.
3.  **Caching:** `ModelIntelligenceCache` is not implemented.
4.  **Configuration:** `unified_config.py` has no `model_intelligence` section.

### C. Integration Points
**Status:** ❌ **MISSING**

The integration code examples in the ADR are not present in the codebase:

1.  **Tier Selection:** `TierContract` (src/llm_council/tier_contract.py) still uses static `TIER_MODEL_POOLS` from `config.py`. It does NOT call `model_intelligence.select_tier_models()`.
2.  **Routing:** No modifications to `not_diamond.py` or gateway logic to use dynamic metadata.

## 3. Discrepancy Findings

The ADR states "Implementation: 2025-12-23 (Blocking Conditions 1-3)". It seems the team strictly interpreted this to *only* mean the blocking conditions, deferring the actual "Intelligence" features (Phase 1) to a later sprint, despite sections of the ADR implying Phase 1 was "APPROVED" for this release.

## 4. Recommendations

1.  **Acknowledge Sovereignty Win:** The system is robustly offline-capable now, which was the Council's primary concern.
2.  **Schedule Phase 1:** Create tickets to implement `src/llm_council/intelligence` and wire it into `unified_config.py` and `TierContract`.
3.  **Update Configuration:** The `unified_config.py` schema needs to be updated to include the `model_intelligence` section defined in the ADR.
