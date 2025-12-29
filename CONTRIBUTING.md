# Contributing to LLM Council

Thank you for your interest in contributing to LLM Council! This document provides guidelines and instructions for contributing.

## Code of Conduct

This project adheres to the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.

## Getting Started

### Prerequisites

- Python 3.11 or higher
- [uv](https://docs.astral.sh/uv/) package manager
- Git

### Development Setup

1. **Fork and clone the repository:**
   ```bash
   git clone https://github.com/YOUR-USERNAME/llm-council.git
   cd llm-council
   ```

2. **Install dependencies:**
   ```bash
   uv sync --all-extras
   ```

3. **Create environment file:**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

4. **Run tests to verify setup:**
   ```bash
   uv run pytest tests/ -v
   ```

5. **Install pre-commit hooks (recommended):**
   ```bash
   pip install pre-commit
   pre-commit install
   ```

   This enables automatic checks before each commit:
   - **Gitleaks**: Secret detection
   - **Ruff**: Python linting and formatting

## Development Workflow

### Creating a Branch

Create a feature branch from `master`:

```bash
git checkout master
git pull origin master
git checkout -b feature/your-feature-name
```

Branch naming conventions:
- `feature/` - New features
- `fix/` - Bug fixes
- `docs/` - Documentation changes
- `refactor/` - Code refactoring
- `test/` - Test additions or fixes

### Making Changes

1. **Write tests first** (TDD approach encouraged)
2. **Make your changes**
3. **Run the test suite:**
   ```bash
   uv run pytest tests/ -v
   ```
4. **Run linting:**
   ```bash
   uv run ruff check src/ tests/
   uv run ruff format src/ tests/
   ```
5. **Run type checking:**
   ```bash
   uv run mypy src/llm_council --ignore-missing-imports
   ```

### Commit Messages

We follow conventional commit format:

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only
- `style`: Formatting, no code change
- `refactor`: Code restructuring
- `test`: Adding tests
- `chore`: Maintenance tasks

**Example:**
```
feat(council): Add retry logic for failed model queries

Implements exponential backoff with 3 retries for transient API failures.

Closes #123
```

### Developer Certificate of Origin (DCO)

All commits must be signed off to certify that you have the right to submit the code:

```bash
git commit -s -m "feat(council): Add new feature"
```

This adds a `Signed-off-by` line to your commit message:
```
Signed-off-by: Your Name <your.email@example.com>
```

By signing off, you certify the [Developer Certificate of Origin](https://developercertificate.org/):

> I certify that I have the right to submit this contribution under the project's license.

### Pull Requests

1. **Push your branch:**
   ```bash
   git push -u origin feature/your-feature-name
   ```

2. **Create a pull request** via GitHub

3. **Fill out the PR template** with:
   - Summary of changes
   - Related issues
   - Test plan
   - Checklist completion

4. **Address review feedback** promptly

5. **Ensure CI passes** before requesting merge

## Testing

### Running Tests

```bash
# Run all tests
uv run pytest tests/ -v

# Run with coverage
uv run pytest tests/ -v --cov=src --cov-report=html

# Run specific test file
uv run pytest tests/test_council.py -v

# Run tests matching pattern
uv run pytest tests/ -k "test_stage1" -v
```

### Writing Tests

- Place tests in `tests/` directory
- Mirror the source structure (e.g., `src/llm_council/council.py` -> `tests/test_council.py`)
- Use descriptive test names: `test_stage1_returns_responses_for_all_models`
- Use pytest fixtures for common setup

## Architecture

See [CLAUDE.md](CLAUDE.md) for detailed architecture documentation and implementation notes.

### Key Concepts

- **Tiers**: Confidence levels (quick, balanced, high, reasoning)
- **Stages**: Council deliberation stages (1: responses, 2: peer review, 3: synthesis)
- **Gateway**: LLM API abstraction layer
- **Triage**: Query classification and routing

## Issue Labels

| Label | Description |
|-------|-------------|
| `bug` | Something isn't working |
| `enhancement` | New feature or request |
| `documentation` | Documentation improvements |
| `good first issue` | Good for newcomers |
| `help wanted` | Extra attention needed |
| `needs-triage` | Needs maintainer review |

## Questions?

- Check the [README](README.md) for usage documentation
- See [SUPPORT.md](SUPPORT.md) for support channels
- Open a [Discussion](https://github.com/amiable-dev/llm-council/discussions) for questions

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
