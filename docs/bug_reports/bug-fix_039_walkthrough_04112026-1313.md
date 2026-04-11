# Walkthrough: Robust Health Check & Auth Fallback (BUG-039)

I have resolved the issue where `council_health_check` would return a 403 error if the hardcoded test model was restricted for a user's API key.

## Changes Made

### MCP Server
#### [mcp_server.py](file:///c:/git_projects/llm-council/src/llm_council/mcp_server.py)
- **Dynamic Testing**: Replaced the hardcoded `google/gemini-2.0-flash-001` with the configured `CHAIRMAN_MODEL`.
- **Auth Fallback Mechanism**: Added logic to detect 403 (Forbidden) errors. If the primary model fails, the system now attempts a fallback check using `openai/gpt-4o-mini` to verify if the API key is valid.
- **Enhanced Diagnostics**: Improved health check messages to distinguish between "API Key Invalid" and "Model Restricted".

## Verification Results

### Automated Tests
I created and executed a new test suite [test_health_check_robustness.py](file:///c:/git_projects/llm-council/tests/test_health_check_robustness.py) which covers three critical scenarios:
1. **Fallback Success**: Chairman fails with 403, but fallback model succeeds. The health check now correctly reports `ready: true` with a warning.
2. **Total Failure**: Both models fail (true auth error). The health check correctly reports `ready: false`.
3. **Direct Success**: Chairman model works immediately.

```bash
python -m pytest tests/test_health_check_robustness.py
```
**Result**: `3 passed in 1.11s`
