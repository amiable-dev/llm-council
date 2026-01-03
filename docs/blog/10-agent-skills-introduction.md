# Introducing Agent Skills: Multi-Model Consensus for AI Code Assistants

*Published: December 2025*

---

Your AI code assistant just wrote 500 lines of code. Is it correct? Is it secure? Does it follow your team's patterns?

You could review it yourself. Or you could let multiple AI models deliberate and reach consensus.

That's what Agent Skills bring to LLM Council.

## The Problem with Single-Model Verification

AI code assistants are powerful, but they have a fundamental limitation: **they can't reliably verify their own work**.

A model that confidently generates buggy code will confidently assert that the code is correct. Self-review doesn't catch the blind spots because the same reasoning that produced the bug will miss it on review.

The traditional solution? Human review. But human review doesn't scale, and humans miss things too.

## Multi-Model Consensus: A Better Way

What if instead of one model reviewing its own work, you had *multiple* models:

1. **Generate independent responses** to the same verification question
2. **Anonymously evaluate** each other's assessments
3. **Synthesize** a final verdict from the collective deliberation

This is LLM Council's core pattern. Now we've packaged it into **Agent Skills** that any AI code assistant can use.

## Three Skills, Three Use Cases

### council-verify: General Work Verification

```bash
mcp://llm-council/verify --snapshot abc123 --file-paths "src/main.py"
```

Use when you need to verify that implementation matches requirements. The council evaluates:

- **Accuracy** (30%): Is the implementation correct?
- **Completeness** (25%): Are all requirements addressed?
- **Clarity** (20%): Is the code understandable?
- **Conciseness** (15%): Is it appropriately sized?
- **Relevance** (10%): Does it solve the right problem?

### council-review: Code Review with Security Focus

```bash
council-review --file-paths "src/api.py" --rubric-focus Security
```

Specialized for PR reviews with **35% accuracy weight** (higher than general verification). Focus areas include:

- **Security**: SQL injection, XSS, secrets exposure, authentication flaws
- **Performance**: Algorithm complexity, N+1 queries, memory leaks
- **Testing**: Coverage gaps, flaky tests, missing edge cases

### council-gate: CI/CD Quality Gates

```yaml
# GitHub Actions
- name: Council Quality Gate
  run: |
    llm-council gate \
      --snapshot ${{ github.sha }} \
      --rubric-focus Security \
      --confidence-threshold 0.8
```

Returns structured exit codes for pipeline integration:

| Exit Code | Verdict | Action |
|-----------|---------|--------|
| `0` | PASS | Continue deployment |
| `1` | FAIL | Block deployment |
| `2` | UNCLEAR | Require human review |

## Why This Matters: The Accuracy Ceiling Rule

Here's a key insight from [ADR-016](../adr/ADR-016-structured-rubric-scoring.md): well-written incorrect answers are *more dangerous* than poorly-written correct ones.

A confident, articulate response that's factually wrong can fool humans. It can also fool single-model self-review.

Multi-model consensus catches this. If one model generates a plausible-sounding bug, other models with different training biases will likely catch it during peer review.

We enforce this with the **accuracy ceiling rule**:

```python
def apply_accuracy_ceiling(accuracy: float, weighted_score: float) -> float:
    """Accuracy caps the maximum possible score."""
    if accuracy < 5:
        return min(weighted_score, 4.0)  # Significant errors
    if accuracy < 7:
        return min(weighted_score, 7.0)  # Mixed accuracy
    return weighted_score  # No ceiling
```

A beautifully written, highly-ranked response with an accuracy score of 4 gets capped at 4.0 overall. No amount of eloquence can overcome fundamental incorrectness.

## Progressive Disclosure: Token Efficiency

Skills use progressive disclosure to minimize context window usage:

| Level | Content | Tokens |
|-------|---------|--------|
| **Level 1** | Metadata only | ~100-200 |
| **Level 2** | Full SKILL.md | ~500-1000 |
| **Level 3** | Resources (rubrics) | Variable |

Your AI assistant loads only what it needs:

```python
from llm_council.skills import SkillLoader

loader = SkillLoader(Path(".github/skills"))

# Level 1: Quick discovery
metadata = loader.load_metadata("council-verify")
print(f"Tokens: {metadata.estimated_tokens}")  # ~150

# Level 2: Full instructions (only when needed)
full = loader.load_full("council-verify")

# Level 3: Resources on demand
rubrics = loader.load_resource("council-verify", "rubrics.md")
```

## Cross-Platform Compatibility

Skills live in `.github/skills/`, a location supported by:

- Claude Code
- VS Code Copilot
- Cursor
- Codex CLI
- Other MCP-compatible clients

```
.github/skills/
├── council-verify/
│   ├── SKILL.md
│   └── references/rubrics.md
├── council-review/
│   ├── SKILL.md
│   └── references/code-review-rubric.md
└── council-gate/
    ├── SKILL.md
    └── references/ci-cd-rubric.md
```

Install via PyPI and the skills come bundled:

```bash
pip install llm-council-core
llm-council install-skills --target .github/skills
```

## The Audit Trail

Every verification produces a complete transcript:

```
.council/logs/2025-12-31T10-30-00-abc123/
├── request.json      # Input snapshot
├── stage1.json       # Individual model responses
├── stage2.json       # Peer reviews (anonymized)
├── stage3.json       # Chairman synthesis
└── result.json       # Final verdict
```

This enables:

- **Reproducibility**: Re-run the same verification
- **Debugging**: Understand why a verdict was reached
- **Compliance**: Audit trail for regulated industries
- **Improvement**: Train on disagreement patterns

## Getting Started

### 1. Install LLM Council

```bash
pip install llm-council-core
```

### 2. Configure API Key

```bash
export OPENROUTER_API_KEY=sk-or-v1-...
```

### 3. Use Skills in Your AI Assistant

Claude Code example:

```
/council-verify --snapshot HEAD --file-paths "src/feature.py"
```

Or via MCP:

```bash
mcp://llm-council/verify \
  --snapshot $(git rev-parse HEAD) \
  --file-paths "src/feature.py"
```

### 4. Integrate with CI/CD

```yaml
# .github/workflows/council-gate.yml
name: Council Quality Gate
on: [pull_request]

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: amiable-dev/llm-council-action@v1
        with:
          snapshot: ${{ github.sha }}
          confidence-threshold: 0.8
        env:
          OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}
```

The [llm-council-action](https://github.com/amiable-dev/llm-council-action) provides:

- **Fast execution** via pip caching (~3-5s after first run)
- **Rich outputs** (verdict, confidence, summary)
- **GitHub Step Summary** with collapsible details
- **PR comments** with evaluation results

## What's Next?

Agent Skills are the foundation for AI-assisted verification workflows. Coming soon:

- **Security audit skill**: Specialized for vulnerability detection
- **Documentation review skill**: Verify docs match code
- **Test generation skill**: Generate tests with council consensus
- **Custom skill marketplace**: Share skills with the community

## Try It Now

```bash
# Clone and explore
git clone https://github.com/amiable-dev/llm-council.git
cd llm-council

# Check out the skills
ls .github/skills/

# Read the detailed guide
cat docs/guides/skills.md
```

---

*This post introduces [ADR-034: Agent Skills Integration for Work Verification](../adr/ADR-034-agent-skills-verification.md).*

*LLM Council is open source: [github.com/amiable-dev/llm-council](https://github.com/amiable-dev/llm-council)*
