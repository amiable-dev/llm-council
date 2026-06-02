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

## Architecture: the L1→L4 layer model (ADR-024)

Requests flow through four layers with formal boundary contracts in `layer_contracts.py`:

- **L1 Tier** (`tier_contract.py`, ADR-022) — picks a confidence tier (`quick|balanced|high|reasoning`, plus `frontier`) and its `TierContract` (timeouts, token budget, peer-review/verifier flags, allowed/aggregator models, escalation policy).
- **L2 Triage** (`triage/`, ADR-020) — domain classification, wildcard specialist selection, per-model prompt optimization (e.g. Claude XML), complexity heuristics.
- **L3 Council** (`council.py`) — the 3-stage deliberation core.
- **L4 Gateway** (`gateway/`, `gateway_adapter.py`, ADR-023/030) — provider calls, circuit breaking.

**Principles (ADR-024):** layer sovereignty (each layer owns its decision), explicit/auditable escalation, failure isolation (gateway failures don't cascade into tier changes), constraint propagation downward, observability by default. Every boundary crossing validates and emits a `LayerEvent` (`emit_layer_event()`); `observability/` bridges those events to StatsD/Prometheus (ADR-030).

## Module map (`src/llm_council/`)

Council core
- `council.py` — `stage1_collect_responses`, `stage2_collect_rankings` (anonymizes → `label_to_model`, parses rankings), `calculate_aggregate_rankings` (Borda), `stage3_synthesize_final`. Shadow-vote integration for frontier tier (ADR-027).
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

Bias (ADR-015/018)
- `bias_audit.py` (ADR-015) — per-session indicators: length↔score correlation (pure-Python Pearson), reviewer calibration, position bias. **These are anomaly indicators, not statistically robust proof** — with N=4–5 models there are only 4–5 data points (≥30 needed for significance), and a single ordering can't separate position effects from quality.
- `bias_persistence.py` (ADR-018 P1) — JSONL store, `ConsentLevel` (OFF→RESEARCH). `bias_aggregation.py` (ADR-018 P2-3) — cross-session pooled correlation w/ CIs (Fisher-z), confidence tiers, temporal trends, anomaly flagging. Surfaced via `llm-council bias-report`.

Observability & telemetry
- `observability/` (ADR-030 metrics export — StatsD/Prometheus/NoOp), `telemetry.py` / `telemetry_client.py`, `webhooks/`.

Verification (ADR-034/040/041) — `verification/api.py`
- `run_verification()` wraps `_run_verification_pipeline()` (stages 1–3) in `asyncio.wait_for()` with a global deadline = `tier_contract.deadline_ms/1000 × 1.5` (`VERIFICATION_TIMEOUT_MULTIPLIER`).
- **Waterfall time budget (ADR-040):** stage1 = 50% of remaining, stage2 = 70% of what's left, stage3 = the rest; each capped by `tier_timeout["per_model"]`.
- **Durable partial state:** `partial_state` is updated after each stage and survives `CancelledError`, so a timeout still returns `completed_stages`. `VerifyResponse` carries `timeout_fired`, `completed_stages`, and (ADR-041) `timing` / `input_metrics`.
- **Per-tier input caps** `TIER_MAX_CHARS` (quick 15K, balanced 30K, high/reasoning 50K). Per-file truncation (#342) is surfaced as an `expansion_warnings` entry rather than silently dropped; `reasoning`/`high` can read a full 50K file.
- Performance tracker is wired on success only, wrapped in try/except so telemetry never fails verification.

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
