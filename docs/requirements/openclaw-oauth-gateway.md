# OpenClaw OAuth Gateway Requirements

## Purpose

The OpenClaw gateway lets LLM Council use provider runtimes that are already
authenticated by OpenClaw. LLM Council authenticates only to the local OpenClaw
operator gateway; OpenClaw owns provider OAuth login, refresh, and model routing.

This integration does not turn an OpenAI or Google subscription into a provider
API key, and it must not copy provider OAuth credentials into LLM Council.

## Functional requirements

| ID | Requirement |
| --- | --- |
| OC-OAUTH-001 | `gateways.default: openclaw` is a valid unified configuration. |
| OC-OAUTH-002 | When no council `base_url` is supplied, the endpoint uses the port in the selected OpenClaw configuration file and remains bound to loopback. |
| OC-OAUTH-003 | `OPENCLAW_CONFIG_PATH` selects the OpenClaw configuration file; otherwise `~/.openclaw/openclaw.json` is used. |
| OC-OAUTH-004 | `OPENCLAW_GATEWAY_PORT` overrides the port read from the OpenClaw configuration. |
| OC-OAUTH-005 | `OPENCLAW_GATEWAY_TOKEN` overrides `gateway.auth.token`; provider API keys and provider OAuth credentials are neither required nor read. |
| OC-OAUTH-006 | An explicit `gateways.providers.openclaw.base_url` overrides endpoint discovery for an operator-managed local proxy or non-default route. |
| OC-OAUTH-007 | Missing, unreadable, malformed, or tokenless OpenClaw configuration fails closed with an actionable error and never includes a credential value in the error. |
| OC-OAUTH-008 | Model IDs such as `openclaw/council-gpt` and `openclaw/council-gemini` pass through to the OpenClaw OpenAI-compatible chat endpoint. |
| OC-OAUTH-009 | Council health uses the OpenClaw operator token as the effective gateway credential and reports only the non-secret source label `openclaw_gateway`. |
| OC-OAUTH-010 | A successful OpenClaw health check probes every model in the selected tier; any unavailable member makes `ready` false and identifies the affected model. |
| OC-OAUTH-011 | Deep health also probes the chairman and preserves the repository's chairman-resilience readiness semantics. |
| OC-OAUTH-012 | If the initial connectivity probe fails, member and chairman probes are skipped to avoid redundant failing requests. |
| OC-OAUTH-013 | Existing OpenRouter, Requesty, direct, auto, and Ollama behavior remains unchanged. |

## Operational requirements

- The OpenClaw OpenAI-compatible chat-completions endpoint must be enabled.
- The gateway should listen on loopback unless an operator deliberately provides
  another trusted, access-controlled endpoint.
- Every `openclaw/<agentId>` used by a tier must have a working OpenClaw runtime
  and provider login.
- The chairman agent must remain reachable for stage-3 synthesis.
- Operator tokens, OAuth authorization codes, refresh tokens, and provider
  credentials must never be committed to the repository or written to test
  fixtures.

## Acceptance criteria

The integration is releasable when the requirements above are mapped to automated
tests in the [OpenClaw OAuth test coverage](../testing/openclaw-oauth-gateway.md),
the focused suite passes, the documentation build passes, and one local deep
health plus combined GPT/Gemini consultation succeeds against a configured
OpenClaw instance.
