# Bug Report: Adversarial Mode Configuration Ignored

## Description
When `adversarial_mode: true` is set in `llm_council.yaml`, the orchestrator fails to trigger the Devil's Advocate (Stage 1B) phase during CLI queries unless the `--adversary` flag is explicitly passed.

## Root Cause Analysis
### 1. Incorrect Config Parsing
In `src/llm_council/unified_config.py:load_config()`, the code extracts the `council` section from the raw YAML dictionary and passes only that section to the `UnifiedConfig` constructor. 
```python
council_config = raw_config.get("council", {})
return UnifiedConfig(**council_config)
```
This is incorrect because `UnifiedConfig` expects the full configuration dictionary (containing keys like `tiers`, `triage`, and `council`). By passing only the `council` sub-dictionary, the settings inside it are misaligned or ignored, and all other configuration sections revert to their defaults.

### 2. Omitted CLI Model Propagation
In `query.py`, the selected models for a confidence tier (e.g., `quick`, `balanced`) are identified but not explicitly passed to `run_full_council`. While the code attempts to modify the global config singleton, this is less robust than explicit parameter passing.

## Verification Strategy
### Reproduction Test
1. Create a `tests/test_bug_adversarial_config.py` that mocks a YAML config with `adversarial_mode: true`.
2. Mock the `query_model_with_status` calls for Stage 1A and Stage 1B.
3. Assert that Stage 1B (Devil's Advocate) is called.

### Manual Verification
Execute `uv run python query.py "test query" --confidence quick` and verify the output contains `[*] Stage 1B: Devil's Advocate (...) is auditing responses`.
