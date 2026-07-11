# Environment Variables

> **Canonical reference** — drift-tested against the source: a test fails if
> code reads a variable missing here, or this page documents one that no
> longer exists (`tests/test_docs_drift.py`). Defaults marked *code* are
> internal defaults; several subsystems are configured in `llm_council.yaml`
> (ADR-031) with env vars as overrides.

## Configuration

| Variable | Description | Default |
|---|---|---|
| `LLM_COUNCIL_CONFIG` | Path to llm_council.yaml | ./llm_council.yaml |

## Gateways

| Variable | Description | Default |
|---|---|---|
| `LLM_COUNCIL_CIRCUIT_BREAKER` | Enable per-model circuit breaker (ADR-030) | true |
| `LLM_COUNCIL_CIRCUIT_MIN_REQUESTS` | Minimum requests before a breaker can trip | 10 |
| `LLM_COUNCIL_CIRCUIT_THRESHOLD` | Failure-rate threshold to open a breaker | 0.25 |
| `LLM_COUNCIL_DEFAULT_GATEWAY` | Default gateway (openrouter/requesty/direct) | openrouter |
| `LLM_COUNCIL_GATEWAY_FALLBACK_CHAIN` | Comma-separated gateway fallback order (ADR-023) | — |
| `NOT_DIAMOND_API_KEY` | Not Diamond routing API key (ADR-020, optional) | — |
| `OPENROUTER_API_KEY` | OpenRouter API key (primary gateway) | — |
| `REQUESTY_API_KEY` | Requesty API key | — |

## Council

| Variable | Description | Default |
|---|---|---|
| `LLM_COUNCIL_CHAIRMAN` | Chairman model override | config |
| `LLM_COUNCIL_CHAIRMAN_DISABLED` | Skip Stage 3 chairman synthesis; return the top-ranked Stage 1 response directly. **Never enable for BINARY-verdict use (`council-verify`/`council-gate`) — no verdict is computed, the verify API reports `verdict: unclear`, `unclear_reason: chairman_disabled`.** | false |
| `LLM_COUNCIL_EXCLUDE_SELF_VOTES` | Exclude self-votes in stage 2 | true |
| `LLM_COUNCIL_MAX_REVIEWERS` | Stratified sampling: max reviewers per response | all |
| `LLM_COUNCIL_MODE` | consensus or debate synthesis | consensus |
| `LLM_COUNCIL_MODELS` | Comma-separated council override | tier pool |
| `LLM_COUNCIL_NORMALIZER_MODEL` | Model used for style normalization | config |
| `LLM_COUNCIL_STYLE_NORMALIZATION` | Stage-1.5 style normalization | false |

## Tiers & routing

| Variable | Description | Default |
|---|---|---|
| `LLM_COUNCIL_DEFAULT_TIER` | Default confidence tier | high |
| `LLM_COUNCIL_FAST_PATH_CONFIDENCE_THRESHOLD` | Fast-path confidence threshold | 0.92 |
| `LLM_COUNCIL_FAST_PATH_ENABLED` | Confidence-gated single-model fast path (ADR-020) | false |
| `LLM_COUNCIL_FAST_PATH_MAX_QUERY_LENGTH` | Max query length eligible for fast path | code |
| `LLM_COUNCIL_FAST_PATH_MODEL` | Fast-path model | auto |
| `LLM_COUNCIL_MODELS_BALANCED` | Model pool override for the balanced tier (ADR-022) | config |
| `LLM_COUNCIL_MODELS_HIGH` | Model pool override for the high tier (ADR-022) | config |
| `LLM_COUNCIL_MODELS_QUICK` | Model pool override for the quick tier (ADR-022) | config |
| `LLM_COUNCIL_MODELS_REASONING` | Model pool override for the reasoning tier (ADR-022) | config |
| `LLM_COUNCIL_NOT_DIAMOND_CACHE_TTL` | Not Diamond cache TTL (s) | 300 |
| `LLM_COUNCIL_NOT_DIAMOND_TIMEOUT` | Not Diamond API timeout (s) | 5.0 |
| `LLM_COUNCIL_PROMPT_OPTIMIZATION_ENABLED` | Per-model prompt optimization (ADR-020) | false |
| `LLM_COUNCIL_ROLLBACK_DISAGREEMENT_THRESHOLD` | Rollback trigger: shadow disagreement | 0.08 |
| `LLM_COUNCIL_ROLLBACK_ENABLED` | Fast-path rollback metric tracking | true |
| `LLM_COUNCIL_ROLLBACK_ERROR_MULTIPLIER` | Rollback trigger: error-rate multiplier | code |
| `LLM_COUNCIL_ROLLBACK_ESCALATION_THRESHOLD` | Rollback trigger: user escalations | 0.15 |
| `LLM_COUNCIL_ROLLBACK_MIN_SAMPLES` | Min samples before rollback can trigger | code |
| `LLM_COUNCIL_ROLLBACK_WILDCARD_TIMEOUT_THRESHOLD` | Rollback trigger: wildcard timeout rate | code |
| `LLM_COUNCIL_ROLLBACK_WINDOW` | Rollback metrics window size | 100 |
| `LLM_COUNCIL_SHADOW_DISAGREEMENT_THRESHOLD` | Shadow disagreement alarm threshold | 0.08 |
| `LLM_COUNCIL_SHADOW_SAMPLING_RATE` | Shadow-sample rate for fast-path QA (ADR-020) | 0.05 |
| `LLM_COUNCIL_SHADOW_WINDOW_SIZE` | Shadow metrics rolling window | code |
| `LLM_COUNCIL_TRIAGE_ENABLED` | L2 triage layer (ADR-020) | false |
| `LLM_COUNCIL_USE_NOT_DIAMOND` | Enable Not Diamond routing (ADR-020) | false |
| `LLM_COUNCIL_WILDCARD_ENABLED` | Wildcard specialist selection (ADR-020) | false |

## Model intelligence

| Variable | Description | Default |
|---|---|---|
| `LLM_COUNCIL_DISCOVERY_ENABLED` | Background candidate discovery (ADR-028) | false |
| `LLM_COUNCIL_DISCOVERY_INTERVAL` | Discovery interval (s) | 300 |
| `LLM_COUNCIL_DISCOVERY_MIN_CANDIDATES` | Min candidates before discovery acts | 3 |
| `LLM_COUNCIL_MODEL_INTELLIGENCE` | Dynamic model metadata (ADR-026) | false |
| `LLM_COUNCIL_OFFLINE` | Force offline/static provider (ADR-026) | false |
| `LLM_COUNCIL_PERFORMANCE_STORE` | Performance index store path | code |
| `LLM_COUNCIL_PERFORMANCE_TRACKING` | Internal performance index (ADR-026 P3) | true |
| `LLM_COUNCIL_REASONING_ENABLED` | Reasoning effort levels (ADR-026 P2) | true |

## Compute-optimal (ADR-044)

| Variable | Description | Default |
|---|---|---|
| `LLM_COUNCIL_EARLY_CONSENSUS` | Early consensus termination (ADR-044 P2; off = shadow) | false |
| `LLM_COUNCIL_GRADUATED_DEPTH` | Graduated deliberation depth (ADR-044 P3) | false |
| `LLM_COUNCIL_PERFORMANCE_SELECTION` | Blend live index into selection (ADR-044 P1) | false |

## Cost & budget (ADR-011)

| Variable | Description | Default |
|---|---|---|
| `LLM_COUNCIL_BUDGET_ENFORCEMENT` | Budget enforcement opt-in (ADR-011 P4) | false |
| `LLM_COUNCIL_BUDGET_MODE` | STRICT / BALANCED / PERMISSIVE | BALANCED |
| `LLM_COUNCIL_COST_AWARE_SELECTION` | Cost-aware ranking opt-in (ADR-011 P3) | false |
| `LLM_COUNCIL_COST_SCALE` | Cost scoring algorithm | code |

## Frontier & audition

| Variable | Description | Default |
|---|---|---|
| `LLM_COUNCIL_AUDITION_ENABLED` | Model audition state machine (ADR-029) | true |
| `LLM_COUNCIL_AUDITION_EVAL_SESSIONS` | Evaluation sessions before full vote | 50 |
| `LLM_COUNCIL_AUDITION_MAX_SEATS` | Concurrent audition seats | 1 |
| `LLM_COUNCIL_AUDITION_SHADOW_SESSIONS` | Shadow sessions before probation | 10 |
| `LLM_COUNCIL_AUDITION_STORE` | Audition status store path | code |

## Evaluation

| Variable | Description | Default |
|---|---|---|
| `ACCURACY_CEILING_ENABLED` | Accuracy caps the weighted score (ADR-016) | true |
| `BIAS_AUDIT_ENABLED` | Per-session bias audit (ADR-015/031) | false |
| `BIAS_PERSISTENCE_ENABLED` | Cross-session bias storage (ADR-018/031) | false |
| `LLM_COUNCIL_HASH_SECRET` | HMAC secret for query hashing (RESEARCH consent) | dev secret |
| `LLM_COUNCIL_QUALITY_METRICS` | Output quality metrics (ADR-036) | false |
| `LLM_COUNCIL_QUALITY_TIER` | Tier gating for quality metrics | code |
| `RUBRIC_SCORING_ENABLED` | Multi-dimensional rubric scoring (ADR-016/031) | false |
| `SAFETY_GATE_ENABLED` | Safety pre-check gate (ADR-016/031) | false |

## Verification (ADR-047)

| Variable | Description | Default |
|---|---|---|
| `LLM_COUNCIL_CALIBRATED_CONFIDENCE` | PASS threshold uses calibrated confidence (ADR-047 P2) | false |
| `LLM_COUNCIL_SCREENING` | Screening judge: off / shadow / active (ADR-047 P3) | off |
| `LLM_COUNCIL_SCREEN_MAX_CHARS` | Screening eligibility: max content chars | 5000 |
| `LLM_COUNCIL_SCREEN_MIN_SCORE` | Screening unanimity minimum per dimension | 9 |
| `LLM_COUNCIL_STRUCTURED_FINDINGS` | ADR-051 structured findings channel: the chairman emits severity-tagged findings and the verdict is derived from them (`blocking_issues` = critical subset). Off by default — additive/opt-in until a later breaking default-ON flip | false |
| `LLM_COUNCIL_FILE_SELECTION` | ADR-053 Q1 verify file classification: `allowlist` (extension `TEXT_EXTENSIONS` — byte-identical to pre-#552), `content` (git's NUL heuristic + snapshot `.gitattributes`, reviews any text file incl. unlisted languages), or `shadow` (acts on allowlist, logs what content would change). Invalid ⇒ allowlist. The secret denylist (#548) and garbage filter always run first regardless | allowlist |
| `LLM_COUNCIL_REVIEW_SVG` | ADR-053 Q2: review `.svg` in `content` mode instead of omitting it as noise (SVG decodes as text but is usually a generated asset). Content-mode only — allowlist mode always reviews `.svg` via `TEXT_EXTENSIONS` | false |
| `LLM_COUNCIL_COVERAGE_POLICY` | ADR-053 #556 coverage clamp: `clamp` (a `pass` over an unreviewed changed/explicit file becomes `unclear(incomplete_coverage)`), `fail` (hard 422 instead), or `warn` (receipt only, no verdict effect). **Ships opt-in — default `warn` (byte-identical); flips to `clamp` in a later release after shadow telemetry (#557), which also makes `gate` refuse an explicit `warn` downgrade.** Invalid ⇒ the current default | warn |
| `LLM_COUNCIL_COVERAGE_ACK_REASONS` | ADR-053 #556: comma-separated omission reasons the operator pre-accepts, so the clamp ignores them. Unset ⇒ `binary,generated,vendored,too_large,ignored,noise` (the clamp then fires only on `non-text`/`not_found`/`truncated`/`denied_secret`). Explicit-origin omissions clamp regardless | (default set above) |
| `LLM_COUNCIL_TIMEOUT_MULTIPLIER` | Verification global-deadline multiplier (ADR-040) | 2.0 |
| `LLM_COUNCIL_TRANSCRIPT_PATH` | Verification transcript root | .council/logs |

## Benchmark (ADR-048)

| Variable | Description | Default |
|---|---|---|
| `LLM_COUNCIL_BENCH_MAX_USD` | Bench per-run spend cap (ADR-048) | 2.00 |
| `LLM_COUNCIL_BENCH_MONTHLY_USD` | Bench month-to-date guard | 30.00 |
| `LLM_COUNCIL_BENCH_UNKNOWN_ITEM_USD` | Cap charge for unknown-cost items | 0.10 |

## MCP & serving

| Variable | Description | Default |
|---|---|---|
| `LLM_COUNCIL_API_TOKEN` | HTTP API bearer token | — |
| `LLM_COUNCIL_MCP_TASKS` | MCP Tasks kill-switch (ADR-045 P1) | enabled-when-supported |

## Caching

| Variable | Description | Default |
|---|---|---|
| `LLM_COUNCIL_PROMPT_CACHING` | Anthropic prompt-cache breakpoints + OpenRouter session affinity on the verify path (ADR-049 D2). Default ON — price-class-only change; set `false` to force byte-identical pre-D2 payloads | true |
| `LLM_COUNCIL_PROMPT_CACHE_TTL` | Prompt-cache TTL override: `5m` or `1h` (ADR-049 D5). Verify path defaults to `1h`, interactive paths to `5m`; invalid values fall back to the path default. Distinct from `LLM_COUNCIL_CACHE_TTL` (response cache, seconds) | per-path |
| `LLM_COUNCIL_LIVE_CACHE_PROBE` | Opt-in LIVE two-call cache probe test (~$0.05 real spend; never in CI) | false |
| `LLM_COUNCIL_CACHE` | Response cache | code |
| `LLM_COUNCIL_CACHE_DIR` | Cache directory | code |
| `LLM_COUNCIL_CACHE_TTL` | Cache TTL (s) | code |

## Observability

| Variable | Description | Default |
|---|---|---|
| `LLM_COUNCIL_METRICS_BACKEND` | none / statsd / prometheus | none |
| `LLM_COUNCIL_METRICS_ENABLED` | Metrics export (ADR-030) | false |
| `LLM_COUNCIL_STATSD_HOST` | StatsD host | localhost |
| `LLM_COUNCIL_STATSD_PORT` | StatsD port | 8125 |
| `LLM_COUNCIL_TELEMETRY` | Telemetry client | code |
| `LLM_COUNCIL_TELEMETRY_ENDPOINT` | Telemetry endpoint | code |

## PostHog LLM Analytics (ADR-050)

Opt-in emission of `$ai_generation` events to PostHog. Off by default — with no `POSTHOG_API_KEY` the emitter is disabled and behavior is byte-identical (the optional `posthog` SDK is never imported). Install with `pip install "llm-council-core[posthog]"`.

| Variable | Description | Default |
|---|---|---|
| `POSTHOG_API_KEY` | PostHog project API key (publishable `phc_` key). Presence enables emission | — (disabled) |
| `POSTHOG_HOST` | PostHog ingestion host. Use `https://us.i.posthog.com` for US Cloud | `https://eu.i.posthog.com` |

## Webhooks

| Variable | Description | Default |
|---|---|---|
| `LLM_COUNCIL_WEBHOOKS_ENABLED` | Webhook notifications (ADR-025) | false |
| `LLM_COUNCIL_WEBHOOK_RETRIES` | Webhook retry attempts | 3 |
| `LLM_COUNCIL_WEBHOOK_TIMEOUT` | Webhook POST timeout (s) | 5.0 |

## Local models

| Variable | Description | Default |
|---|---|---|
| `LLM_COUNCIL_OLLAMA_BASE_URL` | Ollama endpoint (ADR-025) | http://localhost:11434 |
| `LLM_COUNCIL_OLLAMA_TIMEOUT` | Ollama timeout (s) | 120.0 |

## Misc

| Variable | Description | Default |
|---|---|---|
| `LLM_COUNCIL_SUPPRESS_WARNINGS` | Suppress security warnings | false |
