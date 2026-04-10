# ADR-CD: Constructive Dissent CLI Integration

## Overview
Implement the `--dissent` flag in `query.py` to expose the engine's "Constructive Dissent" feature. This feature mathematically detects minority opinions during the Stage 2 Peer Review process and surfaces them to the user.

## User Review Required
> [!NOTE]
> This feature is distinct from the Devil's Advocate. 
> - **Devil's Advocate**: A proactive critique from a reserved model.
> - **Constructive Dissent**: A reactive extraction of disagreements between models during the voting phase.

## Proposed Changes

### CLI Layer

#### [MODIFY] [query.py](file:///c:/git_projects/llm-council/query.py)
- Add `--dissent` argument to `argparse`.
- Update `run_full_council` call to include `include_dissent=args.dissent`.
- Add a new display section for `metadata.get("dissent")` in the terminal output.

### Verification Plan

#### Automated Tests
- Create `tests/test_dissent_integration.py` to verify that `run_full_council` correctly populates the `metadata["dissent"]` field when `include_dissent=True`.
- Run the full test suite `uv run pytest tests/ -v`.

#### Manual Verification
- Run a query with `--dissent` and models that are likely to disagree (e.g., a mix of GPT-4 and Haiku on a complex topic) to ensure the minority perspective is surfaced.
