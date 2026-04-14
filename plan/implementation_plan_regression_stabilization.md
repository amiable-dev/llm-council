# Final Regression Stabilization: Model Centralization

Resolve the 7 specific regressions identified in the project-wide test suite following the centralization of LLM model identifiers.

## Proposed Changes

### [Component] Model Constants

#### [MODIFY] [model_constants.py](file:///c:/git_projects/llm-council/src/llm_council/model_constants.py)
- Support `DEEPSEEK_R1` constant used in enhanced reasoning tier tests.

### [Component] Reliability Tests

#### [MODIFY] [test_council_reliability.py](file:///c:/git_projects/llm-council/tests/test_council_reliability.py)
- Update mock patching to target `config_helpers._get_council_models` instead of legacy `council.COUNCIL_MODELS`.
- Ensure progress callback tests account for the newly modularized stage boundaries.

### [Component] Config & Security Tests

#### [MODIFY] [test_secure_key_handling.py](file:///c:/git_projects/llm-council/tests/test_secure_key_handling.py)
- Update `TestHealthCheckKeySource` to patch `unified_config.get_key_source` and `unified_config._get_api_key`.

#### [MODIFY] [test_tier_model_pools.py](file:///c:/git_projects/llm-council/tests/test_tier_model_pools.py)
- Update `test_reasoning_tier_env_override` to use the now-available `mc.DEEPSEEK_R1`.

### [Component] Telemetry & Context

#### [MODIFY] [test_telemetry_alignment.py](file:///c:/git_projects/llm-council/tests/test_telemetry_alignment.py)
- Fix session_id propagation check in `run_council_with_fallback`.

#### [MODIFY] [test_context.py](file:///c:/git_projects/llm-council/tests/unit/verification/test_context.py)
- Relax timestamp precision check for Python 3.10+ compatibility.

## Verification Plan

### Automated Tests
- `python -m pytest tests/test_council_reliability.py tests/test_secure_key_handling.py tests/test_telemetry_alignment.py tests/test_tier_model_pools.py tests/unit/verification/test_context.py`
- Final full suite run: `python -m pytest tests/ -k "not integration"`
