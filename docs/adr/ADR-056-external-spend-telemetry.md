# ADR-056: External Spend Telemetry — OTLP Spans for Council Cost

**Status:** Proposed 2026-09-24
**Date:** 2026-09-24
**Decision Makers:** llm-council maintainers
**Proposed by:** [#695](https://github.com/amiable-dev/llm-council/issues/695), which requires an ADR before code: this adds both a runtime dependency and a data egress path.
**Relates to:** ADR-011 (cost accounting), ADR-030 (metrics export), ADR-049 (prompt caching / cache counters), ADR-050 (PostHog emission — the opt-in precedent), [#692](https://github.com/amiable-dev/llm-council/issues/692) (the record this reports on)
**External contract:** `amiable-dev/skills-telemetry` ADR-010, `stdtel/artefact.py` at commit `3d93d8b`

> The ticket said "next number is ADR-055". That number was taken by
> [ADR-055 Chairman Resilience](ADR-055-chairman-resilience.md) on 2026-08-27,
> between the ticket being filed and this being written. This is ADR-056.

## Context

`skills-telemetry` attributes the cost of agent work to the artefacts that caused it — skills, sub-agents, turns. Council spend is invisible to it: the harness sees that a command ran, not what it cost. Its ADR-010 defines a fifth artefact kind, `external`, for precisely this case — the one kind stdtel *receives* rather than observes, because only the spending process knows the amount.

This is council's half of that contract.

**It depends on #692.** Until the consult path records a cost, there is nothing for a span to carry. That dependency also resolves what would otherwise be this ADR's hardest question — see *Building against an external contract* below.

## Decision

### D1 — Emit one span per council run, not per model call

`std.artefact.activation`, `kind=external`, at the boundary where the ADR-011 usage summary already exists (`council_usage._build_usage_summary`, and the equivalent point on the verify path).

Per-model spans were considered and rejected: `openrouter.query_model_with_status` is the only universal call site on the default path, but a span there would report N spans per run with no natural parent, and the aggregate an operator wants — "what did this consult cost" — would have to be reassembled downstream from rows that do not know they belong together.

### D2 — The attribute set is a single constant, checked in both directions

The published `external` allowlist is exhaustive; **anything outside it is dropped silently downstream** rather than rejected. A typo, or a rename on their side, therefore produces a column of nulls rather than an error.

So the allowlist lives in exactly one module constant, which both the emitter and the contract test read. The test writes the expected set out **longhand** rather than comparing the constant against itself — a test that asserts `CONSTANT == CONSTANT` passes through any rename. It fails in both directions: an addition says "extend it", a removal or rename fails and says to raise it on #695 first. `skills-telemetry` added the mirror-image test on their side in #87.

The set, from `stdtel/artefact.py` at `3d93d8b`:

| Attribute | Value council sends |
|---|---|
| `std.artefact.kind` | `"external"` |
| `std.artefact.name` | `"llm-council"` |
| `std.artefact.source` | `"emitter"` |
| `std.external.system` | `"llm-council"` |
| `std.external.operation` | `"consult"` or `"verify"` |
| `std.external.cost_usd` | number — **omitted when not observed** |
| `std.external.requests` | int |
| `std.external.duration_ms` | int |
| `gen_ai.request.model` | string |
| `gen_ai.operation.name` | `"chat"` |
| `gen_ai.usage.input_tokens` | int |
| `gen_ai.usage.output_tokens` | int |
| `gen_ai.usage.cache_read_input_tokens` | int |
| `gen_ai.usage.cache_creation_input_tokens` | int |
| `session.id` | the **Claude** session — see D5 |
| `std.scope.*` | **not ours** — set by stdtel |

### D3 — `std.artefact.source` is `emitter`, and the other values are not ours to use

The vocabulary is `hook` (the Claude Code harness handed the value over), `transcript` (stdtel inferred it from a session file) and `emitter` (the spending process reported it). Nothing outside council's own process saw this spend, so either of the other two would assert an observation that never happened. Their checker rejects them.

*(The ticket originally said `hook`; corrected on their side 2026-09-23, before any code was written against it.)*

### D4 — Omit an unobserved cost. Never send zero, never send null

A zero is a measurement: free tiers and fully cached responses really do cost nothing. An absent attribute records that nothing was observed. Collapsing the two makes averages silently wrong.

This is the same rule #692 and #693 turn on, and it is the third layer at which this release has had to state it. Council's own `cost_known` flag is what decides: present and true ⇒ send the number, including `0.0`; otherwise omit the attribute entirely.

**A registry estimate is not an observation of spend.** #694 lets council price a call from `registry.yaml` when the provider reports nothing, labelled `cost_source="registry_estimate"`. That figure is honest locally, where it sits beside its label, but the external contract has no attribute for provenance — a `std.external.cost_usd` carrying an estimate would be indistinguishable from a bill once it reached a warehouse and was summed. **Only provider-reported cost is emitted**; an estimated cost is treated as unobserved and the attribute is omitted.

### D5 — `session.id` is the Claude session, or absent

Stamped from `CLAUDE_CODE_SESSION_ID`, which Claude Code exports to processes the agent spawns. Council's own ids are not it: the verify path uses an 8-character truncated UUID and the council path a full one, and neither joins to anything on the telemetry side. Their checker rejects a `session.id` that is not in the harness's format, so this mistake fails loudly rather than producing rows that join to nothing.

**Emit even when there is no Claude session.** A CLI or CI run is real spend, and a span that is never emitted is a total that cannot be reconciled against an invoice. `session.id` is omitted in that case; absent is honest.

### D6 — Metadata only

No prompt, no response, no question, no file list, no arguments. Their checker fails on any attribute matching a content prefix, and council asserts it independently: a test puts a recognisable string through a run and greps every attribute of every emitted span for it.

This is a **data egress path**, which is why this ADR exists. Spans leave the process carrying cost figures and model names. That is the whole payload, and the allowlist is what keeps it so.

### D7 — Optional dependency, off unless configured

`opentelemetry-sdk` + `opentelemetry-exporter-otlp-proto-http` behind an `[otel]` extra, import-guarded exactly as ADR-050's `[posthog]` extra is: **never imported when unconfigured**, so an install without the extra is byte-identical to today.

The endpoint is the standard `OTEL_EXPORTER_OTLP_ENDPOINT`. No endpoint ⇒ no exporter, no network call, no added latency, no error. An unreachable endpoint must not block or slow a run.

**Council does not depend on the `stdtel` package to emit.** The contract is attribute names on OTLP spans; the SDK and an exporter are the entire runtime requirement. Depending on `stdtel` would pull Claude Code hook machinery into council's MCP server for nothing.

### D8 — Silence is not the same as nothing spent

A no-op emit path when the extra is absent is correct. Saying nothing about it is not.

`council_health_check` reports telemetry status, so an operator can tell **"nothing was spent"** from **"nothing was recorded"**. That distinction is the entire reason #692 exists, and it would be easy to reintroduce one layer down: a council with no `[otel]` extra, or no endpoint, is indistinguishable from a council that ran nothing — unless it says so.

## Consequences

**Good.** Council spend becomes attributable to the work that caused it. The local record (#692) and the external span carry the same figure from the same source, so the two can be reconciled against each other and against a provider invoice. The allowlist constant makes a contract change a one-file edit.

**Costs.** A second telemetry egress path to keep honest alongside ADR-050's. Two optional extras that an operator must know to install. An external contract council does not control, mitigated by D2's two-way test.

**Risks.** The contract is young: it changed once (`hook`→`emitter`) between the ticket being filed and this ADR. D2 is the containment — a change on their side fails council's build with a message naming the issue to raise, rather than silently dropping a column.

## Building against an external contract

The obvious objection is that council should not implement against a contract that might still move. Two things answer it.

**Dependency order.** #695 depends on #692, which depends on nothing external. By the time the external work is reachable, the contract has merged — which it now has (`skills-telemetry` #87, 2026-09-24). This ADR pins the commit it was written against, so a future reader can diff rather than guess.

**The checker is a second opinion, not the gate.** `stdtel-conform` validates an OTLP dump against their allowlist, and is wired into CI. But council's own deterministic test is what fails the build: if the checker is missing, lagging, or itself wrong, council's build must still fail correctly. Treating someone else's tool as the gate would make council's correctness contingent on their release schedule.

## Alternatives considered

**Emit through the existing ADR-030 MetricsAdapter.** Rejected: that is a metrics pipeline (counters and gauges), and this contract is spans with per-run attributes. `observability/usage_metrics.py` already uses OTel *naming* through that adapter without the SDK; conflating them would give one path two incompatible jobs.

**Emit per model call.** Rejected in D1.

**Depend on `stdtel` and use its `external_activation()` helper.** Rejected in D7. It would guarantee the attribute set matches — which is real value — at the cost of pulling a harness-integration package into an MCP server. D2's two-way test buys most of that guarantee without the coupling.

**Send an estimated cost with a marker attribute.** Rejected: there is no attribute for it in the allowlist, and adding one is their decision, not council's. Omitting is the behaviour the contract already defines for an unobserved cost.
