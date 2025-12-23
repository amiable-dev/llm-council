# ADR-025 Implementation Review & Gap Analysis

**Date:** 2025-12-23
**Status:** In Progress / Partially Complete
**Reviewer:** Antigravity

## 1. Executive Summary

The alignment review of ADR-025(a) against the codebase reveals a mixed state of implementation. The core "Local Council" capabilities (OllamaGateway) and the required configuration refactoring (Supplementary Review) have been implemented with high fidelity. However, the connectivity layer—specifically Webhooks and SSE Streaming—is functionally incomplete. While the infrastructure code exists (dispatchers, formatters), it has not been wired into the core `council.py` execution engine.

**Overall Readiness:** 60%

## 2. Component Assessment

| Component | Status | Alignment | Notes |
|-----------|--------|-----------|-------|
| **OllamaGateway** | ✅ Complete | High | Fully implemented via LiteLLM wrapper; includes degradation notices and hardware profiles. |
| **Configuration** | ✅ Complete | High | `unified_config.py` updated; `config.py` deprecation bridge implemented; matches Supplementary Review requirements. |
| **Webhooks** | ⚠️ Partial | Medium | Dispatcher & HMAC auth logic exists (`llm_council.webhooks`), but `council.py` never triggers them. |
| **SSE Streaming** | ❌ Missing | Low | `_council_runner.py` is a placeholder; `OllamaGateway` "streams" entire response at once; `council.py` cannot yield granular events. |
| **Degradation Notices**| ✅ Complete | High | Logic correctly identifies local models and attaches hardware warnings. |

## 3. Detailed Gap Analysis

### Gap 1: Webhook Integration (Critical)
**Requirement:** "P1: Implement event-based webhook system with HMAC authentication"
**Finding:** The webhook infrastructure is built (`src/llm_council/webhooks/dispatcher.py`, `hmac_auth.py`), but it is orphaned. The core execution engine (`src/llm_council/council.py`) emits `LayerEvents` for internal observability but has no mechanism to dispatch these to configured webhooks. The webhook configuration exists but is effectively unused at runtime.

### Gap 2: SSE Streaming & Real-Time Events (Critical)
**Requirement:** "P1: Implement SSE for real-time token streaming"
**Finding:**
1.  **Placeholder Code:** `src/llm_council/webhooks/_council_runner.py` is explicitly marked as a "placeholder implementation" with static yield statements.
2.  **No Event Generator:** `council.py` execution (`run_council_with_fallback`) is strictly `async def` (returning a final Dict) and does not support an `AsyncIterator` mode required for SSE.
3.  **Fake Streaming:** `OllamaGateway.complete_stream` simply awaits the full response and yields it as one chunk, defeating the purpose of token-level streaming.

### Gap 3: Event Bridge Missing
**Requirement:** `council.started`, `council.stage1.complete`, etc.
**Finding:** While `LayerEventType` definitions exist in `layer_contracts.py`, there is no "bridge" or listener system that subscribes to these layer events and forwards them to the `WebhookDispatcher`.

## 4. Recommended Action Plan

To close these gaps and achieve full ADR-025 adherence, the following actions are recommended:

### Phase 1: Wiring the Events (High Priority)
1.  **Create Event Listener Bridge:** Implement a subscriber in `council.py` or a new `runtime.py` that listens for specific `LayerEventType`s and queues them for webhook dispatch.
2.  **Integrate Webhook Dispatcher:** Modify `run_council_with_fallback` to accept a `WebhookDispatcher` instance (or initialize one from config) and flush events to it asynchronously.

### Phase 2: Implementing Real Streaming (Medium Priority)
1.  **Refactor Council Execution:** Refactor `run_council_with_fallback` to optionally return an `AsyncGenerator` that yields events in real-time.
2.  **Fix Gateway Streaming:** Update `OllamaGateway.complete_stream` to use LiteLLM's `stream=True` argument and yield chunks properly.

### Phase 3: Final Integration
1.  **Replace Placeholder:** Rewrite `_council_runner.py` to actually call the new streaming-capable council function.
2.  **Verify End-to-End:** Create an integration test that spins up the `http_server` and verifies that SSE events are received and valid.

## 5. Conclusion

The "hard part" (local model integration and configuration architecture) is well-executed. The "connecting glue" (webhooks/SSE) was likely mocked or scoped out but never fully integrated. Prioritize **Gap 1** (Webhooks) as it is a core P1 deliverable that is currently non-functional.
