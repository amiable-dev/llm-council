# ADR-046: Streaming Deliberation

**Status:** Draft 2026-07-03
**Date:** 2026-07-03
**Decision Makers:** Chris Joseph, LLM Council
**Council Review:** 2026-07-03 (4 models, balanced) — feedback incorporated: event schemas, per-phase DoD, ADR-045 fallback
**Related:** ADR-045 (MCP Tasks/progress — complementary), ADR-023 (gateway SSE, v0.27.1), ADR-012 (progress callbacks), ADR-044 (early consensus — event source)

---

## Context

A council deliberation takes 30–600s and today renders as a spinner. The HTTP
server has an SSE endpoint emitting coarse stage-completion events
(`council.stage1.complete`, …), the gateway grew **true token streaming** in
v0.27.1 (`complete_stream`), and Stage 2 already observes per-reviewer
completions (ADR-040 Option D / ADR-044 P2 incremental path) — but none of
this reaches users as live content. Survey (2026-07): **no implementation in
the llm-council ecosystem streams**; this is the most visible differentiation
available, and perceived latency is the product's felt weakness.

Enabler: `council.py` (~104K) exceeds the Council review cap, so streaming
changes to it cannot be self-reviewed. Split it first (precedent: #380 split
`verification/api.py` 90K → 39K with back-compat re-exports).

## Decision

Stream deliberation progressively at three depths, each opt-in per request
(`stream=true` on HTTP; MCP progress/Tasks per ADR-045). Non-streaming paths
byte-identical.

### Phase 0 — Enabler: split `council.py` below the review cap
Extract cohesive units (stage functions, prompts, aggregation) into submodules
with verbatim moves + back-compat re-exports, per the #380 playbook.

### Phase 1 — Rich stage events
Extend the SSE endpoint from coarse stage events to per-model events:
`stage1.response` (model, full text as each lands — the as_completed path
already observes this), `stage2.review` (reviewer + parsed ranking),
`consensus.early_termination` (ADR-044 P2 event), `stage3.start`.

### Phase 2 — Chairman token streaming
Stage 3 optionally uses the gateway `complete_stream`; SSE emits
`synthesis.delta` tokens, then the final structured result event (verdict,
usage/cost per ADR-011). Non-stream fallback identical to today.

### Phase 3 — MCP surface
Map the same event stream onto MCP progress notifications (and Task progress
when ADR-045 P1 lands) so Claude Code/Cursor users see live deliberation.
**ADR-045 fallback (council feedback):** P3 does not depend on ADR-045 —
plain MCP progress notifications carry the coarse events today; Task-based
delivery is an upgrade when available.

### Event schema (council feedback)
All SSE events are `{"event": <name>, "data": {…}}` with a shared envelope
(`session_id`, `ts`, `seq`). Payloads:
- `stage1.response`: `{model, response, latency_ms, usage}`
- `stage2.review`: `{reviewer, ranking: [labels], parse_ok}`
- `consensus.early_termination`: the ADR-044 P2 event payload verbatim
- `stage3.start`: `{chairman}` · `synthesis.delta`: `{text}`
- `result`: the full CouncilResponse (incl. ADR-011 `usage`) — terminal
- `error`: `{stage, error_status, error_detail}` (#403 semantics) — terminal
Schema is versioned (`v` field); additive changes only.

**P1 implementation note (2026-07-03):** the terminal events keep their
existing ADR-025 wire names `council.complete` / `council.error` — renaming
to `result`/`error` would break existing SSE consumers, violating this ADR's
own additive-only rule. The envelope (`v`/`session_id`/`ts`/`seq`) and all
new per-model events ship exactly as specified above.

## Consequences

**Positive:** the spinner becomes a live deliberation view; ecosystem
differentiation; the event vocabulary also feeds observability (ADR-030).

**Negative / risks:** streaming paths double some code routes (mitigation:
stream assembled FROM the same primitives — the delta path constructs the same
final result object, asserted by tests); Stage-1 responses streamed before
anonymization must not leak into Stage-2 context (they don't — Stage 2 uses
its own anonymized prompt — but tests must pin this); token streams + partial
usage require the ADR-011 accounting to stay correct on cancelled/failed
streams (gateway already raises on stream HTTP errors, #375).

## Definition of Done (per phase — council feedback: concrete)
- **P0:** every extracted module < 50K chars; back-compat re-exports; suite
  count identical; ruff clean.
- **P1:** SSE emits all Phase-1 events with the schema above; non-stream
  responses byte-identical (test); event-order invariants tested.
- **P2:** streamed synthesis assembles to the SAME final result object as the
  non-streamed path (equality test); usage/cost correct on cancelled streams.
- **P3:** MCP progress visible in a real client session; tool descriptions
  document progress semantics.
- All phases: README streaming section, CLAUDE.md, CHANGELOG.

## References
- `docs/roadmap-2026-h2.md` item 3; gateway SSE (v0.27.1, #375); #380 split playbook
