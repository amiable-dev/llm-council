# ADR-DA: Reactive Devil's Advocate (Forensic Auditor) Implementation

## Overview
Implement a sequential deliberation stage where a reserved council member (the Adversary) audits the initial responses of the council before peer review and synthesis.

## Requirements
- **Sequential Execution**: The DA must act *after* Stage 1 initial responses are collected.
- **Context Injection**: The DA's report must be available to Stage 2 (Review) and Stage 3 (Synthesis).
- **CLI Support**: Users must be able to toggle the feature via `--adversary`.
- **Legacy Support**: Must work in `run_full_council` to maintain backward compatibility.

## Technical Design
1. **Adversary Prompting**: Create `src/llm_council/adversary_prompt.py` with the forensic audit template.
2. **Orchestration Logic**:
   - Split model pool (Ideators vs. Adversary).
   - Reserve one model (random or pinned via `LLM_COUNCIL_ADVERSARIAL_MODEL`).
   - Call `query_model_with_status` for the DA report.
3. **Integration**:
   - Update `run_council_with_fallback`.
   - Update `run_full_council`.
   - Update `query.py`.
4. **Verification**:
   - `tests/test_adversarial_logic.py` using Mocks.
   - CLI end-to-end testing with `--no-cache`.
