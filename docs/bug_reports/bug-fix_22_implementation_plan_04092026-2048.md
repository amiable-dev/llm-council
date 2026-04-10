# Implementation Plan: Fix Adversarial Configuration Persistence (BUG-022)

## Basic Principles
The configuration system in this council is designed to be a unified, hierarchical source of truth. When a YAML file is loaded, it must be mapped entirely into the root of the `UnifiedConfig` model. If only a sub-section is passed to the constructor, the root model's fields will remain as defaults, causing settings in the YAML to be effectively ignored. 

To fix this, we must ensure the entire configuration dictionary is passed to the top-level parser. Furthermore, the CLI layer should avoid relying on global state mutation and instead pass explicit parameters to the orchestrator to maximize deterministic behavior.

## Proposed Changes

### 1. Configuration Layer: `unified_config.py`
- Modify `load_config()` to pass the entire `raw_config` dictionary (after environment variable substitution) to the `UnifiedConfig` constructor.
- This ensures that keys like `council: { adversarial_mode: true }` are correctly nested and validated by Pydantic.

### 2. CLI Layer: `query.py`
- Update the `run_full_council()` call in the main loop to explicitly pass `models=target_models`.
- This ensures the orchestrator use the exact models selected by the tier logic, rather than pulling from the global config again.

## Verification Logic
1. Create a unit test `tests/test_bug_adversarial_config.py`.
2. Mock `yaml.safe_load` to return a dictionary with `council.adversarial_mode: true`.
3. Verify that `get_config().council.adversarial_mode` returns `True`.
4. Run an integration test call to `run_full_council` with this config and verify that the Stage 1B (Devil's Advocate) execution logic is triggered.
