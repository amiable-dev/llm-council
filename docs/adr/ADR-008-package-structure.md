# ADR-008: Package Structure - Library with Optional MCP

**Status:** Accepted
**Date:** 2024-12-01
**Deciders:** LLM Council (Unanimous)
**Technical Story:** Restructure package to support both library and MCP server usage patterns

## Context and Problem Statement

The current package `llm-council-mcp` is focused on MCP (Model Context Protocol) server usage. However, users want to:

1. **Use as a Python library**: `from llm_council import run_full_council`
2. **Use as an MCP server**: `llm-council` CLI command

The current structure has issues:
- Package name (`llm-council-mcp`) implies MCP-only usage
- Core library functions aren't properly exported in `__init__.py`
- All users get MCP dependencies even if they only want the library

## Decision Drivers

* **User Experience**: Clean imports matching package name
* **Dependency Hygiene**: Don't force MCP deps on library-only users
* **Maintainability**: Single repo, single version, single release pipeline
* **Python Best Practices**: Follow established patterns (extras)
* **Future Flexibility**: MCP is niche; don't tie identity to one protocol

## Considered Options

### Option A: Single Package `llm-council-mcp`
Keep current name, export both library and MCP functionality.

**Pros:**
- No migration needed
- Simple

**Cons:**
- Name mismatch: `pip install llm-council-mcp` but `from llm_council import ...`
- Forces MCP dependencies on everyone
- Branding suggests MCP-only

### Option B: Two Packages
Separate `llm-council` (library) and `llm-council-mcp` (server).

**Pros:**
- Clean separation
- Minimal dependencies for library users

**Cons:**
- Two release cycles, version sync headaches
- User confusion ("which do I install?")
- Overkill for single integration

### Option C: Single Package with Optional Extras
Rename to `llm-council` with `[mcp]` extra for server functionality.

**Pros:**
- Clean naming: `pip install llm-council` → `from llm_council import ...`
- Library users get minimal dependencies
- MCP users opt-in: `pip install "llm-council[mcp]"`
- One repo, one version
- Standard Python pattern (httpx, fastapi, pandas use this)

**Cons:**
- Requires migration from old package name
- CLI always installed (must handle missing deps gracefully)

## Decision Outcome

**Chosen: Option C** - Single package `llm-council` with optional `[mcp]` extra.

### Rationale (Council Consensus)

1. **Identity**: `llm-council` is the product; MCP is just a protocol it supports
2. **Standards**: Using extras is the Python convention for optional features
3. **Maintenance**: One package to maintain vs two
4. **Technical Constraint**: Python extras cannot conditionally add CLI entry points, but graceful degradation handles this elegantly

## Implementation

### Package Structure

```
src/
└── llm_council/
    ├── __init__.py        # Exports: run_full_council, Council, etc.
    ├── council.py         # Core orchestration logic
    ├── openrouter.py      # LLM API client
    ├── config.py          # Configuration
    ├── cache.py           # Response caching
    ├── telemetry.py       # Telemetry protocol
    ├── cli.py             # Entry point (handles missing deps)
    └── mcp_server.py      # MCP server (optional import)
```

### pyproject.toml

```toml
[project]
name = "llm-council"
version = "1.0.0"
description = "Multi-LLM council system with peer review and synthesis"
requires-python = ">=3.10"

dependencies = [
    "httpx>=0.25.0",
    "pydantic>=2.0.0",
    # Core dependencies only
]

[project.optional-dependencies]
mcp = [
    "mcp>=1.0.0",
    # MCP server dependencies
]

[project.scripts]
llm-council = "llm_council.cli:main"
```

### CLI with Graceful Degradation

```python
# llm_council/cli.py
import sys

def main():
    try:
        from llm_council.mcp_server import mcp
    except ImportError:
        print("Error: MCP dependencies not installed.", file=sys.stderr)
        print("\nTo use the MCP server, install with:", file=sys.stderr)
        print("    pip install 'llm-council[mcp]'", file=sys.stderr)
        sys.exit(1)

    mcp.run()
```

### Public API Exports

```python
# llm_council/__init__.py
from llm_council.council import (
    run_full_council,
    stage1_collect_responses,
    stage2_collect_rankings,
    stage3_synthesize_final,
)
from llm_council.config import CouncilConfig

__all__ = [
    "run_full_council",
    "stage1_collect_responses",
    "stage2_collect_rankings",
    "stage3_synthesize_final",
    "CouncilConfig",
]
```

## Migration Strategy

### Phase 1: Publish New Package
1. Rename package to `llm-council`
2. Restructure with optional MCP extras
3. Export core functions in `__init__.py`
4. Publish to PyPI

### Phase 2: Deprecate Old Package
1. Final release of `llm-council-mcp` v0.x.x
2. Make it depend on `llm-council[mcp]`
3. Add deprecation warning on import
4. Update README with migration instructions

### Phase 3: Sunset
1. After 6 months, mark `llm-council-mcp` as deprecated on PyPI
2. Remove from active maintenance

## Usage Examples

### Library Usage
```bash
pip install llm-council
```

```python
from llm_council import run_full_council

stage1, stage2, stage3, metadata = await run_full_council(
    "What's the best approach for error handling?"
)
print(stage3["response"])
```

### MCP Server Usage
```bash
pip install "llm-council[mcp]"
llm-council
```

### Claude Code Integration
```bash
claude mcp add llm-council -- llm-council
```

## Consequences

### Positive
- Clean, memorable package name
- Library users get minimal install
- Single package to maintain
- Follows Python best practices
- Future-proof for additional protocols/interfaces

### Negative
- Migration required for existing users
- CLI installed even for library-only users (gracefully handles missing deps)
- Old package name needs deprecation period

### Risks
- Users may not notice migration (mitigated by deprecation warnings)
- PyPI name `llm-council` availability (check before implementation)

## References

- [PEP 621 - Project Metadata](https://peps.python.org/pep-0621/)
- [Python Packaging User Guide - Optional Dependencies](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/#dependencies-optional-dependencies)
- Similar patterns: `httpx[http2]`, `fastapi[all]`, `pandas[excel]`
