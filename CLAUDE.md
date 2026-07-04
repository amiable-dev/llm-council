# CLAUDE.md — Technical Notes for LLM Council

Durable architecture, design rationale, and gotchas for future sessions. This file is a **map and a rationale**, not an API reference — for function signatures, read the source (they go stale here). When you change behavior that contradicts a note below, update the note.

## Project Overview

LLM Council is a 3-stage deliberation system where multiple LLMs collaboratively answer a question. The core innovation: **anonymized peer review** in Stage 2 (models rank "Response A/B/C…", not each other by name) so they can't play favorites.

It is a single Python package (`src/llm_council/`) exposing a CLI, an HTTP/REST server, and an MCP server. There is **no separate frontend or `backend/` directory** — older docs referencing `backend.main`, `frontend/src/`, `main.py`, or `storage.py` describe a retired layout.

## Running & Developing

- Install / setup: `make setup` (deps + `.env`), or `make install` (deps only).
- Run the HTTP API: `llm-council serve [--host H] [--port 8000]` (default port **8000**). Entry point is `llm_council.cli:main`; the FastAPI app lives in `src/llm_council/http_server.py`.
- Other CLI subcommands: `setup-key` (store API key in keychain, ADR-013), `bias-report` (cross-session bias analysis, ADR-018), `install-skills`, `gate`.
- Quality gates: `make test` / `make test-fast` / `make test-cov`, `make lint` (ruff), `make typecheck` (mypy), `make check` (lint+typecheck), `make fix`. ~120 test files in `tests/`.
- `tests/test_openrouter.py` verifies OpenRouter connectivity and that a model identifier resolves before you add it to the council.
- **Relative imports**: modules import siblings as `from .unified_config import …`. Keep imports relative within the package.
- ADRs live in `docs/adr/`. Most subsystems below cite the ADR that introduced them — read it for design context.
- **Definition of Done includes the published docs site** (`docs/` + `mkdocs.yml` nav), not just README/CLAUDE.md/CHANGELOG — the site froze at ADR-038 when it was left out of epic DoDs. `tests/test_docs_drift.py` enforces the mechanical parts (env reference, ADR nav, guide snippets).

## Architecture: the L1→L4 layer model (ADR-024)

Requests flow through four layers with formal boundary contracts in `layer_contracts.py`:

- **L1 Tier** (`tier_contract.py`, ADR-022) — picks a confidence tier (`quick|balanced|high|reasoning`, plus `frontier`) and its `TierContract` (timeouts, token budget, peer-review/verifier flags, allowed/aggregator models, escalation policy).
- **L2 Triage** (`triage/`, ADR-020) — domain classification, wildcard specialist selection, per-model prompt optimization (e.g. Claude XML), complexity heuristics.
- **L3 Council** (`council.py`) — the 3-stage deliberation core.
- **L4 Gateway** (`gateway/`, `gateway_adapter.py`, ADR-023/030) — provider calls, circuit breaking.

**Principles (ADR-024):** layer sovereignty (each layer owns its decision), explicit/auditable escalation, failure isolation (gateway failures don't cascade into tier changes), constraint propagation downward, observability by default. Every boundary crossing validates and emits a `LayerEvent` (`emit_layer_event()`); `observability/` bridges those events to StatsD/Prometheus (ADR-030).

## Module map (`src/llm_council/`)

Council core
- `council.py` — the two orchestrators (`run_council_with_fallback`, `run_full_council`), config helpers with patched-attr test semantics, deprecated-constant `__getattr__`. Split below the review cap (ADR-046 P0, #408): stage functions live in `council_stages.py` (`stage1_collect_responses[_with_status]`, `stage1_5_normalize_styles`, `stage2_collect_rankings`, `stage3_synthesize_final`, `quick_synthesis`), ranking/Borda/shadow-votes in `council_rankings.py` (`parse_ranking_from_text`, `calculate_aggregate_rankings`), shared constants + ADR-011 usage accounting in `council_usage.py`. **council.py re-exports every moved name**, so `llm_council.council.X` imports and patches keep working; patches on names CONSUMED inside stage functions (e.g. `query_models_parallel`) must target `llm_council.council_stages.*`. Moved code reads config helpers through the council module at call time, preserving `patch("llm_council.council.CHAIRMAN_MODEL", …)`.
- `openrouter.py` — `query_model` / `query_models_parallel`; returns `{content, reasoning_details?}`; returns `None` on failure (graceful degradation).
- `http_server.py`, `mcp_server.py`, `cli.py` — the three entry surfaces. `skills/` — bundled skills (`install-skills`).

Tiering & model selection
- `tier_contract.py` (ADR-022), `unified_config.py` (ADR-024, see below).
- `metadata/` (ADR-026/028) — model metadata abstraction. `StaticRegistryProvider` (offline, bundled `models/registry.yaml`, ~31 models / 8 providers) and `DynamicMetadataProvider` (OpenRouter API + TTL cache). Background discovery worker + request-time discovery (ADR-028). `intersection.py` resolves tier membership for multi-tier models (e.g. o1-preview).
- `triage/` (ADR-020), `reasoning/` (ADR-026 Phase 2 — effort levels), `performance/` (ADR-026 Phase 3 — internal performance index from real sessions).

Frontier tier lifecycle (ADR-027/029)
- `voting.py` — `VotingAuthority` (FULL / ADVISORY / EXCLUDED). Frontier tier defaults to **ADVISORY (Shadow Mode)**: votes logged + evaluated but zero weight in consensus.
- `audition/` (ADR-029) — cold-start state machine SHADOW → PROBATION → EVALUATION → FULL (+ QUARANTINE). New models earn voting weight by volume before counting.
- `graduation.py` — promote frontier → high (≥30 days, ≥100 sessions, <2% errors, ≥75th pct).
- `cost_ceiling.py` — frontier capped at 5× high-tier avg cost. `frontier_fallback.py` — hard fallback frontier → high on timeout/rate-limit/API error.

Evaluation & scoring
- `rubric.py` (ADR-016) — multi-dimensional scoring (accuracy/relevance/completeness/conciseness/clarity). **Accuracy acts as a ceiling** (`calculate_weighted_score_with_accuracy_ceiling`): accuracy <5 caps at 4.0, 5–6 caps at 7.0, ≥7 uncapped — prevents confident-but-wrong answers ranking well. Falls back to holistic parsing if rubric JSON won't parse.
- `safety_gate.py` (ADR-016) — caps score on harmful-pattern detection; context-aware exclusions for educational/defensive content.
- `evaluation.py`, `quality/`, `verdict.py`, `dissent.py` — additional evaluation/quality surfaces.
- `gateway/` (ADR-030) — `EnhancedCircuitBreaker` (sliding-window failure rate, default 25% over 10-min window, 30-min cooldown, half-open probes) + per-model registry that emits `L4_CIRCUIT_BREAKER_OPEN/CLOSE`. `scoring.py` — cost-scoring algorithms (linear/log_ratio/exponential).

Compute-optimal deliberation (ADR-044, Phase 1–3)
- `graduated_depth.py` (P3) — decision engine + opt-in hook (`plan_escalation`) for the depth ladder single→mini(3)→full: prefix-superset model sets (shallow responses always reusable, escalation only ADDS models), escalation gated on known-low CSS/confidence (unknown never escalates), ADR-011 estimator prices the added rung, opt-in BudgetEnforcer can veto (auditable, never a silent downgrade), approved escalations emit `L2_DELIBERATION_ESCALATION`. `merge_usage_summaries` sums usage across rungs (cost_known ORs). Bounded module — not wired into run_full_council's hot path.
- `early_consensus.py` (P2) — `unassailable_leader` (strict Borda-margin math: decided iff leader > best rival + remaining×(n−1)) + `borda_update` + `estimate_reviewers_cost` (ADR-011 history). Stage 2 checks per completion on the incremental path; flag ON cancels outstanding reviewers cooperatively and emits `L3_EARLY_CONSENSUS_TERMINATION` (votes/cost saved); flag OFF (default) is **shadow mode** — logs the would-have-terminated point so savings are measurable before enabling. Detection is non-authoritative and soft-fail; dissent extraction still runs on collected reviews.
- `metadata/selection.py` `_blend_quality_with_performance` — opt-in (`LLM_COUNCIL_PERFORMANCE_SELECTION`) blend of the live index (`mean_borda_score`) into static quality, weighted by confidence tier (PRELIMINARY 0.3 / MODERATE 0.6 / HIGH 0.8, cap 0.8; INSUFFICIENT→static). `select_tier_models` compares static vs blended selections and emits `L2_PERFORMANCE_SELECTION_APPLIED` only when the set changed (route receipt). Soft-fail; flag-off is byte-identical.

Cost & token accounting (ADR-011, Phase 1–4)
- `budget/` (Phase 4) — **opt-in** budget enforcement, DEFAULT OFF. `CostEstimator` pre-query estimate (low/expected/high) from per-model cost history; `BudgetEnforcer` tiered `pre_query_check` (STRICT/BALANCED/PERMISSIVE) + `mid_query_check` (abort *gracefully* between stages, never mid-completion). Every reject/warn/abort emits an auditable `L1_BUDGET_DECISION` LayerEvent — budget never causes a silent tier change (ADR-024). Enable via `LLM_COUNCIL_BUDGET_ENFORCEMENT=true` + `LLM_COUNCIL_BUDGET_MODE`; wire at the L1 entry (module + hook, not in the hot path by default).
- `performance/` (Phase 3) — `ModelSessionMetric.cost_usd` + `ModelPerformanceIndex.mean_cost_usd`/`.quality_per_cost` (Borda-per-dollar). `tracker.get_cost_per_quality` and `get_all_cost_aware_scores` provide an **opt-in** cost-aware ranking — `get_all_cost_aware_scores` is identical to `get_all_model_scores` unless `LLM_COUNCIL_COST_AWARE_SELECTION=true`, and is the SOLE path by which cost may influence selection (audited). `persist_session_performance_data` records per-model cost from the council's `usage.by_model` (only when `cost_known`).
- `observability/usage_metrics.py` (Phase 2) — `emit_usage_metrics` emits per-model token/cost via the MetricsAdapter (ADR-030) using **OTel GenAI** names (`gen_ai.client.token.usage` histogram + `llm_council.cost.usd` gauge); wired into both council entry points, soft-fail. `examples/observability/` ships an OTel-Collector overlay (Prometheus/Grafana + OTLP → PostHog), a Grafana dashboard, and configs — one emitter, many sinks; dashboards are BYO-backend (ADR-009).
- `gateway/cost_resolver.py` — `CostResolver` stamps `cost_usd` + `cost_source` on each call: **provider** ground-truth for OpenRouter/Requesty (inline `usage.cost`, previously discarded), **registry_estimate** for Direct APIs (`registry.yaml` pricing × tokens), **local_zero** for Ollama. `registry_pricing_lookup` bridges to `metadata.get_provider().get_pricing`. ADR-049 D3: `resolve()` prices `cache_read/_write_5m/_write_1h_tokens` (the provider's SEPARATE fields, additive to `prompt_tokens`) via optional same-named per-1K classes in `registry.yaml` (Anthropic entries carry 0.1×/1.25×/2× prompt); an absent class bills at the prompt price; provider-cost path never consults them (ground truth already includes the discount).
- `openrouter.py` `query_model` now captures `cost`/`cached_tokens`; `council.py` aggregates per-stage **and** per-model (`_add_cost_to_usage` → `_build_usage_summary`, shared by both entry points) into `metadata["usage"] = {by_stage, by_model, total}` — each carries `cost_usd`/`cached_tokens`. **Never presents an estimate as a bill** (`cost_source` distinguishes). Cost accounting never fails a run (soft-fail).
- `cost_summary.py` `format_cost_summary` renders usage with **progressive disclosure**: one dense line by default, full per-model/per-stage breakdown only under `include_details`. Surfaced in MCP `consult_council` ("Cost & Tokens") and as a typed `usage` field on the HTTP `CouncilResponse`. Releases: one version bump per epic, not per PR (git-tag/setuptools-scm; `publish.yml` triggers on tag only).

Prompt caching (ADR-049)
- D1 (#459) — `verification/api.py` `_build_verification_prompt` assembles stability-ordered segments static_head → evidence → subject → volatile_tail; the snapshot SHA lives ONLY in the tail (was line 1, killing cache reuse from byte zero). `render_info["segments"]` = contiguous `{name,start,end,est_tokens(=chars//4)}` — the D2 breakpoint map. Byte-stability golden-tested (`tests/test_prompt_segments.py`).
- D2 (#460) — `cache_context.py`: request-scoped `CacheContext` ContextVar (segments + `session_id` + ttl, house `_request_api_key` pattern). `run_verification` publishes `session_id="verify:{sha1(sorted target_paths)[:12]}"` (stable across rounds — NEVER per-round SHA, affinity-only per ADR-049) and clears in `finally`. `build_openrouter_payload` consumes it: OpenRouter `session_id` on all vendors + `cache_control` breakpoints (`{"type":"ephemeral","ttl":"1h"}`) for `anthropic/*` at evidence/subject boundaries — only when the prompt MATCHES the segment map (stage-2/3 no-op) and cumulative est_tokens meets the per-model min prefix (Fable 5: 512, Opus 4.8/Sonnet 5: 1,024, Haiku 4.5 + unknown: 4,096; below-minimum marks are silently uncached so we skip them). ≤2 of the 4-breakpoint limit used. `LLM_COUNCIL_PROMPT_CACHING=false` ⇒ byte-identical payloads; **default ON** (deliberate — price-class-only, payload format empirically verified). `gateway/base.py` `CachingCapability` descriptor on `RouterCapabilities`. GOTCHA: `LLM_COUNCIL_CACHE_TTL` already exists (response cache, seconds) — D5's prompt-cache TTL knob must use a different name (`LLM_COUNCIL_PROMPT_CACHE_TTL`).

Bench (ADR-048)
- `bench/publication.py` + `bench/adapters.py` (P3, #420) — results page regenerated from harness output (`bench report --publish`); dependency-free DeepEval/RAGAS bridges (`make_council_eval_callable`, `council_to_ragas_row` — stage-1 drafts as contexts); framework wiring examples in `examples/eval_bridges/`.
- `bench/matrix.py` (P2, #419) — config matrix (solo:<model>/council/graduated) over the same dataset; `quality_per_dollar` = pass_rate/known-cost (None when cost unknown/zero — never fabricated); solo configs skip `min_score` floors (no consensus signal); per-config runs individually capped; methodology + caveats in `bench/METHODOLOGY.md`.
- `bench/harness.py` (P1, #418) — golden-dataset drift regression: `bench/dataset/v1/` (20 items, envelopes = any-of `must_contain` groups + `min_score` consensus floor; governance in `bench/dataset/GOVERNANCE.md`), per-run cap enforced against ACTUALS with graceful partial abort (exit 2), monthly guard summed from `.council/bench/runs/*.json`, baseline snapshot + regression compare (exit 1 on drift). `council_runner` is injectable — CI tests never spend. Nightly workflow `.github/workflows/bench.yml`; NEVER per-PR.

Bias (ADR-015/018, ADR-047 P4)
- `bias_audit.py` (ADR-015) — per-session indicators: length↔score correlation (pure-Python Pearson), reviewer calibration, position bias. **These are anomaly indicators, not statistically robust proof** — with N=4–5 models there are only 4–5 data points (≥30 needed for significance), and a single ordering can't separate position effects from quality.
- `bias_amplification.py` (ADR-047 P4, #416) — reviewer-agreement decomposition: `agreement_index` × `position_alignment` per session; high agreement that tracks display order = amplification suspect (multi-agent judges can AMPLIFY shared bias, not cancel it). Report-only by contract (pure, no writes — test-pinned); surfaced via `llm-council bias-report --amplification`.
- `bias_persistence.py` (ADR-018 P1) — JSONL store, `ConsentLevel` (OFF→RESEARCH). `bias_aggregation.py` (ADR-018 P2-3) — cross-session pooled correlation w/ CIs (Fisher-z), confidence tiers, temporal trends, anomaly flagging. Surfaced via `llm-council bias-report`.

MCP 2026-07-28 adoption (ADR-045)
- `mcp_tasks.py` (P1) — SDK-independent Tasks layer: `TaskStore` (durable `.council/tasks/`, 24h TTL from `created_at`, size-capped mtime-LRU eviction, in-memory fallback, atomic writes, terminal states first-writer-wins), 128-bit capability task ids (no enumeration API — the id IS the authz), `LLM_COUNCIL_MCP_TASKS` kill-switch, and `sdk_supports_tasks()` feature-detection (note: mcp 1.26 within the pin already ships the EXPERIMENTAL SEP-1686 types). **Blocked-pending-SDK:** `maybe_expose_tasks` is a documented no-op until the stable SDK v2 pin bump (targeted 2026-07-28), so sync tools stay byte-identical.
- Stateless audit (P3) — `docs/adr-045-p3-state-inventory.md` inventories all MCP-path state for multi-instance deployment: `TaskStore` is the cross-instance contract (two-instance smoke: `tests/test_stateless_smoke.py`); per-instance circuit breakers/metrics/caches are deliberate (optimality, not correctness); `_layer_events` is a bounded ring buffer (`MAX_LAYER_EVENTS`). Re-audit if the MCP server gains streamable-HTTP transport.
- `server_card.py` (P2) — SEP-2127 Server Card generated from the live FastMCP tool registry (no drift; test-pinned). Served by the HTTP server at `/server-card` + `/.well-known/mcp/server-card.json` (unauthenticated, like `/health`); `llm-council server-card` prints it; static `server-card.json` at repo root for registry submission (drift-tested, regenerate on release). Council-specific data (tools, tiers) lives under namespaced `_meta` — SEP-2127 cards exclude top-level primitive listings. **RE-CHECK after 2026-07-28:** RC schema vendored at `tests/fixtures/server_card_v1_rc.schema.json`; re-vendor + re-validate when the final schema ships.

Streaming (ADR-046)
- P3 MCP progress: stage-2 per-reviewer progress flows to `ctx.report_progress` via the orchestrator's `stage2_progress` wrapper — created only when `on_progress` has a consumer (unconditional wiring would flip stage 2 onto the incremental path for every run).
- P2 token streaming: `stream_tokens=true` on the SSE endpoint → `stream_synthesis` on `run_council_with_fallback` → `stage3_synthesize_final(on_synthesis_delta=…)` → `gateway_adapter.query_model_stream_with_status` (gateway `complete_stream`). Streamed path assembles the SAME result object (equality-tested); transport failure falls back to the non-streaming call; CancelledError propagates (never a fallback); streamed `usage` is `{}` ⇒ ADR-011 reports cost UNKNOWN (stream protocol carries no usage).
- P1 rich SSE events: `webhooks/_council_runner.py` wraps every SSE event in the v1 envelope (`v`/`session_id`/`ts`/`seq`); `run_council_with_fallback` wires `on_model_complete` (stage1, through `query_models_with_progress`) and `on_review_event` (stage2 incremental path) into the EventBridge ONLY when a stream consumer exists — no consumer ⇒ None callbacks ⇒ pre-P1 code paths byte-identical (test-pinned). Event names: `stage1.response`, `stage2.review`, `consensus.early_termination`, `stage3.start`; terminals stay `council.complete`/`council.error` (ADR-046 implementation note). An on_event-only EventBridge has an EMPTY subscription set — always pass a `webhook_config` with the event list (see `_council_runner`).

Observability & telemetry
- `observability/` (ADR-030 metrics export — StatsD/Prometheus/NoOp), `telemetry.py` / `telemetry_client.py`, `webhooks/`.

Verification (ADR-034/040/041) — `verification/api.py`
- `run_verification()` wraps `_run_verification_pipeline()` (stages 1–3) in `asyncio.wait_for()` with a global deadline = `tier_contract.deadline_ms/1000 × 2.0` (`VERIFICATION_TIMEOUT_MULTIPLIER`; raised from 1.5 so stage 3 isn't starved on slow days — balanced 180s, high 360s). On timeout, if stage 2 completed, the partial result salvages an advisory rubric/confidence signal (verdict stays `unclear`).
- **Waterfall time budget (ADR-040):** stage1 = 50% of remaining, stage2 = 70% of what's left, stage3 = the rest; each capped by `tier_timeout["per_model"]`.
- **Durable partial state:** `partial_state` is updated after each stage and survives `CancelledError`, so a timeout still returns `completed_stages`. `VerifyResponse` carries `timeout_fired`, `completed_stages`, and (ADR-041) `timing` / `input_metrics`.
- **Per-tier input caps** `TIER_MAX_CHARS` (quick 15K, balanced 30K, high/reasoning 50K). Per-file truncation (#342) is surfaced as an `expansion_warnings` entry rather than silently dropped; `reasoning`/`high` can read a full 50K file.
- Performance tracker is wired on success only, wrapped in try/except so telemetry never fails verification.
- **Screening judge (ADR-047 P3, #415):** `verification/screening.py` — three-state `LLM_COUNCIL_SCREENING` (off default/shadow/active); eligibility INVARIANTS (blocking evidence — dicts AND Pydantic models — security focus, risk globs, 5K cap) checked before any model call; unanimity rule ≥`LLM_COUNCIL_SCREEN_MIN_SCORE` (9) on every dimension; decisions logged to `.council/screening/decisions.jsonl`; active-pass returns PASS-with-audit-note (`screening.acted=true`, council never ran). Soft-fail ⇒ full council.
- **Confidence calibration (ADR-047 P2, #414):** `verification/calibration.py` — corpus loader/analyzer over `.council/logs`, PAV isotonic fit against human dispositions (`.council/calibration/dispositions.jsonl` → `mapping.json`), piecewise-linear `CalibrationMapping` (identity fallback, monotonicity enforced on load). `confidence_calibrated` reported on every response; PASS threshold uses it ONLY behind `LLM_COUNCIL_CALIBRATED_CONFIDENCE` (default off). CLI: `llm-council calibration-report [--fit]`.
- **UNCLEAR disambiguation (ADR-047 P1, #413):** `unclear_reason ∈ {infra_failure, low_confidence, timeout}` on every unclear verdict (`derive_unclear_reason` in `verdict_extractor.py`; timeout checked first, then #403 `error_status`, else low_confidence). Exit code stays 2 — automation routes on the reason: retry infra, accept-and-audit low confidence, re-tier timeouts. None when `error` marker is set (non-deliberated cap results).

## Key design decisions

**Stage 2 prompt format** — strict, to stay parseable: (1) evaluate each response individually, (2) emit a `FINAL RANKING:` header, (3) numbered list (`1. Response C`, `2. Response A`, …), (4) nothing after the ranking. `parse_ranking_from_text()` handles numbered and plain forms; fallback regex extracts any `Response X` in order if a model misbehaves.

**Anonymization / `label_to_model`** — models see `Response A/B/…`; the backend keeps the mapping. Enhanced format (v0.3.0+) uses explicit indices to avoid string-parsing fragility:
```python
{"Response A": {"model": "openai/gpt-4", "display_index": 0}, ...}
# INVARIANT: labels assigned in lexicographic order (A=0, B=1, …)
```
De-anonymization is for display only. Metadata (`label_to_model`, `aggregate_rankings`) is returned via the API but **not persisted**.

**Error handling** — continue with whatever responses succeed; never fail the whole request on a single model failure; only surface an error if *all* models fail.

**Offline mode ("Sovereign Orchestrator", ADR-026)** — `LLM_COUNCIL_OFFLINE=true` forces `StaticRegistryProvider`, disables external metadata/routing, and still completes all core council operations on stale/limited metadata.

## Configuration (`unified_config.py`, ADR-024)

Single Pydantic source of truth consolidating ADR-020/022/023/026/030/031. Priority: **YAML file > env vars > defaults**. YAML searched at `$LLM_COUNCIL_CONFIG` → `./llm_council.yaml` → `~/.config/llm-council/llm_council.yaml`. Supports `${VAR}` substitution. Sections: `tiers`, `triage`, `gateways`, `model_intelligence`, `evaluation` (rubric/safety/bias/scoring/circuit_breaker/audition), `metrics`. Models (council + chairman) are configured in `llm_council.yaml`.

### Environment variable index
| Var | Effect |
|---|---|
| `LLM_COUNCIL_MODELS` | Override council members |
| `LLM_COUNCIL_PERFORMANCE_SELECTION` | ADR-044 P1: blend the live performance index into model selection (default off; auditable route receipt on change) |
| `LLM_COUNCIL_EARLY_CONSENSUS` | ADR-044 P2: cancel remaining Stage-2 reviewers once the Borda leader is mathematically unassailable (default off = shadow mode, which only logs would-have-saved) |
| `LLM_COUNCIL_GRADUATED_DEPTH` | ADR-044 P3: graduated deliberation depth ladder single→mini→full with consensus-gated escalation + budget veto (default off) |
| `LLM_COUNCIL_BENCH_MAX_USD` (2.00) / `_BENCH_MONTHLY_USD` (30.00) | ADR-048 bench spend caps (per-run graceful abort; month-to-date refusal) |
| `LLM_COUNCIL_SCREENING` (off\|shadow\|active) / `_SCREEN_MAX_CHARS` (5000) / `_SCREEN_MIN_SCORE` (9) | ADR-047 P3 screening pre-gate (default off; shadow logs only; active short-circuits unanimous passes — never blocking-capable requests) |
| `LLM_COUNCIL_CALIBRATED_CONFIDENCE` | ADR-047 P2: PASS threshold uses calibrated confidence from the fitted mapping (default off; calibrated value always reported) |
| `LLM_COUNCIL_MCP_TASKS` | ADR-045 P1 kill-switch: disable MCP Tasks exposure even on a task-capable SDK (default enabled-when-supported) |
| `LLM_COUNCIL_PROMPT_CACHING` | ADR-049 D2 kill-switch: Anthropic cache_control breakpoints + OpenRouter session_id on the verify path (default ON — price-class-only; `false` ⇒ byte-identical payloads) |
| `LLM_COUNCIL_MODEL_INTELLIGENCE=true` | Enable dynamic model selection (ADR-026) |
| `LLM_COUNCIL_OFFLINE=true` | Force offline / static provider |
| `LLM_COUNCIL_DISCOVERY_ENABLED` / `_INTERVAL` (300) / `_MIN_CANDIDATES` (3) | Background discovery (ADR-028) |
| `LLM_COUNCIL_PERFORMANCE_TRACKING` (true) / `_STORE` | Internal performance index (ADR-026 P3) |
| `LLM_COUNCIL_AUDITION_ENABLED` (true) / `_MAX_SEATS` (1) / `_SHADOW_SESSIONS` (10) / `_EVAL_SESSIONS` (50) | Audition (ADR-029) |
| `LLM_COUNCIL_METRICS_ENABLED` / `_BACKEND` (none\|statsd\|prometheus) / `LLM_COUNCIL_STATSD_HOST` / `_PORT` | Metrics export (ADR-030) |
| `RUBRIC_SCORING_ENABLED` / `SAFETY_GATE_ENABLED` / `BIAS_AUDIT_ENABLED` / `BIAS_PERSISTENCE_ENABLED` | Evaluation toggles (ADR-031) |
| `WILDCARD_ENABLED` / `PROMPT_OPTIMIZATION_ENABLED` | Triage features (ADR-020) |

**Reasoning effort levels** (`reasoning/`): MINIMAL 10% (quick/creative), LOW 20% (balanced), MEDIUM 50% (high/coding), HIGH 80% (reasoning/math), XHIGH 95% (opt-in). Applied per stage: stage1 on, stage2 off, stage3 on by default.

**Performance/bias confidence tiers** (sample size): INSUFFICIENT <10, PRELIMINARY 10–30, MODERATE 30–100, HIGH 100+.

## Data flow

```
Query
 → Stage 1: parallel queries → [responses]
 → Stage 1.5 (optional): style normalization
 → Stage 2: anonymize → parallel ranking queries → [evaluations + parsed rankings]
 → Aggregate rankings (Borda)
 → Bias audit (if enabled)
 → Stage 3: chairman synthesis with full context
 → {stage1, stage2, stage3, metadata}
```
The flow is async/parallel wherever possible to minimize latency.

## Gotchas

1. Keep package-internal imports relative (`from .x import …`).
2. Ranking parse failures fall back to permissive `Response X` regex extraction.
3. Metadata (`label_to_model`, `aggregate_rankings`) is ephemeral — API response only, never written to storage.
4. Per-session bias metrics are extreme-anomaly indicators, not significance tests (see bias note above).

## Release Workflow

**Branch protection:** PRs + passing CI are required. **Never push directly to `master`**, even for releases.

1. `git checkout master && git pull origin master`
2. `git checkout -b release/v0.X.0`
3. Update `CHANGELOG.md` (Keep a Changelog: Added / Changed / Fixed / Removed).
4. `git commit --signoff -m "chore(release): Prepare v0.X.0 release"` then push the branch.
5. Open PR: `gh pr create --title "Release v0.X.0" --body "…"`.
6. Wait for required checks: **Test, Lint, Type Check, DCO** (DCO needs `--signoff`). Do not merge until green.
7. `gh pr merge --squash --delete-branch`.
8. **After merge**, tag from updated master: `git tag -a v0.X.0 -m "…" && git push origin v0.X.0` — this triggers `publish.yml` (build → test wheel → publish to PyPI).
9. Verify: `gh run list --workflow=publish.yml --limit=1`, then `pip index versions llm-council-core`.

**Versioning:** git tags via `hatch-vcs`/setuptools-scm; `src/llm_council/_version.py` is auto-generated + gitignored. SemVer (MAJOR breaking / MINOR feature / PATCH fix).

## Future enhancement ideas

Streaming responses; conversation export (md/PDF); model performance analytics over time; configurable council/chairman at runtime; custom ranking criteria.
