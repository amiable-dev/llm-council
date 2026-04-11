# Walkthrough: Restoring Python 3.10 Compatibility (BUG-040)

## The Problem
The MCP server was failing to start in Claude Desktop because the production environment uses Python 3.10. Recent additions to the `llm_council.verification` module used `datetime.UTC`, which is only available in Python 3.11+.

## The Fix
I replaced all instances of `datetime.UTC` with `datetime.timezone.utc`, which is compatible with all supported Python versions (>= 3.10).

### 1. Updated Verification Context
In `src/llm_council/verification/context.py`, I changed the import and usage for isolated context creation.
```python
-from datetime import datetime, UTC
+from datetime import datetime, timezone
...
-created_at=datetime.now(UTC),
+created_at=datetime.now(timezone.utc),
```

### 2. Updated Transcript Persistence
In `src/llm_council/verification/transcript.py`, I updated the timestamp generation for audit logs.
```python
-timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%S")
+timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
```

### 3. Updated API Endpoints
In `src/llm_council/verification/api.py`, I updated multiple locations where timestamps are recorded for council stages.

### 4. Updated Telemetry and Registry
I also updated `src/llm_council/telemetry_client.py` and `src/llm_council/metadata/registry.py` to ensure consistent compatibility across the codebase.

## Verification Results
- **Import Check**: `uv run python -c "from llm_council.mcp_server import mcp"` now succeeds in a Python 3.10 environment.
- **Regression Tests**: All 18 tests in `test_mcp_server.py` and `test_health_check_robustness.py` passed under Python 3.10.
