# Bug Report: council_health_check returns 403 on connectivity test (BUG-039)

## Symptom
The `council_health_check` tool consistently returns `ready: false` with an authentication error:
`"message": "API connectivity issue: Authentication failed for google/gemini-2.0-flash-001: 403"`

## Root Cause Analysis
- The `council_health_check` in `mcp_server.py` hardcoded `google/gemini-2.0-flash-001` as its only connectivity test model.
- Gemini 2.0 is a restricted/frontier model on some providers (like OpenRouter).
- If the user's API key does not have access to this specific model, the health check fails, blocking the entire tool even if the user's configured models are functional.

## Verification Strategy
- **Reproduction**: Create a unit test that mocks `query_model_with_status` to return a 403 for the hardcoded model.
- **Fix Verification**: 
    1.  Confirm the health check now attempts to ping the `CHAIRMAN_MODEL`.
    2.  Confirm that if the Chairman returns a 403, a fallback ping to `openai/gpt-4o-mini` is attempted.
    3.  Confirm `ready: true` is returned if the fallback succeeds, with a clear warning.
