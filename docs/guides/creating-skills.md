# Creating Custom Skills

This guide explains how to create custom agent skills for LLM Council verification workflows.

## Skill Structure

Each skill is a directory containing:

```
.github/skills/your-skill/
├── SKILL.md              # Required: Instructions and metadata
└── references/           # Optional: Additional resources
    ├── rubric.md         # Scoring guidelines
    └── examples.md       # Example usage
```

## SKILL.md Format

The SKILL.md file uses YAML frontmatter followed by markdown content:

```markdown
---
name: your-skill
description: |
  Brief description of what this skill does.
  Include keywords for discovery.
  Keywords: keyword1, keyword2, keyword3

license: MIT
compatibility: "llm-council >= 2.0"
metadata:
  category: your-category
  domain: your-domain
  author: your-name
  repository: https://github.com/your/repo

allowed-tools: "Read Grep Glob mcp:llm-council/verify"
---

# Your Skill Name

Main content and instructions here.

## When to Use

- Use case 1
- Use case 2

## Workflow

1. Step one
2. Step two
3. Step three

## Progressive Disclosure

- **Level 1**: This metadata (~X tokens)
- **Level 2**: Full instructions above (~Y tokens)
- **Level 3**: See `references/rubric.md` for detailed scoring
```

## Required Fields

| Field | Description |
|-------|-------------|
| `name` | Skill identifier (lowercase, hyphens) |
| `description` | Multi-line description with keywords |

## Optional Fields

| Field | Description |
|-------|-------------|
| `license` | License identifier (MIT, Apache-2.0, etc.) |
| `compatibility` | Version requirements |
| `metadata.category` | Skill category for filtering |
| `metadata.domain` | Domain expertise area |
| `metadata.author` | Author name or organization |
| `metadata.repository` | Source code URL |
| `allowed-tools` | Space-separated tool permissions |

## Categories and Domains

**Standard Categories**:
- `verification` - General verification tasks
- `code-review` - Code review and PR feedback
- `ci-cd` - CI/CD pipeline integration
- `documentation` - Documentation review
- `testing` - Test generation and validation

**Standard Domains**:
- `software-engineering` - General development
- `devops` - Operations and deployment
- `security` - Security assessment
- `quality` - Quality assurance

## Creating Rubrics

Rubrics define scoring criteria for your skill. Create `references/rubric.md`:

```markdown
# Your Skill Rubrics

## Core Dimensions

### Accuracy (Weight: 30%)

| Score | Anchor | Description |
|-------|--------|-------------|
| 9-10 | **Excellent** | Perfect accuracy |
| 7-8 | **Good** | Minor issues |
| 5-6 | **Mixed** | Some errors |
| 3-4 | **Poor** | Significant errors |
| 1-2 | **Critical** | Fundamental errors |

### Completeness (Weight: 25%)

[Similar table...]

## Domain-Specific Focus

### Your Focus Area

When `rubric_focus: YourFocus` is specified:

**Additional Checks:**
- Check 1
- Check 2

**Red Flags (automatic FAIL):**
- Red flag 1
- Red flag 2

## Verdict Determination

| Confidence | Verdict | Exit Code |
|------------|---------|-----------|
| ≥ threshold | PASS | 0 |
| < threshold, no blockers | UNCLEAR | 2 |
| Any blockers | FAIL | 1 |
```

## Token Efficiency Guidelines

Keep skills token-efficient with progressive disclosure:

| Level | Target | Content |
|-------|--------|---------|
| Level 1 | ~100-200 tokens | YAML frontmatter only |
| Level 2 | ~500-1000 tokens | Full SKILL.md |
| Level 3 | Variable | Resources on demand |

**Tips**:
- Keep descriptions concise
- Use bullet points over prose
- Put detailed examples in references/
- Use tables for structured data

## Using the Skill Loader

```python
from pathlib import Path
from llm_council.skills import SkillLoader

# Initialize loader
loader = SkillLoader(Path(".github/skills"))

# List available skills
skills = loader.list_skills()

# Level 1: Load metadata
metadata = loader.load_metadata("your-skill")
print(f"Name: {metadata.name}")
print(f"Category: {metadata.category}")
print(f"Tokens: {metadata.estimated_tokens}")

# Level 2: Load full content
full = loader.load_full("your-skill")
print(f"Body length: {len(full.body)}")

# Level 3: Load resources
resources = loader.list_resources("your-skill")
if "rubric.md" in resources:
    rubric = loader.load_resource("your-skill", "rubric.md")
```

## Testing Your Skill

Create integration tests to validate your skill:

```python
import pytest
from pathlib import Path
from llm_council.skills import SkillLoader

SKILLS_DIR = Path(".github/skills")

@pytest.fixture
def loader():
    return SkillLoader(SKILLS_DIR)

class TestYourSkill:
    def test_skill_discoverable(self, loader):
        """Skill should be discoverable."""
        assert "your-skill" in loader.list_skills()

    def test_metadata_loads(self, loader):
        """Metadata should load correctly."""
        metadata = loader.load_metadata("your-skill")
        assert metadata.name == "your-skill"
        assert metadata.category is not None

    def test_metadata_is_compact(self, loader):
        """Metadata should be token-efficient."""
        metadata = loader.load_metadata("your-skill")
        assert metadata.estimated_tokens < 300

    def test_full_content_loads(self, loader):
        """Full content should load."""
        full = loader.load_full("your-skill")
        assert len(full.body) > 0

    def test_resources_available(self, loader):
        """Resources should be listed."""
        resources = loader.list_resources("your-skill")
        assert "rubric.md" in resources
```

## Example: Custom Security Audit Skill

```markdown
---
name: security-audit
description: |
  Security audit using LLM Council for vulnerability detection.
  Keywords: security, audit, vulnerability, OWASP, CVE

license: MIT
compatibility: "llm-council >= 2.0"
metadata:
  category: security
  domain: security
  author: your-team

allowed-tools: "Read Grep Glob mcp:llm-council/verify"
---

# Security Audit Skill

Multi-model security assessment for code and configurations.

## When to Use

- Pre-deployment security review
- Dependency vulnerability scanning
- Configuration security audit

## Workflow

1. **Collect Targets**: Specify files or directories to audit
2. **Run Audit**: Invoke `mcp:llm-council/verify` with security focus
3. **Review Findings**: Process blocking issues and suggestions
4. **Remediate**: Address critical and major issues

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | No security issues |
| 1 | Critical vulnerabilities found |
| 2 | Manual security review needed |

## Progressive Disclosure

- **Level 1**: This metadata (~150 tokens)
- **Level 2**: Full instructions (~600 tokens)
- **Level 3**: See `references/security-rubric.md`
```

## Skill Distribution

Skills can be distributed via:

1. **In-Repository**: Commit to `.github/skills/` for project use
2. **PyPI Package**: Bundle in `src/your_package/skills/bundled/`
3. **Skills Marketplace**: Submit to community marketplaces

## Best Practices

1. **Clear Purpose**: Each skill should have one clear purpose
2. **Token Efficiency**: Keep Level 1 under 200 tokens
3. **Actionable Output**: Provide specific remediation suggestions
4. **Test Coverage**: Write integration tests for validation
5. **Documentation**: Include examples in references/
6. **Exit Codes**: Use standard 0/1/2 for CI/CD compatibility

## Related

- [Agent Skills Guide](./skills.md)
- [ADR-034: Agent Skills Verification](../adr/ADR-034-agent-skills-verification.md)
