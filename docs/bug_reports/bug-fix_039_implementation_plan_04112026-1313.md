# Implementation Plan: Fix council_health_check 403 (BUG-039)

## Engineering Logic (First Principles)
1. **Dependency Analysis**: The Chairman model is the only single-point-of-failure in the council (Stage 3). Council members are non-blocking. Therefore, a "health check" should prioritize verifying the Chairman.
2. **Auth Isolation**: 401 (Unauthorized) usually means a bad key. 403 (Forbidden) usually means a restricted model. 
3. **Connectivity Verification**: To determine if "Ready", we need to know if the API key can reach *any* usable model. If the Chairman is 403, we verify the key against a "baseline" model (`gpt-4o-mini`).
4. **Gradual Degradation**: If the key works but the Chairman is restricted, we should alert the user but allow the system to remain "ready" so Stage 1 data can still be gathered of the user chooses.

## Proposed Changes
- **mcp_server.py**:
    - Import `CHAIRMAN_MODEL`.
    - Replace hardcoded ping with `CHAIRMAN_MODEL`.
    - Catch 403 and ping `openai/gpt-4o-mini` as a proxy for key validity.
    - Add `ready_warning` field to JSON response.
