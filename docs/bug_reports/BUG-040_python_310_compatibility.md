# Bug Report: MCP Server Loading Failure (BUG-040)

## Problem Description
The MCP server fails to start in production environments running Python 3.10 (including the user's Claude Desktop setup). The server logs show an `ImportError` when attempting to import `UTC` from `datetime`.

## Root Cause
The `llm_council.verification` module (specifically `context.py`) uses `from datetime import UTC`, which is a Python 3.11+ feature. The `pyproject.toml` specifies compatibility for Python >= 3.10, so this is a regression in environmental support.

## Affected Components
- `llm_council.verification.context`
- `llm_council.verification.api`
- `llm_council.verification.transcript`
- `llm_council.mcp_server` (via transitive import)

## Traceback
```
Traceback (most recent call last):
  File "<string>", line 1, in <module>
  File "C:\git_projects\llm-council\src\llm_council\mcp_server.py", line 46, in <module>
    from llm_council.verification.api import run_verification, VerifyRequest
  File "C:\git_projects\llm-council\src\llm_council\verification\__init__.py", line 8, in <module>
    from llm_council.verification.context import (
  File "C:\git_projects\llm-council\src\llm_council\verification\context.py", line 23, in <module>
    from datetime import datetime, UTC
ImportError: cannot import name 'UTC' from 'datetime'
```

## Proposed Fix
Replace `datetime.UTC` with a compatibility-safe alternative that works across Python 3.10 – 3.13.
The most robust approach is using `timezone.utc` from `datetime`.
