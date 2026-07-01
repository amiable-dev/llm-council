# ADR-011: Cost and Token Accounting

**Status:** Implemented 2026-07-01 (Phases 1–4, v0.25.0; epic #359) — was Accepted 2026-07-01
**Date:** 2026-07-01 (refreshed from Proposed draft 2024-12-12)
**Decision Makers:** Chris Joseph, LLM Council
**Related:** ADR-009 (open-core boundary), ADR-024 (L1→L4 layers), ADR-030 (metrics export), ADR-041 (verification telemetry), ADR-022/ADR-026 (tier/model selection), ADR-027 (frontier cost ceiling)

---

> **Revision note (2026-07-01):** This ADR was drafted in 2024 as a Proposed design and never implemented. It is refreshed here to reflect three developments since: (1) OpenRouter now returns authoritative per-request USD cost inline on every response, (2) OpenTelemetry has standardized GenAI token/cost metric names, and (3) PostHog LLM Analytics is available as a dashboard sink. These collapse most of the original "PricingService" and "cloud dashboard" scope. The layer-ownership model (ADR-024) — absent in the original — is now the organizing principle.

## Context

A council query fans out to 3–10 models across 3 stages, so cost is both significant and hard to predict. Users need: pre-submission estimates, post-submission breakdowns, optional budget controls, and — most importantly as token prices rise — data to **optimize token spend against output quality**.

### Verified current state (2026-07-01)

Token accounting is ~80% plumbed but the cheap, high-value pieces are missing:

- **Tokens are captured** at every gateway as `UsageInfo{prompt_tokens, completion_tokens, total_tokens}` (`gateway/types.py:43`) and aggregated **per stage** in `council.py:2071` → returned inside `metadata["usage"]` (`by_stage` + grand `total`, `council.py:2244`).
- **Tokens are NOT attributed per model** — only per stage. You cannot see which model burned the budget.
- **Tokens are buried** — they live inside an untyped `metadata: Dict[str, Any]` (`http_server.py:139`), are absent from the OpenAPI schema, and the MCP `consult_council` tool returns latency but no tokens/cost (`mcp_server.py:304`). `VerifyResponse` carries `timing`/`input_metrics` (ADR-041) but no token/cost fields.
- **USD cost is never computed.** No `tokens × price` exists anywhere. `cost_ceiling.py` only *filters* candidate models; `metadata/scoring.py` only *scores* models for selection. Registry pricing (`models/registry.yaml`, `pricing.prompt`/`pricing.completion` per 1K tokens) sits unused for accounting.
- **The provider's own cost is discarded** — `openrouter.py:138` extracts `usage` but drops the `cost` field OpenRouter returns.

### The peer-review cost driver

Stage 2 input grows O(N × M) (N models × M avg Stage-1 length): 5 models × ~500 tokens each means every reviewer ingests ~2500+ input tokens. Peer review is typically the largest single cost bucket, which is why per-stage attribution matters.

## Decision Drivers

- **Transparency** — users see exactly how much a query cost and where it went.
- **Optimization** — expose cost *per unit of quality* so model/tier selection can be tuned.
- **Accuracy** — prefer provider ground-truth cost over local estimation.
- **Reliability** — accounting must never fail a query (soft-fail like all telemetry, per ADR-041).
- **No overloading** — cost is a horizontal concern; it must not become a hidden input to layer decisions (ADR-024 sovereignty).

## Decision

Treat cost/token accounting as a **horizontal observability concern** (like metrics/logging), not a new layer and not an input to routing decisions. It threads through the existing L1→L4 model (ADR-024) at four well-defined points and surfaces at the edges.

### 1. Cost data source — provider ground-truth first, registry fallback

The original design centered on a `PricingService` that fetches and caches OpenRouter prices. That is now largely unnecessary for **post-query** accounting:

- **Primary (OpenRouter path):** capture the authoritative cost the provider already returns. Every OpenRouter response now includes `usage.cost` plus `usage.cost_details{upstream_inference_cost, cache_discount}` and `cached_tokens`. This is the exact amount billed — no estimation, and it correctly accounts for prompt caching (a real optimization lever). Extend `UsageInfo` with `cost_usd: float | None` and populate it at `gateway/openrouter.py:311` from the response; drop nothing.
- **Fallback (direct/Ollama and other gateways that don't return cost, and all pre-query estimation):** compute from the pricing table that already exists in `models/registry.yaml` (`pricing.prompt`/`pricing.completion`, per 1K tokens). No hardcoded dict, no new fetch service — read the registry the metadata layer already loads.

So `PricingService` shrinks to a thin helper: "use `usage.cost` if the gateway supplied it, else `(prompt·p_in + completion·p_out)/1000` from the registry." Ground-truth where available, deterministic fallback otherwise.

**Cost is not OpenRouter-only.** The gateway layer (ADR-023) already routes across four providers, and their cost fidelity differs. A single `CostResolver` at L4 applies the right strategy per gateway and stamps each `UsageInfo` with a `cost_source` so accuracy provenance is explicit — a computed estimate is never presented as a bill:

| Gateway | Providers | `cost_source` | Basis |
|---|---|---|---|
| OpenRouter | 100+ models | `provider` | `usage.cost` (+ `cost_details`, `cached_tokens`) — the billed amount |
| Requesty | 300+ models | `provider` if returned, else `registry_estimate` | router-reported when present |
| Direct | Anthropic, OpenAI, Google (native APIs) | `registry_estimate` | `registry.yaml` pricing × tokens (native APIs return tokens only) |
| Ollama | local models | `local_zero` | self-hosted; no marginal API cost |

This is exactly the reconciliation model ADR-023 §5 (`UnifiedCostRecord.pricing_source`) left open; ADR-011 fulfills it. When both a router-reported and a registry-computed figure exist, log the delta to keep the pricing table honest. BYOK subtlety: on OpenRouter, `cost_details.upstream_inference_cost` is populated **only** for BYOK requests — so BYOK users get *more* granular cost detail, worth surfacing. BYOK credential handling itself is unchanged (ADR-023/ADR-013: request-scoped ContextVar → env → keychain → config).

### 2. Where accounting attaches in the layer model (ADR-024)

| Layer | Responsibility | Concrete change |
|---|---|---|
| **L4 Gateway** (capture) | Record `cost_usd` + `cost_source` + `cached_tokens` on the response via the `CostResolver` (§1). **Data only, no decisions.** | Add the three fields to `UsageInfo` (`gateway/types.py:43`); populate per-gateway (ground-truth in `openrouter.py`/`requesty.py`, registry estimate in `direct.py`, zero in `ollama.py`). |
| **L3 Council** (aggregate) | Sum tokens **and** cost, adding the missing **per-model** dimension alongside per-stage. | Extend `total_usage` (`council.py:2071`) and grand total to carry `cost_usd`; add a `by_model` map. Home for the `CostSummary`/`TokenUsage` DTOs. |
| **Edges** (surface) | Make it visible to callers. | Typed `usage`/`cost` block on `CouncilResponse` (`http_server.py:139`); token/cost fields in `VerifyResponse.input_metrics` (ADR-041's existing home, `verification/api.py`); a cost section in MCP `consult_council` output. |
| **Observability** (emit) | Push to metrics backends and dashboards. | Emit via the existing `MetricsAdapter` (ADR-030) using OTel names (below); optionally sink to PostHog LLM Analytics. |

**Sovereignty guardrail:** L1 (tier) and L2 (triage) must **not** silently read cost to gate or escalate. The only place cost influences control flow is the *explicit, opt-in* budget check in §4, which emits an auditable `LayerEvent`. This preserves ADR-024's "explicit/auditable escalation" and "failure isolation" principles.

### 3. Observability — adopt OpenTelemetry GenAI semantic conventions

Rather than invent metric names, adopt the now-standard OTel GenAI conventions so Datadog/Grafana/PostHog ingest them with zero custom mapping:

- `gen_ai.client.token.usage` — histogram of token counts, tagged `gen_ai.token.type` = `input|output`, `gen_ai.request.model`, and `gen_ai.operation.name` = the council stage.
- A cost counter/gauge (`llm_council.cost.usd`) tagged by model and stage, until a GenAI-standard cost metric stabilizes (the token conventions are standardized; cost is still emerging).

These flow through the existing `emit_layer_event()` → `MetricsAdapter` path (`observability/metrics_adapter.py`); `LayerEvent.data` already accepts arbitrary fields, so no structural change is needed. PostHog LLM Analytics (already integrated in tooling) serves as the historical-dashboard sink — this **replaces** the original ADR's "paid cloud tier / PostgreSQL dashboards," which we no longer need to build.

### 4. Budget enforcement — opt-in, tiered, auditable (unchanged in spirit)

Retained from the original design, but explicitly framed as opt-in and auditable:

- Modes: `STRICT` (reject if high estimate exceeds), `BALANCED` (reject if expected exceeds, warn if high exceeds), `PERMISSIVE` (warn only). Default off; when enabled, `BALANCED`.
- **Never abort mid-completion** (wastes spent tokens); check only between stages and return partial results gracefully — consistent with the verification pipeline's durable-partial-state behavior (ADR-040).
- Every reject/warn emits a `LayerEvent` so the decision is visible, never a silent tier change.
- Pre-query estimation uses the percentile predictor (§5), the only place estimation (vs. ground truth) is used.

### 5. Pre-query estimation (Phase 2 only)

Post-query needs no estimation — we have actuals (provider cost or registry math). Estimation is only needed *before* a run, for the budget gate and for showing an expected range. Keep the model×stage historical-percentile predictor from the original draft (p50/p75/p95 completion tokens, EMA-updated from actuals), sourcing per-model history from the **performance index** the `performance/` module already persists (ADR-026 P3 / ADR-041). This avoids a second data store.

### 6. Optimization: cost-per-quality (the "part b" payoff)

Transparency alone doesn't optimize spend. To optimize token-vs-output we add a **cost dimension to the performance index**: extend `ModelSessionMetric` and `ModelPerformanceIndex` (`performance/types.py`) with `cost_usd`, giving a **Borda-per-dollar** (quality-per-cost) signal per model. That signal then feeds cost-aware model/tier selection in L1/L2 (ADR-022/ADR-026) — the one place cost legitimately enters routing, and only via the explicit, audited selection path, never silently. This is deliberately sequenced last: it depends on Phase 1 data existing.

### 7. Output surfaces — progressive disclosure

Cost/token data must reach humans and the *calling LLM* without flooding either. The calling model's context window is a scarce resource, so the governing principle is **progressive disclosure**: a single dense summary line by default, full per-model/per-stage breakdown only on request.

| Surface | Consumer | Default (always) | On request | Notes |
|---|---|---|---|---|
| MCP `consult_council` | Claude Code / Cursor chat | One line: `~8.5k tokens · ~$0.021 · high tier` | Per-model + per-stage table behind existing `include_details=true` | **Prerequisite:** `run_council_with_fallback()` does not currently aggregate usage into `metadata` (unlike `run_full_council()`); fix first, else MCP has no token data at all |
| MCP `verify` / CLI `gate` | LLM chat + CI | One row in the metrics table | `### Cost & Tokens` section | Single change in `verification/formatting.py:format_verification_result()` serves both |
| HTTP council endpoint | SDK / programmatic | Typed `usage` block always present | — | Promote `metadata["usage"]` from `Dict[str, Any]` to a documented Pydantic model so OpenAPI + generated clients expose it |
| HTTP stream (SSE) | live UIs | incremental usage per `stage.complete` event | — | enables a live cost ticker |
| CLI `cost-report` (new) | human analyst | compact summary | `--verbose`, `--days`, `--min-cost`, `--format text\|json\|csv` | Clones the `bias-report` framework (`bias_aggregation.py` text/JSON/CSV + ASCII bars) reading the same performance-index store |

Two distinct consumption modes: **per-query transparency** (inline summary, rendered in the chat/response) and **cross-session reporting** (the `cost-report` CLI). They share DTOs but not surfaces.

### 8. Tooling integration — one emitter, example templates

The observability metrics (§3) double as the integration point for external LLM-cost tooling. **Build one vendor-neutral OTLP exporter, not N per-vendor adapters.**

- **Single OTLP `gen_ai.*` exporter.** Because the metric names follow OTel GenAI conventions, one exporter feeds PostHog, Datadog, Grafana, Langfuse, Honeycomb, and Traceloop with zero per-vendor mapping.
- **PostHog LLM Analytics** (the primary named target) accepts this two ways: (a) native `$ai_generation` events — PostHog auto-computes cost at ingestion from `$ai_provider` + `$ai_model` + token counts, using **OpenRouter pricing as its primary source** (the same reference this ADR uses, so figures reconcile across the stack); or (b) OTLP `gen_ai.*` spans over its OTLP endpoint (Bearer-token auth), auto-converted to `$ai_generation`. Where we hold provider ground-truth (OpenRouter path), we send precalculated cost props (`$ai_input_cost_usd`, …) which PostHog uses verbatim; for `registry_estimate` sources we send tokens + model + provider and let PostHog compute, or send `$ai_*_token_price` custom pricing for exotic/BYOK models.
- **Deployable examples.** The repo ships no observability templates today (single-service `docker-compose.yml`, no Grafana/Prometheus assets). Add `examples/observability/`: a compose overlay wiring an OTel Collector → PostHog **and** Prometheus/Grafana; one Grafana dashboard JSON (cost/tokens by model/stage/tier, plus cost-per-quality once Phase 3 lands); and a PostHog config snippet. "Top N" resolves to three sinks — PostHog, Prometheus/Grafana, generic OTLP — covered by the one emitter.
- **BYO-backend boundary.** We emit standards-compliant signals; we do not bundle a datastore or hosted dashboard. Consistent with the open-core boundary (ADR-009).

## Response schema

```python
@dataclass
class TokenUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cached_tokens: int = 0            # from provider, when available
    by_stage: dict[str, dict]
    by_model: dict[str, dict]         # NEW: fills the per-model gap

@dataclass
class CostSummary:
    total_cost_usd: float
    currency: str = "USD"
    cost_source: str                  # "provider" | "registry_estimate" | "local_zero" | "mixed"
    by_stage: dict[str, float]
    by_model: dict[str, dict]         # reviewer-primary attribution; each carries its own cost + cost_source
    tokens: TokenUsage
    estimate_accuracy: float | None = None   # actual/estimated, when a pre-query estimate existed
```

**Attribution:** primary cost is attributed to the **reviewer** in Stage 2 (the reviewer's verbosity causes the cost; actionable as "Claude's reviews cost 2× GPT's"), with a secondary analytic view splitting cost across reviewed responses. Unchanged from the original decision.

## Where it lives (open-core)

A slim `llm_council/cost_tracking/` module in the OSS core:

```
cost_tracking/
├── types.py         # TokenUsage, CostSummary DTOs
├── calculator.py    # provider-cost passthrough + registry fallback math
├── predictor.py     # pre-query percentile estimation (Phase 2)
└── enforcer.py      # opt-in tiered budget checks (Phase 4)
```

Pricing fallback data is the existing `models/registry.yaml` — no new bundled price list. Dashboards are PostHog LLM Analytics — no bundled storage backend. Everything cost-related is fully functional offline (registry fallback), consistent with the Sovereign Orchestrator principle (ADR-026).

## Consequences

**Positive**
- Full spend transparency for OSS users; provider ground-truth is more accurate than any local estimate and captures cache savings.
- Per-model + per-stage attribution enables real optimization, not just a total.
- OTel-standard naming means dashboards work out of the box; PostHog gives history for free.
- Minimal new surface area — extends existing structures (`UsageInfo`, `total_usage`, `input_metrics`, `MetricsAdapter`, performance index) rather than adding a parallel system.

**Negative / risks**
- Registry fallback prices go stale (mitigated: OpenRouter path uses ground truth; registry only covers non-OpenRouter gateways and estimates).
- OTel GenAI cost metrics are still stabilizing (mitigated: token metrics are standardized; we namespace our cost metric until a standard lands).
- Per-model attribution requires threading model identity through Stage-2 aggregation, which today only sums per stage.

## Migration path

1. **Phase 1 — Transparency (post-query):** capture provider `cost_usd` at L4; add per-model aggregation at L3; surface typed token/cost blocks in HTTP, MCP, and `VerifyResponse`. Highest leverage, smallest change.
2. **Phase 2 — Observability:** emit OTel-named token/cost metrics via `MetricsAdapter`; route to StatsD/Prometheus/PostHog.
3. **Phase 3 — Optimization:** cost dimension in the performance index → cost-per-quality → cost-aware selection (ADR-022/026).
4. **Phase 4 — Enforcement (opt-in):** pre-query estimation + tiered `BudgetEnforcer` + budget `LayerEvent`s.

## Definition of Done

This feature adds cross-cutting surface area (config, gateway fields, output rendering, external tooling), so **no phase is "done" on code + tests alone.** Each phase's DoD includes the documentation and LLM-facing text that keep the feature discoverable and context-safe:

1. **Code + tests** — unit tests for the `CostResolver` per gateway (provider / registry_estimate / local_zero), aggregation correctness (per-stage **and** per-model), and soft-fail behavior (accounting errors never propagate to results, per ADR-041).
2. **User documentation** — update `CLAUDE.md` (env-var index + module map + the L4→L3→edge cost path), the README/docs site (what cost data appears where, the new `cost-report` CLI, `examples/observability/` templates), and `CHANGELOG.md`. Document `cost_source` semantics so users know when a number is billed vs estimated.
3. **LLM-facing support text (context management)** — this is a first-class deliverable, not an afterthought. Update:
   - **MCP tool descriptions/instructions** (`consult_council`, `verify`) so calling models know the cost/token fields exist, that a compact summary is returned by default, and that the full breakdown is available via `include_details` — instructing them **not** to request or echo the full breakdown unless the user asks. This encodes progressive disclosure at the protocol boundary so it protects the caller's context window by default.
   - **Bundled skills** (`skills/` — council-verify, council-review, council-gate) to describe the cost summary and how to surface it succinctly.
   - **HTTP OpenAPI** field descriptions on the typed `usage`/`CostSummary` model.
4. **Deployable examples** — `examples/observability/` (compose overlay + Grafana JSON + PostHog snippet) present and referenced from the docs.
5. **Config surface** — new keys documented in `unified_config.py` schema and the env-var index, defaults called out (accounting on, enforcement off).

**Progressive-disclosure invariant:** the default output of any human/LLM-facing surface is the one-line summary; the verbose breakdown is always gated behind an explicit flag/parameter. A phase that renders full per-model detail by default fails DoD.

## Compliance / Validation

- No cost read occurs in L1/L2 decision code except the explicit `BudgetEnforcer` call (grep-able invariant).
- Accounting failures are caught and never propagate to verification/council results (mirrors ADR-041's try/except telemetry wiring).
- Token/cost metric names conform to OTel GenAI semantic conventions.

## References

- [ADR-009: HTTP API and Open Core Boundary](./ADR-009-http-api-open-core-boundary.md)
- [ADR-024: Unified Routing Architecture (L1→L4)](./ADR-024-unified-routing-architecture.md)
- [ADR-030: Scoring Refinements / Metrics Export](./ADR-030-scoring-refinements.md)
- [ADR-041: Verification Telemetry Wiring](./ADR-041-verification-telemetry-wiring.md)
- [ADR-023: Multi-Router Gateway Support](./ADR-023-multi-router-gateway-support.md) — provider/BYOK layer; cost-reconciliation gap this ADR closes
- [OpenRouter Usage Accounting](https://openrouter.ai/docs/cookbook/administration/usage-accounting)
- [OpenTelemetry GenAI Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-spans/)
- [PostHog LLM Analytics — Calculating costs](https://posthog.com/docs/llm-analytics/calculating-costs) and [OpenTelemetry ingestion](https://posthog.com/docs/ai-observability/installation/opentelemetry)
