# ADR-045: MCP 2026-07-28 Specification Adoption (Tasks, Server Card, Stateless Transport)

**Status:** Draft 2026-07-03
**Date:** 2026-07-03
**Decision Makers:** Chris Joseph, LLM Council
**Council Review:** 2026-07-03 (4 models, balanced) — feedback incorporated: task authz, task-state persistence/expiry, phase independence, rollback semantics
**Related:** ADR-012 (MCP reliability — this extends it), ADR-040 (timeouts), ADR-046 (streaming — complementary)

---

## Context

The council's #1 documented MCP UX pain is **client transport timeouts**: high
(~180s) and reasoning (~600s) tiers exceed typical MCP client defaults (~60s),
forcing users to raise `MCP_TIMEOUT` manually (documented in the README and the
`consult_council` tool description). A long deliberation that outlives its
transport is lost.

The **MCP 2026-07-28 specification** (release candidate published; final on
2026-07-28) ships primitives that address this directly:

- **Tasks** — a first-class long-running-operation primitive: create a task,
  poll/resume it, retrieve results after client disconnects. Purpose-built for
  30–600s deliberations.
- **Server Cards** — structured server metadata at a `.well-known` URL so
  registries (19k+ indexed servers) and clients can discover capabilities
  without connecting.
- **Stateless Streamable HTTP** — protocol-level statelessness so servers run
  behind load balancers with scalable session handling.

## Decision

Adopt the 2026-07-28 spec in three opt-in, backward-compatible phases. Older
clients keep today's synchronous tools unchanged.

### Phase 1 — Tasks-backed deliberation
- Expose council deliberation and verification as MCP **Tasks** when the
  connected client advertises task support (feature-detect via the negotiated
  protocol version/capabilities): `consult_council` / `verify` create a task,
  emit progress, and deliver the result durably; clients may disconnect and
  resume.
- Synchronous tool behaviour is preserved verbatim for clients without task
  support — no breaking change, no flag needed on the server side.
- SDK dependency: bump the `mcp` Python SDK to the first release with
  2026-07-28 support; if task lifecycle gaps remain (retry semantics/expiry
  are known open items in the RC), constrain to the stable subset and document.
- **Task state & persistence (council feedback):** task results are stored in
  a bounded on-disk store under `.council/tasks/` (same durability class as
  transcripts), keyed by an unguessable task id; default expiry 24h with
  size-capped eviction; in-memory fallback when the store is unavailable
  (degrades to sync semantics, never crashes).
- **Authorization (council feedback):** the task id is a capability — 128-bit
  random, returned only to the creating client; retrieval requires it. Where
  the HTTP surface exposes tasks, `LLM_COUNCIL_API_TOKEN` (ADR-038) gates
  access exactly as for synchronous endpoints. No cross-client enumeration
  (no task listing without auth).
- **Rollback (council feedback):** the synchronous path IS the rollback — task
  exposure is capability-negotiated per client and additionally kill-switched
  by `LLM_COUNCIL_MCP_TASKS=false`.

Phases 2 and 3 are independent of Phase 1 and of each other (council
feedback): any subset may ship alone.

### Phase 2 — Server Card
- Serve a Server Card at `.well-known` from the HTTP server, and ship a static
  card in the repo for registry submission: name, capabilities (tools, tiers),
  auth expectations, and docs links.
- Card content generated from the actual tool registry (no drift).

### Phase 3 — Stateless transport alignment
- Audit session state in the MCP server path; move any per-session state into
  request scope or durable stores (task results) so multiple instances behind a
  load balancer behave correctly. Validate with a two-instance smoke test.

## Consequences

**Positive:** kills the MCP_TIMEOUT footgun for long tiers; registry
discoverability; horizontal scalability; early, correct adoption of a spec
finalizing within weeks is high-visibility for the project.

**Negative / risks:** SDK availability/decay of experimental Task semantics
(mitigation: feature-detect + sync fallback, pin SDK, constrain to stable
subset); Server Card schema may shift between RC and final (mitigation: ship
after the 2026-07-28 final, generate from code).

## Definition of Done (per phase)
Code + tests (incl. old-client fallback proving byte-identical sync behaviour);
user docs (README MCP section — retire the MCP_TIMEOUT warning for task-capable
clients — CLAUDE.md, CHANGELOG); LLM-facing tool descriptions updated for task
flows.

## References
- MCP 2026 roadmap & 2026-07-28 RC (modelcontextprotocol.io / blog)
- `docs/roadmap-2026-h2.md` item 2 (sources)
