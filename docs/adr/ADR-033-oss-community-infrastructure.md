# ADR-033: Open Source Community Infrastructure

**Status:** DRAFT
**Date:** 2025-12-28
**Context:** Scaling community engagement for LLM Council
**Depends On:** None
**Author:** @amiable-dev
**Council Review:** 2025-12-28 (High Tier, 3/4 models)

## Context

LLM Council is transitioning from an internal tool to a public open source project. To attract contributors, build a healthy community, and establish credibility with engineers evaluating the project, we need comprehensive community infrastructure that follows GitHub and OSS best practices.

### Current State

**Existing infrastructure:**
- `LICENSE` (MIT)
- `README.md` (comprehensive technical documentation)
- `CHANGELOG.md` (following Keep a Changelog format)
- `.github/CODEOWNERS` (maintainer review requirements)
- `.github/workflows/ci.yml` (tests, lint, type-check)
- `.github/workflows/publish.yml` (PyPI publishing)

**Missing standard OSS files:**
- `CONTRIBUTING.md`
- `CODE_OF_CONDUCT.md`
- `SECURITY.md`
- `SUPPORT.md`
- `GOVERNANCE.md`
- Issue and PR templates
- Discussion templates
- Community health files

**Underutilized GitHub features:**
- Discussions (disabled)
- Projects (not configured)
- Wiki (disabled)
- Releases (basic, no release notes)
- Social preview image
- Repository topics/tags
- Sponsors/funding

### Goals

1. **Discoverability**: Make the project easy to find and evaluate
2. **Accessibility**: Lower the barrier to first contribution
3. **Trust**: Establish credibility through professional community practices
4. **Engagement**: Create clear paths for community participation
5. **Sustainability**: Set up structures for long-term maintenance

## Decision

Implement comprehensive OSS community infrastructure across five areas: Documentation, GitHub Configuration, Templates, Community Channels, and LLM-Specific Practices.

### 1. Documentation Files

#### CONTRIBUTING.md

```markdown
# Contributing to LLM Council

Thank you for your interest in contributing! This document provides guidelines
and instructions for contributing to the project.

## Quick Start

1. Fork the repository
2. Clone your fork: `git clone https://github.com/YOUR-USERNAME/llm-council.git`
3. Install dependencies: `make setup` (or `uv sync --all-extras`)
4. Create a branch: `git checkout -b feature/your-feature`
5. Make changes and add tests
6. Run tests: `make test`
7. Submit a pull request

## Development Setup

### Prerequisites

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) package manager
- Docker (optional, for devcontainer)

### One-Command Setup

```bash
# Clone and setup everything
git clone https://github.com/amiable-dev/llm-council.git
cd llm-council
make setup
```

Or use the devcontainer (VS Code / GitHub Codespaces):
```bash
# Opens in fully configured container with all dependencies
code --folder-uri vscode-remote://dev-container+$(pwd)
```

### Manual Installation

```bash
# Install with dev dependencies
uv sync --all-extras

# Copy environment template
cp .env.example .env

# Verify installation
make test
```

## Testing WITHOUT API Keys

**You do not need API keys to run tests.** Our test suite uses recorded responses
(VCR cassettes) for all LLM API calls.

```bash
# Run all tests (uses mocked responses)
make test

# Run with coverage
make test-cov
```

To record new cassettes (maintainers only):
```bash
export OPENROUTER_API_KEY="..."
pytest tests/test_new_feature.py --vcr-record=new_episodes
```

## Code Style

We use [Ruff](https://github.com/astral-sh/ruff) for linting and formatting:

```bash
# Check and format code
make lint
make format
```

## Pull Request Process

1. **Sign-off your commits** (DCO): `git commit -s -m "your message"`
2. **Branch naming**: `feature/`, `fix/`, `docs/`, `refactor/`
3. **Commit messages**: Follow [Conventional Commits](https://conventionalcommits.org)
4. **PR description**: Use the PR template, explain the "why"
5. **Tests**: Add/update tests for changes
6. **Documentation**: Update relevant docs

### Developer Certificate of Origin (DCO)

By contributing, you certify that you wrote or have the right to submit the code.
All commits must be signed off:

```bash
git commit -s -m "feat(council): add custom voting weights"
```

### Commit Message Format

```
type(scope): description

[optional body]

Signed-off-by: Your Name <your.email@example.com>
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

## Good First Issues

Look for issues labeled [`good-first-issue`](https://github.com/amiable-dev/llm-council/labels/good-first-issue).
These are curated for new contributors and include clear guidance.

## Getting Help

- **Questions**: Open a [Discussion](https://github.com/amiable-dev/llm-council/discussions)
- **Bugs**: File an [Issue](https://github.com/amiable-dev/llm-council/issues)
- **Chat**: Join our [Discord](https://discord.gg/llm-council)

## Recognition

Contributors are recognized in:
- Release notes
- CONTRIBUTORS.md file
- GitHub contributor graphs

Thank you for contributing!
```

#### GOVERNANCE.md

```markdown
# Governance

LLM Council is an open source project maintained by Amiable with community input.

## Roles

### Users
Anyone using LLM Council. Can report bugs, request features, and participate in discussions.

### Contributors
Anyone who has had a PR merged. Can participate in design discussions and vote on RFCs.

### Maintainers
Trusted contributors with merge access. Responsible for:
- Reviewing and merging PRs
- Triaging issues
- Participating in release decisions
- Mentoring new contributors

**Current Maintainers:**
- @christopherjoseph (Amiable)

### Core Team
Maintainers with admin access. Make final decisions on:
- Project direction
- Breaking changes
- New maintainer nominations
- License changes

## Becoming a Maintainer

Contributors who demonstrate:
1. **Sustained contribution** (3+ quality PRs over 3+ months)
2. **Code review quality** (helpful, constructive reviews)
3. **Community engagement** (helping others in issues/discussions)
4. **Alignment with project values**

...may be nominated for maintainership by any existing maintainer. Nominations are
discussed privately among maintainers and require unanimous approval.

## Decision Making

- **Minor changes**: Single maintainer approval
- **Significant changes**: ADR review + maintainer consensus
- **Breaking changes**: ADR + Core Team approval + 2-week comment period
- **Governance changes**: Core Team approval + 4-week comment period

## Code of Conduct

All participants must follow our [Code of Conduct](CODE_OF_CONDUCT.md).
```

#### CODE_OF_CONDUCT.md

Adopt the [Contributor Covenant v2.1](https://www.contributor-covenant.org/version/2/1/code_of_conduct/), the industry standard used by projects like Kubernetes, Rails, and Swift.

**Key enforcement details:**
- Contact: conduct@amiable.dev (or GitHub issue for now)
- Enforcement: Maintainers have authority to remove, edit, or reject contributions
- Scope: Project spaces and public representation

#### SECURITY.md

```markdown
# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.17.x  | :white_check_mark: |
| < 0.17  | :x:                |

## Reporting a Vulnerability

**Do not report security vulnerabilities through public GitHub issues.**

Instead, please report them via:

1. **GitHub Security Advisories**: Use the "Report a vulnerability" button
   in the Security tab of this repository (preferred)

2. **Email**: security@amiable.dev

Please include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

### Response Timeline

- **Acknowledgment**: Within 48 hours
- **Initial Assessment**: Within 7 days
- **Resolution Target**: Within 30 days for critical issues

### Safe Harbor

We consider security research conducted in accordance with this policy to be:
- Authorized
- Exempt from DMCA anti-circumvention provisions
- Not subject to legal action from us

## Supply Chain Security

- Releases are signed
- Dependencies are reviewed before major upgrades
- SBOM (Software Bill of Materials) available for each release

Thank you for helping keep LLM Council secure!
```

#### SUPPORT.md

```markdown
# Support

## Getting Help

### Documentation

- [README](README.md) - Installation and quick start
- [Documentation Site](https://docs.council.amiable.dev) - Full documentation
- [ADRs](docs/adr/) - Architecture decisions
- [Blog](docs/blog/) - Technical deep-dives

### Community Support

- **GitHub Discussions**: Best for questions, ideas, and general discussion
  - [Q&A](https://github.com/amiable-dev/llm-council/discussions/categories/q-a)
  - [Ideas](https://github.com/amiable-dev/llm-council/discussions/categories/ideas)
  - [Show & Tell](https://github.com/amiable-dev/llm-council/discussions/categories/show-and-tell)

- **Discord**: Real-time chat and community
  - Join: https://discord.gg/llm-council
  - Use the #support forum for questions

### Bug Reports

Found a bug? Please [open an issue](https://github.com/amiable-dev/llm-council/issues/new?template=bug_report.md).

### Feature Requests

Have an idea? Start a [discussion](https://github.com/amiable-dev/llm-council/discussions/categories/ideas) first.

## Commercial Support

For commercial support, training, or consulting:
- Email: enterprise@amiable.dev
- See: [Council Cloud](https://council.amiable.dev) (hosted solution)
```

#### CITATION.cff

```yaml
cff-version: 1.2.0
message: "If you use this software in research, please cite it as below."
type: software
title: "LLM Council: Multi-LLM Deliberation System"
authors:
  - family-names: "Joseph"
    given-names: "Christopher"
    affiliation: "Amiable"
repository-code: "https://github.com/amiable-dev/llm-council"
url: "https://council.amiable.dev"
license: MIT
keywords:
  - llm
  - multi-agent
  - consensus
  - peer-review
  - deliberation
```

### 2. GitHub Repository Configuration

#### Repository Settings

| Setting | Value | Rationale |
|---------|-------|-----------|
| **Description** | "Multi-LLM deliberation system with peer review. Available as Python library, MCP server, or HTTP API." | Clear, keyword-rich |
| **Website** | https://docs.council.amiable.dev | Link to docs |
| **Topics** | `llm`, `ai`, `multi-agent`, `mcp`, `consensus`, `peer-review`, `python`, `openrouter`, `claude`, `gpt`, `langchain`, `autogen` | Discoverability |
| **Discussions** | Enabled | Community Q&A |
| **Wiki** | Disabled | Use docs/ instead |
| **Projects** | Enabled | Roadmap visibility |
| **Sponsors** | Enabled | Sustainability |

#### Issue Labels (Triage Taxonomy)

| Label | Color | Description |
|-------|-------|-------------|
| `good-first-issue` | #7057ff | Good for newcomers |
| `help-wanted` | #008672 | Extra attention needed |
| `needs-triage` | #d93f0b | Needs maintainer review |
| `needs-repro` | #fbca04 | Needs reproduction steps |
| `bug` | #d73a4a | Something isn't working |
| `enhancement` | #a2eeef | New feature or request |
| `documentation` | #0075ca | Improvements to docs |
| `breaking-change` | #b60205 | Incompatible API change |
| `wontfix` | #ffffff | Will not be addressed |
| `duplicate` | #cfd3d7 | Duplicate issue |

#### Social Preview Image

Create a 1280x640px image featuring:
- LLM Council logo
- Tagline: "Consensus through deliberation"
- Visual diagram of 3-stage pipeline (Generate → Critique → Synthesize)
- Clean, professional design in GitHub-friendly colors

#### Branch Protection (master)

- Require PR reviews (1 maintainer)
- Require status checks (CI, lint, DCO)
- Require conversation resolution
- Do not allow force pushes
- Do not allow deletions

### 3. Issue and PR Templates

#### `.github/ISSUE_TEMPLATE/bug_report.md`

```markdown
---
name: Bug Report
about: Report a bug to help us improve
title: '[BUG] '
labels: 'bug, needs-triage'
assignees: ''
---

## Description
A clear description of the bug.

## Steps to Reproduce
1. Install llm-council with `pip install llm-council-core`
2. Configure with...
3. Run...
4. See error

## Expected Behavior
What you expected to happen.

## Actual Behavior
What actually happened.

## Environment
- OS: [e.g., macOS 14.0, Ubuntu 22.04]
- Python version: [e.g., 3.12.0]
- llm-council version: [e.g., 0.17.0]
- Gateway: [e.g., OpenRouter, Direct]

## Logs
```
Paste relevant logs here
```

## Additional Context
Any other context about the problem.
```

#### `.github/ISSUE_TEMPLATE/feature_request.md`

```markdown
---
name: Feature Request
about: Suggest an idea for this project
title: '[FEATURE] '
labels: 'enhancement, needs-triage'
assignees: ''
---

## Problem Statement
A clear description of the problem this feature would solve.

## Proposed Solution
How you think this should work.

## Alternatives Considered
Other solutions you've thought about.

## Additional Context
Any other context, mockups, or examples.

## Would you be willing to contribute this?
- [ ] Yes, I'd like to implement this
- [ ] I'd like to help but need guidance
- [ ] No, just suggesting
```

#### `.github/ISSUE_TEMPLATE/config.yml`

```yaml
blank_issues_enabled: false
contact_links:
  - name: Questions & Discussion
    url: https://github.com/amiable-dev/llm-council/discussions
    about: Please ask and answer questions here
  - name: Discord Community
    url: https://discord.gg/llm-council
    about: Chat with the community in real-time
  - name: Documentation
    url: https://docs.council.amiable.dev
    about: Check the docs first
```

#### `.github/PULL_REQUEST_TEMPLATE.md`

```markdown
## Summary

Brief description of changes (1-2 sentences).

## Motivation

Why is this change needed? Link to issue if applicable.

Fixes #(issue number)

## Changes

- Change 1
- Change 2
- Change 3

## Testing

How were these changes tested?

- [ ] Unit tests added/updated
- [ ] Integration tests added/updated (mocked)
- [ ] Manual testing performed

## Checklist

- [ ] Commits are signed off (`git commit -s`)
- [ ] Code follows project style guidelines
- [ ] Tests pass locally (`make test`)
- [ ] Lint passes (`make lint`)
- [ ] Documentation updated (if applicable)
- [ ] ADR created (for significant changes)
- [ ] Changelog updated

## Screenshots/Recordings

If applicable, add screenshots or recordings.
```

### 4. GitHub Discussions Configuration

Enable Discussions with these categories:

| Category | Description | Format |
|----------|-------------|--------|
| **Announcements** | Project news and updates | Announcement |
| **Q&A** | Ask questions, get answers | Question/Answer |
| **Ideas** | Feature ideas and proposals | Open |
| **Show and Tell** | Share what you've built | Open |
| **General** | General discussion | Open |

### 5. README Badge Updates

Add these badges to README.md header:

```markdown
[![PyPI version](https://img.shields.io/pypi/v/llm-council-core.svg)](https://pypi.org/project/llm-council-core/)
[![Python versions](https://img.shields.io/pypi/pyversions/llm-council-core.svg)](https://pypi.org/project/llm-council-core/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![CI](https://github.com/amiable-dev/llm-council/actions/workflows/ci.yml/badge.svg)](https://github.com/amiable-dev/llm-council/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/amiable-dev/llm-council/branch/master/graph/badge.svg)](https://codecov.io/gh/amiable-dev/llm-council)
[![Docs](https://img.shields.io/badge/docs-online-blue)](https://docs.council.amiable.dev)
[![Discord](https://img.shields.io/discord/DISCORD_SERVER_ID?label=Discord&logo=discord)](https://discord.gg/llm-council)
```

### 6. Discord Server Structure (Streamlined)

**Information**
- `#welcome` - Server rules, getting started, links to docs
- `#announcements` - Project updates (manual, not webhook spam)

**Community**
- `#general` - General discussion
- `#showcase` - Share your projects using LLM Council

**Support (Forum Channel)**
- `#support` - Forum-style support threads (searchable, organized)

**Development**
- `#contributors` - Contributor discussion (role-gated)

**Moderation:**
- Anti-spam bot (MEE6 or Dyno)
- Role: `@Contributor` (auto-assigned from GitHub)
- No GitHub webhook firehose (use manual updates)

### 7. GitHub Funding

#### `.github/FUNDING.yml`

```yaml
github: [amiable-dev]
```

### 8. DCO Enforcement

Install the [DCO GitHub App](https://github.com/apps/dco) to automatically check that all commits are signed off.

### 9. Documentation Site

Deploy searchable documentation using MkDocs Material:

```yaml
# mkdocs.yml
site_name: LLM Council
site_url: https://docs.council.amiable.dev
repo_url: https://github.com/amiable-dev/llm-council
theme:
  name: material
  features:
    - navigation.instant
    - navigation.tabs
    - search.suggest
nav:
  - Home: index.md
  - Getting Started:
    - Installation: getting-started/installation.md
    - Quick Start: getting-started/quickstart.md
    - Configuration: getting-started/configuration.md
  - Guides:
    - MCP Server: guides/mcp.md
    - HTTP API: guides/http-api.md
    - Python Library: guides/python.md
  - Architecture:
    - Overview: architecture/overview.md
    - ADRs: architecture/adrs.md
  - Blog: blog/index.md
  - Contributing: contributing.md
```

### 10. Devcontainer

#### `.devcontainer/devcontainer.json`

```json
{
  "name": "LLM Council Dev",
  "image": "mcr.microsoft.com/devcontainers/python:3.12",
  "features": {
    "ghcr.io/astral-sh/uv:latest": {}
  },
  "postCreateCommand": "uv sync --all-extras",
  "customizations": {
    "vscode": {
      "extensions": [
        "charliermarsh.ruff",
        "ms-python.python",
        "ms-python.vscode-pylance"
      ]
    }
  },
  "forwardPorts": [8001]
}
```

### 11. Makefile (Developer Experience)

```makefile
.PHONY: setup test lint format

setup:
	uv sync --all-extras
	cp -n .env.example .env || true
	@echo "Setup complete! Run 'make test' to verify."

test:
	uv run pytest tests/ -v

test-cov:
	uv run pytest tests/ -v --cov=src --cov-report=html

lint:
	uv run ruff check src/ tests/

format:
	uv run ruff format src/ tests/

docs:
	uv run mkdocs serve

docs-build:
	uv run mkdocs build
```

## Implementation Phases (Revised)

### Phase 1: Visual & Discovery (Week 1)
- [ ] Create social preview image (1280x640)
- [ ] Update repository description and topics
- [ ] Create roadmap project board (public)
- [ ] Add README badges
- [ ] Create CITATION.cff

### Phase 2: Core Documentation (Week 1)
- [ ] Create CONTRIBUTING.md (with testing-without-keys section)
- [ ] Create CODE_OF_CONDUCT.md
- [ ] Create SECURITY.md
- [ ] Create SUPPORT.md
- [ ] Create GOVERNANCE.md
- [ ] Create .env.example

### Phase 3: Developer Experience (Week 2)
- [ ] Create Makefile with common commands
- [ ] Create .devcontainer/devcontainer.json
- [ ] Set up VCR cassettes for mocked tests
- [ ] Create .github/ISSUE_TEMPLATE/* files
- [ ] Create .github/PULL_REQUEST_TEMPLATE.md
- [ ] Create .github/FUNDING.yml
- [ ] Install DCO GitHub App

### Phase 4: GitHub Configuration (Week 2)
- [ ] Enable Discussions with categories
- [ ] Configure issue labels (triage taxonomy)
- [ ] Configure branch protection rules
- [ ] Enable Sponsors

### Phase 5: Documentation Site (Week 3)
- [ ] Set up MkDocs Material
- [ ] Deploy to docs.council.amiable.dev
- [ ] Migrate relevant README content
- [ ] Add search functionality

### Phase 6: Discord Setup (Week 4 - After Docs Stable)
- [ ] Create Discord server
- [ ] Configure channels (streamlined structure)
- [ ] Set up moderation bot
- [ ] Add support forum channel
- [ ] Update all docs with Discord link

## Consequences

### Positive

- **Lower contribution barrier**: Clear guidelines, mocked tests, one-command setup
- **Professional appearance**: Complete community profile signals mature project
- **Better issue quality**: Templates ensure necessary information is provided
- **Searchable knowledge**: Docs site + Discussions build SEO footprint
- **Governance clarity**: Clear path from user → contributor → maintainer
- **Research credibility**: CITATION.cff enables academic citations
- **Sustainability**: Funding options support long-term maintenance

### Negative

- **Maintenance overhead**: More files to keep updated
- **Moderation burden**: Discord requires active moderation (delayed to Phase 6)
- **Response expectations**: Public channels create support expectations

### Neutral

- **DCO over CLA**: Using DCO (sign-off) initially, simpler and sufficient for most OSS
- **Wiki disabled**: Keeping docs in MkDocs for version control and search

## Alternatives Considered

### 1. Minimal Community Files Only
Just add CONTRIBUTING.md and CODE_OF_CONDUCT.md.

**Rejected**: Misses opportunity to establish professional community infrastructure early.

### 2. Use GitHub Discussions Only (No Discord)
Rely entirely on GitHub for community.

**Considered but Delayed**: Discord adds value for real-time community but should come after async infrastructure is stable.

### 3. Use Slack Instead of Discord
Enterprise-friendly option.

**Rejected**: Discord is free, has better OSS community features, and is standard for developer communities.

### 4. Full CLA Requirement
Require Contributor License Agreement for all contributions.

**Rejected initially**: DCO (commit sign-off) is simpler and sufficient for most OSS projects. Can add CLA later if commercial needs require it.

### 5. GitHub Webhooks in Discord
Pipe all GitHub activity to Discord.

**Rejected**: Creates noise that users mute, leading to dead channels. Use manual announcements instead.

## References

- [GitHub Community Profile](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions)
- [Open Source Guides](https://opensource.guide/)
- [Contributor Covenant](https://www.contributor-covenant.org/)
- [Developer Certificate of Origin](https://developercertificate.org/)
- [Keep a Changelog](https://keepachangelog.com/)
- [Conventional Commits](https://www.conventionalcommits.org/)
- [MkDocs Material](https://squidfunk.github.io/mkdocs-material/)
- [VCR.py for API Mocking](https://vcrpy.readthedocs.io/)
- [Citation File Format](https://citation-file-format.github.io/)
