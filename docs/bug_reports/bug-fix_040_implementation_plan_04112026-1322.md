# Implementation Plan: Restoring Python 3.10 Compatibility (BUG-040)

## Objectives
1. Restore MCP server functionality on Python 3.10 platforms.
2. Replace all instances of `datetime.UTC` (added in 3.11) with `timezone.utc` (compatible with 3.10+).

## Proposed Changes

### Verification Module
- [ ] `src/llm_council/verification/context.py`:
    - Replace `from datetime import datetime, UTC` with `from datetime import datetime, timezone`.
    - Replace `datetime.now(UTC)` with `datetime.now(timezone.utc)`.
- [ ] `src/llm_council/verification/transcript.py`:
    - Replace `from datetime import datetime, UTC` with `from datetime import datetime, timezone`.
    - Replace `datetime.now(UTC)` with `datetime.now(timezone.utc)`.
- [ ] `src/llm_council/verification/api.py`:
    - Replace `from datetime import datetime, UTC` with `from datetime import datetime, timezone`.

### Telemetry Module
- [ ] `src/llm_council/telemetry_client.py`:
    - Replace `from datetime import datetime, UTC` with `from datetime import datetime, timezone`.
    - Replace `datetime.now(UTC)` with `datetime.now(timezone.utc)`.

### Other Affected Files
- [ ] `src/llm_council/metadata/registry.py`: Check and fix if necessary.
- [ ] `src/llm_council/audition/*.py`: Check and fix if necessary.

## Verification
1. Run `uv run python -c "from llm_council.mcp_server import mcp"` on a Python 3.10 environment to verify import success.
2. Run manual `uv run llm-council` in a Python 3.10 environment.
3. Verify existing tests still pass (Regression testing).
