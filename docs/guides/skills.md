# Agent Skills Guide

LLM Council provides agent skills for AI-assisted verification, code review, and CI/CD quality gates. Skills enable multi-model consensus to be integrated into development workflows.

## Overview

Agent skills are self-contained instruction sets that guide AI agents through specific tasks. Each skill includes:

- **SKILL.md**: Instructions and workflow documentation
- **references/**: Detailed rubrics and scoring guidelines

Skills use **progressive disclosure** to minimize token usage:

| Level | Content | Tokens |
|-------|---------|--------|
| **Level 1** | Metadata only | ~100-200 |
| **Level 2** | Full SKILL.md | ~500-1000 |
| **Level 3** | Resources on demand | Variable |

## Available Skills

### council-verify

General-purpose verification using multi-model consensus.

**Category**: verification
**Domain**: quality

**When to Use**:
- Verify implementation correctness
- Validate documentation accuracy
- Check for completeness and clarity

**Example**:
```bash
# Via MCP
mcp:llm-council/verify --snapshot abc123 --file-paths "src/main.py"
```

### council-review

Code review with structured feedback and security focus.

**Category**: code-review
**Domain**: software-engineering

**Accuracy Weight**: 35% (vs 30% for general verification)

**When to Use**:
- PR reviews before merging
- Code quality assessment
- Security and performance audits

**Focus Areas**:
- **Security**: SQL injection, XSS, secrets, authentication
- **Performance**: Algorithm complexity, N+1 queries, memory leaks
- **Testing**: Coverage, mocking, flaky tests

**Example**:
```bash
# Review specific files
council-review --file-paths "src/api.py,src/auth.py" --snapshot HEAD

# Review with security focus
council-review --rubric-focus Security --file-paths "src/auth.py"
```

### council-gate

Quality gate for CI/CD pipelines with structured exit codes.

**Category**: ci-cd
**Domain**: devops

**Exit Codes**:

| Code | Verdict | Pipeline Action |
|------|---------|-----------------|
| `0` | PASS | Continue deployment |
| `1` | FAIL | Block deployment |
| `2` | UNCLEAR | Require human review |

**When to Use**:
- Automated PR approval gates
- Deployment quality checks
- Compliance verification

**Example** (GitHub Actions):
```yaml
- name: Council Quality Gate
  run: |
    llm-council gate \
      --snapshot ${{ github.sha }} \
      --rubric-focus Security \
      --confidence-threshold 0.8
```

## Scoring Dimensions

All skills use ADR-016 multi-dimensional rubric scoring:

| Dimension | council-verify | council-review | council-gate |
|-----------|----------------|----------------|--------------|
| Accuracy | 30% | 35% | 30% |
| Completeness | 25% | 20% | 25% |
| Clarity | 20% | 20% | 20% |
| Conciseness | 15% | 15% | 15% |
| Relevance | 10% | 10% | 10% |

### Accuracy Ceiling Rule

Accuracy acts as a ceiling on overall scores to prevent well-written incorrect content from ranking highly:

- **Accuracy < 5**: Overall capped at 4.0 (significant errors)
- **Accuracy 5-6**: Overall capped at 7.0 (needs fixes)
- **Accuracy ≥ 7**: No ceiling

## Skill Location

Skills are located in `.github/skills/` for cross-platform compatibility:

```
.github/skills/
├── council-verify/
│   ├── SKILL.md
│   └── references/
│       └── rubrics.md
├── council-review/
│   ├── SKILL.md
│   └── references/
│       └── code-review-rubric.md
└── council-gate/
    ├── SKILL.md
    └── references/
        └── ci-cd-rubric.md
```

This location works with:
- Claude Code
- VS Code Copilot
- Cursor
- Codex CLI
- Other MCP-compatible clients

## Progressive Disclosure in Practice

Skills are loaded progressively to minimize context usage:

```python
from llm_council.skills import SkillLoader

# Initialize loader
loader = SkillLoader(Path(".github/skills"))

# Level 1: Quick discovery (~100-200 tokens)
skills = loader.list_skills()  # ["council-verify", "council-review", "council-gate"]
metadata = loader.load_metadata("council-verify")
print(f"Tokens: {metadata.estimated_tokens}")  # ~150

# Level 2: Full instructions (~500-1000 tokens)
full = loader.load_full("council-verify")
print(f"Tokens: {full.estimated_tokens}")  # ~750

# Level 3: Resources on demand
rubrics = loader.load_resource("council-verify", "rubrics.md")
```

## CI/CD Integration

### GitHub Actions

```yaml
name: Council Quality Gate

on:
  pull_request:
    branches: [main, master]

jobs:
  council-gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Install LLM Council
        run: pip install llm-council-core

      - name: Run Council Gate
        env:
          OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}
        run: |
          llm-council gate \
            --snapshot ${{ github.sha }} \
            --rubric-focus Security \
            --confidence-threshold 0.8

      - name: Upload Transcript
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: council-transcript
          path: .council/logs/
```

### GitLab CI

```yaml
council-gate:
  script:
    - pip install llm-council-core
    - llm-council gate --snapshot $CI_COMMIT_SHA
  allow_failure:
    exit_codes:
      - 2  # UNCLEAR triggers manual approval
```

## Blocking Issues

Issues are classified by severity:

### Critical (automatic FAIL)
- Security vulnerabilities (CVE ≥ 7.0)
- Data loss potential
- Breaking changes without migration
- Production crash potential

### Major (request changes)
- Bugs in core functionality
- Missing error handling
- Performance regressions >50%
- Missing tests for new code

### Minor (suggestions)
- Style inconsistencies
- Naming improvements
- Documentation gaps

## Output Schema

All skills return structured output:

```json
{
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
  "weighted_score": 8.45,
  "blocking_issues": [],
  "suggestions": [
    {
      "severity": "minor",
      "file": "src/api.py",
      "line": 42,
      "message": "Consider adding type hints"
    }
  ],
  "rationale": "Code is well-structured and correct...",
  "transcript_path": ".council/logs/2025-12-31T12-00-00-abc123/"
}
```

## Transcript Audit Trail

All deliberations are saved for audit:

```
.council/logs/{timestamp}-{hash}/
├── request.json      # Input snapshot
├── stage1.json       # Model responses
├── stage2.json       # Peer reviews
├── stage3.json       # Synthesis
└── result.json       # Final verdict
```

## Related

- [ADR-034: Agent Skills Verification](../adr/ADR-034-agent-skills-verification.md)
- [ADR-016: Structured Rubric Scoring](../adr/ADR-016-structured-rubric-scoring.md)
- [MCP Server Guide](./mcp.md)
