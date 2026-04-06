# Implementation Plan - Model Selection Stability (Issue #8)

## 1. Problem Statement
The LLM Council's original `query_model` logic sometimes defaulted to hardcoded "phantom" models (expensive or unavailable preview models) even when they were not listed in the user's `llm_council.yaml`. This led to unexpected billing and query timeouts.

## 2. Solution Summary
- **Global Config Patching**: Modified `query.py` to dynamically load the selected tier's model pool from `unified_config.py` and mutate the global `config.council.models` object before calling the runner.
- **Enforce Local Registry**: Ensured the system respects the `model_intelligence: enabled: false` flag strictly.

## 3. Implementation Details
- `query.py`: Patched the `run_full_council` entry point to enforce the user's specified model pool based on requested confidence level.

## 4. Verification Strategy
- **Log Verification**: Run the query script with the `--details` flag and confirm that *only* the models listed in the YAML participated in Stage 1 ideation.
