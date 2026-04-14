# Regression Stabilization Rev. 4: Deep Orchestrator Trace

Resolve the final 3 failing tests by fixing critical mock misalignments and ensuring orchestrator status logic is correctly triggered.

## Proposed Changes

### [Component] Council Orchestrator

#### [MODIFY] [council.py](file:///c:/git_projects/llm-council/src/llm_council/council.py)
- **Problem**: telemetry emission still flaking.
- **Fix**: Use `datetime.now(timezone.utc)` (already applied but verify). Ensure `requested_models` is consistently available across all paths.

### [Component] Reliability Tests

#### [MODIFY] [test_council_reliability.py](file:///c:/git_projects/llm-council/tests/test_council_reliability.py)
- **Problem**: `AssertionError: assert 'failed' == 'partial'`.
- **Root Cause**: `stage1_5_normalize_styles` mock was returning an empty list `([], {})`, effectively wiping out all Stage 1 responses and triggering the "no models responded" early exit in `council.py`.
- **Fix**: Update the mock to return valid normalized results (matching the input structure).

### [Component] Telemetry Tests

#### [MODIFY] [test_telemetry_alignment.py](file:///c:/git_projects/llm-council/tests/test_telemetry_alignment.py)
- **Problem**: `mock.send_event.called` is `False`.
- **Root Cause**: Patching `llm_council.telemetry.get_telemetry` does not override the local import in `council.py` (`from llm_council.telemetry import get_telemetry`).
- **Fix**: Revert patch target to `llm_council.council.get_telemetry`.
- **Fix**: Ensure `stage1_5_normalize_styles` is also mocked in this test if needed, or ensure it doesn't return empty results.

## Verification Plan

### Automated Tests
- `python -m pytest tests/test_council_reliability.py tests/test_telemetry_alignment.py -vv`
- Final full suite run: `python -m pytest tests/ -k "not integration"`
