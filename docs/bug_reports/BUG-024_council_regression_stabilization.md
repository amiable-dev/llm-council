# Bug Report: BUG-024 Council Integration Regressions

## 1. Description
Following the modularization of the LLM Council into a 3-stage architecture (PR #28), several regressions were identified in the orchestration layer and webhook integration. Key issues included a missing enum member causing `AttributeError`, an uninitialized `EventBridge` causing `RuntimeError`, and test failures in ADR-040 due to mock-patching discrepancies.

## 2. Root Cause Analysis
- **Missing Enum**: `L3_COUNCIL_ERROR` was used in `council.py` but not defined in `LayerEventType` (contracts).
- **Uninitialized Bridge**: The `EventBridge` was instantiated but its background worker (`start()`) was never awaited in the `run_full_council` facade.
- **Webhook Mapping Gap**: `L3_COUNCIL_ERROR` was missing from the `LAYER_TO_WEBHOOK_MAPPING`, preventing error notifications from reaching consumers.
- **Mock Over-Patching**: Tests in `test_adr040_timeout_guardrails.py` were patching `llm_council.council._get_council_models`, but the stage 2 components (now in `stages.stage2`) were using the reference from their own module or imported via `config_helpers`.

## 3. Impact
- **Orchestration Crash**: Any attempt to run a council session would fail if the EventBridge was enabled.
- **Silent Failures**: Council errors were not being propagated to external webhook consumers.
- **Test Suite instability**: ADR-040 and Triage integration tests were failing, blocking CI/CD.

## 4. Verification Strategy
- **Reproduction**: Run `tests/test_webhook_integration.py` and observe `RuntimeError` and `AttributeError`.
- **Reproduction (ADR-040)**: Run `tests/test_adr040_timeout_guardrails.py` and observe `AssertionError` in `test_stage2_defaults_to_council_models_when_none`.
- **Fix Verification**:
    - Run full webhook integration suite (11 tests).
    - Run ADR-040 suite (31 tests).
    - Run Triage integration suite (12 tests).
    - Run all integration tests (126 tests).

## 5. Status
- Resolved. All tests passing 100%.
