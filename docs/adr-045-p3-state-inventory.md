# ADR-045 Phase 3 — MCP-path state inventory (stateless-deployment audit)

**Date:** 2026-07-03 · **Scope:** every piece of state on the MCP tool path
(`consult_council`, `council_health_check`, `verify`, `audit`) that outlives a
single request, audited for multi-instance (load-balanced) deployment.
Validated by the two-instance smoke suite (`tests/test_stateless_smoke.py`).

## Deployment model

The **MCP server is stdio**: one process per client session, so MCP tool calls
never span instances today. Multi-instance concerns apply to (a) the **HTTP
server** behind a load balancer and (b) **durable stores shared by concurrent
processes**. Tasks-backed deliberation (ADR-045 P1) is the piece that will
make MCP results cross-instance — which is why `TaskStore` is the load-bearing
item below.

## Inventory

| # | State | Location | Class | Multi-instance impact | Verdict |
|---|-------|----------|-------|----------------------|---------|
| 1 | `TaskStore` (`.council/tasks/`) | `mcp_tasks.py` | durable | Cross-instance by design: atomic writes (`tmp`+`os.replace`), created_at TTL, terminal states first-writer-wins | **OK — smoke-tested** (`test_stateless_smoke.py`: lifecycle split across instances, two-process concurrency, torn-read guard) |
| 2 | Layer-event accumulator | `layer_contracts.py` `_layer_events` | in-memory | Was **unbounded** — a memory leak in any long-lived process (only tests cleared it) | **FIXED** — bounded ring buffer (`MAX_LAYER_EVENTS=1000`); durable observability goes through metrics adapters (ADR-030), this is a debugging window |
| 3 | Circuit-breaker registry | `gateway/circuit_breaker_registry.py` `_circuit_breakers` | in-memory | Instances learn failures independently; one instance's open breaker isn't visible to others | **Per-instance by design.** Each instance protecting itself with its own failure window is standard practice; divergence affects optimality (a few extra probes), never response correctness. Distributed breaker state is deliberate non-scope. |
| 4 | Audition tracker cache | `audition/tracker.py` | in-memory over JSONL | Quarantine/promotion decisions read through a per-process cache; instances converge on the JSONL store with a staleness window | **Eventual-consistent by design.** Audition state gates *voting weight ramp* (advisory), not answer correctness. |
| 5 | Metrics adapter subscriptions | `observability/metrics_adapter.py` | in-memory | Each instance emits its own metrics | **Per-instance by design** — that is how StatsD/Prometheus exporters work; aggregation happens in the metrics backend. |
| 6 | Telemetry singleton | `telemetry.py` `_telemetry` | in-memory | Set at process startup | **OK** — startup-scoped configuration, identical across instances started from the same config. |
| 7 | Model registry / metadata cache | `metadata/registry.py` | in-memory TTL over static/dynamic providers | Staleness window between instances for model discovery | **Eventual-consistent by design** — TTL-bounded; affects candidate selection freshness, not correctness. Offline mode (ADR-026) is the degenerate always-static case. |
| 8 | Module-level config constants (`COUNCIL_MODELS`, `CONFIDENCE_CONFIGS`, `TIER_MODEL_POOLS`, unified config) | `mcp_server.py`, `unified_config.py` | import-time immutable | Identical across instances given identical config/env | **OK** — frozen at import; per ADR-024 config priority is deterministic. |
| 9 | Request API key | `ContextVar` in the HTTP path | request-scoped | None — async-local | **OK** — the reference pattern for request scope. |
| 10 | Durable JSONL stores (bias persistence, performance tracker, transcripts under `.council/logs`) | `bias_persistence.py`, `performance/` | durable append-only | Two instances appending is safe (line-append semantics); aggregation reads whole files | **OK** — append-only; cross-session analytics tolerate interleaving. |

## Conclusions

- **No correctness violations remain.** The one true defect found (unbounded
  `_layer_events`) is fixed with a bounded ring buffer.
- Per-instance circuit breakers, metrics, and caches are deliberate: they
  affect efficiency, not answers, and distributing them would add a shared
  dependency (the thing statelessness avoids) for no correctness gain.
- The cross-instance contract that matters — durable task results — is the
  ADR-045 P1 `TaskStore`, and is pinned by the two-instance smoke suite.

## Re-check triggers

- If the MCP server gains a **streamable-HTTP transport** (post SDK v2, #425),
  re-run this audit for MCP-session-scoped state — stdio's
  process-per-session assumption no longer holds there.
- If audition/quarantine ever becomes a hard gate (voting EXCLUDED enforced at
  selection), revisit #4's staleness window.
