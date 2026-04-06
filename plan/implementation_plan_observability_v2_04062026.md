# Implementation Plan: Resolving OpenRouter Source Attribution

This plan addresses several gaps identified in the OpenRouter observability implementation (Issue #2), ensuring consistent source attribution ("LLM Council") in OpenRouter logs across both CLI and Claude Desktop (MCP) interfaces.

## 1. Problem Identification
- **Missed File**: `src/llm_council/metadata/openrouter_client.py` is making discovery and metadata calls to OpenRouter without the required `X-Title` and `HTTP-Referer` headers.
- **Old Repository Reference**: All existing `HTTP-Referer` headers refer to the original `amiable-dev/llm-council` instead of the current `mgammarino/llm-council`.
- **Missing X-Council-ID**: The plan to include `X-Council-ID` (for tracing individual council deliberations) was documented but never implemented in any client.
- **Lack of Verification**: There are no existing tests to verify outbound headers, leading to silent failures when using the MCP server environment.

## 2. Proposed Changes

### 2.1 Update Metadata Client
Add the required headers to `OpenRouterClient._build_headers` in `src/llm_council/metadata/openrouter_client.py`.

### 2.2 Consolidate and Correct Referer URLs
Update the `HTTP-Referer` headers across the stack to use the current repository URL.

### 2.3 Implement X-Council-ID / X-Session-ID
Ensure that the `session_id` generated during a council deliberation is passed down through the gateway adapter to the HTTP client and injected as `X-Council-ID`.

### 2.4 New Verification Test
Create a unit test `tests/test_openrouter_attribution.py` that mocks outbound requests to `openrouter.ai` and asserts that all identity and tracing headers are present.

## 3. Detailed File Updates

| File | Change |
| :--- | :--- |
| `src/llm_council/metadata/openrouter_client.py` | Update `_build_headers` to include `X-Title` and `HTTP-Referer` |
| `src/llm_council/openrouter.py` | Add `X-Council-ID` header; Update `HTTP-Referer` |
| `src/llm_council/gateway/openrouter.py` | Add `X-Council-ID` header support; Update `HTTP-Referer` |
| `src/llm_council/council.py` | Pass `session_id` to gateway adapter functions |
| `src/llm_council/gateway_adapter.py` | Accept `session_id` and pass it to the underlying client/gateway |
| `tests/test_openrouter_attribution.py` | **New**: Mock OpenRouter with `httpx.Response` and verify headers |

## 4. Verification Plan
1. Run the new header verification test: `uv run pytest tests/test_openrouter_attribution.py`.
2. Force a metadata refresh via the MCP server: `list_available_models`.
3. Manually check the OpenRouter dashboard logs to verify "LLM Council" appears consistently.
