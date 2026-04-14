# Regression Stabilization Rev. 2: Deep Mock Compatibility

Resolve the 4 persistent regressions identified in the second stabilization pass. These failures are primarily due to module-level imports in Python bypassing module-level patches (classic mocking pitfall) and a Python 3.10 datetime type mismatch.

## Proposed Changes

### [Component] Reliability Tests

#### [MODIFY] [test_council_reliability.py](file:///c:/git_projects/llm-council/tests/test_council_reliability.py)
- **Problem**: `AssertionError: assert 'failed' == 'partial'`
- **Fix**: Patch `llm_council.stages.stage1._get_council_models` instead of `llm_council.config_helpers._get_council_models` because `stage1.py` uses `from ...config_helpers import _get_council_models`.
- **Logic**: Ensure `run_stage1` finds mock models so it doesn't trigger the "early failure" exit in `run_full_council`.

### [Component] Config & Security Tests

#### [MODIFY] [test_secure_key_handling.py](file:///c:/git_projects/llm-council/tests/test_secure_key_handling.py)
- **Problem**: `AssertionError: assert 'unknown' == 'environment'`
- **Fix**: Patch `llm_council.mcp_server.get_key_source` directly.
- **Problem**: `DEEPSEEK_R1` check in `test_reasoning_tier_env_override` might be flaking if constants are not reloaded.
- **Fix**: Use `patch.object(mc, "DEEPSEEK_R1", "deepseek/deepseek-r1")` for absolute isolation.

### [Component] Telemetry

#### [MODIFY] [test_telemetry_alignment.py](file:///c:/git_projects/llm-council/tests/test_telemetry_alignment.py)
- **Problem**: `mock.send_event.called` is `False`.
- **Fix**: Verify `council.py` telemetry call is using the correctly patched module reference. Ensure `run_council_with_fallback` is calling the patched `run_full_council` if it was imported separately. (Actually, verify `get_telemetry` patch target).

### [Component] Context Tests (Verification)

#### [MODIFY] [test_context.py](file:///c:/git_projects/llm-council/tests/unit/verification/test_context.py)
- **Problem**: `TypeError: tzinfo argument must be None or of a tzinfo subclass, not type 'type'`
- **Fix**: Change `datetime.now(UTC)` to `datetime.now(timezone.utc)`. The test was using the `timezone` *class* instead of the `timezone.utc` *instance* because of an incorrect alias/import usage.

## Verification Plan

### Automated Tests
- `python -m pytest tests/test_council_reliability.py tests/test_secure_key_handling.py tests/test_telemetry_alignment.py tests/test_tier_model_pools.py tests/unit/verification/test_context.py -vv`
- Final full suite run: `python -m pytest tests/ -k "not integration"`
