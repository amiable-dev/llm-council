# Bug Report: BUG-002 - OpenRouter Source Attribution Discrepancy

## 1. Description
The "App" column in OpenRouter logs shows "Unknown" when requests originate from the MCP Claude Desktop server, despite a previous fix having been implemented. While the CLI correctly reports "LLM Council", the background metadata discovery calls and certain orchestration paths are still missing the required identity and observability headers.

## 2. Evidence
- **OpenRouter Gateway Logs**: Show "Unknown" for requests coming from the `mgammarino/llm-council` project when using the MCP interface.
- **CLI Comparison**: `query.py` successfully sends headers, but `src/llm_council/metadata/openrouter_client.py` (used for model discovery) was found to be missing them.
- **Code Audit**: `X-Council-ID` is absent from all headers across the codebase, contradicting the original observability implementation plan.

## 3. Root Cause Analysis
1.  **Improper Scope**: The initial observability fix (#2) only patched the main completion clients but did not include the metadata client (`openrouter_client.py`).
2.  **Outdated References**: Hardcoded `HTTP-Referer` URLs pointed to an old organization repo (`amiable-dev`), which can lead to platform-wide attribution issues if the new repo's reputation is used for identification.
3.  **Missing Global ID**: The `session_id` generated during council deliberations was never propagated to the gateway layer as `X-Council-ID`, hindering end-to-end tracing.

## 4. Discovery Results
- Stash: Empty.
- Affected Files: 
    - `src/llm_council/metadata/openrouter_client.py`
    - `src/llm_council/openrouter.py`
    - `src/llm_council/gateway/openrouter.py`
    - `src/llm_council/council.py` (propagation logic)

## 5. Verification Strategy
1.  **Mocked Output Headers**: Create a unit test `tests/test_bug_002_openrouter_headers.py` that intercepts all `httpx` calls to `openrouter.ai`.
2.  **Assert Presence of Required Headers**: 
    - `X-Title: LLM Council`
    - `HTTP-Referer: https://github.com/mgammarino/llm-council`
    - `X-Council-ID: <session_uuid>`
3.  **Traceability Simulation**: Verify that the `session_id` from council deliberations matches the `X-Council-ID` sent to the API.
