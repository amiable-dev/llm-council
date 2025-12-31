# CI/CD Quality Gate Rubrics

Detailed scoring guidelines for LLM Council CI/CD quality gates. Each dimension uses a 1-10 scale with pipeline-specific behavioral anchors.

## Core Dimensions

### Accuracy (Weight: 30%)

Measures correctness of changes and absence of regressions.

| Score | Anchor | Description |
|-------|--------|-------------|
| 9-10 | **Excellent** | No regressions; all changes correct; passes all validation |
| 7-8 | **Good** | Minor issues that don't affect production; mostly correct |
| 5-6 | **Mixed** | Some issues present but core functionality intact |
| 3-4 | **Poor** | Significant issues; would cause production problems |
| 1-2 | **Critical** | Breaking changes; would cause outage or data loss |

**CI/CD Accuracy Checks:**
- No breaking API changes without versioning
- Database migrations are reversible
- Configuration changes are valid
- Dependency updates are compatible
- Environment variables are documented

**Accuracy Ceiling Rule**: Per ADR-016, accuracy acts as a ceiling on overall scores:
- Accuracy < 5: Overall score capped at 4.0 (blocking issues)
- Accuracy 5-6: Overall score capped at 7.0 (needs fixes)
- Accuracy ≥ 7: No ceiling applied

### Completeness (Weight: 25%)

Measures coverage of pipeline requirements and validation.

| Score | Anchor | Description |
|-------|--------|-------------|
| 9-10 | **Comprehensive** | All checks pass; full test coverage; complete validation |
| 7-8 | **Adequate** | Main checks pass; good coverage; minor gaps |
| 5-6 | **Partial** | Core checks pass; some gaps in coverage |
| 3-4 | **Incomplete** | Major checks failing; significant gaps |
| 1-2 | **Minimal** | Most checks failing; minimal validation |

**Completeness Checks:**
- All required tests passing
- Lint/format checks pass
- Type checking passes
- Security scans complete
- Coverage thresholds met
- Documentation updated

### Clarity (Weight: 20%)

Measures clarity of changes for review and rollback.

| Score | Anchor | Description |
|-------|--------|-------------|
| 9-10 | **Crystal Clear** | Changes well-documented; easy to review/rollback |
| 7-8 | **Clear** | Good documentation; straightforward changes |
| 5-6 | **Acceptable** | Understandable with effort; some confusion |
| 3-4 | **Unclear** | Poor documentation; hard to understand changes |
| 1-2 | **Opaque** | No documentation; unclear purpose |

**Clarity Checks:**
- Commit messages are descriptive
- PR description explains changes
- Breaking changes documented
- Migration steps provided
- Rollback procedure clear

### Conciseness (Weight: 15%)

Measures change scope and deployment risk.

| Score | Anchor | Description |
|-------|--------|-------------|
| 9-10 | **Optimal** | Focused changes; minimal blast radius |
| 7-8 | **Efficient** | Well-scoped; manageable risk |
| 5-6 | **Adequate** | Some scope creep; moderate risk |
| 3-4 | **Verbose** | Too many changes; high risk |
| 1-2 | **Bloated** | Massive changes; extreme risk |

**Conciseness Checks:**
- Single responsibility changes
- No unrelated refactoring
- Feature flags for large changes
- Incremental rollout supported
- Reasonable diff size

### Relevance (Weight: 10%)

Measures alignment with deployment requirements.

| Score | Anchor | Description |
|-------|--------|-------------|
| 9-10 | **Perfectly Aligned** | Matches deployment criteria exactly |
| 7-8 | **Well Aligned** | Meets requirements with minor additions |
| 5-6 | **Somewhat Aligned** | Core requirements met, some tangents |
| 3-4 | **Misaligned** | Partially addresses wrong criteria |
| 1-2 | **Off Target** | Does not meet deployment criteria |

**Relevance Checks:**
- Matches release criteria
- Appropriate for target environment
- Follows deployment schedule
- No unauthorized changes

## Exit Code Determination

### Exit Code 0: PASS

Pipeline continues when ALL conditions met:
- Confidence ≥ threshold (default 0.7)
- No blocking issues
- All critical checks pass

```json
{
  "verdict": "pass",
  "exit_code": 0,
  "action": "Deploy proceeds"
}
```

### Exit Code 1: FAIL

Pipeline fails when ANY condition met:
- Blocking issues present
- Critical security vulnerabilities
- Breaking changes detected
- Required checks failing

```json
{
  "verdict": "fail",
  "exit_code": 1,
  "action": "Pipeline halted, fix required"
}
```

### Exit Code 2: UNCLEAR

Pipeline pauses for human review when:
- Confidence < threshold but no blocking issues
- Conflicting reviewer opinions
- Edge cases requiring judgment
- Insufficient context

```json
{
  "verdict": "unclear",
  "exit_code": 2,
  "action": "Human review required"
}
```

## Domain-Specific Focus Areas

### Security Focus

When `rubric_focus: Security` is specified:

**Additional Checks:**
- No secrets in code or config
- Dependencies free of CVEs
- Security headers configured
- Input validation present
- Authentication/authorization correct
- Encryption properly implemented

**Red Flags (automatic FAIL):**
- Hardcoded secrets or API keys
- Known vulnerable dependencies (CVSS ≥ 7.0)
- Disabled security features
- SQL injection vulnerabilities
- Missing authentication

### Performance Focus

When `rubric_focus: Performance` is specified:

**Additional Checks:**
- No N+1 query introductions
- Bundle size within limits
- API response time acceptable
- Database query efficiency
- Memory usage reasonable
- Cache strategy appropriate

**Red Flags (automatic FAIL):**
- >50% regression in response time
- Memory leak potential
- Unbounded resource usage
- Missing pagination

### Compliance Focus

When `rubric_focus: Compliance` is specified:

**Additional Checks:**
- Audit logging present
- Data retention policies followed
- PII handling correct
- Access controls enforced
- License compliance met

**Red Flags (automatic FAIL):**
- GDPR/HIPAA/SOC2 violations
- Missing audit trail
- Unauthorized data exposure
- License violations

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

### Confidence to Exit Code Mapping

```python
def determine_exit_code(confidence, blocking_issues, threshold=0.7):
    if blocking_issues:
        return 1  # FAIL
    elif confidence >= threshold:
        return 0  # PASS
    else:
        return 2  # UNCLEAR
```

## Pipeline Integration Patterns

### GitHub Actions

```yaml
- name: Council Gate
  id: gate
  run: llm-council gate --snapshot ${{ github.sha }}
  continue-on-error: true

- name: Handle Unclear
  if: steps.gate.outcome == 'failure' && steps.gate.outputs.exit_code == '2'
  run: gh pr comment --body "⚠️ Council requires human review"
```

### GitLab CI

```yaml
council-gate:
  script:
    - llm-council gate --snapshot $CI_COMMIT_SHA
  allow_failure:
    exit_codes:
      - 2  # UNCLEAR triggers manual approval
```

### Azure DevOps

```yaml
- task: Bash@3
  displayName: 'Council Gate'
  inputs:
    targetType: 'inline'
    script: |
      llm-council gate --snapshot $(Build.SourceVersion)
      if [ $? -eq 2 ]; then
        echo "##vso[task.setvariable variable=needsReview]true"
      fi
```

## Blocking Issues

Issues that automatically trigger FAIL (exit code 1):

### Critical Severity
- Security vulnerabilities (CVSS ≥ 7.0)
- Data loss potential
- Production-breaking changes
- Compliance violations

### Major Severity
- Required tests failing
- Missing security controls
- Performance regressions >50%
- Breaking API changes

## Transcript Format

All gate decisions include audit trail:

```json
{
  "verification_id": "abc123",
  "timestamp": "2025-12-31T12:00:00Z",
  "snapshot_id": "git-sha",
  "verdict": "pass",
  "confidence": 0.85,
  "exit_code": 0,
  "rubric_scores": {
    "accuracy": 8.5,
    "completeness": 8.0,
    "clarity": 9.0,
    "conciseness": 8.5,
    "relevance": 9.0
  },
  "blocking_issues": [],
  "reviewers": ["model-a", "model-b", "model-c"],
  "consensus_method": "borda_count",
  "transcript_path": ".council/logs/2025-12-31T12-00-00-abc123/"
}
```

## Rollback Support

When a gate fails after deployment:

1. **Transcript Available**: Full deliberation saved for post-mortem
2. **Snapshot Pinning**: Exact code state preserved
3. **Issue List**: Specific problems identified
4. **Remediation Hints**: Suggestions for fixes

## Example Gate Output

```json
{
  "verdict": "fail",
  "confidence": 0.72,
  "exit_code": 1,
  "rubric_scores": {
    "accuracy": 5.5,
    "completeness": 7.0,
    "clarity": 8.0,
    "conciseness": 8.5,
    "relevance": 9.0
  },
  "weighted_score": 7.15,
  "accuracy_ceiling_applied": true,
  "final_score": 7.0,
  "blocking_issues": [
    {
      "severity": "critical",
      "category": "security",
      "message": "Dependency lodash@4.17.15 has known prototype pollution vulnerability (CVE-2019-10744)",
      "remediation": "Upgrade to lodash@4.17.21 or later"
    }
  ],
  "rationale": "Security vulnerability in dependencies blocks deployment. Recommend upgrading lodash before proceeding."
}
```
