# Implementation Plan: Centralized Docstring Alignment (Post-Review Cleanup)

This plan addresses findings from the QA code review to align key module docstrings and usage examples with the newly established `model_constants.py` pattern. This ensures that even high-level documentation reflects the decoupling of model identifiers from literals.

## User Review Required

> [!NOTE]
> This refactor is purely cosmetic/documentative and will not affect functional code.

## Proposed Changes

### [Docs & Examples]

#### [MODIFY] [performance/__init__.py](file:///src/llm_council/performance/__init__.py)
- Replace hardcoded `model_id="openai/gpt-4o"` in the usage example with a generic placeholder or a comment referencing `model_constants`.

#### [MODIFY] [reasoning/__init__.py](file:///src/llm_council/reasoning/__init__.py)
- Replace `extract_reasoning_usage(response, "openai/o1", ...)` with a reference to `model_constants.REASONING_FAMILY_O1` or a generic placeholder.

#### [MODIFY] [unified_config.py](file:///src/llm_council/unified_config.py)
- Update top-level docstring example to show the `model_constants` usage pattern instead of literals in the YAML example.

#### [MODIFY] [triage/prompt_optimizer.py](file:///src/llm_council/triage/prompt_optimizer.py)
- Update the docstring example in `get_model_provider` to use generic `<provider>/<model>` placeholders instead of specific literals.

## Verification Plan

### Automated Tests
- Run `uv run ruff check` to ensure docstring formatting remains clean.
- Run `uv run pytest tests/test_unified_config.py` as a sanity check.

### Manual Verification
- Review the `help()` output in a Python REPL for these modules to confirm the examples lead developers toward the centralization pattern.
