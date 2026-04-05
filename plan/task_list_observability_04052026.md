# Task List: OpenRouter Observability (Issue #2)

## Phase 1: Preparation
- [x] Create implementation plan. (Currently at `plan/implementation_plan_observability_04052026.md`)
- [x] **Create GitHub Issue**: Document Issue #2 on the `mgammarino/llm-council` fork. ✅
- [x] **Create Branch**: Initialize `feature/issue-2-observability`. ✅

## Phase 2: Implementation & Validation
- [x] Correct OpenRouter model identifiers. (Done in commit `9dab7d4`)
- [x] Add identity tracking headers (`X-Title`, `HTTP-Referer`). (Done in commit `9b67803`)
- [x] Integrate `council_id` with gateway logs. (Done in commit `c495c68`)
- [x] **Run Quality Gates**:
  - `uv run ruff check src/ tests/` ✅
  - `uv run mypy src/llm_council` ✅
- [x] **Run Gateway Tests**:
  - `uv run pytest tests/test_gateway.py -v` ✅ (201 passed)

## Phase 3: Delivery
- [ ] **Push & PR**: Create Pull Request from `feature/issue-2-observability`.
- [ ] **Verify PR**: Await CI check and merge into fork master.
- [ ] **Close Issue**: Formally close Issue #2.
