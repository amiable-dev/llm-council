# Bug Fix 003: Implementation Plan (Incomplete Type Hints)

## 04092026-1502

## Problem Analysis
The function `_merge_dicts` in `unified_config.py` is used to deep-merge dictionary overrides (from Environment Variables or YAML) into the base configuration. The current type hint `Dict` is a generic that requires type parameters in strict Python 3.10+ environments. Using it without parameters causes the type checker to fail.

## First Principles Thinking
- **Truth 1**: Python 3.9+ allows the use of the native `dict` class in type hints, which is implicitly `dict[Any, Any]` when no parameters are provided.
- **Truth 2**: The `typing.Dict` generic is deprecated in favor of the native `dict` for readability and modern standards.
- **Conclusion**: Replacing the non-indexed `Dict` with the native `dict` is the most robust and future-proof way to satisfy the type checker while maintaining the existing merge logic.

## Proposed Changes
- **Target File**: `src/llm_council/unified_config.py`
- **Location**: Line 1083
- **Change**: 
    Original: `def _merge_dicts(base: Dict, override: Dict) -> Dict:`
    New: `def _merge_dicts(base: dict, override: dict) -> dict:`

## Verification Plan
1.  **Static**: Run `uv run ruff check` and `uv run mypy`.
2.  **Runtime**: Run `uv run pytest tests/test_unified_config.py` to ensure the merge logic still works.
