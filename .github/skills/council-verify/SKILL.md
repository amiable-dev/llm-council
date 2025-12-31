---
name: council-verify
description: |
  Verify code, documents, or implementation against requirements using LLM Council multi-model deliberation.
  Use when you need multi-model consensus on correctness, completeness, or quality.
  Keywords: verify, check, validate, review, approve, pass/fail, consensus, multi-model

license: Apache-2.0
compatibility: "llm-council >= 2.0, mcp >= 1.0"
metadata:
  category: verification
  domain: ai-governance
  council-version: "2.0"
  author: amiable-dev
  repository: https://github.com/amiable-dev/llm-council

allowed-tools: "Read Grep Glob mcp:llm-council/verify mcp:llm-council/audit"
---

# Council Verification Skill

Use LLM Council's multi-model deliberation to verify work with structured, machine-actionable verdicts.

## When to Use

- Verify code changes before committing
- Validate implementation against requirements
- Check documents for accuracy and completeness
- Get multi-model consensus on quality

## Workflow

1. **Capture Snapshot**: Capture current git diff or file state (snapshot pinning for reproducibility)
2. **Invoke Verification**: Call `mcp:llm-council/verify` with isolated context
3. **Receive Verdict**: Get structured JSON with verdict, confidence, and blocking issues
4. **Audit Trail**: Persist transcript via `mcp:llm-council/audit`

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `rubric_focus` | string | null | Focus area: "Security", "Performance", "Accessibility" |
| `confidence_threshold` | float | 0.7 | Minimum confidence for PASS verdict |
| `snapshot_id` | string | required | Git commit SHA for reproducibility |

## Output Schema

```json
{
  "verdict": "pass|fail|unclear",
  "confidence": 0.85,
  "rubric_scores": {
    "accuracy": 8.5,
    "completeness": 7.0,
    "clarity": 9.0,
    "conciseness": 8.0
  },
  "blocking_issues": [...],
  "rationale": "Chairman synthesis...",
  "transcript_location": ".council/logs/..."
}
```

## Exit Codes (for CI/CD)

- `0`: PASS - Approved with confidence >= threshold
- `1`: FAIL - Rejected
- `2`: UNCLEAR - Confidence below threshold, requires human review

## Example Usage

```bash
# Verify current changes
council-verify --snapshot $(git rev-parse HEAD) --rubric-focus Security

# Verify specific files
council-verify --target-paths "src/auth.py,src/api.py" --snapshot abc123
```

## Progressive Disclosure

- **Level 1**: This metadata (~200 tokens)
- **Level 2**: Full instructions above (~600 tokens)
- **Level 3**: See `references/rubrics.md` for detailed rubric definitions

## Related Skills

- `council-review`: Code review with structured feedback
- `council-gate`: CI/CD quality gate
