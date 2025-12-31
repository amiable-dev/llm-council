# Code Review Rubrics

Detailed scoring guidelines for LLM Council code review. Each dimension uses a 1-10 scale with code-specific behavioral anchors.

## Core Dimensions

### Accuracy (Weight: 35%)

Measures correctness of implementation, absence of bugs, and logic errors. Higher weight than general verification because code correctness is paramount.

| Score | Anchor | Description |
|-------|--------|-------------|
| 9-10 | **Excellent** | No bugs; handles all edge cases; correct algorithm choice; thread-safe if needed |
| 7-8 | **Good** | Minor issues that don't affect core functionality; mostly correct logic |
| 5-6 | **Mixed** | Some bugs present but main path works; needs fixes before production |
| 3-4 | **Poor** | Significant bugs affecting functionality; incorrect algorithm or data structure |
| 1-2 | **Critical** | Fundamental logic errors; would crash or corrupt data; security vulnerabilities |

**Code Review Accuracy Checks:**
- Correct algorithm implementation
- Proper null/undefined handling
- Boundary condition handling
- Type correctness (for typed languages)
- Concurrency safety (if applicable)
- Resource cleanup (memory, connections, handles)

**Accuracy Ceiling Rule**: Per ADR-016, accuracy acts as a ceiling on overall scores:
- Accuracy < 5: Overall score capped at 4.0 (bugs present)
- Accuracy 5-6: Overall score capped at 7.0 (needs fixes)
- Accuracy ≥ 7: No ceiling applied

### Completeness (Weight: 20%)

Measures coverage of requirements, error handling, and test coverage.

| Score | Anchor | Description |
|-------|--------|-------------|
| 9-10 | **Comprehensive** | All requirements met; full error handling; comprehensive tests |
| 7-8 | **Adequate** | Main requirements met; basic error handling; key paths tested |
| 5-6 | **Partial** | Core functionality present; minimal error handling; sparse tests |
| 3-4 | **Incomplete** | Major features missing; poor error handling; few or no tests |
| 1-2 | **Minimal** | Skeletal implementation; no error handling; no tests |

**Completeness Checks:**
- All acceptance criteria addressed
- Error paths handled gracefully
- Input validation present
- Logging for debugging
- Test coverage (unit, integration)
- Documentation updated

### Clarity (Weight: 20%)

Measures readability, maintainability, and code organization.

| Score | Anchor | Description |
|-------|--------|-------------|
| 9-10 | **Crystal Clear** | Self-documenting; excellent naming; clear structure; easy to modify |
| 7-8 | **Clear** | Good naming; logical organization; minor clarity issues |
| 5-6 | **Acceptable** | Understandable with effort; some confusing sections |
| 3-4 | **Unclear** | Poor naming; spaghetti logic; hard to follow |
| 1-2 | **Opaque** | Incomprehensible; no structure; magic numbers everywhere |

**Clarity Checks:**
- Meaningful variable/function names
- Consistent formatting
- Appropriate comments (why, not what)
- Single responsibility principle
- Reasonable function length
- Clear control flow

### Conciseness (Weight: 15%)

Measures efficiency without unnecessary complexity or over-engineering.

| Score | Anchor | Description |
|-------|--------|-------------|
| 9-10 | **Optimal** | No redundancy; DRY principles; elegant solutions |
| 7-8 | **Efficient** | Minor redundancy; mostly concise; appropriate abstractions |
| 5-6 | **Adequate** | Some duplication; could be simplified |
| 3-4 | **Verbose** | Significant redundancy; over-engineered; premature abstraction |
| 1-2 | **Bloated** | Extreme redundancy; unnecessary complexity throughout |

**Conciseness Checks:**
- No copy-paste duplication
- Appropriate use of abstractions
- No premature optimization
- No dead code
- Reasonable file sizes
- Focused commits

### Relevance (Weight: 10%)

Measures alignment with PR scope and requirements.

| Score | Anchor | Description |
|-------|--------|-------------|
| 9-10 | **Perfectly Scoped** | Changes match PR description; no scope creep |
| 7-8 | **Well Scoped** | Addresses requirements with minor related changes |
| 5-6 | **Somewhat Scoped** | Core changes present but with notable tangents |
| 3-4 | **Poorly Scoped** | Mixed unrelated changes; unclear purpose |
| 1-2 | **Off Target** | Changes don't match stated PR purpose |

**Relevance Checks:**
- Changes match PR title/description
- No unrelated refactoring
- Focused on single concern
- Breaking changes documented
- Migration path provided (if needed)

## Domain-Specific Focus Areas

### Security Focus

When `rubric_focus: Security` is specified:

**Additional Checks:**
- Input validation and sanitization
- SQL parameterization (no string concatenation)
- XSS prevention (output encoding)
- Authentication/authorization correctness
- Secure session handling
- Secrets management (no hardcoded credentials)
- HTTPS enforcement
- CORS configuration

**Red Flags (automatic FAIL):**
- Hardcoded secrets or API keys
- SQL injection vulnerabilities
- XSS vulnerabilities
- Insecure deserialization
- Missing authentication on sensitive endpoints
- Plaintext password storage
- Disabled security features (CSRF, CSP)

### Performance Focus

When `rubric_focus: Performance` is specified:

**Additional Checks:**
- Algorithm complexity (Big O analysis)
- Database query efficiency (indexes, N+1)
- Memory usage patterns
- Caching strategy
- Lazy loading appropriateness
- Connection pooling
- Async/await correctness

**Red Flags (automatic FAIL):**
- O(n²) or worse where O(n) is possible
- N+1 query patterns
- Unbounded memory growth
- Missing pagination
- Synchronous I/O in async context
- Memory leaks

### Testing Focus

When `rubric_focus: Testing` is specified:

**Additional Checks:**
- Test coverage percentage
- Unit vs integration test balance
- Mock appropriateness
- Edge case coverage
- Test isolation (no shared state)
- Deterministic tests (no flaky tests)
- Performance regression tests

**Red Flags (automatic FAIL):**
- No tests for new functionality
- Tests that always pass
- Tests with hardcoded sleeps
- Tests that depend on execution order
- Mocking implementation details

## Scoring Calculation

### Weighted Average Formula

```
overall_score = (
    accuracy * 0.35 +
    completeness * 0.20 +
    clarity * 0.20 +
    conciseness * 0.15 +
    relevance * 0.10
)
```

### Accuracy Ceiling Application

```python
def apply_accuracy_ceiling(overall_score, accuracy_score):
    if accuracy_score < 5:
        return min(overall_score, 4.0)
    elif accuracy_score < 7:
        return min(overall_score, 7.0)
    else:
        return overall_score
```

### Verdict Determination

| Confidence | Verdict | Exit Code | Action |
|------------|---------|-----------|--------|
| ≥ threshold (default 0.7) | PASS | 0 | Approve PR |
| < threshold AND no blocking issues | UNCLEAR | 2 | Request changes, re-review |
| Any blocking issues | FAIL | 1 | Block merge |

## Blocking Issues

Issues that automatically trigger FAIL verdict:

### Critical Severity (Block Merge)
- Security vulnerabilities
- Data loss potential
- Breaking changes without migration
- Production crashes

### Major Severity (Request Changes)
- Bugs in core functionality
- Missing error handling for likely failures
- Performance regressions >2x
- Missing tests for new code

### Minor Severity (Suggestions)
- Style inconsistencies
- Naming improvements
- Documentation gaps
- Refactoring opportunities

## Issue Format

Each issue should include:

```json
{
  "severity": "critical|major|minor",
  "category": "bug|security|performance|style|testing",
  "file": "src/api.py",
  "line": 42,
  "message": "Missing input validation for user_id parameter",
  "suggestion": "Add validation: if not isinstance(user_id, int) or user_id < 0: raise ValueError(...)"
}
```

## Reviewer Calibration

To ensure consistent scoring across reviewers:

1. **Anchoring**: Use behavioral anchors, not "feels like a 7"
2. **Evidence-Based**: Cite specific lines for each issue
3. **Severity Consistency**: Minor issues don't block, critical issues always block
4. **Constructive Feedback**: Every issue should have a suggested fix
5. **Scope Awareness**: Don't review unrelated code

## Example Review Output

```json
{
  "verdict": "fail",
  "confidence": 0.78,
  "rubric_scores": {
    "accuracy": 6.5,
    "completeness": 7.0,
    "clarity": 8.5,
    "conciseness": 8.0,
    "relevance": 9.0
  },
  "weighted_score": 7.35,
  "accuracy_ceiling_applied": true,
  "final_score": 7.0,
  "blocking_issues": [
    {
      "severity": "major",
      "category": "bug",
      "file": "src/api.py",
      "line": 42,
      "message": "Missing null check before accessing user.email",
      "suggestion": "Add: if user is None: return None"
    }
  ],
  "suggestions": [
    {
      "severity": "minor",
      "category": "style",
      "file": "src/api.py",
      "line": 15,
      "message": "Consider renaming 'x' to 'user_count' for clarity"
    }
  ],
  "rationale": "Code is well-structured but has a null pointer bug that could cause production errors. Recommend fixing the blocking issue before merge."
}
```
