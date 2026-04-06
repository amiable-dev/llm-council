# Task List: Model Selection Stability (Issue #8)

## Phase 1: Preparation
- [x] Create implementation plan. (Currently at `plan/implementation_plan_phantom_model_04052026.md`) ✅
- [ ] **Create GitHub Issue**: Document Issue #8 on the `mgammarino/llm-council` fork.

## Phase 2: Implementation & Validation
- [x] Patch `query.py` to bypass hardcoded model defaults. ✅
- [x] **Verify Stability**:
  - `python query.py "test query" --details` ✅ (Verified: strictly follows YAML)

## Phase 3: Delivery
- [ ] **Update CHANGELOG.md**: Record core stabilization.
- [ ] **Push & PR**: Final PR to document `query.py` stabilization on Master.
- [ ] **Close Issue**: Formally close Issue #8.
