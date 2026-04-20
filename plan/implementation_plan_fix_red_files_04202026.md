# Implementation Plan - Resolve IDE "Red" Status in Configuration Files

Resolve the linting and type-checking errors in `tier_contract.py` and `unified_config.py` that are causing the IDE to flag them with red text.

## User Review Required

> [!NOTE]
> Resolving these errors involves installing missing type stubs for the project environment and adding explicit type casting/annotations where the static analyzer cannot infer them correctly.

## Proposed Changes

### Environment & Dependencies

#### [MODIFY] [pyproject.toml](file:///c:/git_projects/llm-council/pyproject.toml)
- Add `types-PyYAML` to the development dependencies to provide type stubs for Mypy and IDEs (Pylance/Pyright).

### Core Configuration

#### [MODIFY] [unified_config.py](file:///c:/git_projects/llm-council/src/llm_council/unified_config.py)
- Address any internal type inconsistencies surfaced after installing YAML stubs.

#### [MODIFY] [tier_contract.py](file:///c:/git_projects/llm-council/src/llm_council/tier_contract.py)
- Add explicit type casting or narrowing in `create_tier_contract` when extracting values from the `tier_configs` dictionary to satisfy Mypy's strict type checking.
    - Example: `token_budget=int(config["token_budget"])` or using a TypedDict for `tier_configs`.

---

## Verification Plan

### Automated Tests
- Run Mypy specifically on the target files:
  ```bash
  uv run mypy src/llm_council/tier_contract.py src/llm_council/unified_config.py --ignore-missing-imports
  ```
- Run full test suite to ensure no regressions:
  ```bash
  uv run pytest tests/
  ```

### Manual Verification
- Confirm that the "red text" and "9+" indicators in the VS Code sidebar disappear after the changes and a re-scan.
