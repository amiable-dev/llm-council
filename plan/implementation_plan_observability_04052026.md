# Implementation Plan - OpenRouter Observability (Issue #2)

## 1. Problem Statement
The LLM Council used generic request headers, making it difficult to trace which council requests were which in the OpenRouter gateway logs. Additionally, several model IDs were outdated, leading to failed queries for newer models.

## 2. Solution Summary
- **Identity Headers**: Add `X-Title`, `HTTP-Referer`, and custom `X-Council-ID` headers to all outbound requests to OpenRouter.
- **Model ID Registry update**: Synchronize `src/llm_council/gateway/openrouter.py` with current OpenRouter model strings.
- **Gateway logging**: Ensure every request/response cycle includes its unique `council_id` in logs for easy filtering.

## 3. Implementation Details
- Modified `src/llm_council/gateway/openrouter.py` and base gateway logic to inject identity metadata.
- Updated `registry.yaml` with the latest identifiers.

## 4. Verification Strategy
- **Gateway Simulation**: Mock an OpenRouter response and verify the outbound headers contain the new identifiers.
- **Test Suite**: Run `uv run pytest tests/test_gateway.py` to ensure core routing still works.
