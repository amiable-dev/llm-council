---
name: council-review
description: |
  Multi-model code review with structured feedback using LLM Council peer evaluation.
  Use for PR reviews, code quality checks, or implementation review.
  Keywords: code review, PR, pull request, quality check, peer review, feedback

license: Apache-2.0
compatibility: "llm-council >= 2.0, mcp >= 1.0"
metadata:
  category: code-review
  domain: software-engineering
  council-version: "2.0"
  author: amiable-dev
  repository: https://github.com/amiable-dev/llm-council

allowed-tools: "Read Grep Glob mcp:llm-council/verify mcp:llm-council/audit"
---

# Council Code Review Skill

Get multiple AI perspectives on code changes with structured, actionable feedback.

## When to Use

- Review pull requests before merging
- Get code quality feedback on implementations
- Identify potential issues across multiple dimensions
- Validate changes against coding standards

## Workflow

1. **Prepare Input**: Provide file paths or git diff
2. **Invoke Review**: Call `mcp:llm-council/verify` with code-review rubric
3. **Process Feedback**: Receive structured scores and issue list
4. **Address Issues**: Fix blocking issues before proceeding

## Input Formats

Supports both:
- `file_paths`: List of files to review (full file analysis)
- `git_diff`: Unified diff format for change-focused review
- `snapshot_id`: Git commit SHA (required for reproducibility)

## Rubric (ADR-016)

| Dimension | Weight | Focus |
|-----------|--------|-------|
| Accuracy | 35% | Correctness, no bugs, logic errors |
| Completeness | 20% | All requirements addressed |
| Clarity | 20% | Readable, maintainable code |
| Conciseness | 15% | No unnecessary complexity |
| Relevance | 10% | Addresses stated requirements |

## Output Schema

```json
{
  "verdict": "pass|fail|unclear",
  "confidence": 0.82,
  "rubric_scores": {
    "accuracy": 7.5,
    "completeness": 8.0,
    "clarity": 9.0,
    "conciseness": 8.5,
    "relevance": 9.0
  },
  "blocking_issues": [
    {
      "severity": "major",
      "file": "src/api.py",
      "line": 42,
      "message": "Missing input validation"
    }
  ],
  "suggestions": [...],
  "rationale": "Overall, the code is well-structured..."
}
```

## Example Usage

```bash
# Review specific files
council-review --file-paths "src/main.py,src/utils.py" --snapshot abc123

# Review git diff
council-review --git-diff "$(git diff HEAD~1)" --snapshot $(git rev-parse HEAD)

# Review with custom focus
council-review --rubric-focus Security --file-paths "src/auth.py"
```

## Progressive Disclosure

- **Level 1**: This metadata (~200 tokens)
- **Level 2**: Full instructions above (~800 tokens)
- **Level 3**: See `references/code-review-rubric.md` for detailed scoring anchors

## Related Skills

- `council-verify`: General verification
- `council-gate`: CI/CD quality gate
