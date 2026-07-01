# Observability templates (ADR-011 Phase 2)

LLM Council emits token/cost metrics using **OpenTelemetry GenAI semantic
conventions** via its metrics adapter (ADR-030), so any OTLP-compatible sink
ingests them with zero custom mapping:

| Metric | Type | Key tags |
|---|---|---|
| `gen_ai.client.token.usage` | histogram | `gen_ai.token.type` (input\|output), `gen_ai.request.model`, `gen_ai.operation.name` |
| `llm_council.cost.usd` | gauge | `gen_ai.request.model` |

These are **collect-only** — emitting them never affects a council result
(soft-fail, ADR-041). Dashboards are **bring-your-own-backend**: we emit
standards-compliant signals; we do not bundle a datastore (open-core boundary,
ADR-009).

## Enable emission

```bash
export LLM_COUNCIL_METRICS_ENABLED=true
export LLM_COUNCIL_METRICS_BACKEND=prometheus   # or statsd
export LLM_COUNCIL_PROMETHEUS_PORT=9464         # scrape target
```

## One emitter, three sinks

The included OTel Collector scrapes the Prometheus endpoint and re-exports
`gen_ai.*` over OTLP — so the *same* emission feeds Prometheus/Grafana **and**
PostHog **and** Datadog. Bring the overlay up alongside the council:

```bash
docker compose -f docker-compose.yml -f examples/observability/docker-compose.observability.yml up
```

- **Grafana** → http://localhost:3000 (import `grafana-dashboard.json`)
- **Prometheus** → http://localhost:9090
- **PostHog LLM Analytics** → set `POSTHOG_API_KEY` and the OTLP endpoint below

## PostHog

PostHog accepts OTLP `gen_ai.*` spans/metrics directly and auto-converts them
into `$ai_generation` events, computing cost from `gen_ai.request.model` using
its OpenRouter-derived pricing (the same reference this project uses — figures
reconcile). Point the collector at PostHog's OTLP endpoint with a Bearer token:

```yaml
# otel-collector-config.yaml — exporters.otlphttp/posthog
exporters:
  otlphttp/posthog:
    endpoint: https://us.i.posthog.com   # or eu.i.posthog.com
    headers:
      Authorization: "Bearer ${POSTHOG_API_KEY}"
```

See `otel-collector-config.yaml` for the full pipeline.
