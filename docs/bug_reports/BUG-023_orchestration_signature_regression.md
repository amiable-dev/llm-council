# Bug Report: BUG-023 Orchestration Signature Regression

## Description
The modularization refactor of the LLM Council pipeline (Issue #28) introduced breaking changes to the core `run_full_council` orchestrator in `src/llm_council/council.py`. This has caused the CLI (`query.py`) and the HTTP Server (`http_server.py`) to fail with `TypeError` and structure mismatch errors.

## Root Cause Analysis
1. **Parameter Rename**: The `models` parameter was renamed to `council_models` in `run_full_council`, but callers still pass `models=`, resulting in `TypeError: unexpected keyword argument 'models'`.
2. **Return Type Swap**: The function previously returned a 4-tuple of `(stage1, stage2, stage3, metadata)`. It was changed to return `(response_text, metadata, label_mapping, rankings)`, causing unpacking errors and logic failures in all downstream callers.

## Affected Components
- `src/llm_council/council.py` (Orchestration Layer)
- `src/llm_council/http_server.py` (REST API)
- `query.py` (CLI Interface)
- `src/llm_council/evaluation.py` (Benchmarking)
- `src/llm_council/triage/shadow_sampling.py` (Auto-selection logic)

## Verification Strategy
- **Reproduction Test**: Create a new integration test `tests/test_bug_023_orchestration_parity.py` that specifically exercises `run_full_council` with the legacy signature (passing `models=` and expecting the original 4-tuple).
- **CLI Verification**: Run `uv run python query.py "Test query" --confidence quick` and verify it completes without `TypeError`.
- **HTTP Verification**: Run a mock request to the `/v1/council/run` endpoint and verify the response JSON matches the `CouncilResponse` schema.
