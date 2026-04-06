# Implementation Plan - Deliberation Documentation (Issue #6)

## 1. Problem Statement
The LLM Council's multi-stage process (Stage 1, 1.5, 2, 3) is powerful but invisible to new users. Without a clear guide, it is difficult for users to understand how individual model responses are refined and synthesized into a final verdict.

## 2. Solution Summary
- **Visual Flowchart**: Design an ASCII flowchart tracking the lifecycle of a query from Stage 1 (Ideation) to Stage 3 (Synthesis).
- **Core Guide**: Create `docs/how_the_llm_council_works.md` explaining peer review, Borda scoring, and self-preference protection.
- **Terminology Sync**: Ensure all docs use the correct project terminology (Chairman, Juror, Synthesis, Dissent).

## 3. Implementation Details
- `docs/how_the_llm_council_works.md`: The flagship guide for explaining the council's "brain."

## 4. Verification Strategy
- **Visual Audit**: Ensure the ASCII art renders correctly in markdown previewers.
- **Accuracy Check**: Cross-reference the guide's Stage 2 explanation with the actual Borda points logic in `council.py`.
