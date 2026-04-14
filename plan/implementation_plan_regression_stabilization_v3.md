# Regression Stabilization Rev. 3: Orchestrator Status Logic

Resolve the 3 persistent regressions by fixing the orchestrator status logic in `council.py` and aligning the telemetry mock.

## Proposed Changes

### [Component] Council Orchestrator

#### [MODIFY] [council.py](file:///c:/git_projects/llm-council/src/llm_council/council.py)
- **Problem**: `metadata["status"]` is hardcoded to `"complete"` at the end, causing `test_run_council_with_fallback_partial_on_timeout` to fail (expected `partial`).
- **Fix**: 
    1. Capture `requested_models` at the start.
    2. At the end, check if `len(metadata["models"]) < requested_models`.
    3. If so, set status to `"partial"`, otherwise `"complete"`.
    4. Ensure `metadata["status"]` is correctly propagated to telemetry.

### [Component] Reliability Tests

#### [MODIFY] [test_council_reliability.py](file:///c:/git_projects/llm-council/tests/test_council_reliability.py)
- **Problem**: Mocks returned 1 model for a test that expected 2 (one timeout).
- **Fix**: Ensure mocks consistently return `["a", "b"]` when simulating a partial failure of "b".

### [Component] Telemetry Tests

#### [MODIFY] [test_telemetry_alignment.py](file:///c:/git_projects/llm-council/tests/test_telemetry_alignment.py)
- **Problem**: `mock.send_event.called` is `False`.
- **Fix**: The orchestrator fix (status logic) will ensure the logic reaches the telemetry block without crashing. I will also ensure the `get_telemetry` patch is applied to `llm_council.telemetry.get_telemetry` to be universally effective.

## Verification Plan

### Automated Tests
- `python -m pytest tests/test_council_reliability.py tests/test_telemetry_alignment.py -vv`
- Final full suite run: `python -m pytest tests/ -k "not integration"`
