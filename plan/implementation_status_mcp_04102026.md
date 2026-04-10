# Implementation Plan - MCP Real-Time Status Updates (Feature #1)

## Objective
Enhance the LLM Council observability by providing descriptive, real-time status updates via the MCP Progress Protocol. This will allow users in Claude Desktop to see exactly what stage the council is in (e.g., Stage 1, Stage 1B Audit, Peer Review).

## Requirements
- Status messages must include stage identifiers (e.g., `[*] Stage 1`).
- Messages should provide context (e.g., which model is acting as Devil's Advocate).
- Tier information should be included if available.
- Progress bar step/total counts must remain accurate.

## Proposed Changes

### 1. `src/llm_council/council.py`
- Update `run_council_with_fallback`'s `report_progress` calls.
- Inject tier information into the initial stage 1 status message.
- Update `stage1_progress` to include the `[*] ` prefix.
- Enhance Stage 1B message to include the adversary model name.
- Standardize all stage transitions to use the `[*] ` style.

### 2. `src/llm_council/mcp_server.py`
- Ensure `on_progress` pass-through is robust.
- Standardize output headers and rankings to match `query.py`.
- Surface `dissent_report` (Adversary) and `dissent` (Minority Opinion) even when `include_details` is False to ensure parity with the CLI.

### 3. `query.py` (CLI)
- Update manual stage print statements to match the exact wording used in the orchestrator's progress callback.

## Verification Plan
- **Unit Tests**: Create `tests/test_mcp_status_updates.py` to verify that `run_council_with_fallback` calls the progress callback with the expected strings.
- **Manual Verification**: Run a `consult_council` tool call in Claude Desktop and observe the "Thinking" block.

## DCO Sign-off
I certify that the code I'm contributing is my own work or that I have the right to contribute it under the DCO.
