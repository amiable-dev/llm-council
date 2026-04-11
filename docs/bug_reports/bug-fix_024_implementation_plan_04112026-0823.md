# Bug Fix 024: Implementation Plan - Council Regression Stabilization

## 1. Basic Truths (First Principles)
- **Enum Integrity**: A system using typed enums for orchestration MUST have all possible runtime event types defined in its contract to avoid `AttributeError`.
- **Lifecycle Management**: Background workers (like an EventBridge) MUST be explicitly started before being utilized to ensure message queues and listeners are active.
- **Dependency Isolation**: Modular components moved to different namespaces MUST have their dependencies (like configuration helpers) correctly resolved or re-linked to maintain behavior.
- **Contract Matching**: External integration points (hooks) MUST have explicit mappings for all critical internal events to ensure correct transformation and delivery.

## 2. Engineering Approach
### Fix 1: Contracts & Enums
- Add `L3_COUNCIL_ERROR` to the `LayerEventType` enum in `src/llm_council/layer_contracts.py`.
- This ensures the orchestrator can emit error events without failing on missing attributes.

### Fix 2: Lifecycle Management
- In `src/llm_council/council.py`, specifically within the `run_full_council` facade, call `await event_bridge.start()` immediately after instantiation.
- This ensures the `EventBridge` is ready to receive and process events.

### Fix 3: Webhook Mapping
- Update `src/llm_council/webhooks/event_bridge.py` mapping to include `LayerEventType.L3_COUNCIL_ERROR`, directing it to `WebhookEventType.ERROR`.

### Fix 4: Test Environment Compatibility
- Update `tests/test_adr040_timeout_guardrails.py` to patch `llm_council.council.COUNCIL_MODELS` directly.
- Use the `_check_patched_attr` mechanism in `config_helpers.py` to ensure Stage 2 picks up these mock values regardless of which module it is executing from.

## 3. Risk Assessment
- Low risk for Fix 1-3 as they are additive and restore missing logic.
- Fix 4 is purely test-side and ensures the test reflects the new modular structure.
