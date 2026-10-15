# OpenClaw OAuth Gateway Test Coverage

## Coverage objective

The test strategy verifies configuration, endpoint and credential precedence,
fail-closed behavior, and readiness reporting without contacting real providers
or storing real credentials. Live OAuth is an operator smoke test because it
depends on local OpenClaw accounts and must not run in shared CI.

## Automated coverage matrix

| Requirement | Automated coverage | Status |
| --- | --- | --- |
| OC-OAUTH-001 | `test_resolve_endpoint_supports_openclaw_oauth_broker` loads a top-level OpenClaw gateway configuration. | Covered |
| OC-OAUTH-002, OC-OAUTH-003 | `test_openclaw_gateway_reads_local_operator_token_without_provider_keys` verifies config-path and discovered-port behavior. | Covered |
| OC-OAUTH-004, OC-OAUTH-005 | `test_openclaw_gateway_environment_overrides_port_and_operator_token` verifies environment precedence; the discovery test removes provider API keys. | Covered |
| OC-OAUTH-006 | `test_resolve_endpoint_honors_explicit_openclaw_base_url` verifies the explicit route override while retaining local operator authentication. | Covered |
| OC-OAUTH-007 | `test_openclaw_gateway_fails_closed_without_operator_token` and `test_openclaw_gateway_reports_unreadable_configuration` verify actionable failures. Malformed JSON follows the same guarded read path. | Covered |
| OC-OAUTH-008 | Resolver and health tests use the real `openclaw/<agentId>` routing identifiers. | Covered |
| OC-OAUTH-009 | `test_deep_health_check_covers_members_and_chairman` verifies the non-secret credential source label. | Covered |
| OC-OAUTH-010 | `test_health_check_probes_every_openclaw_oauth_member` verifies member-level auth failure and readiness downgrade. | Covered |
| OC-OAUTH-011 | `test_deep_health_check_covers_members_and_chairman` verifies successful member and chairman probes and widened readiness scope. Existing chairman-resilience tests cover chairman failure. | Covered |
| OC-OAUTH-012 | `test_health_check_skips_extra_oauth_probes_after_connectivity_failure` verifies only the initial request is attempted. | Covered |
| OC-OAUTH-013 | Existing gateway resolver, unified configuration, MCP server, and council reliability suites provide regression coverage for other gateways. | Covered by regression suites |

## Verification commands

```bash
uv run pytest tests/test_gateway_resolver_openclaw.py -v
uv run pytest tests/test_gateway_resolver_openclaw.py tests/test_gateway_router.py \
  tests/test_unified_config.py tests/test_mcp_server.py tests/test_council_reliability.py -v
uv run ruff check src/ tests/
uv run mypy src/llm_council --ignore-missing-imports
uv run pytest tests/ -v
mkdocs build
```

## Local OAuth smoke test

Use a local configuration containing GPT and Gemini OpenClaw agents, then run a
deep `council_health_check` followed by one `consult_council` request. Acceptance
requires:

- `ready: true`
- both selected models report `ok`
- the chairman reports `ok`
- the consultation reaches stage 3 and returns a chairman synthesis

On 2026-08-27, the local two-model balanced smoke test met all four criteria.
No OAuth token or authorization code is recorded in this document.
