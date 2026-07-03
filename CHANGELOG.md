# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.33.0] - 2026-07-03

**Documentation Usability Overhaul** — epic [#443](https://github.com/amiable-dev/llm-council/issues/443), from the 2026-07-03 documentation review. Ships the documented-but-missing API surfaces (docs-as-spec: the `consult_council` Python facade and `gate --tier`), fixes every doc that failed when executed, surfaces the v0.25–v0.32 feature set on the published site (which had frozen at ADR-038), and adds CI drift guards so docs currency is enforced like code currency.

### Added

- **Docs small-fixes batch + DoD process fix (#449)** — clean `llm_council.yaml.example` template (the root `llm_council.yaml` is the project's own dev config and was headered v0.15.0); `examples/eval_bridges/README.md` with prereqs + spend warning; the HTTP API now reports the real package version in Swagger (was hardcoded 1.0.0) with proper OpenAPI description/tags; METHODOLOGY↔GOVERNANCE cross-links + the full bench workflow in METHODOLOGY; bench/calibration `--help` text now shows the spend caps; epic DoD guidance updated to include the published docs site (the process hole that froze it at ADR-038).
- **Canonical env reference + CI docs-drift guards (#448)** — `docs/reference/environment-variables.md` documents all 95 environment variables the code actually reads (grouped by subsystem), and `tests/test_docs_drift.py` makes divergence a test failure: env reads missing from the reference, phantom documented vars (the #446 failure class — which immediately caught #446's own over-deletion of the real `FAST_PATH_*`/`ROLLBACK_*`/`SHADOW_*` vars), README phantom mentions, ADRs unreachable from the mkdocs nav, and guide snippets that fail to parse/import. Docs currency is now enforced like code currency (server-card/bench drift-test pattern).
- **Docs-site refresh — v0.25–v0.32 functionality surfaced (#447)** — mkdocs nav gains ADRs 039–048, the 2026-H2 roadmap (all five items now marked shipped), and the ADR-045 stateless audit; three NEW guides: Verification & CI Gating (tiers, `unclear_reason` routing, calibration, screening, evidence), Streaming (SSE event/envelope reference, token streaming, MCP progress), and Quality Benchmark (drift regression, quality-per-dollar, spend caps) with a nav home for the harness-published results page; the MCP guide documents all four tools (verify/audit were absent); landing-page features updated past 2025.
- **Critical documentation accuracy fixes (#446)** — the published quickstart and Python guide now use APIs that exist (the #444 facade; `run_full_council` examples corrected to its real list/dict shapes with ADR-011 cost access); `docs/api.md` installs the right package and documents the streaming, server-card, and Jury-Mode surfaces; the README install flow leads with `[mcp,secure]` + the silent-keychain warning + the `uv tool` path; MCP client-timeout guidance (MCP_TIMEOUT) added to README and the MCP guide; hardcoded tier model lists replaced with a `council_health_check` pointer. The env reference was audited against `unified_config`: **21 documented variables didn't exist** — four renamed to their real ADR-031 names, ADR-031 YAML-only knobs re-labelled with their YAML paths, and never-shipped rows removed (canonical generated reference lands with the #448 drift guards).
- **`gate --tier` + accurate bundled skills (#445)** — `llm-council gate` gains `--tier {quick,balanced,high,reasoning}` (tier-sovereign models/timeouts/input caps, matching the verify tool); `unclear_reason` and `confidence_calibrated` flow through both gate output formats via the shared formatter. All three bundled SKILL.md files now execute against the shipped CLI (invocations corrected to `llm-council gate`, phantom `--timeout` flag removed, version claims fixed) and council-verify documents the ADR-047 UNCLEAR routing table.
- **`consult_council` Python facade (#444)** — the API the published quickstart always documented now exists: `from llm_council import consult_council` returns a `CouncilResult` (`.synthesis`, `.metadata`, `.model_responses`, `.raw`) with MCP-tool-parity tier semantics (confidence → tier contract → tier-sovereign timeouts; unknown confidence falls back to `high`; unknown `verdict_type` raises — it changes the output contract, so it is never silently coerced). Docs-as-spec fix from the 2026-07-03 documentation review.

## [0.32.0] - 2026-07-03

**Council Quality Benchmark (ADR-048)** — epic [#421](https://github.com/amiable-dev/llm-council/issues/421). The core product claim becomes measurable: a governed golden dataset with drift regression, a quality-per-dollar configuration matrix from ADR-011 actuals ("when does deliberation pay?"), harness-regenerated results publication, and DeepEval/RAGAS bridges. Spend is capped per-run and per-month with honest unknown-cost accounting; CI never spends (mocked-council tests only; nightly workflow only).

### Added

- **Publication + eval bridges (ADR-048 P3, #420)** — `llm-council bench report --publish docs/bench-results.md` regenerates the results page FROM the harness output (reproducibility fields mandatory: dataset version, date, spend, methodology pointer — never hand-edited). Thin dependency-free adapters let external eval suites drive the council as a target: `make_council_eval_callable` (DeepEval-style prompt→answer) and `council_to_ragas_row` (synthesis as answer, stage-1 drafts as contexts), each with a round-trip example under `examples/eval_bridges/`.
- **Quality-per-dollar config matrix (ADR-048 P2, #419)** — `llm-council bench matrix --configs solo-members,council,graduated` runs the same dataset across configurations (each member solo, full council, ADR-044 graduated depth) and renders the empirical "when does deliberation pay?" table from ADR-011 actuals. Unknown/zero cost renders `n/a` (never a fabricated ratio); solo configs skip consensus score floors by design; one broken config never aborts the rest. Methodology + caveats in `bench/METHODOLOGY.md`.
- **Golden-dataset drift harness (ADR-048 P1, #418)** — `llm-council bench run|baseline|report` executes the versioned dataset (`bench/dataset/v1/`, 20 original items across four domains, governance doc included) against the council and checks expected-quality envelopes (any-of key-content groups + consensus score floors, never exact-string). Hard per-run spend cap (`LLM_COUNCIL_BENCH_MAX_USD`, $2 default) with graceful partial abort, month-to-date guard (`LLM_COUNCIL_BENCH_MONTHLY_USD`, $30 default) from persisted run artefacts, committed-baseline regression detection, exit codes 0/1/2, and a nightly (never per-PR) workflow with explicit caps. Harness fully unit-tested with mocked councils — zero live spend in CI.

## [0.31.0] - 2026-07-03

**Verifier Calibration & Judge Reliability (ADR-047)** — epic [#417](https://github.com/amiable-dev/llm-council/issues/417). The verify gate becomes trustworthy: UNCLEAR verdicts carry machine-readable causes, confidence is calibrated against observed outcomes (both values surfaced), a shadow-first screening judge cuts gate cost for easy changes, and reviewer agreement is decomposed for position-confound amplification. Everything additive; all behavior changes flag-gated default-off.

### Added

- **Reviewer-agreement decomposition (ADR-047 P4, #416)** — `llm-council bias-report --amplification` decomposes each session's reviewer agreement over the ADR-015/018 store: an `agreement_index` (share of score variance between models vs between reviewers) crossed with `position_alignment` (does the consensus track display order?). High agreement WITH high position alignment flags an amplification suspect — the council converged along the position confound, not quality. Strictly report-only (pure functions, no writes, no gating — test-pinned); ADR-015 small-N caveats apply.
- **Lightweight screening judge (ADR-047 P3, #415)** — opt-in verify pre-gate: a single quick-tier model scores the change against the rubric in seconds. `LLM_COUNCIL_SCREENING=off` (default, byte-identical — a screen adds a model call, so no free shadow) | `shadow` (screen + log every decision with scores to `.council/screening/decisions.jsonl`, full council always runs — measures the screen's own precision first) | `active` (short-circuits to a PASS-with-audit-note only on a unanimous ≥9 across all dimensions). Hard invariants, never tunables: blocking-capable requests (blocking evidence or security focus) and risk-glob paths (auth/security/crypto/payment) are NEVER screened; content cap 5K. Soft-fail: any screen error runs the full council.
- **Confidence calibration (ADR-047 P2, #414)** — `llm-council calibration-report` reproducibly analyzes the verify transcript corpus (`.council/logs`): the current corpus shows the anomaly the ADR predicted — 42/42 FAIL verdicts carry ZERO blocking issues at mean confidence 0.965. `--fit` fits a monotonic (isotonic/PAV) mapping from human dispositions (`.council/calibration/dispositions.jsonl`) and persists it; every VerifyResponse now carries `confidence_calibrated` alongside raw `confidence` (identity mapping until fitted). The PASS threshold consumes the calibrated value only behind `LLM_COUNCIL_CALIBRATED_CONFIDENCE` (default off — flag-off byte-identical, test-pinned).
- **UNCLEAR disambiguation (ADR-047 P1, #413)** — `VerifyResponse.unclear_reason` splits exit-code-2 into machine-readable causes: `infra_failure` (chairman call errored per #403 `error_status` — retry after checking billing/auth), `low_confidence` (deliberation completed below threshold — accept-and-audit per policy), `timeout` (ADR-040 global deadline — re-tier or reduce scope). Exit code stays 2 (compat, additive field); surfaced in the MCP verify output table with routing hints; `None` on pass/fail and on non-deliberated cap results (where the `error` marker governs).

## [0.30.0] - 2026-07-03

**Streaming Deliberation (ADR-046)** — epic [#412](https://github.com/amiable-dev/llm-council/issues/412). The 30–600s spinner becomes a live deliberation view: rich per-model SSE events in a versioned envelope, opt-in chairman token streaming that assembles the identical final result, per-reviewer MCP progress, and the enabling `council.py` split (101K→44K, below the Council review cap). Non-streaming paths are byte-identical throughout.

### Added

- **MCP progress surface (ADR-046 P3, #411)** — per-reviewer stage-2 progress ("<model> reviewed (n/N)") now reaches MCP `ctx.report_progress` (and the HTTP progress channel), wired only when a progress consumer exists — consumer-less runs stay byte-identical (test-pinned). `consult_council` and `verify` tool descriptions document the progress semantics.
- **Chairman token streaming (ADR-046 P2, #410)** — `/v1/council/stream?stream_tokens=true` streams the chairman's synthesis live as `synthesis.delta` events. The streamed path assembles the identical final result object as the non-streamed path (equality-tested); transport failure falls back silently to the regular call; cancellation propagates (never triggers a fallback double-call); streamed usage is reported as unknown per ADR-011 (the stream wire protocol carries no usage data) rather than fabricated. Default off — flag-off byte-identical.
- **Rich SSE stage events (ADR-046 P1, #409)** — the `/v1/council/stream` endpoint now emits per-model events as deliberation progresses: `stage1.response` (each model's answer as it lands), `stage2.review` (each peer review, with parsed ranking + `parse_ok`), `consensus.early_termination` (ADR-044), and `stage3.start` — every event wrapped in a versioned envelope (`v: 1`, `session_id`, `ts`, monotonic `seq`; additive-only). Terminal events keep their ADR-025 names (`council.complete`/`council.error`) for consumer compat. Non-streaming paths are byte-identical: the callbacks are wired only when a stream consumer is attached (test-pinned batch path). Also fixes a latent bug where the non-gateway query path passed `shared_results` positionally into `reasoning_params`.

### Changed

- **council.py split below the Council review cap (ADR-046 P0, #408)** — verbatim moves into `council_stages.py` (stage functions, 40K), `council_rankings.py` (ranking parse/Borda/shadow votes, 17K), and `council_usage.py` (shared constants + ADR-011 usage accounting, 4K), leaving `council.py` at 44K (was 101K). Full back-compat: `council.py` re-exports every moved name; patched-attr config semantics preserved; suite count identical. Unblocks self-review of ADR-046 streaming changes.

## [0.29.0] - 2026-07-03

**MCP 2026-07-28 Adoption (ADR-045)** — epic [#407](https://github.com/amiable-dev/llm-council/issues/407). Early, correct adoption of the MCP 2026-07-28 spec cycle: a durable Tasks core (SDK wiring gated on the stable v2 SDK), SEP-2127 Server Card discovery, and a stateless-deployment audit with a two-instance smoke suite. Post-spec re-checks tracked in [#425](https://github.com/amiable-dev/llm-council/issues/425). Also ships the #397 chairman error-surfacing fix.

### Added

- **Stateless-deployment audit + two-instance smoke (ADR-045 Phase 3, #406)** — full inventory of MCP-path state that outlives a request (`docs/adr-045-p3-state-inventory.md`): the durable `TaskStore` is the load-bearing cross-instance contract and is now pinned by a two-instance smoke suite (lifecycle split across instances, two-process concurrency, torn-read guard). Per-instance circuit breakers/metrics/caches are documented as deliberate (optimality, not correctness). One true defect fixed: the layer-event accumulator was unbounded in long-lived processes — now a ring buffer (`MAX_LAYER_EVENTS=1000`).
- **MCP Server Card (ADR-045 Phase 2, #405)** — public discovery metadata per SEP-2127, generated from the live FastMCP tool registry (drift-tested): served by the HTTP server at `/server-card` and `/.well-known/mcp/server-card.json`, printable via `llm-council server-card`, with a static `server-card.json` committed for registry submission. Validated against the experimental-extension RC schema; **re-check against the final schema after the MCP 2026-07-28 release**.
- **MCP Tasks core layer (ADR-045 Phase 1, #404)** — groundwork for the MCP 2026-07-28 Tasks primitive (long-running deliberations that survive client disconnects): a durable `TaskStore` under `.council/tasks/` (24h expiry, size-capped eviction, in-memory fallback), 128-bit capability task ids with no enumeration API, a `LLM_COUNCIL_MCP_TASKS` kill-switch, and SDK feature-detection. The MCP wiring itself is **blocked pending the stable SDK v2** (targeted 2026-07-28 alongside the spec; the current pin is `mcp<1.27`) — synchronous tool behaviour is byte-identical until then.

### Fixed

- **Stage-3 chairman failures no longer swallow the underlying error (#397)** — `stage3_synthesize_final` used `query_model`, which collapses every failure (billing 402, auth, rate-limit, timeout) into `None`, so the fallback emitted only 'Error: Unable to generate final synthesis.' During the 2026-07-02 OpenRouter billing outage this made an infra failure look like a dead chairman model. Stage 3 now uses the status-preserving call and surfaces the failure class and detail in the synthesis text (`… (auth_error: Payment required (402): …)`), in structured `error_status`/`error_detail` fields, and in a warning log.

## [0.28.0] - 2026-07-03

**Compute-Optimal Deliberation (ADR-044)** — epic [#394](https://github.com/amiable-dev/llm-council/issues/394). The write-only performance index (ADR-026 P3) and cost-per-quality signals (ADR-011 P3) now power adaptive routing: performance-aware selection, early consensus termination, and a graduated deliberation-depth cascade. Everything is **default-OFF**, flag-gated, and LayerEvent-audited (route receipts); flag-off behaviour is byte-identical. Supersedes draft ADRs 039 (LLMRouter) and 043 (Pareto Router).

### Added

- **Graduated deliberation depth (ADR-044 Phase 3, #392)** — a new `graduated_depth` module (default **OFF**, `LLM_COUNCIL_GRADUATED_DEPTH`) provides the compute-optimal cascade: a depth ladder single → mini-council(3) → full council with prefix-superset model sets, so shallow-pass responses are always reused and escalation only *adds* models. Escalation is gated on known-low consensus signals (CSS / verdict confidence; unknown signals never escalate), priced via the ADR-011 estimator, optionally vetoed by the opt-in `BudgetEnforcer` (auditable, never a silent downgrade), and emits `L2_DELIBERATION_ESCALATION`. Includes `merge_usage_summaries` for correct cost accounting across rungs. Shipped as a bounded decision engine + documented hook (`plan_escalation`) rather than hot-path rewiring.
- **Early consensus termination (ADR-044 Phase 2, #391)** — during Stage-2 peer review, once the leading response's Borda margin is mathematically unassailable given the reviewers still outstanding, the remaining reviewer calls can be cancelled (flag `LLM_COUNCIL_EARLY_CONSENSUS`, default **OFF**). Off = **shadow mode**: the would-have-terminated point and estimated cost saved (from ADR-011 history) are logged so savings are measurable before enabling. Active terminations emit an auditable `L3_EARLY_CONSENSUS_TERMINATION` LayerEvent (votes saved, reviewers cancelled, est. cost saved); usage aggregation for completed reviewers is unaffected and dissent extraction still runs.
- **Performance-aware model selection (ADR-044 Phase 1, #390)** — the internal performance index (ADR-026 P3, previously write-only) now optionally blends into candidate quality scores during tier selection: `w·live + (1−w)·static` with `w` stepped by the index's confidence tier (0.3/0.6/0.8; cold start stays fully static). **Default OFF** (`LLM_COUNCIL_PERFORMANCE_SELECTION`); flag-off behaviour is byte-identical. When blending changes the selected model set, an auditable `L2_PERFORMANCE_SELECTION_APPLIED` LayerEvent records the static vs blended selections (route receipt). Soft-fail: tracker errors never affect selection.

## [0.27.1] - 2026-07-02

Tech-debt cleanup, part 2 (epic #382): internal perf + a scoring fix for the opt-in cost-aware ranking, and the `verification/api.py` module split — no public API changes.

### Changed

- **`verification/api.py` split into submodules (#380)** — the ~90K module now delegates to `verification/constants.py` (tier caps, extension whitelists, timeouts), `verification/schemas.py` (request/response models + validation patterns), `verification/evidence_render.py` (ADR-042 evidence budgeting/rendering + input-metrics helpers), and `verification/file_ops.py` (git snapshot + file-fetching operations). All moved names are re-exported from `verification.api` verbatim for backward compatibility; behaviour is unchanged (verbatim moves, full suite green). `api.py` drops to ~39K — back under the Council review cap, so future changes to the verify pipeline are reviewable whole.

### Fixed

- **Cost data no longer penalizes ranking (#384 review)** — in the opt-in cost-aware scoring, a raw min-max normalization sent the lowest value-for-money model to 0.0 while unknown-cost models kept their raw quality (having cost data acted as a penalty). Quality-per-cost is now rescaled onto the cost-known cohort's own quality range: value-for-money reorders models within their cohort's span and never drops one below its quality floor.
- **Cost-aware scoring no longer does N+1 store reads (#384)** — `get_all_cost_aware_scores` (opt-in, ADR-011 Phase 3) read the JSONL performance store once per model via `get_model_index`; it now reads the store once and groups records by model — bounded reads and a single consistent snapshot for the quality-per-cost pass. New `_index_from_records` helper aggregates from already-loaded records; `get_model_index` behaviour unchanged.

## [0.27.0] - 2026-07-02

Follow-up tech-debt cleanup (epic #382): the OpenRouter gateway now surfaces reasoning traces and streams for real, plus performance-tracker correctness fixes.

### Added

- **OpenRouter gateway: reasoning trace + real streaming (#375)** — `GatewayResponse` now carries `reasoning_details` (o1/o3/deepseek-r1 reasoning traces were captured but dropped on the gateway path), and `complete_stream` now performs a true SSE stream yielding incremental content deltas instead of buffering the whole response into one chunk.

### Fixed

- **Performance tracker minor debt (#377)** — `record_session` now stamps its `session_id` onto every metric as the authoritative id (the parameter was previously unused) and no longer mutates the caller's objects; the decay weight clamps future-dated timestamps; clarified that `get_quality_score`'s 0–100 scale (selection-facing) vs `get_all_model_scores`' 0–1 scale (percentile math) is intentional, and that latency percentiles are intentionally unweighted.

## [0.26.0] - 2026-07-02

Follow-up & tech-debt cleanup from the ADR-011 cost-accounting epic (batched as [#373](https://github.com/amiable-dev/llm-council/issues/373)): one additive enhancement (token/cost in `VerifyResponse`) plus correctness fixes to the OpenRouter gateway, the performance tracker, and the reasoning path.

### Added

- **Token/cost in `VerifyResponse` (ADR-011 Phase 2 follow-up, #366)** — `verify` now surfaces per-run token and cost totals (`prompt_tokens`, `completion_tokens`, `total_tokens`, `cost_usd`, `cost_known`, `cached_tokens`) under `input_metrics`, sourced from the council usage summary. `cost_known` distinguishes a genuine $0 from unknown cost; the fields are omitted entirely when usage is unavailable.

### Fixed

- **`reasoning_params` no longer dropped in `query_models_with_progress` (#365)** — the progress-callback query path (used by the council) now threads `reasoning_params` through to each model call, matching `query_models_parallel` and the gateway path (ADR-026). Reasoning-effort injection was previously silently lost on this path.
- **Performance tracker correctness (#370)** — (1) `get_quality_percentile` now excludes the model itself from its own ranking (self-inclusion inflated the rank by 1/N and biased the ADR-029 graduation gate); (2) `_calculate_decay_weight` docstring corrected — `decay_days` is an e-folding time-constant, not a half-life (behaviour unchanged); (3) documented the intentional 0–1 (`get_all_model_scores`) vs 0–100 (`get_quality_score`) scale split and the intentionally-unweighted parse-success rate.
- **OpenRouter gateway correctness (#367)** — (1) the API key is no longer frozen at import: `OpenRouterGateway` resolves it per-request via the ADR-013 chain, so a request-scoped BYOK key is honored (was silently bypassed); (2) null response `content` (e.g. a tool-call-only turn) is coerced to `""` so downstream never sees `None`; (3) `tool_calls`/`tool_call_id` are now propagated in message conversion instead of being silently dropped.

## [0.25.0] - 2026-07-01

**Cost and token accounting (ADR-011)** — a four-phase epic ([#359](https://github.com/amiable-dev/llm-council/issues/359)) that makes LLM spend transparent and optimizable: capture & surfacing (Phase 1), OpenTelemetry-standard observability (Phase 2), cost-per-quality optimization (Phase 3), and an opt-in budget gate (Phase 4). Everything is additive and backward-compatible — new behaviour is opt-in or soft-fail, and the council never fails a request because of cost accounting.

### Added

- **Opt-in budget enforcement (ADR-011, Phase 4)** — a new `budget/` module (DEFAULT OFF) adds a pre-query `CostEstimator` (low/expected/high USD estimate from per-model cost history) and a tiered `BudgetEnforcer`: `STRICT` rejects if even the high estimate exceeds the budget, `BALANCED` rejects on the expected estimate (warns on high), `PERMISSIVE` warns only. Between stages it can abort **gracefully** (returning partial results) but never aborts a completion in flight (ADR-040). Every reject/warn/abort emits an auditable `L1_BUDGET_DECISION` LayerEvent — budget never causes a silent tier change (ADR-024). Enable with `LLM_COUNCIL_BUDGET_ENFORCEMENT=true` and `LLM_COUNCIL_BUDGET_MODE=strict|balanced|permissive`.

- **Cost-per-quality optimization (ADR-011, Phase 3)** — the internal performance index now carries per-model cost (`ModelSessionMetric.cost_usd`, `ModelPerformanceIndex.mean_cost_usd`) and derives a **Borda-per-dollar** value signal (`quality_per_cost`). A new **opt-in** cost-aware ranking (`InternalPerformanceTracker.get_all_cost_aware_scores`) is byte-for-byte identical to plain quality scoring unless `LLM_COUNCIL_COST_AWARE_SELECTION=true` — the single audited path by which cost may influence model selection; unknown-cost models keep their quality score (never penalized for missing data). Cost is recorded from the council's per-model usage (only when actually reported), and unknown costs are excluded from the mean rather than counted as $0.

- **Cost/token observability (ADR-011, Phase 2)** — the council now emits per-model token and cost metrics through the existing metrics adapter (ADR-030) using **OpenTelemetry GenAI semantic conventions** (`gen_ai.client.token.usage` histogram tagged `gen_ai.token.type`/`gen_ai.request.model`, plus a `llm_council.cost.usd` gauge), so any OTLP sink (PostHog, Grafana, Datadog) ingests them with zero custom mapping. Emission is soft-fail (never affects a run). Ships `examples/observability/` — an OTel-Collector compose overlay (Prometheus + Grafana, OTLP export to PostHog), a Grafana dashboard, and collector/prometheus configs. Enable with `LLM_COUNCIL_METRICS_ENABLED=true` + `LLM_COUNCIL_METRICS_BACKEND=prometheus`.
- **Cost and token accounting (ADR-011, Phase 1)** — the council now captures and reports USD cost alongside tokens. A per-gateway `CostResolver` (`gateway/cost_resolver.py`) stamps `cost_usd` + a `cost_source` provenance tag onto every call — `provider` ground-truth for OpenRouter/Requesty (capturing the previously-discarded inline `usage.cost`), `registry_estimate` from `registry.yaml` pricing for Direct APIs, and `local_zero` for Ollama — so an estimate is never presented as a bill. `metadata["usage"]` now carries `{by_stage, by_model, total}` with `cost_usd`/`cached_tokens` (per-model uses reviewer-primary attribution), exposed as a typed, OpenAPI-documented `usage` field on the HTTP `CouncilResponse` and as a progressive-disclosure **Cost & Tokens** summary in MCP `consult_council` (one line by default; full per-model/per-stage breakdown only under `include_details`). The MCP fallback path (`run_council_with_fallback`) now aggregates usage into metadata too (previously absent — the MCP surface had no token data). Cost accounting is soft-fail and never breaks a council run. Surfacing token/cost in `VerifyResponse` is deferred to a follow-up (verification telemetry, ADR-041).

## [0.24.45] - 2026-06-16

Verify-gate robustness pass, from a real epic-loop session that "kept reporting council timeouts." Investigation of the live transcripts and `.council/logs` found the council server healthy — the pain was four distinct verify-layer defects conflated as "timeouts". All four are fixed here.

### Fixed

- **`verify` no longer crashes with `bad operand type for unary -: 'str'`** ([#354](https://github.com/amiable-dev/llm-council/issues/354)) — `detect_score_rank_mismatch` (`council.py`) sorted candidate labels with `key=lambda x: -scores.get(x, 0)`. `scores` is `Dict[str, Any]` populated from untrusted model output; when a model emits a score as a string (`"9"`, `"N/A"`, `""`) the unary minus raised `TypeError` and aborted the entire verification with **no verdict produced** (the intermittent, input-size-correlated "internal crash" seen in real usage). Scores are now coerced via a new `_coerce_score()` helper — numeric values pass through, non-numeric sort lowest, nothing raises.
- **`verify` no longer reports FAIL/UNCLEAR for changes the council approved** ([#355](https://github.com/amiable-dev/llm-council/issues/355)) — two compounding bugs in the verdict layer. (1) The pipeline already obtains the chairman's **structured BINARY verdict** (`verdict_result` from `stage3_synthesize_final`, ADR-025b) but `build_verification_result` discarded it and re-derived the verdict with a naive prose regex that fires on *negated* mentions ("no **failures**", "**critical** issues resolved") — across 44 persisted real runs only 1 passed despite frequent unanimous approvals. The structured verdict is now authoritative; regex extraction is a fallback only. (2) `extract_blocking_issues` matched the bare word `CRITICAL|MAJOR|MINOR` anywhere in prose (`[:\s]+`), so approval text like "the critical issues have been resolved" and "No blocking issues were identified" was fabricated into `CRITICAL` blockers that drove false gate failures. It now requires a genuine line-anchored, colon-delimited marker (`- **CRITICAL**: …`).
- **Verify timeout budget raised so the chairman stage is not starved** ([#356](https://github.com/amiable-dev/llm-council/issues/356)) — `VERIFICATION_TIMEOUT_MULTIPLIER` is now `2.0` (was `1.5`), so the global deadline becomes `balanced` 180s / `high` 360s (was 135s / 270s). On a slow day the `balanced` tier could spend its entire 135s on stage 1 (~62s) + stage 2 (~73s), so stage 3 — the chairman go/no-go — never ran and the gate timed out with **no verdict**, which the MCP client timeout could not fix (the bottleneck was the server's own deadline). The extra headroom lets synthesis complete. Additionally, when stage 3 *is* still starved, the timeout path now **salvages an advisory signal** — the rubric scores and reviewer-agreement confidence recovered from the completed peer-review stage — instead of returning a bare `unclear`/`0.0` (the verdict stays `unclear` since no chairman decision was reached, but the caller gets something actionable).
- **Timeout and input-cap verifications are now persisted to `.council/logs`** ([#356](https://github.com/amiable-dev/llm-council/issues/356)) — the input-cap and `asyncio.TimeoutError` early-return paths returned a result without ever calling `store.write_stage(..., "result", …)`, so timeouts (the dominant real-world failure mode) left **no `result.json`** and were un-investigable after the fact. Both paths now persist via a best-effort `_persist_result_safe()` (a store error never escalates a degraded result into a hard failure).

- **Test suite is compatible with Starlette 1.x** — the unbounded `fastapi>=0.100.0` dependency now resolves to FastAPI 0.137 / Starlette 1.3, where `include_router` produces a nested `_IncludedRouter` route object without a top-level `.path`. Several tests introspected routes with `[route.path for route in app.routes]`, which raised `AttributeError` and turned CI red (the app itself is fine — TestClient integration tests pass on Starlette 1.x). Replaced with a recursive flatten helper that works on both 0.x and 1.x route trees. Surfaced while landing this release; orthogonal to the verdict-layer fixes.

### Changed

- **Input-cap rejection is now a distinct, non-verdict signal** ([#357](https://github.com/amiable-dev/llm-council/issues/357)) — an over-cap payload (e.g. 31K chars at the 30K `balanced` limit) previously returned `verdict="unclear"`/`exit_code=2`, indistinguishable from a deliberated UNCLEAR. Automation that treats UNCLEAR as "accept & proceed" (e.g. epic-loop) would therefore let an **unreviewed oversized input silently pass the gate**. The result now carries `error="input_too_large"` (surfaced on `VerifyResponse`), and the formatted output renders a distinct **"INPUT TOO LARGE — the council did not run"** banner instead of a verdict.

## [0.24.44] - 2026-06-02

### Fixed

- **`verify` no longer crashes when the chairman synthesis is empty/None** — `extract_verdict_from_synthesis` and `extract_blocking_issues` read the synthesis via `stage3_result.get("response", "")`, but the `"response"` key is normally present with a `None` value (e.g. a reasoning-only model returning null content, or a partial/timed-out stage 3), so the `""` default never applied. `None.upper()` / `re.finditer(pattern, None)` then raised `AttributeError: 'NoneType' object has no attribute 'upper'` (surfaced to MCP callers as a generic crash), instead of degrading to an `"unclear"` verdict the way a *missing* key already did. Both extractors now coalesce a missing/None synthesis to `""`. Regression tests added in `tests/unit/verification/test_verdict_extractor.py`.
- **`council_health_check` now reports the real API-key source** — `key_source` showed `"unknown"` whenever the key came from the macOS Keychain (ADR-013), because `mcp_server._get_key_source()` only checked the `OPENROUTER_API_KEY` env var. It now delegates to `unified_config.get_key_source()`, which tracks the actual resolution path, so a keychain-resolved key reports `"keychain"` (env still reports `"environment"`). Cosmetic only — key resolution itself already worked.

## [0.24.43] - 2026-06-02

### Fixed

- **Health check no longer reports a spurious "error" from a retired probe model** — `council_health_check` (and the OpenRouter / Requesty / direct gateway `health_check()` methods) probed connectivity with a hardcoded `google/gemini-2.0-flash-001`, which has since been retired from OpenRouter and now 404s. The probe failure surfaced as a health-check `error` / `ready: false` even when the council itself was perfectly healthy. The probe model is now a single shared constant `DEFAULT_HEALTH_CHECK_MODEL` in `gateway/base.py` (set to the current, cheap, GA `google/gemini-2.5-flash-lite`) referenced by all four call sites, so the next retirement is a one-line update instead of five scattered literals. The direct gateway's native-API probe ids were refreshed too (`claude-3-5-haiku-20241022` → `claude-haiku-4-5`, `gemini-2.0-flash-001` → `gemini-2.5-flash-lite`).
- **Broken model in the `high` / `reasoning` / `frontier` tier pools** — those pools (and their code-level defaults in `tier_contract.py` / `unified_config.py`) referenced `deepseek/deepseek-v3.2-speciale`, which does not exist on OpenRouter and would fail at request time. Replaced with current DeepSeek models (`deepseek-v4-pro` for high/frontier, the reasoning-specialised `deepseek-r1` for reasoning).

### Changed

- **Tier model pools refreshed against the live OpenRouter catalogue (2026-06-02)** — every tier pool model was cross-checked against `https://openrouter.ai/api/v1/models`; all 20 pool entries plus the health probe now resolve both in the bundled registry and live on OpenRouter. Changes: `quick`/`balanced` move from the `gemini-3.1-flash-lite-preview` preview to the GA `gemini-3.1-flash-lite`; `high`/`reasoning`/`frontier` bump Anthropic from `claude-opus-4.7` to the newest `claude-opus-4.8` (same price); `frontier` bumps OpenAI to `gpt-5.5-pro`. Tier aggregators and the default council model list were updated to match. Registry (`models/registry.yaml`) bumped to v1.3 with `gpt-5.5-pro`, `claude-opus-4.8`, `gemini-3.1-flash-lite` (GA), `gemini-2.5-flash-lite`, and `deepseek-v4-pro` added; retired `gemini-2.0-flash-001` and non-existent `deepseek-v3.2-speciale` removed; stale `claude-opus-4.7` pricing corrected to live values.

## [0.24.42] - 2026-05-26

### Fixed

- **`consult_council` docstring no longer hides the `reasoning` tier** ([#347](https://github.com/amiable-dev/llm-council/pull/347)) — the MCP tool schema for `confidence` is plain `string` with no enum, so the docstring is the only signal an LLM caller gets about valid values. Since 4a4234d (Dec 2025, ADR-012 Section 5) the runtime has accepted `"reasoning"` and routed it to the 600s/300s tier budget, but the docstring still advertised only `"quick" / "balanced" / "high"` with stale pre-ADR-012 duration estimates (`high (~45s)` vs the actual 180s server budget). An LLM consumer of the MCP tool (e.g. a fresh Claude Code instance) reading the schema would correctly conclude reasoning wasn't an option. `verify` and the bundled `council-verify` / `council-review` skills already documented the tier correctly; only `consult_council` was out of sync. The docstring now lists all four runnable tiers (`quick` / `balanced` / `high` / `reasoning`) with their real server budgets and per-model timeouts, and explicitly notes that unknown values silently fall back to `"high"`.

### Added

- **MCP client timeout guidance for slow tiers** ([#347](https://github.com/amiable-dev/llm-council/pull/347)) — new "Configuring MCP Client Timeouts" section in [`docs/integrations/index.md`](docs/integrations/index.md). The council's `high` and `reasoning` tiers can take 3–10 minutes when frontier reasoning models review large inputs (e.g. multi-thousand-line ADRs). MCP clients have their own transport-layer timeout that is **independent of the server's tier budget** — Claude Code's default is around 60s. If the client times out first, callers see "MCP layer timeout" errors even though the council is still working. ADR-012 §419 explicitly chose not to fix this server-side ("We don't control client-side timeouts") and issue [#327](https://github.com/amiable-dev/llm-council/issues/327) has hard data (Stage 1 alone took 652s at high tier on a large input, killed by the client transport). The new section gives an explicit tier→`MCP_TIMEOUT` mapping (`quick` 60000ms, `balanced` 120000ms, `high` 300000ms, `reasoning` 900000ms) and a concrete `.mcp.json` env block. The `consult_council` docstring also carries an inline note pointing callers to this requirement.

## [0.24.41] - 2026-05-26

### Added

- **ADR-043: OpenRouter Pareto Router integration** ([#339](https://github.com/amiable-dev/llm-council/pull/339)) — adds `openrouter/pareto-code` as an optional council seat for coding-focused sessions. The Pareto Router auto-selects a coding model from the quality/cost frontier maintained by Artificial Analysis benchmarks. `min_coding_score` maps to council tiers: quick=0.2, balanced=0.5, high=0.8, reasoning=0.9, frontier=default. Built-in fallback cascading aligns with ADR-023. Three-phase rollout per the ADR: this release implements Phase 1 (integration); Phase 2 (observe Pareto selections + peer review scores) and Phase 3 (expand) follow. Extends ADR-022/023/028. ADR document is in Draft status pending council review; the implementation is shipped behind tier-pool configuration so it's opt-in.

### Fixed

- **`[mcp]` extra no longer ships a broken MCP server** ([#344](https://github.com/amiable-dev/llm-council/issues/344), [#345](https://github.com/amiable-dev/llm-council/pull/345)) — `pip install 'llm-council-core[mcp]'` previously produced a non-functional server: `mcp_server.py` transitively imports `fastapi` via `llm_council.verification.api`, but the `[mcp]` extra declared only `mcp>=1.22.0` (no fastapi / uvicorn). Fresh installs surfaced as `ModuleNotFoundError: No module named 'fastapi'`. Three related fixes: (1) `[mcp]` now transitively depends on `[http]` so fastapi / uvicorn track `[http]`'s versions (follows the existing `[all]` transitive-extras pattern); (2) `mcp` upper-pinned to `<1.27` — mcp 1.27.x has breaking API changes from 1.25.x that prevent `mcp_server.py` from importing; (3) `serve_mcp()` now surfaces the real `ImportError` in its error path so future regressions report the actual missing module instead of always blaming `[mcp]`.

## [0.24.40] - 2026-05-16

### Fixed

- **Verify no longer silently amputates large files to 15K chars** ([#342](https://github.com/amiable-dev/llm-council/issues/342)) — `_fetch_file_at_commit_async` clamped every single file to `MAX_FILE_CHARS = 15000` regardless of the active tier's char budget, and `_fetch_files_for_verification_async_with_metadata` then discarded the per-file `truncated` boolean without surfacing it on `VerifyResponse`. End-to-end symptom: a 56,093-char ADR reviewed at the `reasoning` tier (50K budget) reached reviewers as 15,942 chars; reviewers noticed (and said so in their text) but the caller saw `expansion_warnings: null` and a confident verdict. Two-part fix: (1) `_fetch_file_at_commit_async` now accepts a `max_file_chars` parameter and `_fetch_files_for_verification_async_with_metadata` derives it from `TIER_MAX_CHARS[tier]` — at reasoning tier, a single 50K file is now fully readable; per-batch budget scales the same way. (2) Per-file truncation produces a structured `expansion_warnings` entry (`"file '<path>' truncated at N chars (<tier> tier per-file budget)"`) so the caller has a non-textual signal that the review was partial. Backward compat: `_fetch_file_at_commit_async(snapshot_id, path)` without `max_file_chars` still defaults to the legacy 15K constant; the legacy `_fetch_files_for_verification_async` wrapper still works without specifying a tier. The bug had been latent since ADR-040 introduced `TIER_MAX_CHARS` — the per-file inner cap was sized for a multi-file world and never refactored when single-file ADR review became the common case.

## [0.24.39] - 2026-05-13

### Fixed

- **Verify snapshot resolver no longer silently returns empty content** ([#340](https://github.com/amiable-dev/llm-council/issues/340)) — when `target_paths` couldn't be resolved at the given `snapshot_id` (e.g. commit not present in the daemon's local checkout, push-replication race, paths missing at that commit), `run_verification` previously sent a boilerplate-only prompt (~916 chars) to the council and returned UNCLEAR. Skill rules told callers to "accept and move on", making the bug undetectable end-to-end. Three compounding defects fixed: (1) `_build_verification_prompt` now uses the metadata-aware fetch variant — `expansion_warnings` / `expanded_paths` / `paths_truncated` are no longer discarded; they're surfaced on `VerifyResponse` for every call. (2) When non-empty `target_paths` resolves to zero files, the endpoint raises `SnapshotResolutionError` → HTTP 422 with `{error: "snapshot_resolution_failed", snapshot_id, unresolved_paths, expansion_warnings}` (the MCP wrapper mirrors the same shape, parallel to `BlockingEvidenceTooLarge`). Partial resolution still produces a verdict — the warnings just show up on the response. (3) `_get_git_object_type` and `_git_ls_tree_z_name_only` now log git's stderr at WARN with `snapshot_id` + `path` instead of swallowing it under bare `except Exception: pass`, so operators can diagnose missing-fetch / unknown-revision cases.

## [0.24.38] - 2026-05-13

### Fixed

- **Bundled skills synced** ([#338](https://github.com/amiable-dev/llm-council/pull/338)) — `.github/skills/` (dev copy) and `src/llm_council/skills/bundled/` (shipped copy) had drifted across all three bundled skills:
  - `council-verify`: ADR-042 evidence content (Evidence section + `references/evidence.md` + compatibility bump to `>= 2.1`) was missing from bundled — introduced in v0.24.37.
  - `council-review`: ADR-040 timeout-behavior section + `completed_stages`/`timeout_fired` schema fields were never synced to bundled (pre-existing drift, surfaced by the new regression test).
  - `council-gate`: same ADR-040 timeout-handling section missing from bundled (pre-existing drift).
  Synced all three bundled copies to match the dev copies. Added `tests/unit/test_bundled_skills_in_sync.py` as a regression guard — fails on any future drift between the two trees, with an error message that tells the editor exactly how to fix it. Users who ran `llm-council install-skills` from any version up to v0.24.37 should upgrade to v0.24.38 and re-install to get the up-to-date skill content.

## [0.24.37] - 2026-05-13

### Added

- **ADR-042: Verify evidence injection** ([#336](https://github.com/amiable-dev/llm-council/issues/336)) — pre-computed analysis output from upstream tools (linters, slop detectors, custom checkers) can now be passed to verify calls via a new optional `evidence` parameter on `POST /v1/council/verify` and the MCP `verify` tool. Each item carries `source`, `format` (markdown/json/text), `content`, `strength` (informational/blocking), and optional `evidence_id`. Council renders evidence inside `<evidence_item>` XML-sentinel wrappers with tilde-fenced bodies (prevents prompt-injection via heading collisions and fence escapes). The Chairman synthesis prompt is extended to require a fenced JSON `evidence_dispositions` block with a `status` enum (`acknowledged | confirmed | rejected | unresolved | not_reviewed_due_to_budget | parser_error`). `VerifyResponse` gains `evidence_summary` (one disposition per submitted item, including dropped-by-budget) and `evidence_warnings` (structured budgeting notes). A new `evidence.json` transcript artefact is persisted alongside `request.json`/`stage[1-3].json`/`result.json`. `input_metrics` gains evidence-specific counters; raw source/version strings are intentionally kept out of telemetry dimensions (cardinality hygiene). Oversized blocking evidence triggers a structured HTTP 422 (and a mirrored MCP error blob) rather than being silently dropped. Backward compatible — `evidence=None` produces byte-identical prompts to pre-ADR-042 behaviour (locked by a golden hash regression test). See [docs/adr/ADR-042-verify-evidence-injection.md](docs/adr/ADR-042-verify-evidence-injection.md) for the design and [docs/adr/ADR-042-implementation-spec.md](docs/adr/ADR-042-implementation-spec.md) for the prescriptive spec.

## [0.24.36] - 2026-04-24

### Fixed

- **Security Scanning workflow repaired** ([#332](https://github.com/amiable-dev/llm-council/pull/332)) — two unrelated failures had been blocking the `Security Scanning` status badge since mid-March:
  - `aquasecurity/trivy-action@0.34.2` no longer resolved. The original unprefixed tags (`0.0.1`–`0.34.2`) were deleted during remediation of the March 2026 trivy-action supply chain compromise ([CVE-2026-33634](https://github.com/aquasecurity/trivy/security/advisories/GHSA-69fq-xp46-6x23)) and republished with a `v` prefix. Bumped to `v0.36.0` (published 2026-04-22, post-remediation) and pinned to commit SHA for supply-chain robustness.
  - Gitleaks kept flagging a historical OpenRouter key in commit `b8ad10d` (tagged in v0.3.0, Dec 2025). Key already revoked; added a commit-level allowlist entry so scheduled scans pass.
- **Supply chain exposure assessment:** No exposure. Last successful Trivy run was 2026-03-12, seven days before the 12-hour attack window on 2026-03-19. No master pushes occurred during or after the window until this fix, so no malicious trivy-action code ever reached a runner.

## [0.24.35] - 2026-04-23

### Changed

- **April 2026 model refresh** — refreshed tier defaults to incorporate newly-available models:
  - **Claude Opus 4.6 → 4.7** in `high`, `reasoning`, and `frontier` tier pools + aggregators. Opus 4.7 (GA on OpenRouter since Apr 16, 2026) ships a 13% coding-benchmark lift over 4.6, 3× vision resolution, and a 1M context window. Pricing unchanged per Anthropic.
  - **Balanced tier aggregator and pool: `gpt-5.3-chat` → `gpt-5.4-mini`** — newer model, 400K context (was 128K), ~57% cheaper input / 68% cheaper output, with reasoning support.
  - Updated `CouncilConfig.models` default, `TIER_AGGREGATORS`, `_DEFAULT_TIER_MODEL_POOLS`, and `llm_council.yaml`.

### Added

- **Registry entries** in `src/llm_council/models/registry.yaml`:
  - `anthropic/claude-opus-4.7` (FRONTIER, 1M ctx, $15/$75 per 1M)
  - `openai/gpt-5.4-mini` (STANDARD, 400K ctx, $0.75/$4.50 per 1M, reasoning)
  - `openai/gpt-5.4-nano` (ECONOMY, 400K ctx, $0.20/$1.25 per 1M, reasoning)
  - Older entries retained for backwards compatibility.

## [0.24.34] - 2026-03-12

### Fixed

- **Concurrent verify shotgunning** ([#327](https://github.com/amiable-dev/llm-council/issues/327)) — agents fired 4 verify calls within 15 seconds with progressively fewer files, overwhelming the MCP server. Replaced "Handling Verdicts" with stricter "Rules" section: one call at a time, one call per commit, no scope-reduction retries.

## [0.24.33] - 2026-03-12

### Fixed

- **Calling agents stuck in verify retry loops** ([#327](https://github.com/amiable-dev/llm-council/issues/327)) — agents retried FAIL/UNCLEAR verdicts instead of fixing code, burning 26+ minutes on unchanged snapshots. Added "Handling Verdicts" section to council-verify skill with explicit PASS/FAIL/UNCLEAR action guidance and a "never retry same snapshot" rule.

## [0.24.32] - 2026-03-11

### Fixed

- **Verification timeouts on large code inputs** ([#327](https://github.com/amiable-dev/llm-council/issues/327)) — default tier `high` used frontier models (opus-4.6, gpt-5.4-pro) that took 600+ seconds on 25K+ token inputs, exceeding the 270s global deadline. Changed default to `balanced` (mid-tier models, 90s deadline). Added tier selection guidance to skill based on content size and criticality.

## [0.24.31] - 2026-03-08

### Added

- **ADR-041: Verification telemetry wiring** - Wire existing performance tracking infrastructure into verification pipeline
  - Per-stage timing (`stage1_elapsed_ms`, `stage2_elapsed_ms`, `stage3_elapsed_ms`) captured in verification results and transcripts
  - Total elapsed time, global deadline, and `budget_utilization` ratio for timeout tuning
  - `input_metrics` (`content_chars`, `tier_max_chars`, `num_models`, `num_reviewers`, `tier`) for input size correlation analysis
  - Timing data preserved on timeout via `partial_state` and `finally` blocks
  - `persist_session_performance_data()` wired to verification pipeline (ADR-026 Phase 3 no longer dead code)
  - Performance tracker failures isolated from verification results (telemetry never fails verification)
  - `VerifyResponse` schema extended with optional `timing` and `input_metrics` fields

## [0.24.29] - 2026-03-07

### Fixed

- **ADR-040: Verification timeout guardrails** - Fix verify/review tools hanging for 10-57 minutes
  - **Bug fix**: `stage2_collect_rankings()` now accepts `timeout` and `models` params, honoring tier contract instead of defaulting to 120s and global config models
  - **Bug fix**: `stage3_synthesize_final()` now accepts `timeout` param, passed through to `query_model()`
  - **Global timeout**: `run_verification()` wraps pipeline in `asyncio.wait_for()` with deadline derived from `tier_contract.deadline_ms * 1.5`
  - **Partial results**: On timeout, returns `partial=True, timeout_fired=True` with `verdict=unclear` instead of hanging indefinitely
  - **Input size guardrails**: Per-tier character limits (quick: 15K, balanced: 30K, high/reasoning: 50K) reject oversized inputs with helpful error
  - **Pre-flight info**: First progress callback includes tier, content size, model count, and deadline estimate
  - **Enhanced Stage 2 progress**: Per-model progress reporting during peer review (total_steps now includes stage2 models)
  - **Formatting**: Both full and compact verification formatters now surface timeout/partial indicators

## [0.24.22] - 2026-02-06

### Changed

- **Model Upgrade**: Replaced `anthropic/claude-opus-4.5` with `anthropic/claude-opus-4.6` across all configurations
  - Updated tier pools (high, reasoning, frontier) in `unified_config.py`
  - Updated tier aggregators in `tier_contract.py`
  - Updated model registry (`registry.yaml`)
  - Updated `llm_council.yaml` user-facing config
  - Updated all documentation (README, ADRs, blog posts, getting-started guide)
  - Closes #323

## [0.24.21] - 2026-01-30

### Security

- **CRITICAL: Remove API key exposure in health check** (CVE pending)
  - Removed `key_preview` field that exposed first 20 characters of API key
  - Removed `working_directory` debug field from health check response
  - Health check result is returned to MCP clients (LLMs), so partial keys were being sent to models
  - **Action required**: Users should rotate their OpenRouter API keys if they used `council_health_check()`

## [0.24.20] - 2026-01-21

### Changed

- **Default Council Model**: Replaced `openai/gpt-5.2-pro` with `openai/gpt-5.2` in all tier pools
  - Reasoning tier now uses `gpt-5.2` instead of expensive `gpt-5.2-pro`
  - Frontier tier now uses `gpt-5.2` instead of `gpt-5.2-pro`
  - Default council models list updated
  - Cost reduction while maintaining quality (both are frontier-tier models)

## [0.24.19] - 2026-01-16

### Fixed

- **Cold Start Protection**: Added `min_samples` config (default: 10) for rollback metrics
  - Prevents false 100% rate from first failure (1/1 = 100% triggering immediate rollback)
  - Rate calculation returns 0.0 until minimum sample threshold is met
  - New env var: `LLM_COUNCIL_ROLLBACK_MIN_SAMPLES`

## [0.24.18] - 2026-01-16

### Fixed

- **Metrics Load Error Handling**: Added logging for corrupted metrics file recovery
  - Logs warning with file path and error details via `logging.warning()`
  - Documents "fail-safe" design: empty metrics = no thresholds breached = fast path stays enabled
  - Graceful degradation when historical data is unavailable

## [0.24.17] - 2026-01-16

### Fixed

- **Rollback Monitoring Enabled Flag**: Added proper `enabled` checks
  - `record()` now skips recording when monitoring is disabled
  - `check_thresholds()` returns False immediately when disabled
- **RollbackConfig.from_env()**: Now loads all parameters from environment
  - Added: `error_multiplier`, `wildcard_timeout_threshold`
  - Previously only loaded `enabled` and `window_size`
- **File Locking Documentation**: Clarified atomic replacement design
  - `_truncate_file()` uses atomic `os.replace()` (no lock needed)
  - File locking applies to `_load()` and `_save_record()` only

## [0.24.16] - 2026-01-16

### Fixed

- **Duplicate SSE Events**: Removed `DELIBERATION_START` and `COMPLETE` from webhook subscription
  - These events are emitted manually by `_council_runner.py`
  - Subscribing to them via webhook caused duplicate events in SSE stream
- **Truncation Race Condition**: Changed from open-then-lock to atomic file replacement
  - Uses `tempfile.mkstemp()` + `os.replace()` for POSIX atomic rename
  - Prevents data loss from concurrent truncation operations

## [0.24.15] - 2026-01-16

### Fixed

- **ERROR_RATE Rollback Trigger**: Added missing check in `check_thresholds()`
  - Now checks `error_rate > baseline * error_multiplier` per ADR-020
  - Uses 5% baseline with 1.5x multiplier (7.5% threshold)
- **request_id Security**: Prevented payload overwrite in SSE events
  - Moved `request_id` after `**payload.data` spread in dictionary construction
  - Prevents malicious payload from injecting false request IDs

### Security

- **File Locking**: Added `fcntl` file locking for metrics persistence
  - Shared lock (`LOCK_SH`) for reading
  - Exclusive lock (`LOCK_EX`) for writing
  - Graceful fallback to no-op on Windows (no fcntl)

## [0.24.14] - 2026-01-16

### Fixed

- **Thread Safety**: Fixed race conditions in SSE event handling
  - Uses `asyncio.call_soon_threadsafe()` for event queue operations
  - Prevents concurrent modification of `events_seen` set
- **Fast Path Case Sensitivity**: Fixed keyword matching in complexity classifier
  - Keywords now matched case-insensitively
- **Blocking I/O**: Moved file operations off event loop
  - Metrics persistence uses non-blocking writes

### Changed

- **Council Runner Cleanup**: Added task cancellation on client disconnect
  - Prevents zombie LLM API calls when SSE client disconnects
  - Uses `asyncio.wait_for()` with timeout for graceful cleanup

## [0.24.5] - 2026-01-03

### Fixed

- **Build fix**: Use `artifacts` instead of `force-include` for bundled skills packaging
  - Previous configuration tried to include `.github/skills` which doesn't exist in sdist
  - Skills are now correctly bundled from `src/llm_council/skills/bundled/`

## [0.24.4] - 2026-01-03

### Added

- **`install-skills` CLI command**: Install bundled skills to any project
  - `llm-council install-skills --target .github/skills` - Install to project
  - `llm-council install-skills --list` - List available skills
  - `llm-council install-skills --force` - Overwrite existing skills
  - Bundled skills: `council-verify`, `council-review`, `council-gate`

### Changed

- Skills are now bundled in the package for distribution via pip

## [0.24.3] - 2026-01-03

### Fixed

- **Documentation**: Corrected logo path from `assets/logo.svg` to `img/logo.svg` on homepage

## [0.24.2] - 2026-01-03

### Documentation

- **ADR-036 Implementation Changelog**: Added implementation notes for Phase 1 core metrics
  - Documents CSS, DDI, SAS calculation approaches
  - Notes Jaccard-based similarity (async embeddings reserved for future)
  - Integration points: `council.py`, `mcp_server.py`

## [0.24.1] - 2026-01-03

### Fixed

- **Jaccard tokenization**: Changed regex from `\w{3,}` to `\w{2,}` to include 2-letter domain terms (AI, ML, IO, etc.) in similarity calculations for DDI and SAS metrics

## [0.24.0] - 2026-01-03

### Added

- **Output Quality Quantification (ADR-036)**: Three metrics for multi-model deliberation quality
  - **Consensus Strength Score (CSS)**: Measures Stage 2 reviewer agreement
    - Winner margin (40%), ordering clarity (40%), non-tie factor (20%)
    - Interpretation thresholds: 0.85+ strong, 0.70-0.84 moderate, 0.50-0.69 weak
  - **Deliberation Depth Index (DDI)**: Measures thoroughness of deliberation
    - Response diversity (35%), review coverage (35%), critique richness (30%)
    - Uses Jaccard dissimilarity for diversity calculation
  - **Synthesis Attribution Score (SAS)**: Measures grounding of synthesis
    - `winner_alignment`, `max_source_alignment`, `hallucination_risk`, `grounded`
    - Threshold: `grounded=True` when `max_source_alignment >= 0.6`

- **Quality Metrics Module**: New `llm_council.quality` package
  - `types.py`: QualityMetrics, CoreMetrics, SynthesisAttribution dataclasses
  - `consensus.py`: CSS calculation from aggregate rankings
  - `deliberation.py`: DDI calculation with Jaccard-based diversity
  - `attribution.py`: SAS calculation for synthesis grounding
  - `integration.py`: Council integration with configurable enable/disable

- **MCP Tool Enhancement**: Visual quality metrics display
  - Progress bars for CSS and DDI in council responses
  - Grounded status with hallucination risk percentage
  - Warnings display for quality threshold violations

- **Quality Metrics Configuration**
  - `LLM_COUNCIL_QUALITY_METRICS`: Enable/disable (default: true)
  - `LLM_COUNCIL_QUALITY_TIER`: Tier selection (core|standard|enterprise)
  - YAML config support via `quality.enabled` and `quality.tier`

- **Quality Metrics Tests**: 44 TDD tests covering all components
  - Edge cases: empty inputs, single responses, all tied rankings
  - Boundary conditions: threshold values, interpretation ranges
  - Integration tests with council pipeline

- **Documentation Updates**
  - README: Added "Output Quality Metrics (ADR-036)" section
  - ADR-036: Updated status from Draft to Accepted with implementation notes
  - Blog Post 15: "Quantifying Council Quality: CSS, DDI, and SAS"
  - Community announcements for Twitter, Reddit, HN

### Technical Notes

- **Jaccard Similarity Fallback**: Phase 1 uses synchronous Jaccard-based calculations
  - Offline-compatible, no external dependencies
  - Async embedding functions preserved for Tier 2/3 (future phases)
- **Performance**: <30ms total overhead (CSS <5ms, DDI <10ms, SAS <15ms)
- **Tier System**: Core (OSS) tier implemented; Standard/Enterprise reserved for future

## [0.23.1] - 2026-01-03

### Fixed

- **README logo**: Corrected path from `docs/assets/logo.svg` to `docs/img/logo.svg`
- **Blog post broken link**: Removed curl reference to non-existent `examples/github-actions/` directory
- **Blog post clarity**: Added model name disclaimer and import clarification (`pip install llm-council-core` imports as `llm_council`)

## [0.23.0] - 2026-01-01

### Added

- **Directory Expansion for Verification (ADR-034 v2.7)**: Expand directory paths to constituent files
  - `_get_git_object_type()`: Detect blob (file) vs tree (directory) via `git cat-file -t`
  - `_git_ls_tree_z_name_only()`: NUL-delimited parsing for safe filename handling
  - `_expand_target_paths()`: Core expansion with text filtering and truncation
  - `TEXT_EXTENSIONS`: 80+ text file extensions (source code, config, documentation)
  - `GARBAGE_FILENAMES`: Lock files excluded (package-lock.json, yarn.lock, etc.)
  - `MAX_FILES_EXPANSION`: Hard cap of 100 files per expansion

- **Verification Response Schema Enhancement**
  - `expanded_paths`: List of files included after expansion
  - `paths_truncated`: Boolean indicating if MAX_FILES_EXPANSION was hit
  - `expansion_warnings`: Warnings about skipped files or truncation

- **Directory Expansion Tests**: 34 unit and integration tests
  - Real git operations against actual repo
  - Mock tests for edge cases (spaces, newlines, symlinks, submodules)
  - Integration tests with docs/ and src/ directories

### Fixed

- **Verification with Directory Paths**: Now returns file contents instead of git tree listings
  - Previously: `target_paths=["docs/"]` returned tree listing (040000 tree, 100644 blob, etc.)
  - Now: Expands to actual markdown/text files for meaningful council review

### Security

- **Symlink Skipping**: Silently skip symlinks (mode 120000) to prevent path escape
- **Submodule Skipping**: Skip submodules (mode 160000) that lack snapshot context

## [0.22.0] - 2026-01-01

### Added

- **Council Deliberation for Verification (ADR-034 A7)**: Full 3-stage multi-model deliberation
  - Stage 1: Parallel code reviews from multiple models
  - Stage 2: Anonymous peer ranking with rubric scoring
  - Stage 3: Chairman synthesis with structured APPROVED/REJECTED verdict
  - Confidence calculation based on reviewer agreement (rubric score variance)
  - Binary verdict extraction with configurable threshold (default 0.7)
  - Exit codes: 0=PASS, 1=FAIL, 2=UNCLEAR (for CI/CD integration)

- **Verification Prompt Enhancement**: Include actual file contents in verification requests
  - Fetches changed files from git at specified commit SHA
  - Truncates large files to prevent token overflow
  - Supports target_paths filtering for focused verification

- **Blog Post**: "Multi-Model Deliberation: How LLM Council Verifies Code"
  - Explains 3-stage architecture with code examples
  - Documents confidence calculation and verdict extraction
  - Includes GitHub Actions CI/CD integration example
  - Performance considerations table (quick/balanced/high tiers)

### Changed

- **SkillLoader**: Enhanced robustness per council review
  - Better error handling for malformed SKILL.md files
  - Improved metadata caching

### Fixed

- **Async File Operations**: Replaced blocking subprocess calls with async
  - Uses `asyncio.create_subprocess_exec()` instead of `subprocess.run()`
  - Streaming file reads with 8KB chunks (DoS protection)
  - Batched file fetching with early termination
  - Semaphore-based concurrency limiting (10 concurrent git ops)
  - Path traversal attack prevention

- **Rubric Extraction**: Fixed format mismatch in Stage 2 rubric scores
  - Handles both JSON and text-based rubric formats
  - Graceful fallback when parsing fails

### Security

- **DoS Protection**: Multiple layers of protection in verification API
  - File size limits with streaming truncation
  - Batch processing prevents memory exhaustion on large commits
  - Early termination when character limits reached

## [0.21.0] - 2025-12-31

### Added

- **Agent Skills (ADR-034)**: AI-assisted verification, code review, and CI/CD quality gates
  - `council-verify`: General work verification with multi-dimensional scoring
  - `council-review`: Code review with 35% accuracy weight, security/performance/testing focus
  - `council-gate`: CI/CD quality gates with structured exit codes (0=PASS, 1=FAIL, 2=UNCLEAR)
  - Progressive disclosure for token efficiency (Level 1: ~200 tokens, Level 2: ~1000 tokens)
  - Cross-platform compatibility (Claude Code, VS Code Copilot, Cursor, Codex CLI)
  - Skills located at `.github/skills/` for cross-platform discovery

- **Skill Loader**: Python API for progressive skill loading
  - `SkillLoader` class with metadata caching
  - `load_metadata()`: Level 1 - YAML frontmatter only
  - `load_full()`: Level 2 - Complete SKILL.md content
  - `load_resource()`: Level 3 - On-demand resource loading
  - `list_skills()` and `list_resources()` discovery methods

- **Rubric Scoring**: ADR-016 multi-dimensional evaluation
  - 5 dimensions: Accuracy, Completeness, Clarity, Conciseness, Relevance
  - Configurable weights (council-review uses 35% accuracy vs 30% default)
  - Accuracy ceiling rule: prevents eloquent incorrect answers from ranking highly

- **Code Review Rubrics**: Specialized scoring for PR reviews
  - Security focus: SQL injection, XSS, secrets, authentication
  - Performance focus: Algorithm complexity, N+1 queries, memory leaks
  - Testing focus: Coverage gaps, flaky tests, mocking issues
  - Blocking issues by severity: Critical (auto-FAIL), Major, Minor

- **CI/CD Rubrics**: Pipeline integration patterns
  - GitHub Actions, GitLab CI, Azure DevOps examples
  - Exit code documentation (0/1/2 mapping)
  - Security, Performance, Compliance focus areas
  - Confidence threshold configuration

- **Documentation**: Comprehensive guides for agent skills
  - User guide: `docs/guides/skills.md`
  - Developer guide: `docs/guides/creating-skills.md`
  - README section with quick reference table
  - ADR-034 implementation status update

- **Blog Posts**: Three posts documenting the release
  - "Introducing Agent Skills" - Feature announcement
  - "Defense-in-Depth Security" - 8-layer security architecture
  - "CI/CD Quality Gates" - Pipeline integration guide

- **Social Media Announcements**: Launch content prepared
  - Twitter/X threads (feature + technical deep dive)
  - Hacker News "Show HN" post
  - Reddit posts (r/LocalLLaMA, r/MachineLearning)
  - LinkedIn and Discord/Slack announcements

### Changed

- **mkdocs.yml**: Added navigation for skills guides and blog posts
- **README.md**: Added Agent Skills section with installation and usage

## [0.20.0] - 2025-12-30

### Added

- **One-Click Deployment (ADR-038)**: Deploy LLM Council to cloud platforms in minutes
  - Railway template with deploy button and marketplace listing
  - Render blueprint with free tier support
  - Docker Compose for local development
  - `deploy/railway/Dockerfile` optimized for cloud deployment
  - `railway.json` configuration for Railway platform
  - `render.yaml` blueprint for Render platform
  - `docker-compose.yml` for local development
  - `.github/workflows/validate-templates.yml` CI for template validation
  - Comprehensive deployment documentation (`docs/deployment/`)
  - Blog post: "From Clone to Cloud in 60 Seconds"

- **API Token Authentication**: Secure HTTP API endpoints
  - `LLM_COUNCIL_API_TOKEN` environment variable for Bearer token auth
  - Protected endpoints require `Authorization: Bearer <token>` header
  - `/health` endpoint remains public for load balancer checks
  - Backwards compatible: auth optional when token not configured

- **n8n Workflow Integration**: Connect LLM Council to workflow automation
  - Blog post with code review, support triage, and design decision examples
  - HTTP Request node configuration guide
  - Webhook security with HMAC verification
  - Authentication best practices

- **ADR-035 DevSecOps Implementation**: Complete 5-layer security pipeline
  - `.github/dependabot.yml`: Automated dependency updates (pip + GitHub Actions)
  - `.github/workflows/security.yml`: Main security workflow with all scans
  - `.github/workflows/release-security.yml`: SBOM attachment to releases
  - `.gitleaks.toml`: Custom secret patterns for OpenRouter, Anthropic, OpenAI
  - `.pre-commit-config.yaml`: Ruff + Gitleaks pre-commit hooks
  - `.semgrep/llm-security.yaml`: LLM-specific security rules
  - `sonar-project.properties`: SonarCloud configuration
  - Security badge added to README
  - Automated scanning section added to SECURITY.md
  - TDD test suites for security configurations

- **Supply Chain Security**: SLSA Level 3 provenance and OpenSSF Scorecard
  - SLSA provenance attestations for releases (#234)
  - OpenSSF Scorecard workflow for security visibility (#233)

- **Documentation Site**: Custom domain and branding
  - `llm-council.dev` custom domain
  - Brand typography and styling
  - Improved navigation with ADRs and blog

### Changed

- **Security Visibility**: Updated SECURITY.md with automated scanning documentation
  - Documents 5-layer security architecture
  - Pre-commit installation instructions
  - Links to ADR-035 for architecture details

### Fixed

- **Railway Deployment**: Fixed `$PORT` variable expansion (#253)
  - Wrapped start command in `sh -c` for proper shell expansion
- **Render Blueprint**: Set `plan: free` to use free tier by default
- **SBOM/Snyk Workflows**: Fixed Layer 3 workflow failures (#230)

## [0.19.2] - 2025-12-28

### Changed

- **Release Workflow Documentation**: Updated CLAUDE.md with correct PR-based release process
  - Emphasizes never pushing directly to master
  - Documents required CI checks (Test, Lint, Type Check, DCO)
  - Adds verification steps and enforcement notes

### Fixed

- **CI Pipeline**: Disabled failing `Notify Council Cloud` job temporarily (#202)
  - Job requires `CROSS_REPO_TOKEN` secret which is not configured
  - Will be reinstated when secret is set up

## [0.19.1] - 2025-12-28

### Added

- **Model Registry**: Added 6 missing models to `registry.yaml` for offline mode support
  - `openai/gpt-5-mini`: 400K context, economy tier
  - `openai/gpt-5.2`: 400K context, frontier tier
  - `anthropic/claude-sonnet-4.5`: 200K context, frontier tier
  - `anthropic/claude-haiku-4.5`: 200K context, economy tier
  - `google/gemini-3-flash-preview`: 1M context, economy tier
  - `x-ai/grok-code-fast-1`: 256K context, economy tier

### Fixed

- **Branch Protection**: Fixed CI status check name mismatch (`test` → `Test`)

## [0.19.0] - 2025-12-28

### Added

- **ADR-035 DevSecOps Implementation**: Comprehensive security pipeline for OSS
  - 5-layer security pipeline (Pre-commit → PR → Main → Release → Runtime)
  - Fork-compatible CI design (PR checks work without repo secrets)
  - GitHub Actions workflows: CodeQL, Trivy, Semgrep, Gitleaks, Dependency Review
  - SBOM generation with CycloneDX for supply chain transparency
  - Council-reviewed with reasoning tier feedback incorporated

### Fixed

- **Discovery Import Bug**: Fixed `discovery.py` importing from deleted `config.py`
  - Now correctly imports from `tier_contract._get_tier_model_pools()`

### Changed

- **Model Pool Configuration**: Updated tier model pools to next-gen identifiers
  - quick: gpt-5-mini, claude-haiku-4.5, gemini-3-flash-preview
  - balanced: gpt-5-mini, claude-sonnet-4.5, gemini-3-flash-preview, grok-code-fast-1
  - high: gpt-5.2, claude-opus-4.5, gemini-3-pro-preview, grok-4.1-fast
  - reasoning/frontier: gpt-5.2-pro, claude-opus-4.5, gemini-3-pro-preview, grok-4.1-fast
- Synced `llm_council.yaml` with `unified_config.py` TierConfig defaults

## [0.18.1] - 2025-12-28

### Fixed

- **CI/CD Pipeline**: Fixed GitHub Actions failures
  - Added `pydantic>=2.0.0` to core dependencies (required by unified_config.py)
  - Relaxed ruff lint rules to ignore intentional patterns (E402, I001, F401, etc.)
  - Skip MCP tests when `mcp` package not installed (optional dependency)
  - Skip mkdocs build test when `mkdocs` not installed (docs optional dependency)
  - Updated test expectation for `site_name` to match mkdocs.yml

## [0.18.0] - 2025-12-28

### Added

- **ADR-034 Agent Skills Integration**: Standard skill interface for work verification
  - Comparison of Banteg's multi-CLI approach vs LLM Council deliberation
  - Proposed skill wrappers: `council-verify`, `council-review`, `council-gate`
  - Verification API design (`POST /v1/council/verify`) with machine-actionable JSON
  - Pluggable backend architecture supporting multiple verification engines
  - Defense-in-depth security model with context isolation
  - Council-reviewed with feedback incorporated

- **ADR-033 OSS Community Infrastructure**: Documentation and branding
  - MkDocs Material theme with brand typography (Montserrat + JetBrains Mono)
  - Custom domain `llm-council.dev` configured
  - 28 ADRs and 7 blog posts added to navigation
  - Hero section with styled CTAs
  - GitHub issue templates for bugs, features, and ADRs

### Fixed

- MkDocs navigation: All 28 ADRs now properly listed
- MkDocs navigation: All 7 blog posts now in Blog section
- 9 broken links in ADR documentation files

### Changed

- Documentation URL updated to `https://llm-council.dev`
- README.md: Added documentation badge linking to llm-council.dev

## [0.17.0] - 2025-12-27

### Added

- **ADR-031 EvaluationConfig**: Unified evaluation configuration schema
  - `EvaluationConfig` class with benchmark, comparison, and reporting settings
  - Environment variable overrides for all evaluation settings
  - Integration with unified configuration system

- **ADR-032 Complete Configuration Migration**: Single source of truth
  - All configuration now flows through `unified_config.py`
  - Added `get_api_key()` with ADR-013 resolution chain (env → keychain → dotenv)
  - Added `get_key_source()` for API key diagnostics
  - Added `dump_effective_config()` for debugging
  - Public `get_tier_timeout()` function in `tier_contract.py`

### Removed

- **Deleted `config.py`**: 823 lines of legacy configuration code removed
  - All 16 import sites migrated to `unified_config.py` and `tier_contract.py`
  - Tier model pools now accessed via `tier_contract._get_tier_model_pools()`
  - `OLLAMA_HARDWARE_PROFILES` moved to `gateway/ollama.py`

### Changed

- Updated 15 test files to use new configuration imports
- `metadata/selection.py` now imports from `tier_contract` instead of `config`
- Documentation updated to reflect configuration changes

## [0.16.0] - 2025-12-24

### Added

- **ADR-027 Frontier Tier**: Cutting-edge model support with Shadow Mode
  - `VotingAuthority` enum (FULL, ADVISORY, EXCLUDED) for tier-based voting
  - Shadow Mode: Frontier models vote but don't affect consensus
  - `GraduationCriteria` for promoting models from frontier to high tier
  - Cost ceiling protection (5x high-tier average)
  - Hard fallback from frontier to high tier on failure

- **ADR-028 Dynamic Candidate Discovery**: Real-time model discovery
  - Background worker for periodic model refresh
  - Circuit breaker integration for model health tracking
  - Automatic candidate pool updates from OpenRouter API

- **ADR-029 Model Audition Mechanism**: Controlled model evaluation
  - Structured audition process for new models
  - Performance tracking during audition period
  - Graduation criteria based on quality metrics

- **ADR-030 Scoring Refinements**: Improved model scoring
  - `CostScaleAlgorithm` options: linear, log_ratio, exponential
  - Benchmark-justified `QUALITY_TIER_SCORES` with citations
  - `MetricsAdapter` for circuit breaker telemetry
  - Cost scoring with configurable algorithms

### Changed

- Tier model pools now include `frontier` tier
- Quality tier scores updated based on MMLU benchmarks
- Circuit breaker integration with model selection

## [0.15.0] - 2025-12-24

### Added

- **ADR-026 Model Intelligence Layer**: Dynamic model metadata and selection
  - **Phase 1**: Dynamic metadata with TTL caching
    - `DynamicMetadataProvider` with OpenRouter API integration
    - `StaticRegistryProvider` with 31 bundled models
    - `select_tier_models()` for weighted model selection
    - Anti-herding penalties for traffic concentration
    - Provider diversity enforcement (min 2 providers)
  - **Phase 2**: Reasoning parameter optimization
    - `ReasoningConfig` with effort levels (MINIMAL to XHIGH)
    - Automatic reasoning injection for o1/R1 models
    - Usage tracking for reasoning tokens
  - **Phase 3**: Internal performance tracking
    - `InternalPerformanceTracker` with exponential decay
    - JSONL persistence for performance metrics
    - Quality scores based on Borda rankings

- **Offline Mode**: `LLM_COUNCIL_OFFLINE=true` for air-gapped deployments
  - Forces `StaticRegistryProvider` exclusively
  - All core operations work without external calls

- **Bundled Model Registry**: `models/registry.yaml` with 31 models
  - OpenAI, Anthropic, Google, xAI, DeepSeek, Meta, Mistral, Ollama
  - Includes context windows, pricing, and quality tiers

### Changed

- `create_tier_contract()` now accepts optional `task_domain` parameter
- Model selection uses real metadata instead of regex heuristics

## [0.14.0] - 2025-12-23

### Added

- **ADR-025b Jury Mode**: Transform the council from "Summary Generator" to "Decision Engine"
  - **Binary Verdict Mode**: Go/no-go decisions with confidence scores (0.0-1.0)
    - `verdict_type="binary"` returns `{verdict: "approved"|"rejected", confidence, rationale}`
    - Confidence derived from council ranking agreement
    - Use cases: CI/CD gates, PR reviews, policy enforcement
  - **Tie-Breaker Mode**: Chairman resolves deadlocked decisions
    - Auto-escalates when top Borda scores within 0.1 threshold
    - `deadlocked: true` flag indicates chairman intervention
    - Explicit rationale for tie-breaker decisions
  - **Constructive Dissent**: Extract minority opinions from Stage 2
    - `include_dissent=True` surfaces outlier evaluations
    - Statistical detection: score < median - 1.5 × std
    - Formatted as "Minority perspective: ..." in output

- **New Files**:
  - `src/llm_council/verdict.py`: VerdictType enum, VerdictResult dataclass
  - `src/llm_council/dissent.py`: Dissent extraction from Stage 2 evaluations
  - `tests/test_verdict.py`: 8 TDD tests for verdict functionality
  - `tests/test_dissent.py`: 15 TDD tests for dissent extraction

- **API Changes**:
  - `consult_council` MCP tool: Added `verdict_type` and `include_dissent` parameters
  - `run_full_council()`: Added `verdict_type` and `include_dissent` parameters
  - `run_council_with_fallback()`: Added `verdict_type` and `include_dissent` parameters
  - HTTP API `/v1/council/run`: Added `verdict_type` and `include_dissent` fields

### Changed

- README.md: Added comprehensive Jury Mode documentation section
- ADR-025: Updated with ADR-025b implementation status (100% complete)
- `webhooks/__init__.py`: Updated docstring to include EventBridge examples

### Documentation

- Jury Mode section in README with:
  - Verdict types table (synthesis, binary, tie_breaker)
  - Code examples for each mode
  - CI/CD gate integration example
  - Environment variables reference
- Updated `consult_council` tool documentation with new parameters
- ADR-025b implementation status with files created/modified

## [0.12.3] - 2025-12-23

### Added

- **ADR-025: Future Integration Capabilities**: Strategic roadmap for 2025+ integrations
  - Industry landscape analysis (Agentic AI, MCP adoption, Local LLM trends)
  - Council-reviewed priorities for OllamaGateway, webhooks, streaming API
  - Consensus: Native OllamaGateway as top priority for privacy/compliance
  - Agentic positioning as "agent jury" for multi-agent consensus

- **CLI Version Flag**: `llm-council --version` / `llm-council -V`
  - Displays installed package version

### Documentation

- Comprehensive industry analysis with December 2025 trends
- Council review with unanimous verdicts on all 5 key questions
- Phased implementation roadmap (3-6 months)
- Hardware requirements for fully local council deployment

## [0.12.2] - 2025-12-22

### Added

- **RequestyGateway (ADR-023 Phase 2, Issue #66)**: Requesty API integration with BYOK support
  - `RequestyGateway` class implementing `BaseRouter` protocol
  - BYOK (Bring Your Own Key) for provider API keys
  - Full message format conversion and health checking
  - Integration with `GatewayRouter` fallback chains
  - 20 TDD tests

- **DirectGateway (ADR-023 Phase 3, Issue #67)**: Direct provider API access
  - `DirectGateway` class implementing `BaseRouter` protocol
  - Direct API calls to Anthropic, OpenAI, and Google
  - Provider-specific message format handling
  - Anthropic Messages API support (differs from OpenAI format)
  - Google Gemini API support
  - 24 TDD tests

### Changed

- ADR-023 status updated to COMPLETE (all gateways implemented)
- Gateway package now exports `RequestyGateway` and `DirectGateway`
- 44 new tests for gateway implementations

## [0.12.1] - 2025-12-22

### Added

- **Gateway Fallback Chain (ADR-023)**: Seamless retry with secondary gateways on failure
  - `GatewayRouter.complete()` now iterates through fallback chain
  - `fallback_chains` parameter for configuring fallback order
  - Emits `L4_GATEWAY_FALLBACK` event on gateway switch
  - Circuit breaker integration skips unavailable gateways

- **Full Observability Wiring (ADR-024)**: Layer events emitted throughout execution
  - `L2_FAST_PATH_TRIGGERED`: Emitted when fast path routing is attempted (Issue #64)
  - `L2_WILDCARD_SELECTED`: Emitted when wildcard specialist is selected (Issue #65)
  - `L3_COUNCIL_START`: Emitted at council execution start
  - `L3_COUNCIL_COMPLETE`: Emitted at council completion (success, timeout, error)
  - `L4_GATEWAY_RESPONSE`: Emitted for all gateway responses (success and error)
  - Layer boundary crossings: `cross_l1_to_l2()`, `cross_l2_to_l3()`, `cross_l3_to_l4()`

### Fixed

- Gateway router indentation issue
- L4_GATEWAY_RESPONSE now emitted for error/timeout responses (not just success)

### Changed

- 11 new tests for gateway fallback, observability wiring, fast path events, and wildcard events

## [0.12.0] - 2025-12-22

### Added

- **Confidence-Gated Fast Path (ADR-020 Tier 1, Issue #57)**: Route simple queries to single model
  - `FastPathRouter`: Routes queries based on complexity classification
  - `FastPathConfig`: Configuration for confidence threshold (default: 0.92), model selection
  - `ConfidenceExtractor`: Extracts confidence scores from model responses
  - `FastPathResult`: Structured result with confidence, escalation status
  - Graceful escalation to full council when confidence is below threshold
  - Environment variables: `LLM_COUNCIL_FAST_PATH_ENABLED`, `LLM_COUNCIL_FAST_PATH_CONFIDENCE_THRESHOLD`

- **Shadow Council Sampling (ADR-020 Tier 1, Issue #58)**: Quality validation for fast path
  - `ShadowSampler`: Random 5% sampling of fast-path queries through full council
  - `DisagreementDetector`: Text similarity comparison (word-based Jaccard)
  - `ShadowMetricStore`: JSONL persistence for disagreement tracking
  - `ShadowSampleResult`: Structured result with agreement score and analysis
  - Configurable sampling rate and disagreement threshold
  - Environment variables: `LLM_COUNCIL_SHADOW_SAMPLE_RATE`, `LLM_COUNCIL_SHADOW_DISAGREEMENT_THRESHOLD`

- **Rollback Metric Tracking (ADR-020 Tier 1, Issue #60)**: Automatic rollback triggers
  - `RollbackMonitor`: Tracks metrics and checks thresholds for automatic rollback
  - `RollbackMetricStore`: JSONL persistence with rolling window
  - `MetricType`: Shadow disagreement, user escalation, error rate, wildcard timeout
  - `RollbackEvent`: Structured event with breach detection
  - Council-defined thresholds: 8% disagreement, 15% escalation
  - Environment variables: `LLM_COUNCIL_ROLLBACK_ENABLED`, `LLM_COUNCIL_ROLLBACK_WINDOW`

- **Not Diamond API Integration (ADR-020 Tier 1, Issue #59)**: Optional external routing
  - `NotDiamondClient`: API client with caching and graceful fallback
  - `NotDiamondClassifier`: Complexity classification with heuristic fallback
  - `NotDiamondRouter`: Model routing with tier constraint support
  - `NotDiamondConfig`: Configuration from environment variables
  - Graceful degradation to heuristics when API unavailable
  - Environment variables: `NOT_DIAMOND_API_KEY`, `LLM_COUNCIL_USE_NOT_DIAMOND`

### Changed

- 73 new tests for ADR-020 Tier 1 (TDD approach)
- Triage package exports updated with all new modules

## [0.11.1] - 2025-12-22

### Fixed

- **CRITICAL: Gateway Layer Execution Wiring (ADR-024)**
  - `council.py` now imports from `gateway_adapter` instead of `openrouter` directly
  - This enables the gateway layer features (CircuitBreaker, fallback routing) to actually execute
  - Previously, gateway layer code was implemented but never called ("dead code")
  - Gateway wiring is now verified by 4 new integration tests

### Added

- **Gateway Wiring Tests**: `TestGatewayWiring` class in `test_layer_integration.py`
  - `test_council_imports_gateway_adapter`: Verifies council uses gateway_adapter
  - `test_council_module_has_correct_imports`: Validates function object identity
  - `test_gateway_adapter_routes_to_direct_by_default`: Tests backward compatibility
  - `test_gateway_adapter_uses_router_when_enabled`: Tests gateway routing path

## [0.11.0] - 2025-12-22

### Added

- **Integration Testing (ADR-024 Phase 4)**: Comprehensive cross-layer testing
  - 21 integration tests validating layer interactions
  - Tier escalation paths (L1 → L2)
  - Gateway failure isolation (L4 failures NEVER escalate tier)
  - Auto-tier selection via complexity classification
  - End-to-end flow through all four layers
  - Circuit breaker behavior validation
  - Rollback trigger tracking (escalation_rate, fallback_rate)

### Key Invariants Tested

- Gateway failures trigger L4 fallback, NOT L1 tier escalation
- Tier escalation is explicit and logged via LayerEvent
- Layer sovereignty: each layer owns its decision
- Events emitted in layer order (L1 → L2 → L4)

## [0.10.0] - 2025-12-22

### Added

- **Layer Interface Contracts (ADR-024 Phase 3)**: Formal layer boundaries with validation
  - `llm_council.layer_contracts` module formalizing L1→L2→L3→L4 boundaries
  - Re-exports all layer interface types (TierContract, TriageResult, GatewayRequest)
  - `validate_tier_contract()`, `validate_triage_result()`, `validate_gateway_request()`
  - `validate_l1_to_l2_boundary()`, `validate_l2_to_l3_boundary()`, `validate_l3_to_l4_boundary()`

- **Observability Hooks at Layer Boundaries**:
  - `LayerEvent` and `LayerEventType` for event emission
  - `emit_layer_event()`, `get_layer_events()`, `clear_layer_events()`
  - Event types: L1_TIER_SELECTED, L2_TRIAGE_COMPLETE, L4_GATEWAY_REQUEST, etc.
  - Escalation events: L1_TIER_ESCALATION, L2_DELIBERATION_ESCALATION, L4_GATEWAY_FALLBACK

- **Boundary Crossing Helpers**:
  - `cross_l1_to_l2()`, `cross_l2_to_l3()`, `cross_l3_to_l4()`
  - Combined validation + event emission for audit trail

### Changed

- 31 new tests for layer contracts (TDD approach)

## [0.9.0] - 2025-12-22

### Added

- **Unified YAML Configuration (ADR-024 Phase 2)**: Single source of truth for all settings
  - `llm_council.yaml` file support with Pydantic validation
  - Consolidates settings from ADR-020, ADR-022, ADR-023
  - Environment variable substitution with `${VAR_NAME}` syntax
  - Automatic config discovery in current directory and `~/.config/llm-council/`

- **`llm_council.unified_config` module**:
  - `UnifiedConfig`: Main configuration class with all settings
  - `TierConfig`, `TriageConfig`, `GatewayConfig`: Sub-configurations
  - `load_config()`: Load from YAML file with validation
  - `get_effective_config()`: Get config with env var overrides applied
  - `get_config()`, `reload_config()`: Global configuration management

- **Configuration Priority**: YAML > Environment Variables > Defaults
  - All existing environment variables continue to work
  - New YAML configuration is optional and additive

- **Schema Validation**:
  - Invalid tier names rejected (must be: quick, balanced, high, reasoning)
  - Invalid gateway names rejected (must be: openrouter, requesty, direct, auto)
  - Confidence thresholds validated (0.0-1.0 range)
  - Escalation limits validated (0-5 range)

### Changed

- PyYAML added as dependency
- 36 new tests for unified configuration (TDD approach)

## [0.8.0] - 2025-12-22

### Added

- **Triage Layer (ADR-020 Phase 3)**: Query classification and model selection optimization
  - `llm_council.triage` package with modular components
  - `TriageResult`, `TriageRequest`, `WildcardConfig`, `DomainCategory` types
  - Wildcard selection: Adds domain-specialized models based on query classification
  - Prompt optimization: Per-model prompt adaptation (Claude XML, etc.)
  - Complexity classifier: Heuristic-based with Not Diamond placeholder

- **Domain-Specialized Model Selection**:
  - CODE: DeepSeek, Codestral for programming queries
  - REASONING: o1-preview, DeepSeek-R1 for math/logic
  - CREATIVE: Claude Opus, Command-R+ for fiction/poetry
  - MULTILINGUAL: GPT-4o, Command-R+ for translation
  - GENERAL: Llama 3 fallback

- **Council Integration**:
  - `use_wildcard` parameter for `run_council_with_fallback()`
  - `optimize_prompts` parameter for per-model adaptation
  - Triage metadata included in council results

- **New Environment Variables**:
  - `LLM_COUNCIL_WILDCARD_ENABLED`: Enable wildcard selection (default: false)
  - `LLM_COUNCIL_PROMPT_OPTIMIZATION_ENABLED`: Enable prompt optimization (default: false)

### Changed

- Triage layer is opt-in for backward compatibility
- 111 new tests for triage package (TDD approach)

## [0.7.0] - 2025-12-22

### Added

- **Gateway Abstraction Layer (ADR-023)**: Multi-router support with fault tolerance
  - `llm_council.gateway` package with provider-agnostic types
  - `OpenRouterGateway`: BaseRouter implementation for OpenRouter
  - `CircuitBreaker`: State machine (CLOSED → OPEN → HALF_OPEN) for fault tolerance
  - `GatewayRouter`: Orchestrates requests with circuit breaker integration
  - Canonical message formats: `CanonicalMessage`, `ContentBlock`, `GatewayRequest`, `GatewayResponse`
  - Error taxonomy: `TransportFailure`, `RateLimitError`, `AuthenticationError`, `CircuitOpenError`

- **Gateway Adapter Module**: Unified interface for council operations
  - `gateway_adapter.py` provides same interface as `openrouter` module
  - Automatically uses gateway layer when `USE_GATEWAY_LAYER=true`
  - Full backward compatibility when disabled (default)

- **New Environment Variables**:
  - `LLM_COUNCIL_USE_GATEWAY`: Enable gateway layer (default: false)

### Changed

- Gateway layer is opt-in via `LLM_COUNCIL_USE_GATEWAY=true`
- 88 new tests for gateway package (TDD approach)

## [0.6.0] - 2025-12-22

### Added

- **Tier-Appropriate Model Selection (ADR-022)**: Each confidence level now uses optimized model pools
  - `quick`: Fast models (gpt-4o-mini, claude-haiku, gemini-flash) for ~30s responses
  - `balanced`: Mid-tier models (gpt-4o, claude-sonnet, gemini-pro) for ~90s responses
  - `high`: Full council (gpt-4o, claude-opus, gemini-3-pro, grok-4) for ~180s responses
  - `reasoning`: Deep thinking models (gpt-5.2-pro, claude-opus, o1-preview, deepseek-r1) for ~600s responses

- **TierContract Dataclass**: Immutable contract defining tier execution parameters
  - `tier`, `deadline_ms`, `per_model_timeout_ms`, `token_budget`, `max_attempts`
  - `requires_peer_review`, `requires_verifier`, `allowed_models`, `aggregator_model`
  - `create_tier_contract()` factory function for easy creation
  - `TIER_AGGREGATORS`: Speed-matched aggregator models per tier

- **New Environment Variables**:
  - `LLM_COUNCIL_MODELS_QUICK`: Override quick tier models
  - `LLM_COUNCIL_MODELS_BALANCED`: Override balanced tier models
  - `LLM_COUNCIL_MODELS_HIGH`: Override high tier models
  - `LLM_COUNCIL_MODELS_REASONING`: Override reasoning tier models

### Changed

- `run_council_with_fallback()` now accepts `models` and `tier_contract` parameters
- MCP `consult_council` creates TierContract from confidence level
- Response metadata includes `tier` field when tier_contract provided

## [0.5.1] - 2025-12-22

### Changed

- **Doubled Reasoning Tier Timeouts**: Increased from 300s/150s to 600s/300s (total/per-model)
  - Addresses timeout issues with deep reasoning models (GPT-5.2-pro, o1)
  - 10-minute total timeout allows complex multi-model deliberation to complete

## [0.5.0] - 2025-12-19

### Added

- **Tier-Sovereign Timeout Architecture (ADR-012 Section 5)**: Configurable per-tier timeouts for reasoning models
  - New `reasoning` confidence tier: 600s total, 300s per-model (supports GPT-5.2-pro, o1, o1-preview)
  - Existing tiers updated: quick (30s/20s), balanced (90s/45s), high (180s/90s)
  - `get_tier_timeout()`: Retrieves timeout config with environment variable overrides
  - `infer_tier_from_models()`: Auto-selects tier based on slowest model in council
  - `per_model_timeout` parameter on `run_council_with_fallback()` for fine-grained control

- **New Environment Variables**:
  - `LLM_COUNCIL_TIMEOUT_<TIER>`: Override total timeout per tier (QUICK, BALANCED, HIGH, REASONING)
  - `LLM_COUNCIL_MODEL_TIMEOUT_<TIER>`: Override per-model timeout per tier

### Documentation

- ADR-012 Section 5: Tier-Sovereign Timeout Architecture with model compatibility matrix
- Infrastructure considerations for AWS ALB, Nginx, and proxy timeouts

## [0.4.1] - 2025-12-19

### Changed

- **Default Council Model Update**: Replaced `openai/gpt-5.1` with `openai/gpt-5.2-pro`
  - Upgraded to OpenAI's latest reasoning model for improved council quality

## [0.4.0] - 2025-12-18

### Added

- **Cross-Session Bias Aggregation (ADR-018)**: Statistically meaningful bias detection
  - Phase 1: JSONL-based bias metric persistence with schema versioning (v1.1.0)
  - Phase 2: Statistical aggregation with Fisher z-transforms and confidence intervals
  - Phase 3: Temporal trend detection and anomaly flagging
  - `BiasMetricRecord` dataclass with one record per (session, model, reviewer)
  - `ConsentLevel` enum: OFF(0), LOCAL_ONLY(1), ANONYMOUS(2), ENHANCED(3), RESEARCH(4)
  - Reviewer profiles with harshness z-scores for calibration analysis
  - Position bias aggregation via variance of position means
  - 74 new tests (44 Phase 1 + 30 Phase 2-3)

- **CLI `bias-report` Command**: Cross-session bias analysis from the command line
  - Text and JSON output formats
  - Filtering by sessions (`--sessions N`) and days (`--days N`)
  - Verbose mode (`--verbose`) for detailed reviewer profiles
  - Custom input path (`--input FILE`)

- **New Aggregation Functions**:
  - `run_aggregated_bias_audit()`: Main entry point for cross-session analysis
  - `pooled_correlation_with_ci()`: Pooled length-score correlation with 95% CI
  - `aggregate_reviewer_profiles()`: Per-reviewer mean, std, harshness z-score
  - `aggregate_position_bias()`: Variance of position means
  - `detect_temporal_trends()`: Rolling window trend detection
  - `detect_anomalies()`: Outlier session flagging

- **New Configuration Options**:
  - `LLM_COUNCIL_BIAS_PERSISTENCE`: Enable cross-session storage (default: false)
  - `LLM_COUNCIL_BIAS_STORE`: Path to JSONL file (default: ~/.llm-council/bias_metrics.jsonl)
  - `LLM_COUNCIL_BIAS_CONSENT`: Privacy consent level 0-4 (default: 1)
  - `LLM_COUNCIL_BIAS_WINDOW_SESSIONS`: Rolling window max sessions (default: 100)
  - `LLM_COUNCIL_BIAS_WINDOW_DAYS`: Rolling window max days (default: 30)
  - `LLM_COUNCIL_MIN_BIAS_SESSIONS`: Minimum sessions for aggregation (default: 20)
  - `LLM_COUNCIL_HASH_SECRET`: Secret for query hashing (RESEARCH consent only)

- **Statistical Confidence Tiers**:
  - INSUFFICIENT (N < 10): "Collecting data..."
  - PRELIMINARY (10-19): High volatility warning
  - MODERATE (20-49): Confidence intervals displayed
  - HIGH (N >= 50): Full analysis with narrow CIs

### Documentation

- ADR-018: Implementation status section with CLI usage examples
- README.md: Cross-session bias aggregation section and environment variables
- CLAUDE.md: Documentation for bias_persistence.py and bias_aggregation.py modules

## [0.3.0] - 2025-12-17

### Added

- **Bias Auditing (ADR-015)**: Per-session bias indicators for peer review scoring
  - Length-score correlation detection (Pearson r, threshold |r| > 0.3)
  - Position bias detection via `display_index` tracking
  - Reviewer calibration analysis (harsh/generous reviewers)
  - Overall bias risk assessment ("low", "medium", "high")
  - Pure Python implementation (no scipy/numpy dependency)
  - Configuration: `LLM_COUNCIL_BIAS_AUDIT=true`
  - **Note**: With 4-5 models per session, these are indicators for extreme anomalies, not statistically robust proof

- **Structured Rubric Scoring (ADR-016)**: Multi-dimensional evaluation
  - Five dimensions: accuracy (35%), relevance (10%), completeness (20%), conciseness (15%), clarity (20%)
  - Accuracy ceiling mechanism: prevents confident lies from ranking well
  - Scoring anchors with behavioral examples for each 1-10 level
  - Customizable weights via `LLM_COUNCIL_WEIGHT_*` environment variables
  - Configuration: `LLM_COUNCIL_RUBRIC_SCORING=true`

- **Safety Gate (ADR-016)**: Pass/fail pre-check for harmful content
  - Detects: dangerous instructions, weapon making, malware/hacking, self-harm, PII exposure
  - Context-aware: allows educational/defensive security content
  - Failed responses capped at score 0
  - Configuration: `LLM_COUNCIL_SAFETY_GATE=true`

- **Enhanced Position Tracking (Council-Recommended)**: Robust position bias detection
  - Enhanced `label_to_model` format with explicit `display_index`
  - Eliminates string parsing fragility
  - Backward compatible with legacy format
  - Documented invariant for label assignment order

- **New Bias Audit Functions**:
  - `run_bias_audit()`: Main entry point for bias analysis
  - `calculate_length_correlation()`: Pure Python Pearson correlation
  - `audit_reviewer_calibration()`: Detect harsh/generous reviewers
  - `calculate_position_bias()`: Position effect detection
  - `derive_position_mapping()`: Extract positions from label mapping
  - `extract_scores_from_stage2()`: Convert Stage 2 results for analysis

- **New Safety Functions**:
  - `check_response_safety()`: Scan for harmful content patterns
  - `apply_safety_gate_to_score()`: Cap scores for failed safety checks

- **New Rubric Functions**:
  - `calculate_weighted_score()`: Weighted average from dimension scores
  - `calculate_weighted_score_with_accuracy_ceiling()`: Accuracy-capped scoring
  - `parse_rubric_evaluation()`: Extract rubric JSON from model responses

### Changed

- `label_to_model` now uses enhanced format: `{"Response A": {"model": "...", "display_index": 0}}`
- Stage 2 evaluation prompts updated for rubric scoring when enabled
- Council metadata now includes `bias_audit` results when enabled

### Documentation

- ADR-015: Bias Auditing - Implementation status and invariants documented
- ADR-016: Structured Rubric Scoring - Scoring anchors and safety gate details
- ADR-017: Response Order Randomization - Position tracking implementation and future scenarios
- README.md: New environment variables and feature documentation
- CLAUDE.md: Developer documentation for new modules

## [0.2.0] - 2025-12-13

### Added

- **MCP Server Reliability (ADR-012)**: Comprehensive improvements for long-running operations
  - Progress notifications via `ctx.report_progress()` during council execution
  - Health check tool `council_health_check()` to verify API connectivity before expensive operations
  - Confidence levels parameter: "quick" (2 models, ~10s), "balanced" (3 models, ~25s), "high" (full council, ~45s)

- **Tiered Timeout Strategy (ADR-012 Phase 2)**: Graceful degradation under time pressure
  - Per-model soft deadline: 15s (start planning fallback)
  - Per-model hard deadline: 25s (abandon that model)
  - Global synthesis trigger: 40s (must start synthesis)
  - Response deadline: 50s (must return something)

- **Partial Results on Timeout**: Return whatever data has been collected
  - `run_council_with_fallback()`: New function with ADR-012 structured result schema
  - `quick_synthesis()`: Fast fallback synthesis from Stage 1 responses when Stage 2 times out
  - `generate_partial_warning()`: Clear warning messages indicating partial results
  - Per-model status tracking throughout the pipeline

- **Structured Error Handling**: Better failure taxonomy for model queries
  - Status types: `ok`, `timeout`, `rate_limited`, `auth_error`, `error`
  - Each response includes `latency_ms`, error messages, `retry_after` where applicable
  - Distinguishes between timeout, rate limiting (429), and auth errors (401/403)

- **New Council Functions**:
  - `stage1_collect_responses_with_status()`: Stage 1 with per-model status tracking
  - `run_council_with_fallback()`: Full pipeline with tiered timeouts and fallback synthesis

- **New OpenRouter Functions**:
  - `query_model_with_status()`: Returns structured result with status instead of None on failure
  - `query_models_with_progress()`: Parallel queries with real-time progress callbacks

- **Secure API Key Handling (ADR-013)**: Multi-tier secure key resolution
  - Key resolution priority: Environment variable → System Keychain → Config file
  - Optional `keyring` dependency for system keychain integration
  - `setup-key` CLI command for securely storing API keys
  - Key source tracking via `get_key_source()` for diagnostics
  - Warning emitted when key loaded from insecure config file (suppressible)

- **New CLI Command**:
  - `llm-council setup-key`: Securely store API key in system keychain
  - `llm-council setup-key --stdin`: Read key from stdin for CI/CD automation

- **New Optional Dependency**:
  - `[secure]` extra: `pip install "llm-council-core[secure]"` for keychain support

### Changed

- `consult_council` MCP tool now uses `run_council_with_fallback()` for reliability
- `consult_council` MCP tool now accepts optional `confidence` parameter
- Council rankings now displayed in output when available
- Partial result warnings shown when some models timeout
- Health check now includes `key_source` field showing where API key came from

## [0.1.0] - 2024-12-01

### Changed

- **Package Renamed**: PyPI package renamed from `llm-council` to `llm-council-core`
  - Import remains `llm_council` (no code changes needed)
  - CLI command remains `llm-council`
  - Install: `pip install llm-council-core[mcp]`

### Added

- **Version Export**: `__version__` and `__version_tuple__` now exported from package root
  - Enables version checking: `from llm_council import __version__`

## [0.3.0] - 2024-11-29

### Added

- **Cost Transparency**: Token usage tracking across all pipeline stages
  - Per-stage breakdown (Stage 1, 1.5, 2, 3)
  - Grand total tokens (prompt, completion, total)
  - Included in response metadata for cost monitoring

- **Borda Count Ranking**: More robust ranking aggregation
  - 1st place = (N-1) points, 2nd = (N-2), ..., last = 0 points
  - Uses relative rankings (which LLMs are good at) instead of absolute scores
  - Scores still tracked as secondary signal

- **Small Council Handling**: Graceful degradation for N ≤ 2
  - Single model (N=1): Skip Stage 2 peer review entirely
  - Two models (N=2): Proceed but mark rankings as "degraded" (single vote each)
  - Clear warnings in metadata for transparency

- **Reviewer Refusal Detection**: Handle safety refusals gracefully
  - Detects common refusal patterns ("I cannot evaluate", "I must decline", etc.)
  - Marks abstained reviewers in metadata with reason
  - Abstentions excluded from ranking aggregation

- **HTML Escaping for XML Defense**: Enhanced prompt injection protection
  - Response content HTML-escaped within XML tags
  - Prevents injection via HTML/XML special characters

- **Tool Calling Disabled**: Stage 2/3 now explicitly disable tool calling
  - Prevents prompt injection via tool invocation
  - Uses OpenRouter's `tools: []` and `tool_choice: "none"` options

### Changed

- All stage functions now return usage data alongside results
- Metadata structure updated to include `usage.by_stage` and `usage.total`

### Fixed

- Aggregate rankings now use Borda Count for more stable results
- Reviewer abstentions no longer corrupt ranking calculations

## [0.2.0] - 2024-11-29

### Added

- **JSON-based Rankings**: Stage 2 now uses structured JSON output instead of string parsing
  - Rankings include both ordered list and numeric scores (1-10)
  - Robust parsing with multiple fallback strategies
  - Backwards compatible with legacy "FINAL RANKING:" format

- **Self-Vote Exclusion**: Models' votes for their own responses are excluded from aggregation
  - Prevents self-preference bias
  - Configurable via `LLM_COUNCIL_EXCLUDE_SELF_VOTES` (default: true)
  - Each response still receives N-1 peer reviews

- **XML Sandboxing**: Prompt injection defense for Stage 2
  - Responses wrapped in `<candidate_response>` tags
  - Explicit instruction to ignore embedded commands
  - Protects against adversarial response content

- **Style Normalization (Stage 1.5)**: Optional preprocessing to strengthen anonymization
  - Rewrites responses in neutral style before peer review
  - Removes AI preambles and stylistic fingerprints
  - Configurable via `LLM_COUNCIL_STYLE_NORMALIZATION` (default: false)
  - Uses fast/cheap model for efficiency

- **Consensus/Debate Modes**: Configurable synthesis strategy
  - `consensus` (default): Chairman synthesizes single best answer
  - `debate`: Chairman highlights disagreements and trade-offs
  - Configurable via `LLM_COUNCIL_MODE`

- **Stratified Sampling**: Scalability for large councils
  - Limits reviewers per response to reduce O(N²) complexity
  - Configurable via `LLM_COUNCIL_MAX_REVIEWERS`
  - Recommended: 3 reviewers for councils > 5 models

- **Position Randomization**: Response order shuffled before Stage 2
  - Prevents position bias in peer review

- **Enhanced Metadata**: Council responses now include configuration details
  - Synthesis mode, self-vote settings, council size
  - Aggregate rankings with scores and vote counts

### Changed

- Updated default council models to latest versions:
  - GPT-5.1, Gemini 3 Pro Preview, Claude Sonnet 4.5, Grok 4
- Default chairman changed to Gemini 3 Pro Preview
- Stage 3 now receives aggregate rankings for better synthesis context

### Fixed

- Ranking aggregation now correctly parses JSON structure
- Position bias reduced via response order randomization

## [0.1.0] - 2024-11-28

### Added

- Initial MCP server release
- 3-stage council process (collect, rank, synthesize)
- OpenRouter integration for multi-model access
- User-configurable model selection via env vars and config file
- Graceful degradation when individual models fail
- PyPI package distribution
- GitHub Actions CI/CD pipeline
