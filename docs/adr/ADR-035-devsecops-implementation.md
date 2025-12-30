# ADR-035: DevSecOps Implementation for Open Source

**Status:** ACCEPTED (v2)
**Date:** 2025-12-28
**Context:** Security automation for OSS project with zero-cost contributor experience
**Depends On:** ADR-033 (OSS Community Infrastructure)
**Author:** @amiable-dev
**Council Review v1:** 2025-12-28 (Reasoning Tier: openai/o1, google/gemini-3-pro-preview)
**Council Review v2:** 2025-12-28 (High Tier: gpt-5.2, claude-opus-4.5, gemini-3-pro-preview, grok-4.1-fast)

## Context

As LLM Council transitions to a public open source project (ADR-033), we need comprehensive security automation that:

1. **Protects users** from vulnerabilities in dependencies and code
2. **Maintains zero cost** for OSS contributors (no paid tool requirements)
3. **Minimizes friction** in the contribution workflow
4. **Provides visibility** into security posture for evaluators

### Current State

**Existing security measures:**
- `.github/workflows/ci.yml` - Basic linting and tests
- `SECURITY.md` - Vulnerability reporting process (ADR-033)
- Manual dependency updates

**Missing security automation:**
- Dependency vulnerability scanning
- Static Application Security Testing (SAST)
- Secret detection in commits
- Container image scanning (for future Docker distribution)
- Software Bill of Materials (SBOM) generation
- Dynamic Application Security Testing (DAST) for HTTP API

### Tool Landscape

The team has experience with enterprise security tools:

| Tool | Category | OSS-Free Tier | Notes |
|------|----------|---------------|-------|
| **Snyk** | SCA, SAST, Container | Yes (limited) | 200 tests/month on free tier |
| **SonarCloud** | SAST, Code Quality | Yes (public repos) | Free for public OSS |
| **Aqua Trivy** | Container, SCA | Yes (fully free) | Apache 2.0, CLI-based |
| **Bright (NeuraLegion)** | DAST | Limited free | Enterprise-focused |
| **GitHub CodeQL** | SAST | Yes (public repos) | Native GitHub integration |
| **GitHub Dependabot** | SCA | Yes (free) | Native, automatic PRs |
| **GitHub Secret Scanning** | Secrets | Yes (public repos) | Native, partner alerts |
| **Gitleaks** | Secrets | Yes (fully free) | Pre-commit hook friendly |
| **Semgrep** | SAST | Yes (community rules) | Fast, extensible |
| **StackHawk** | DAST | Limited free | Developer-friendly DAST |

### Design Principles

1. **GitHub-Native First**: Prefer GitHub's built-in security features
2. **Defense in Depth**: Multiple overlapping tools catch different issues
3. **Shift Left**: Catch issues in PRs before merge, not after release
4. **Non-Blocking by Default**: Security findings are advisory in PRs, blocking only for critical/high severity
5. **Zero Contributor Cost**: No paid accounts or API keys required to contribute
6. **Transparent Security**: Public security posture (badges, scorecards)
7. **Fork-Aware Design**: PR checks must work without secrets (forks don't have access to repo secrets)

## Decision

Implement a layered DevSecOps pipeline using free-for-OSS tools, prioritizing GitHub-native features supplemented by best-in-class open source scanners.

### Architecture: Security Layers

```
┌─────────────────────────────────────────────────────────────────┐
│                     Layer 1: Pre-Commit                         │
│  Developer workstation (optional but recommended)               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   Gitleaks   │  │    Ruff      │  │   Semgrep    │          │
│  │   (secrets)  │  │   (lint)     │  │   (SAST)     │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Layer 2: Pull Request                       │
│  GitHub Actions (runs on every PR - fork-compatible)            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   CodeQL     │  │  Dependabot  │  │  Dep Review  │          │
│  │   (SAST)     │  │    (SCA)     │  │  (license)   │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│  ┌──────────────┐  ┌──────────────┐                            │
│  │   Semgrep    │  │   Gitleaks   │                            │
│  │ (SAST+LLM)   │  │  (secrets)   │                            │
│  └──────────────┘  └──────────────┘                            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Layer 3: Main Branch                        │
│  GitHub Actions (runs on merge to master)                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  SonarCloud  │  │    Snyk      │  │    Trivy     │          │
│  │ (full scan)  │  │  (monitor)   │  │    (SCA)     │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│  ┌──────────────┐                                              │
│  │   SBOM Gen   │                                              │
│  │  (CycloneDX) │                                              │
│  └──────────────┘                                              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Layer 4: Release                            │
│  GitHub Actions (runs on tag/release)                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │    Trivy     │  │   Cosign     │  │    SBOM      │          │
│  │ (container)  │  │  (signing)   │  │  (attach)    │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Layer 5: Runtime (Future)                   │
│  For HTTP API deployment (Council Cloud)                        │
│  ┌──────────────┐  ┌──────────────┐                            │
│  │  StackHawk   │  │   Runtime    │                            │
│  │   (DAST)     │  │  Monitoring  │                            │
│  └──────────────┘  └──────────────┘                            │
└─────────────────────────────────────────────────────────────────┘
```

### Tool Selection Rationale

#### 1. Software Composition Analysis (SCA)

**Primary: GitHub Dependabot** (Native)
- Automatic PRs for vulnerable dependencies
- Zero configuration for public repos
- Integrated security advisories

**Secondary: Trivy** (Apache 2.0)
- Comprehensive vulnerability database (NVD, GitHub Advisory, etc.)
- Scans Python dependencies, containers, IaC
- Fast CI execution (~30s for Python project)
- No API keys required

**Monitoring: Snyk** (Free tier)
- Continuous monitoring of `master` branch
- Remediation advice and fix PRs
- Free for OSS: 200 tests/month sufficient for our cadence

#### 2. Static Application Security Testing (SAST)

**Primary: GitHub CodeQL** (Native)
- Deep semantic analysis for Python
- Queries for SQL injection, command injection, XSS
- Native GitHub integration, appears in Security tab
- Free for public repositories

**Secondary: Semgrep** (Community rules)
- Fast pattern-based scanning (~10s)
- Community rules for Python security
- Custom rules for LLM-specific patterns (prompt injection)
- OSS (LGPL-2.1), runs locally

**Quality Gate: SonarCloud** (Free for public repos)
- Comprehensive code quality + security
- Technical debt tracking
- Quality gate blocking for critical issues
- Free for public open source

#### 3. Secret Detection

**Primary: GitHub Secret Scanning** (Native)
- Partner program alerts (AWS, OpenAI, etc.)
- Push protection (blocks commits with secrets)
- Zero configuration

**Secondary: Gitleaks** (MIT License)
- Pre-commit hook for local detection
- CI validation for comprehensive patterns
- Custom patterns for OpenRouter, etc.
- Fully open source, no API keys

#### 4. Container Security (Future)

**Primary: Trivy** (Apache 2.0)
- Image vulnerability scanning
- Dockerfile best practice checks
- SBOM generation in CycloneDX/SPDX format
- No API keys required

#### 5. SBOM (Software Bill of Materials)

**Tool: CycloneDX Python** (Apache 2.0)
- Generate SBOM from pyproject.toml/uv.lock
- Attach to GitHub releases
- Required for supply chain transparency

#### 6. DAST (Future - HTTP API)

**Deferred**: DAST for HTTP API (`/v1/council/run`) will be implemented when Council Cloud launches. Options:
- StackHawk (free tier for OSS)
- OWASP ZAP (fully open source)

#### 7. LLM-Specific Security (Council Recommendation)

**Model Serialization Attacks**:
- If loading model weights (Pickle/PyTorch), use **Modelscan** or **Picklescan**
- Standard SAST tools are blind to malicious serialization

**Prompt Injection Defense**:
- Custom Semgrep rules for prompt template validation
- Test suite for prompt integrity (future)

**License Compliance**:
- Configure Trivy or Dependency Review to block GPL/AGPL dependencies
- MIT license requires freedom from viral license contamination

#### 7b. LLM-Specific Security Vectors (Council v2 Addition)

LLM orchestration libraries face unique attack vectors beyond standard AppSec:

**Indirect Prompt Injection (RAG)**:
- Malicious content in retrieved documents hijacks model instructions
- Mitigation: Separate data vs instructions; treat retrieved text as untrusted input
- Custom Semgrep rules to detect unsanitized retrieval → prompt flows

**Tool/Function Calling Abuse**:
- If library allows LLM to call tools (HTTP, shell, DB), risks include:
  - SSRF via HTTP tools
  - Command injection via shell execution
  - Data exfiltration via broad tool permissions
- Mitigation: Tool allowlists, argument validation, sandboxing, audit logs

**Prompt/Log Leakage**:
- Orchestrators often log full prompt context for debugging
- Risks: API key exposure, PII leakage, proprietary prompt theft
- Mitigation: Redaction filters, structured logging with sensitive-field tagging
- Default: "no prompt logging" unless explicitly enabled

**Cross-Session State Bleed**:
- Shared caches, vector results, or tool outputs can leak across users
- Mitigation: Clear session boundaries, explicit scoping, thread-safe storage

**Output Injection**:
- Model outputs rendered in Markdown/HTML or executed as code
- Risks: XSS in UIs, command injection if outputs used unsafely
- Mitigation: Output encoding, "never execute model output" documentation

**Custom Semgrep Rules (Implement in Phase 2)**:
```yaml
rules:
  - id: unsafe-pickle-load
    patterns:
      - pattern: pickle.load(...)
      - pattern: torch.load(..., weights_only=False)
    message: "Unsafe deserialization - use safetensors or weights_only=True"
    severity: ERROR

  - id: llm-output-to-exec
    patterns:
      - pattern: exec($LLM_OUTPUT)
      - pattern: eval($LLM_OUTPUT)
    message: "Never execute LLM output"
    severity: ERROR

  - id: unbounded-llm-loop
    pattern: |
      while True:
        ... = $LLM.generate(...)
    message: "Add iteration limit to LLM generation loop"
    severity: WARNING
```

#### 8. GitHub Dependency Review (Council Addition)

**Tool: Dependency Review Action** (Native)
- Blocks PRs that introduce vulnerabilities
- License compliance checking
- No secrets required (fork-compatible)

### Implementation: GitHub Actions Workflows

#### `.github/workflows/security.yml`

```yaml
name: Security Scanning

on:
  push:
    branches: [master]
  pull_request:
    branches: [master]
  schedule:
    # Run weekly on Monday at 9am UTC
    - cron: '0 9 * * 1'

permissions:
  contents: read
  security-events: write
  actions: read
  pull-requests: read  # Required for dependency review

jobs:
  # ============================================================
  # Layer 2: PR Security Checks (Fork-Compatible - No Secrets)
  # These jobs work on external contributor PRs from forks
  # NOTE: Trivy moved to Layer 3 to avoid anonymous rate limits
  # ============================================================

  codeql:
    name: CodeQL Analysis
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Initialize CodeQL
        uses: github/codeql-action/init@v3
        with:
          languages: python
          # Council recommendation: use security-extended, not security-and-quality
          # Avoids blocking PRs on opinionated style issues
          queries: security-extended

      - name: Perform CodeQL Analysis
        uses: github/codeql-action/analyze@v3
        with:
          category: "/language:python"

  semgrep:
    name: Semgrep SAST
    runs-on: ubuntu-latest
    container:
      image: semgrep/semgrep:1.96.0  # Pinned version
    steps:
      - uses: actions/checkout@v4

      # Semgrep for custom rules and fast pattern matching
      # CodeQL handles deep semantic analysis (avoid duplicates)
      - name: Run Semgrep
        run: semgrep scan --config auto --config .semgrep/ --sarif --output semgrep.sarif . || true

      - name: Upload Semgrep results
        uses: github/codeql-action/upload-sarif@v3
        if: always()
        with:
          sarif_file: semgrep.sarif

  gitleaks:
    name: Secret Detection
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Run Gitleaks
        uses: gitleaks/gitleaks-action@v2.3.7  # Pinned version, no license needed for OSS
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}

  # Council Addition: Dependency Review for license compliance
  dependency-review:
    name: Dependency Review
    runs-on: ubuntu-latest
    if: github.event_name == 'pull_request'
    steps:
      - uses: actions/checkout@v4

      - name: Dependency Review
        uses: actions/dependency-review-action@v4
        with:
          # Use config file for license rules (allows build-time action exceptions)
          config-file: ./.github/dependency-review-config.yml

  # ============================================================
  # Layer 3: Main Branch (post-merge, requires secrets)
  # These jobs only run after merge, not on fork PRs
  # ============================================================

  trivy-sca:
    name: Trivy Dependency Scan
    runs-on: ubuntu-latest
    if: github.event_name == 'push' && github.ref == 'refs/heads/master'
    steps:
      - uses: actions/checkout@v4

      - name: Run Trivy vulnerability scanner
        uses: aquasecurity/trivy-action@0.28.0  # Pinned version
        with:
          scan-type: 'fs'
          scan-ref: '.'
          format: 'sarif'
          output: 'trivy-results.sarif'
          severity: 'CRITICAL,HIGH,MEDIUM'

      - name: Upload Trivy scan results
        uses: github/codeql-action/upload-sarif@v3
        if: always()
        with:
          sarif_file: 'trivy-results.sarif'

  sonarcloud:
    name: SonarCloud Analysis
    runs-on: ubuntu-latest
    if: github.event_name == 'push' && github.ref == 'refs/heads/master'
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: SonarQube Scan
        uses: SonarSource/sonarqube-scan-action@v6  # Pinned version
        env:
          SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}

  snyk-monitor:
    name: Snyk Monitoring
    runs-on: ubuntu-latest
    if: github.event_name == 'push' && github.ref == 'refs/heads/master'
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install uv
        uses: astral-sh/setup-uv@v5

      - name: Install dependencies
        run: |
          uv pip install --system -e ".[dev]"

      - name: Generate requirements.txt for Snyk
        run: |
          pip freeze > requirements.txt

      - name: Run Snyk to monitor
        uses: snyk/actions/python@0.4.0  # Pinned version
        env:
          SNYK_TOKEN: ${{ secrets.SNYK_TOKEN }}
        with:
          command: monitor
          args: --org=amiable-dev --project-name=llm-council --file=requirements.txt

  sbom-generate:
    name: Generate SBOM
    runs-on: ubuntu-latest
    if: github.event_name == 'push' && github.ref == 'refs/heads/master'
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install uv
        uses: astral-sh/setup-uv@v5

      - name: Install dependencies
        run: |
          uv pip install --system -e ".[dev]"

      - name: Generate SBOM
        run: |
          pip install cyclonedx-bom==4.6.0
          cyclonedx-py environment -o sbom.json --output-format JSON

      - name: Upload SBOM artifact
        uses: actions/upload-artifact@v4
        with:
          name: sbom
          path: sbom.json
```

#### `.github/workflows/release-security.yml`

```yaml
name: Release Security

on:
  release:
    types: [published]

permissions:
  contents: write
  id-token: write
  packages: write

jobs:
  sbom-attach:
    name: Attach SBOM to Release
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Generate SBOM
        run: |
          pip install cyclonedx-bom==4.6.0
          cyclonedx-py environment -o llm-council-${{ github.ref_name }}-sbom.json --output-format JSON

      - name: Attach SBOM to release
        uses: softprops/action-gh-release@v1
        with:
          files: llm-council-${{ github.ref_name }}-sbom.json

  # Future: Container scanning when Docker image is published
  # container-scan:
  #   name: Scan Container Image
  #   runs-on: ubuntu-latest
  #   steps:
  #     - name: Run Trivy container scan
  #       uses: aquasecurity/trivy-action@master
  #       with:
  #         image-ref: 'ghcr.io/amiable-dev/llm-council:${{ github.ref_name }}'
  #         format: 'sarif'
  #         output: 'trivy-container.sarif'
```

### Pre-Commit Configuration

#### `.pre-commit-config.yaml`

```yaml
repos:
  # Existing hooks
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.6
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  # Security: Secret detection (fast, catches secrets before commit)
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.21.2
    hooks:
      - id: gitleaks

  # Note: Semgrep runs in CI only (too slow for pre-commit)
  # CodeQL provides deep analysis in CI
```

### Gitleaks Configuration

#### `.gitleaks.toml`

```toml
title = "LLM Council Gitleaks Config"

[extend]
useDefault = true

[[rules]]
id = "openrouter-api-key"
description = "OpenRouter API Key"
regex = '''(?i)(openrouter[_-]?api[_-]?key|sk-or-v1-)[\s'"=:]+[a-zA-Z0-9_-]{32,}'''
tags = ["api", "openrouter"]

[[rules]]
id = "anthropic-api-key"
description = "Anthropic API Key"
regex = '''(?i)(anthropic[_-]?api[_-]?key|sk-ant-)[\s'"=:]+[a-zA-Z0-9_-]{32,}'''
tags = ["api", "anthropic"]

[allowlist]
description = "Global allowlist"
paths = [
    '''\.env\.example$''',
    '''tests/cassettes/.*\.yaml$''',
    '''docs/.*\.md$''',
]
```

### SonarCloud Configuration

#### `sonar-project.properties`

```properties
sonar.projectKey=amiable-dev_llm-council
sonar.organization=amiable-dev

sonar.sources=src
sonar.tests=tests
sonar.python.coverage.reportPaths=coverage.xml
sonar.python.version=3.10,3.11,3.12

# Quality gate
sonar.qualitygate.wait=true
```

### Dependabot Configuration

#### `.github/dependabot.yml`

```yaml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
    open-pull-requests-limit: 5
    groups:
      dev-dependencies:
        patterns:
          - "pytest*"
          - "ruff"
          - "mypy"
      security:
        patterns:
          - "cryptography"
          - "httpx"
          - "pyyaml"
    labels:
      - "dependencies"
      - "security"
    commit-message:
      prefix: "chore(deps)"

  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
    labels:
      - "ci"
      - "dependencies"
```

### Security Policy Updates

Update `SECURITY.md` to reference automated scanning:

```markdown
## Automated Security Scanning

This project uses automated security scanning:

- **Dependency Scanning**: Trivy, Dependabot, Snyk
- **Static Analysis**: CodeQL, Semgrep, SonarCloud
- **Secret Detection**: GitHub Secret Scanning, Gitleaks

Security findings are visible in the GitHub Security tab.

### SBOM

A Software Bill of Materials (SBOM) in CycloneDX format is attached to each release.
```

### README Badge Updates

Add security badges:

```markdown
[![Security: Snyk](https://snyk.io/test/github/amiable-dev/llm-council/badge.svg)](https://snyk.io/test/github/amiable-dev/llm-council)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/amiable-dev/llm-council/badge)](https://scorecard.dev/viewer/?uri=github.com/amiable-dev/llm-council)
[![FOSSA Status](https://app.fossa.com/api/projects/git%2Bgithub.com%2Famiable-dev%2Fllm-council.svg?type=shield)](https://app.fossa.com/projects/git%2Bgithub.com%2Famiable-dev%2Fllm-council)
```

## Implementation Phases

### Phase 1: GitHub-Native Security (Immediate) - ✅ Complete
- [x] Enable GitHub Secret Scanning with push protection (manual: Settings > Security)
- [x] Enable Dependabot for pip ecosystem (`.github/dependabot.yml`)
- [x] Add CodeQL workflow (security-extended queries)
- [x] Configure Dependabot grouping
- [x] Add Dependency Review Action (license compliance)
- [ ] Configure branch protection with required checks (manual)

### Phase 2: Enhanced Scanning + Supply Chain - ✅ Complete
- [x] Add Semgrep SAST workflow with LLM-specific rules (fork-compatible)
- [x] Add Gitleaks workflow (fork-compatible)
- [x] Create `.gitleaks.toml` config
- [x] Update `.pre-commit-config.yaml` (Gitleaks + Ruff)
- [x] Add SBOM generation (CycloneDX)
- [ ] Add Cosign signing to releases (deferred - requires setup)
- [x] Pin all GitHub Actions by version
- [x] Add custom Semgrep rules for LLM patterns (`.semgrep/llm-security.yaml`)

### Phase 3: Quality Gates - Main Branch Only - ✅ Complete
- [x] Set up SonarCloud project (`sonar-project.properties`)
- [x] Configure Snyk monitoring workflow
- [x] Add Trivy to main branch only (avoid fork rate limits)
- [x] Add SBOM attachment to releases (`release-security.yml`)
- [x] Verify fork PRs don't fail due to missing secrets (design verified)

### Phase 4: Visibility & Trust - ✅ Complete
- [x] Add security badges to README
- [x] Add OpenSSF Scorecard workflow (`.github/workflows/scorecard.yml`)
- [x] Update SECURITY.md with automation details
- [x] Add SLSA Level 3 provenance attestations (`actions/attest-build-provenance`)
- [ ] Document security posture in docs site (future)

### Phase 5: Advanced Supply Chain (Future)
- [x] Add pre-commit hooks documentation (SECURITY.md)
- [ ] Create security testing guide for contributors
- [ ] Add security checklist to PR template
- [ ] Add Garak/Promptfoo LLM red-teaming (when Council Cloud launches)
- [ ] Evaluate Socket.dev for typosquatting detection

## Implementation Status

**Implementation Date:** 2025-12-28

Phases 1-4 implemented via GitHub issues #205-#222. Key files created:
- `.github/dependabot.yml` - Dependency update automation
- `.github/dependency-review-config.yml` - License rules with build-time action exceptions
- `.github/workflows/security.yml` - Main security workflow (Layers 2-3)
- `.github/workflows/release-security.yml` - Release security (Layer 4)
- `.github/workflows/scorecard.yml` - OpenSSF Scorecard analysis (Phase 4)
- `.gitleaks.toml` - Custom secret patterns
- `.pre-commit-config.yaml` - Pre-commit hooks
- `.semgrep/llm-security.yaml` - LLM-specific SAST rules
- `sonar-project.properties` - SonarCloud configuration
- `tests/test_security_configs.py` - TDD tests for configs
- `tests/test_security_workflows.py` - TDD tests for workflows

**Manual Steps Completed:**
1. ✅ Enable GitHub Secret Scanning (Settings > Code security and analysis)
2. ✅ Configure branch protection to require security checks
3. ✅ Add `SONAR_TOKEN` and `SNYK_TOKEN` to repository secrets
4. ✅ Disable SonarCloud "Automatic Analysis" (conflicts with CI-based analysis)

## Consequences

### Positive

- **Zero contributor cost**: All tools free for public OSS
- **Fork-friendly**: External PRs work without secrets (Council recommendation)
- **Defense in depth**: Multiple overlapping scanners
- **GitHub-native integration**: Findings appear in Security tab
- **Supply chain transparency**: SBOM with every release
- **License compliance**: Blocks viral licenses (GPL/AGPL)
- **Professional security posture**: Badges demonstrate commitment
- **Fast feedback**: PR checks complete in <5 minutes

### Negative

- **CI time increase**: ~3-5 minutes added to PR checks
- **Noise potential**: May generate false positives initially
- **Secret management**: Need SNYK_TOKEN, SONAR_TOKEN as repo secrets
- **Maintenance**: Must keep tool versions updated

### Mitigations

| Risk | Mitigation |
|------|------------|
| CI slowdown | Run scans in parallel, cache where possible |
| False positives | Tune tool configs, use `.gitleaksignore` |
| Secret sprawl | Use GitHub Environments, document in CONTRIBUTING |
| Version drift | Dependabot updates GitHub Actions too |

## Alternatives Considered

### 1. Snyk-Only Approach
Use Snyk for SCA, SAST, and container scanning.

**Rejected**: Free tier limits (200 tests/month) insufficient for active development. GitHub-native tools are more reliable for OSS.

### 2. Self-Hosted SonarQube
Deploy SonarQube instance for analysis.

**Rejected**: Operational overhead incompatible with OSS goal. SonarCloud is free for public repos.

### 3. No DAST Until Production
Skip DAST entirely.

**Accepted**: DAST requires running application. Defer to Council Cloud launch.

### 4. Paid Security Platform
Use enterprise platform like Checkmarx or Veracode.

**Rejected**: Cost barrier for OSS. Free tools provide sufficient coverage.

### 5. OWASP ZAP for DAST
Use fully open source ZAP instead of StackHawk.

**Considered for future**: ZAP is viable but requires more configuration. Will evaluate when DAST becomes priority.

## Council Review Summary (v2)

The ADR was reviewed by the LLM Council using high tier (gpt-5.2, claude-opus-4.5, gemini-3-pro-preview, grok-4.1-fast) on 2025-12-28.

### Executive Summary

The council unanimously agreed that the **Layered Architecture** (fork-compatible vs secret-requiring) is correctly designed. However, they identified:

1. **Significant SCA tool redundancy** (4 tools doing similar work)
2. **Weak LLM-specific security coverage** (generic AppSec, not LLM AppSec)
3. **Supply chain hardening should be earlier** (SLSA/Signing in Phase 2, not Future)
4. **Trivy rate limiting risk** on fork PRs

### Critical Changes Made

| Finding | Resolution |
|---------|------------|
| Trivy may hit rate limits on fork PRs | Rely on Dependency Review for PR blocking; Trivy moved to Layer 3 |
| SCA redundancy (4 tools) | Clarified roles: Dependabot (updates), Dep Review (blocking), Snyk (monitoring) |
| LLM security gaps | Added Section 7b with indirect injection, tool abuse, log leakage |
| SLSA too late | Moved Cosign/SBOM to Phase 2 |
| Missing action pinning | Added SHA pinning requirement to ADR |

### LLM-Specific Attack Vectors Added

| Vector | Risk | Mitigation |
|--------|------|------------|
| Indirect Prompt Injection (RAG) | Critical | Separate data vs instructions; trust boundaries |
| Tool/Function Abuse | Critical | Tool allowlists, argument validation, sandboxing |
| Prompt/Log Leakage | High | Redaction filters, no-prompt-logging defaults |
| Cross-Session State Bleed | Medium | Clear session boundaries, scoped storage |
| Output Injection (XSS/Command) | High | Output encoding, never execute model output |

### Recommendations Deferred

| Recommendation | Reason |
|----------------|--------|
| Garak/Promptfoo LLM red-teaming | No runtime API yet; implement with Council Cloud |
| Socket.dev for typosquatting | pip-audit covers basic cases; Socket is Phase 5 |

---

## Council Review Summary (v1)

The ADR was reviewed by the LLM Council using reasoning tier (openai/o1, google/gemini-3-pro-preview) on 2025-12-28. Key findings and changes:

### Critical Issue Resolved: Fork Compatibility

**Problem Identified**: External contributor PRs from forks cannot access repository secrets (`SNYK_TOKEN`, `SONAR_TOKEN`). The original design would fail CI on every fork PR.

**Resolution**:
- Layer 2 (PR checks) now uses only token-less tools (CodeQL, Trivy, Gitleaks, Dependency Review)
- Layer 3 (Snyk, SonarCloud) moved to `push: master` only
- Added clear comments in workflow separating fork-compatible vs secret-requiring jobs

### Council Recommendations Implemented

| Recommendation | Change Made |
|----------------|-------------|
| Pin action versions | All `@master` refs replaced with specific versions |
| Remove GITLEAKS_LICENSE | Removed (unnecessary for OSS) |
| Use security-extended | Changed from `security-and-quality` to avoid style blocking |
| Add Dependency Review | Added with license compliance (blocks GPL/AGPL) |
| LLM-specific security | Added Section 7 covering model serialization, prompt injection |
| Document tool roles | Added comments clarifying Semgrep vs CodeQL scope |

### Recommendations Deferred

| Recommendation | Reason |
|----------------|--------|
| Modelscan/Picklescan | LLM Council doesn't load external model weights |
| Custom Semgrep rules for prompts | Create after establishing patterns |

### Recommendations Implemented (Post-Review)

| Recommendation | Implementation |
|----------------|----------------|
| SLSA/Sigstore provenance | Implemented as SLSA Level 3 in Phase 4 using `actions/attest-build-provenance` |

## References

- [GitHub Security Features](https://docs.github.com/en/code-security)
- [OWASP DevSecOps Guideline](https://owasp.org/www-project-devsecops-guideline/)
- [OpenSSF Scorecard](https://scorecard.dev/)
- [CycloneDX Specification](https://cyclonedx.org/specification/overview/)
- [Trivy Documentation](https://aquasecurity.github.io/trivy/)
- [Semgrep Registry](https://semgrep.dev/r)
- [SonarCloud for OSS](https://www.sonarsource.com/open-source-editions/)
- [Snyk Open Source](https://snyk.io/product/open-source-security-management/)
