# Verification Rubrics

Detailed scoring guidelines for LLM Council verification. Each dimension uses a 1-10 scale with specific behavioral anchors.

## Core Dimensions

### Accuracy (Weight: 30%)

Measures factual correctness and absence of errors.

| Score | Anchor | Description |
|-------|--------|-------------|
| 9-10 | **Excellent** | No factual errors; all claims verifiable; edge cases handled correctly |
| 7-8 | **Good** | Minor inaccuracies that don't affect functionality; mostly correct |
| 5-6 | **Mixed** | Some errors present but core functionality intact; needs review |
| 3-4 | **Poor** | Significant errors affecting functionality; requires rework |
| 1-2 | **Critical** | Fundamental errors; incorrect approach; dangerous if deployed |

**Accuracy Ceiling Rule**: Per ADR-016, accuracy acts as a ceiling on overall scores:
- Accuracy < 5: Overall score capped at 4.0 ("significant errors")
- Accuracy 5-6: Overall score capped at 7.0 ("mixed accuracy")
- Accuracy ≥ 7: No ceiling applied

### Completeness (Weight: 25%)

Measures coverage of requirements and handling of all cases.

| Score | Anchor | Description |
|-------|--------|-------------|
| 9-10 | **Comprehensive** | All requirements addressed; edge cases handled; thorough coverage |
| 7-8 | **Adequate** | Main requirements met; minor gaps in edge case handling |
| 5-6 | **Partial** | Core functionality present but notable gaps; happy path only |
| 3-4 | **Incomplete** | Major requirements missing; significant gaps |
| 1-2 | **Minimal** | Only skeletal implementation; most requirements unaddressed |

### Clarity (Weight: 20%)

Measures readability, organization, and ease of understanding.

| Score | Anchor | Description |
|-------|--------|-------------|
| 9-10 | **Crystal Clear** | Self-documenting; excellent organization; easy to follow |
| 7-8 | **Clear** | Well-organized; good naming; minor clarity issues |
| 5-6 | **Acceptable** | Understandable with effort; some confusing sections |
| 3-4 | **Unclear** | Difficult to follow; poor organization; needs refactoring |
| 1-2 | **Opaque** | Nearly incomprehensible; no clear structure |

### Conciseness (Weight: 15%)

Measures efficiency without unnecessary complexity.

| Score | Anchor | Description |
|-------|--------|-------------|
| 9-10 | **Optimal** | No redundancy; elegant solutions; perfectly sized |
| 7-8 | **Efficient** | Minor redundancy; mostly concise; good balance |
| 5-6 | **Adequate** | Some unnecessary complexity; could be simplified |
| 3-4 | **Verbose** | Significant redundancy; over-engineered |
| 1-2 | **Bloated** | Extreme redundancy; unnecessary complexity throughout |

### Relevance (Weight: 10%)

Measures alignment with requirements and stated goals.

| Score | Anchor | Description |
|-------|--------|-------------|
| 9-10 | **Perfectly Aligned** | Directly addresses requirements; no scope creep |
| 7-8 | **Well Aligned** | Addresses requirements with minor tangents |
| 5-6 | **Somewhat Aligned** | Addresses core requirements but with notable deviations |
| 3-4 | **Misaligned** | Partially addresses wrong problems |
| 1-2 | **Off Target** | Does not address stated requirements |

## Domain-Specific Rubrics

### Security Focus

When `rubric_focus: Security` is specified:

**Additional Checks:**
- Input validation and sanitization
- Authentication/authorization correctness
- Secure data handling (encryption, secrets management)
- Protection against OWASP Top 10 vulnerabilities
- Secure defaults and fail-safe behavior

**Red Flags (automatic FAIL):**
- Hardcoded credentials or secrets
- SQL injection vulnerabilities
- XSS vulnerabilities
- Insecure deserialization
- Missing authentication on sensitive endpoints

### Performance Focus

When `rubric_focus: Performance` is specified:

**Additional Checks:**
- Algorithm complexity (Big O analysis)
- Database query efficiency
- Memory usage patterns
- Caching strategy appropriateness
- Concurrency handling

**Red Flags (automatic FAIL):**
- O(n²) or worse where O(n) is possible
- N+1 query patterns
- Unbounded memory growth
- Missing pagination on large datasets

### Accessibility Focus

When `rubric_focus: Accessibility` is specified:

**Additional Checks:**
- WCAG 2.1 AA compliance
- Keyboard navigation support
- Screen reader compatibility
- Color contrast ratios
- Alternative text for images

**Red Flags (automatic FAIL):**
- Missing alt text on meaningful images
- Inaccessible form controls
- Color-only information conveyance
- Missing focus indicators

## Scoring Calculation

### Weighted Average Formula

```
overall_score = (
    accuracy * 0.30 +
    completeness * 0.25 +
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

| Confidence | Verdict | Exit Code |
|------------|---------|-----------|
| ≥ threshold (default 0.7) | PASS | 0 |
| < threshold AND no blocking issues | UNCLEAR | 2 |
| Any blocking issues | FAIL | 1 |

## Blocking Issues

Issues that automatically trigger FAIL verdict:

### Critical Severity
- Security vulnerabilities (injection, auth bypass)
- Data loss potential
- System crash potential
- Regulatory compliance violations

### Major Severity
- Broken core functionality
- Significant performance degradation (>10x slowdown)
- Missing critical error handling
- Incorrect business logic

## Reviewer Calibration

To ensure consistent scoring across reviewers:

1. **Anchoring**: Use behavioral anchors, not relative comparisons
2. **Independence**: Score each dimension independently before combining
3. **Evidence-Based**: Cite specific code/text for each score
4. **Uncertainty Acknowledgment**: Use UNCLEAR when evidence is insufficient

## Example Scoring

```json
{
  "rubric_scores": {
    "accuracy": 8.5,
    "completeness": 7.0,
    "clarity": 9.0,
    "conciseness": 8.0,
    "relevance": 9.0
  },
  "weighted_score": 8.15,
  "accuracy_ceiling_applied": false,
  "blocking_issues": [],
  "verdict": "pass",
  "confidence": 0.85
}
```
