# Security Policy

## Supported Versions

We release patches for security vulnerabilities in the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 0.19.x  | :white_check_mark: |
| 0.18.x  | :white_check_mark: |
| < 0.18  | :x:                |

## Reporting a Vulnerability

We take security seriously. If you discover a security vulnerability, please report it responsibly.

### How to Report

**Do NOT open a public GitHub issue for security vulnerabilities.**

Instead, please report vulnerabilities via one of these methods:

1. **GitHub Security Advisories** (Preferred)
   - Go to the [Security tab](https://github.com/amiable-dev/llm-council/security)
   - Click "Report a vulnerability"
   - Fill out the private security advisory form

2. **Email**
   - Send details to: security@amiable.dev
   - Use our PGP key for sensitive information (available upon request)

### What to Include

Please include:

- Description of the vulnerability
- Steps to reproduce
- Affected versions
- Potential impact
- Any suggested fixes (optional)

### Response Timeline

- **Initial Response**: Within 48 hours
- **Status Update**: Within 7 days
- **Resolution Target**: Within 90 days (depending on severity)

### Disclosure Policy

- We will acknowledge your report within 48 hours
- We will provide a more detailed response within 7 days
- We will work with you to understand and resolve the issue
- We will credit you in the security advisory (unless you prefer anonymity)
- We ask that you give us reasonable time to address the issue before public disclosure

## Security Best Practices for Users

### API Key Security

- **Never commit API keys** to version control
- Use environment variables or secure key storage
- Rotate keys periodically
- Use the built-in keychain storage: `llm-council setup-key`

### Configuration Security

- Keep `.env` files in `.gitignore`
- Use `LLM_COUNCIL_SUPPRESS_WARNINGS=false` in production
- Review webhook URLs before enabling (HTTPS required by default)

### Network Security

- Use HTTPS for all external communications
- Configure webhook HTTPS enforcement: `LLM_COUNCIL_WEBHOOK_HTTPS_ONLY=true`
- Review gateway configurations for sensitive data exposure

## Known Security Considerations

### Prompt Injection

The council uses XML sandboxing in Stage 2 to prevent prompt injection attacks during peer review. However, users should still:

- Sanitize user inputs before sending to the council
- Review synthesized outputs before automated actions
- Use binary verdict mode for security-critical decisions

### Data Privacy

- Session data is stored locally by default
- Cross-session bias metrics require explicit consent
- Query hashing (for RESEARCH consent) uses HMAC with configurable secret

## Automated Security Scanning

LLM Council implements a multi-layered security scanning pipeline (see [ADR-035](docs/adr/ADR-035-devsecops-implementation.md)):

### Pre-commit Hooks (Layer 1)
- **Gitleaks**: Secret detection before commit
- **Ruff**: Python linting and formatting

### CI/CD Security Checks (Layer 2)
- **CodeQL**: Semantic code analysis for Python vulnerabilities
- **Semgrep**: SAST with custom LLM-specific rules
- **Dependency Review**: License and vulnerability checking on PRs

### Post-Merge Security (Layer 3)
- **Snyk**: Continuous dependency monitoring
- **Trivy**: Container and filesystem vulnerability scanning
- **SonarCloud**: Code quality and security analysis

### Release Security (Layer 4)
- **SBOM**: CycloneDX Software Bill of Materials attached to releases
- **SLSA Provenance**: Level 3 build provenance attestations (Sigstore-signed)
- **OpenSSF Scorecard**: Automated security health metrics ([view score](https://scorecard.dev/viewer/?uri=github.com/amiable-dev/llm-council))
- **PyPI Attestations**: Automatic attestations via Trusted Publisher
- Enables downstream vulnerability tracking and artifact verification

### Installing Pre-commit Hooks

```bash
pip install pre-commit
pre-commit install
```

## Security Updates

Security updates are released as patch versions. Subscribe to:

- [GitHub Releases](https://github.com/amiable-dev/llm-council/releases) (Watch > Custom > Releases)
- [Security Advisories](https://github.com/amiable-dev/llm-council/security/advisories)

## Acknowledgments

We thank the security researchers who have helped improve the security of LLM Council:

- (Your name could be here!)
