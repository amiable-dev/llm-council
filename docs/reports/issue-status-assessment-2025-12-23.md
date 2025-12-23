# GitHub Issue Status Assessment

**Date:** 2025-12-23
**Scope:** Review of open issues vs. current codebase
**Assessor:** Antigravity

## 1. Executive Summary

A comprehensive review of the 18 open issues in `amiable-dev/llm-council` reveals that the "Local Council" (Ollama/Hardware) features are substantially complete and their tracking issues can be closed. However, the "Connectivity" features (Webhooks, SSE) are in a fragmented state: foundational classes exist and pass tests, but they are not integrated into the runtime execution flow.

## 2. Detailed Assessment by Feature

### A. Local Council (OllamaGateway)
**Metric:** High Readiness (100% Implemented)

| Issue | Title | Expected | Actual Status | Recommendation |
|-------|-------|----------|---------------|----------------|
| **#69** | OllamaGateway: Core | Implementation of `OllamaGateway` class in `gateway/ollama.py` | ✅ **Complete**. Class exists, implements `BaseRouter`, handles errors. | **Close** |
| **#70** | OllamaGateway: Config | Integration with `LiteLLM` and config vars | ✅ **Complete**. `config.py` updated, imports LiteLLM lazily. | **Close** |
| **#71** | Degradation Notices | `QualityDegradationNotice` logic | ✅ **Complete**. Implemented in `ollama.py`. | **Close** |
| **#72** | Hardware Profiles | Hardware dict in config & docs | ✅ **Complete**. `OLLAMA_HARDWARE_PROFILES` exists. | **Close** |
| **#68** | OllamaGateway: TDD | Test suite | ✅ **Complete**. `tests/test_gateway_ollama.py` exists (23KB). | **Close** |

### B. Webhook Infrastructure
**Metric:** Medium Readiness (70% Implemented)

| Issue | Title | Expected | Actual Status | Recommendation |
|-------|-------|----------|---------------|----------------|
| **#74** | Webhooks: Types | `types.py` with Pydantic models | ✅ **Complete**. `src/llm_council/webhooks/types.py` exists. | **Close** |
| **#75** | Webhooks: Dispatcher | `dispatcher.py` with retry/backoff | ✅ **Complete**. Implemented with full logic. | **Close** |
| **#82** | EventBridge Class | `event_bridge.py` mapping class | ⚠️ **Partial**. Class exists and tests PASS, but file is **not exported** in `__init__.py`. | **Keep Open** (fix export) |

### C. Webhook & SSE Integration
**Metric:** Low Readiness (10% Implemented)

| Issue | Title | Expected | Actual Status | Recommendation |
|-------|-------|----------|---------------|----------------|
| **#76** | HTTP API Integration | `/v1/council/run` accepts `webhook` param | ❌ **Missing**. `CouncilRequest` model lacks `webhook` field. | **Keep Open** (High Priority) |
| **#83** | EventBridge Integration | `council.py` uses `EventBridge` | ❌ **Missing**. No reference to EventBridge in `council.py`. Events are emitted to log only. | **Keep Open** (High Priority) |
| **#84** | SSE Real Impl | Replace `_council_runner` placeholder | ❌ **Missing**. File explicitly explicitly marked as placeholder. | **Keep Open** |
| **#77** | SSE Infrastructure | Streaming endpoint | ❌ **Missing**. No streaming endpoint in `http_server.py`. | **Keep Open** |

## 3. Critical Gaps & Next Steps

### 1. The "Orphaned Bridge" Problem
The `EventBridge` class (#82) is a solid implementation of the "Hybrid Pub/Sub" pattern and passes its test suite (`tests/test_event_bridge.py`). However, it is an island.
*   **Gap:** `src/llm_council/webhooks/__init__.py` does not export it.
*   **Action:** Add `EventBridge` to `__all__` in `__init__.py`.

### 2. No Event Egress
The engine (`council.py`) executes the logic but keeps its events to itself (logging them only).
*   **Gap:** `run_council_with_fallback` needs to be dependency-injected with an `EventBridge` or `Dispatcher`, or the `emit_layer_event` function needs a hook to forward events to the bridge.
*   **Action:** Implement Issue #83 (Wiring).

### 3. Missing API Surface
Users cannot actually use the webhooks because the API doesn't let them specify a URL.
*   **Gap:** `http_server.py` → `CouncilRequest` is missing the `webhook: WebhookOptions` field.
*   **Action:** Implement Issue #76.

## 4. Conclusion
The team has successfully delivered the "Kernel" (Ollama support) but stopped short of delivering the "IO" (Webhooks/SSE). The code for the IO *mechanism* (Dispatcher/Bridge) exists, but the *wires* connecting it to the kernel are unset.

**Immediate Recommendation:**
1.  **Close** issues #68, #69, #70, #71, #72, #74, #75.
2.  **Focus** sprint on wiring #82 (fix export), #83 (integrate), and #76 (API).
