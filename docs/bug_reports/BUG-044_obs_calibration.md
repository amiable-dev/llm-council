# BUG-044: Health Check Observability & Default Calibration

## Description
The `council_health_check` was providing a generic `403 Forbidden` error when an API key reached its monthly usage limit on OpenRouter. This led to confusion about whether the code was faulty (hardcoded models) or the environment was restricted. Furthermore, the system defaulted to a mid-tier synthesis model (`gemini-2.0-flash-001`) by default.

## Root Cause
- **Ambiguity**: The health check did not distinguish between `401 Unauthorized` (bad key) and `403 Forbidden` (account/policy restriction).
- **Zero Visibility**: No balance or credit check was performed during the health check.
- **Stale Defaults**: The hardcoded default chairman model was outdated.

## Proposed Strategy
1. **Differentiate 403 Failures**: Use a "lite" fallback model (`gpt-4o-mini`) to verify key validity when the primary fails.
2. **Account Balances**: Call OpenRouter's `/credits` API and report the status in the health check.
3. **Calibrate Defaults**: Set the system-wide default chairman to `google/gemini-3.1-pro-preview`.

## Verification Strategy
- **Manual**: Run `council_health_check` and verify the `account_credits` field shows either a balance or a specific error code.
- **Automated**: Verify that an invalid key returns a `401` while a restricted key (balance/limit) returns a `403` with a specific `ready_warning`.
