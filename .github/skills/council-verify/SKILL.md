---
name: council-verify
description: |
  Verify code, documents, or implementation against requirements using LLM Council multi-model deliberation.
  Use when you need multi-model consensus on correctness, completeness, or quality.
  Keywords: verify, check, validate, review, approve, pass/fail, consensus, multi-model

license: Apache-2.0
compatibility: "llm-council-core >= 0.33, mcp >= 1.0"
metadata:
  category: verification
  domain: ai-governance
  council-version: "0.33"
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

1. **Snapshot**: pin the git commit SHA (reproducibility)
2. **Verify**: call `mcp:llm-council/verify` (isolated context)
3. **Act on the verdict** (structured JSON below)
4. **Audit**: transcript via `mcp:llm-council/audit`

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `snapshot_id` | string | required | Git commit SHA for reproducibility |
| `rubric_focus` | string | null | Focus area: "Security", "Performance", "Accessibility" |
| `confidence_threshold` | float | 0.7 | Minimum confidence for PASS verdict |
| `tier` | string | "balanced" | Confidence tier: "quick", "balanced", "high", "reasoning" |

### Tier Selection Guide

| Tier | Use When | Timeout | Max Input |
|------|----------|---------|-----------|
| `quick` | Fast sanity checks, small diffs | ~30s | 15K chars |
| `balanced` | **Default.** Routine verification | ~90s | 30K chars |
| `high` | Security-critical reviews only | ~180s | 50K chars |
| `reasoning` | Complex architectural decisions | ~600s | 50K chars |

**Important**: `high`/`reasoning` use slow frontier models. For large diffs (>20K chars), prefer `balanced` to avoid timeouts.

## Evidence (ADR-042)

Pass pre-computed analysis from upstream tools (linters, slop detectors) via `evidence: List[EvidenceItem]`. Council emits `evidence_summary` and `evidence_warnings` in the response. See [`references/evidence.md`](references/evidence.md) for fields, limits, example.

## Output Schema

```json
{
  "verdict": "pass|fail|unclear",
  "confidence": 0.85,
  "confidence_calibrated": 0.62,
  "unclear_reason": null,
  "rubric_scores": { "accuracy": 8.5, "completeness": 7.0, "...": "..." },
  "blocking_issues": [...],
  "rationale": "Chairman synthesis...",
  "transcript_location": ".council/logs/...",
  "partial": false,
  "timeout_fired": false,
  "completed_stages": ["stage1", "stage2", "stage3"],
  "timing": { "total_elapsed_ms": 142000, "budget_utilization": 0.53, "...": "..." },
  "input_metrics": { "content_chars": 32000, "tier": "high", "...": "..." },
  "evidence_summary": [...],
  "evidence_warnings": [...]
}
```

If `timeout_fired: true`, the tier deadline was exceeded. Check `completed_stages` for progress. `timing.budget_utilization` shows time used vs deadline (1.0 on timeout). See ADR-040 for full timeout semantics.

On UNCLEAR, route on `unclear_reason`: infra_failure → check gateway + RETRY; low_confidence → accept-and-audit if no blocking issues; timeout → re-tier. Details: `references/unclear-routing.md`.

## Rules

1. **One call at a time.** Never fire multiple verify calls concurrently or in rapid succession. Wait for each to complete before deciding next steps.
2. **One call per commit.** Never retry the same snapshot_id. If it fails, fix the code first.
3. **Act on verdicts, don't retry them:**
   - **PASS** (exit_code 0): Proceed.
   - **FAIL** (exit_code 1): Read `blocking_issues`. Fix the code, commit, then re-verify the *new* snapshot.
   - **UNCLEAR** (exit_code 2): Accept and move on. Do not retry.
4. **Do not reduce scope and retry.** Sending the same code with fewer files is still a retry.

## Related Skills

`council-review` (code review), `council-gate` (CI/CD gate)
