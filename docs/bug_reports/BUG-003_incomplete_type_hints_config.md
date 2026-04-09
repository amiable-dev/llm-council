# BUG-003: Incomplete Type Hints in Unified Config

## Status
- **Priority**: Medium (Fixes IDE Red Status)
- **Status**: Identified
- **Date**: 2026-04-09

## Description
The `unified_config.py` module contains a utility function `_merge_dicts` that uses the generic `Dict` type hint without providing type arguments. This causes a terminal error in IDEs (Pylance/MyPy) because generics must be explicitly typed (e.g., `Dict[Any, Any]`) or replaced with the native `dict` type available in Python 3.9+.

## Root Cause
- **File**: `src/llm_council/unified_config.py`
- **Line**: 1083
- **Logic**: `def _merge_dicts(base: Dict, override: Dict) -> Dict:` uses `Dict` as a raw type instead of a generic.

## Impact
- **Developer Experience**: The file is marked as "Red" in the IDE, obscuring real syntax or runtime errors.
- **Maintenance**: Type checkers cannot verify the safety of dictionary operations within the merge logic.

## Verification Strategy
- **Static Analysis**: Run `uv run ruff check` and `uv run mypy` to confirm the error is cleared.
- **Visual Verification**: Confirm the "Red 9+" indicator in the IDE clears or reverts to "Warning Yellow."
- **Runtime Check**: Run existing tests to ensure the logic of `_merge_dicts` (which is critical for config loading) remains intact.
