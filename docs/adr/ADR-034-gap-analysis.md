# ADR-034 Implementation Gap Analysis

**Date:** 2026-01-01
**Author:** Claude Code (Post-Implementation Review)
**Status:** ✅ RESOLVED (PR #298)

---

## Executive Summary

The ADR-034 verification system (`mcp://llm-council/verify`) returns **hardcoded placeholder values** instead of running actual council deliberation. This gap was present from the initial implementation and was not caught during planning, development, or review phases.

---

## Gap Description

### What Was Implemented (Infrastructure)

| Component | Status | Evidence |
|-----------|--------|----------|
| `VerificationRequest` schema | ✅ Working | `verification/types.py` |
| `VerificationResult` schema | ✅ Working | `verification/types.py` |
| Context isolation | ✅ Working | `verification/context.py` |
| Git SHA validation | ✅ Working | `validate_snapshot_id()` |
| Transcript persistence | ✅ Partial | Only writes `request.json` and `result.json` |
| Exit codes (0/1/2) | ✅ Working | Logic in `_verdict_to_exit_code()` |
| MCP `verify` tool | ✅ Registered | `mcp_server.py` line 332 |
| MCP `audit` tool | ✅ Working | Reads transcripts correctly |

### What Was NOT Implemented (Core Logic)

| Component | Status | Evidence |
|-----------|--------|----------|
| Council deliberation integration | ❌ Missing | `api.py` lines 170-207 - TODO comment |
| Stage 1 (model responses) | ❌ Missing | No `stage1.json` written |
| Stage 2 (peer review) | ❌ Missing | No `stage2.json` written |
| Stage 3 (synthesis) | ❌ Missing | No `stage3.json` written |
| Dynamic rubric scoring | ❌ Missing | Hardcoded values: 8.5, 8.0, 7.5, 8.0, 8.5 |
| Dynamic confidence | ❌ Missing | Hardcoded: 0.85 |
| Dynamic verdict | ❌ Missing | Always returns "pass" |

---

## Evidence

### 1. Hardcoded Values in `api.py`

File: `src/llm_council/verification/api.py`, lines 170-207:

```python
# TODO: In full implementation, this would run council deliberation
# For now, return a mock result for API structure validation
#
# The actual implementation will:
# 1. Run stage1_collect_responses() with verification prompt
# 2. Run stage2_collect_rankings() for peer review
# 3. Run stage3_synthesize_final() for verdict
# 4. Extract verdict from synthesis

# Mock result for API structure (will be replaced with real council)
verdict = "pass"
confidence = 0.85
...
"rubric_scores": {
    "accuracy": 8.5,
    "relevance": 8.0,
    "completeness": 7.5,
    "conciseness": 8.0,
    "clarity": 8.5,
},
```

### 2. Missing Stage Files in Transcripts

ADR-034 specifies this transcript structure:

```
.council/logs/
├── 2025-12-28T10-30-00-abc123/
│   ├── request.json      # Input snapshot
│   ├── stage1.json       # Individual responses    ← NOT WRITTEN
│   ├── stage2.json       # Peer reviews            ← NOT WRITTEN
│   ├── stage3.json       # Synthesis               ← NOT WRITTEN
│   └── result.json       # Final verdict
```

Actual files written:
```
.council/logs/2026-01-01T11-45-53-a9f51269/
├── request.json    # ✅ Written
└── result.json     # ✅ Written (but with hardcoded values)
```

### 3. Tests Mock the Core Function

File: `tests/integration/verification/test_api.py`, line 77:

```python
with patch("llm_council.verification.api.run_verification") as mock_verify:
    mock_verify.return_value = {...}
```

All API tests mock `run_verification()`, meaning they never test actual council execution.

---

## Root Cause Analysis

### 1. Task Definition Gap

The GitHub issue #273 (A4: Verification API) had these acceptance criteria:

```markdown
- [ ] POST /v1/council/verify endpoint implemented
- [ ] Accepts VerificationRequest JSON body
- [ ] Returns VerificationResult with verdict
- [ ] Exit codes: 0=PASS, 1=FAIL, 2=UNCLEAR
```

**Missing criteria:**
- ❌ "Actually runs council deliberation"
- ❌ "Writes stage1/stage2/stage3 to transcript"
- ❌ "Returns dynamic scores from council"

### 2. TDD Focused on Schema, Not Behavior

The TDD approach focused on API schema validation (correct JSON structure) rather than behavioral testing (correct council execution).

### 3. VCR Cassette Strategy Masked the Gap

The test plan mentioned "VCR cassettes for API mocking" which inherently assumes mocking external calls. This mindset may have normalized mocking `run_verification()` entirely.

### 4. No Integration Test Without Mocks

There is no test that actually calls `run_verification()` with a real council. All tests use mocks.

### 5. Documentation Claimed Completion

ADR-034 v2.1 changelog claims:
> "**Implementation**: Added Implementation Status section documenting Track A and Track B completion"

The status table shows "✅ Complete" for all Track A items, but the actual code has TODO comments.

### 6. PR Review Gap

PR #279 was merged with this TODO still present:
- PR title: "[ADR-034] Track A: Verification API + MCP Foundation (Consolidated)"
- PR claimed: "121 tests pass"
- Tests pass because they mock the unimplemented function

---

## Impact Assessment

| Impact Area | Severity | Description |
|-------------|----------|-------------|
| Verification accuracy | **Critical** | Always returns "pass" regardless of code quality |
| CI/CD integration | **High** | Exit code always 0, gates never fail |
| Audit trail | **Medium** | Missing stage1/2/3 means no deliberation record |
| Trust | **High** | Users believe verification is real when it's not |
| ADR compliance | **High** | Claimed complete but isn't |

---

## Remediation Plan

### Immediate (P0)

1. **Update ADR-034** to mark Track A as "Partial - Infrastructure Only"
2. **Create tracking issue** for council integration
3. **Update epic #262** with accurate status

### Short-term (P1)

4. **Implement council integration** in `run_verification()`:
   - Call `stage1_collect_responses()` with verification prompt
   - Call `stage2_collect_rankings()` for peer review
   - Call `stage3_synthesize_final()` for verdict
   - Extract scores from Stage 2 rubric evaluations
   - Write stage1.json, stage2.json, stage3.json to transcript

5. **Add integration test without mocks**:
   - Use VCR cassettes for external API calls
   - But actually call `run_verification()` directly

### Medium-term (P2)

6. **Add verification-specific prompts**:
   - Security focus rubric
   - Performance focus rubric
   - Custom rubric support

---

## Lessons Learned

1. **Acceptance criteria must include behavioral requirements**, not just schema validation
2. **TDD should include at least one test without mocks** for core business logic
3. **TODO comments should block PR merge** or be tracked as issues
4. **Implementation status should be verified** by running the feature, not just running tests
5. **Council review of implementation** (not just ADR) would catch these gaps

---

## Affected Files

| File | Issue |
|------|-------|
| `src/llm_council/verification/api.py` | Contains TODO with hardcoded values |
| `docs/adr/ADR-034-agent-skills-verification.md` | Claims Track A complete |
| `tests/integration/verification/test_api.py` | All tests use mocks |
| `.github/issues/262` | Epic not updated with accurate status |

---

## Resolution (2026-01-01)

**Status**: ✅ RESOLVED in PR #298

All gaps identified in this analysis have been addressed:

| Gap | Resolution |
|-----|------------|
| Council deliberation integration | Implemented in `api.py` - calls all 3 stages |
| Stage 1/2/3 transcript files | Now written to `.council/logs/{id}/` |
| Dynamic rubric scoring | Extracted from Stage 2 via `verdict_extractor.py` |
| Dynamic confidence | Calculated from council agreement |
| Dynamic verdict | Derived from Stage 3 synthesis |
| Integration tests without mocks | Added 10 tests in `test_council_integration.py` |

### Files Changed

- `src/llm_council/verification/api.py` - Full council integration
- `src/llm_council/verification/verdict_extractor.py` - New module
- `tests/integration/verification/test_council_integration.py` - New test file
- `docs/adr/ADR-034-agent-skills-verification.md` - Updated to v2.4

### Lessons Applied

The implementation followed the lessons learned from this gap analysis:
1. Tests verify actual behavior, not just schema validation
2. No mocks on core verification function in integration tests
3. All code reviewed and tracked via GitHub issues (#297)

---

## References

- ADR-034: Agent Skills Integration for Work Verification
- PR #279: Track A Implementation
- PR #298: Council Deliberation Integration
- Issue #297: Tracking issue for council integration
- Issue #262: ADR-034 Epic
- Issue #273: A4 Verification API
