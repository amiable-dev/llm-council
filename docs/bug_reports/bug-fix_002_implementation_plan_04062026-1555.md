# Implementation Plan: BUG-002 - OpenRouter Source Attribution (v2)

## 1. First Principles Analysis
- **Identity Integrity**: OpenRouter logs are populated based on the presence of `X-Title` and `HTTP-Referer`. If a single request (even for metadata) lacks these, it results in an "Unknown" entry, degrading the observability audit trail.
- **Traceability Consistency**: A distributed council system requires a single correlation ID (`X-Council-ID`) to be shared across all model queries within a deliberation session. Without this, individual model responses cannot be linked back to the originating council prompt in external logs.
- **State Propagation**: The `session_id` generated during a council's initialization is the "Source of Truth" for tracing and must be passed as an argument down every call path until the final HTTP client assembly.

## 2. Engineering Solution
- **Global Header Injection**: Update the metadata client and orchestrator to always include identity headers.
- **Signature Refactoring**: Update internal API signatures to optionally accept a `council_id` parameter.
- **Traceability Injection**: Inject the deliberation `session_id` as the `X-Council-ID` header in all model-facing requests.

## 3. Targeted Injection Points
1.  `src/llm_council/metadata/openrouter_client.py`: Update `_build_headers` to include the standard project headers.
2.  `src/llm_council/openrouter.py`: Update `query_model_with_status` to accept and send `X-Council-ID`.
3.  `src/llm_council/gateway_adapter.py`: Ensure that `council_id` is accepted in parallel query functions and passed to the underlying backend.
4.  `src/llm_council/council.py`: Propagate the `session_id` into all Stage 1, Stage 2, and Synthesis Stage calls.
