# LLM Council Governance

This document describes the governance structure and decision-making process for the LLM Council project.

## Project Structure

### Roles

#### Maintainers

Maintainers have full commit access and are responsible for:

- Reviewing and merging pull requests
- Triaging issues
- Making architectural decisions
- Releasing new versions
- Enforcing the code of conduct

**Current Maintainers:**
- @amiable-dev (Amiable Dev)

#### Committers

Committers have write access to specific areas and can:

- Review and approve pull requests in their area
- Help triage issues
- Mentor new contributors

To become a committer:
- Demonstrate sustained, quality contributions
- Be nominated by a maintainer
- Receive approval from existing maintainers

#### Contributors

Anyone who contributes to the project through:

- Code contributions (pull requests)
- Documentation improvements
- Bug reports and feature requests
- Helping others in discussions
- Reviewing pull requests

All contributors are listed in the commit history and release notes.

## Decision Making

### Architecture Decision Records (ADRs)

Significant technical decisions are documented as ADRs in `docs/adr/`. We follow the Michael Nygard format.

For detailed instructions on formats, templates, and the decision lifecycle (including deprecation), please refer to the **[ADR Process Guide](docs/architecture/adrs.md)**.

**Summary of Process:**

1. **Draft**: Create an ADR using the [template](docs/adr/ADR-000-template.md).
2. **Propose**: Open a PR for discussion.
3. **Decide**: Maintainers review and merge (Status: Accepted).

### Consensus-Based Decisions

For most decisions, we seek consensus:

1. Proposals are made via GitHub Issues or Discussions
2. Community feedback is gathered
3. Maintainers synthesize feedback
4. Decision is documented (ADR for technical, issue for operational)

### Voting

For contentious decisions without clear consensus:

- Maintainers vote after reasonable discussion period (minimum 7 days)
- Simple majority required
- Ties broken by project lead

## Contributions

### Pull Request Process

1. **Open Issue First**: For significant changes, discuss in an issue first
2. **Fork and Branch**: Create feature branch from `master`
3. **Develop**: Follow coding standards in [CONTRIBUTING.md](CONTRIBUTING.md)
4. **Test**: Ensure tests pass and add new tests as needed
5. **Submit PR**: Reference related issues
6. **Review**: Address feedback from reviewers
7. **Merge**: Maintainer merges after approval

### Review Requirements

| Change Type | Required Reviewers |
|-------------|-------------------|
| Bug fixes | 1 maintainer |
| New features | 1 maintainer |
| Breaking changes | 2 maintainers |
| Security fixes | 1 maintainer (expedited) |

### Breaking Changes

Breaking changes require:

- ADR documenting the change
- Migration guide in the PR
- Minimum 14-day discussion period
- Announcement in release notes

## Releases

### Versioning

We follow [Semantic Versioning](https://semver.org/):

- **MAJOR**: Breaking changes
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes (backward compatible)

### Release Process

1. Update CHANGELOG.md
2. Update version in pyproject.toml
3. Create release PR
4. After merge, tag release
5. CI publishes to PyPI

## Code of Conduct

All participants must follow our [Code of Conduct](CODE_OF_CONDUCT.md). Violations can be reported to conduct@amiable.dev.

## Amendments

This governance document can be amended by:

1. Opening a PR with proposed changes
2. 14-day discussion period
3. Approval by majority of maintainers
4. Changes take effect upon merge

## Contact

- **General**: Open a GitHub Discussion
- **Security**: security@amiable.dev
- **Conduct**: conduct@amiable.dev
- **Enterprise**: enterprise@amiable.dev
