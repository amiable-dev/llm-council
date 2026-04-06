# Walkthrough: BUG-002 - OpenRouter Traceability Fix

This fix ensures that all requests to OpenRouter are correctly attributed to "LLM Council" and that individual requests within a council deliberation session can be traced using a unified `X-Council-ID`.

## Key Changes

### 1. Orchestration Layer (`src/llm_council/council.py`)
- We updated both the modern `run_council_with_fallback` and the legacy `run_full_council` methods to generate a unique `session_id` using `uuid.uuid4()`.
- This `session_id` is now passed as the `council_id` parameter to all internal stages:
    - **Stage 1**: `stage1_collect_responses`
    - **Stage 1.5**: `stage1_5_normalize_styles`
    - **Stage 2**: `stage2_collect_rankings`
    - **Stage 3**: `stage3_synthesize_final`

### 2. Adapter Layer (`src/llm_council/gateway_adapter.py`)
- The adapter functions `query_models_parallel` and `query_models_with_progress` were updated to accept an optional `council_id`.
- For the modern **Gateway Layer**, the `council_id` is injected into the `GatewayRequest` object.
- For the **Direct Query path**, the `council_id` is passed down to the underlying HTTP client methods.

### 3. Gateway Layer (`src/llm_council/gateway/openrouter.py`)
- The `complete` and `complete_many` methods in the OpenRouter gateway implementation now extract the `council_id` from the `GatewayRequest`.
- This ID is passed to the internal `_query_openrouter` method, which injects it into the `X-Council-ID` HTTP header.

### 4. HTTP Client Layer (`src/llm_council/openrouter.py`)
- The `query_model_with_status` function now accepts `council_id` and adds it to the request headers.
- Standardized `X-Title: LLM Council` and `HTTP-Referer: https://github.com/mgammarino/llm-council` are now globally enforced.

## Verification

We created a specialized test suite `tests/test_bug_002_openrouter_attribution.py` that:
- Mocks the `httpx` POST calls.
- Simulates a full council deliberation using `run_full_council`.
- Asserts that *every* outbound HTTP request contains:
    - `X-Title: LLM Council`
    - `HTTP-Referer: https://github.com/mgammarino/llm-council`
    - A consistent `X-Council-ID` (matching the session).

The test is now passing:
```bash
uv run pytest tests/test_bug_002_openrouter_attribution.py
============================= 3 passed in 0.84s ==============================
```
