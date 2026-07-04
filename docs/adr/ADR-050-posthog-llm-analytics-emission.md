# ADR-050: PostHog LLM Analytics Emission

**Status:** Implemented 2026-07-04 (v0.35.0, epic #472: D1 #473/PR #477, D2 #474/PR #478, D3 #475/PR #479, D4 #476/PR #480 — emission-only first cut. Part 4 feature-flag tier routing DEFERRED to a future ADR per Council rev-2. Rev 2 research: every external claim verified against primary PostHog docs — adversarial deep-research, 92 agents — plus empirical verification of the live receiving project via the PostHog MCP; one claim REFUTED and corrected, see "Research verification".)
**Date:** 2026-07-04
**Decision Makers:** llm-council maintainers (review requested)
**Proposed by:** epic-loop project (consumer hand-over — Chris / Claude; companion: ADR-049 rev 2, `epic-loop/docs/assessments/research-2026-07-04-headroom-context-compression.md`, `council-verify-stats.md`)
**Relates to:** ADR-011 (cost tracking), ADR-022 (tiered model selection), ADR-040/041 (verification timeout & telemetry wiring), ADR-047 (verifier calibration), ADR-049 (prompt caching across gateways — this ADR is the observability backend its part 4 gestures at)

---

## Context

llm-council's telemetry is local-only: `observability/usage_metrics.py`
computes per-call usage and cost, ADR-040/041 wired it into verification
records, and ADR-049 rev 2 established that OpenRouter's `usage.cost` is
billing ground truth with cache fields in `prompt_tokens_details`. But
none of it leaves the machine. Consequences, measured on the consumer
side:

- **Calibration is a hand-maintained markdown table.** epic-loop's
  `council-verify-stats.md` transcribes verdict/confidence/disposition
  per call by hand. The loop-improvements research (2026-07-04) ranked
  "ground-truth adjudication markers → TPR/FPR → the (TPR−FPR)²
  judge-adoption test" as a top-4 change; it has no queryable home.
- **ADR-049's guard has no backend.** Its telemetry part requires cache
  hit-rate observability per route — "a zero cache-read count across
  rounds is the diagnostic for a non-byte-stable prefix" — currently
  only visible by grepping logs.
- **Cost trends are invisible.** $0.4–1.1/verify at high tier × 1,170
  calls/month (June 2026), with no trend line, no per-PR rollup, no
  alerting on regressions.

The display side already exists (built 2026-07-04 via PostHog MCP, org
"Monstrous Media", EU instance): dedicated project **`amiable-llm-ops`**
(id 212129, API key `phc_rBfeomPEyZHU6SDVwuLsrnamoucnazMHnvVXH2cRsSnM`),
dashboard **"LLM Ops — cost, cache & volume"**
(<https://eu.posthog.com/project/212129/dashboard/793592>) with insights
for cost/day by model, cache hit-rate % (the ADR-049 guard), cost per
generation, generations by provider, and a daily spend-spike alert.
These tiles read PostHog's standard **`$ai_generation`** event schema
and sit empty until llm-council emits.

## Research verification (rev 2)

Two independent passes on 2026-07-04: an adversarial deep-research sweep
(92 agents, 3-vote verification) against primary PostHog docs, and
empirical checks against the live receiving project via the PostHog MCP.

### Compatibility surface — the `$ai_generation` schema

| Claim | Status | Evidence |
|---|---|---|
| `$ai_generation` is the current canonical event for one LLM call (distinct from `$ai_trace`/`$ai_span`/`$ai_embedding`) | **VERIFIED** | [generations](https://posthog.com/docs/llm-analytics/generations), [manual-capture](https://posthog.com/docs/llm-analytics/installation/manual-capture) |
| All 12 mapped property names exist with exactly those spellings (`$ai_trace_id`, `$ai_span_name`, `$ai_model`, `$ai_provider`, `$ai_input_tokens`, `$ai_output_tokens`, `$ai_cache_read_input_tokens`, `$ai_cache_creation_input_tokens`, `$ai_total_cost_usd`, `$ai_latency`, `$ai_input`, `$ai_output_choices`) | **VERIFIED** | [generations](https://posthog.com/docs/llm-analytics/generations) — output is `$ai_output_choices` (not bare `$ai_output`); `$ai_latency` in seconds; `$ai_cache_creation_input_tokens` labelled Anthropic-specific |
| The five dashboard tiles read `$ai_generation` + `$ai_total_cost_usd` / `$ai_provider` / `$ai_model` / `$ai_cache_read_input_tokens` / `$ai_input_tokens` | **VERIFIED (empirical)** | project 212129 dashboard 793592, live query definitions |
| Cost is auto-calculated from `$ai_model` + token counts (OpenRouter pricing, manual-DB fallback); `$ai_total_cost_usd` is **optional** and, when supplied, **overrides** the estimate | **VERIFIED** | [calculating-costs](https://posthog.com/docs/llm-analytics/calculating-costs) |

### SDK, privacy, key posture

| Claim | Status | Evidence |
|---|---|---|
| `posthog.capture(distinct_id, event="$ai_generation", properties={…})` is a first-class manual path, independent of any LangChain/OpenAI wrapper | **VERIFIED** | [manual-capture](https://posthog.com/docs/llm-analytics/installation/manual-capture) |
| `capture()` is non-blocking + batched by default (background consumer, `flush_at=100`, `flush_interval=0.5s`, `max_queue_size=10000`); call `shutdown()` on exit to flush; `sync_mode=True` forces synchronous send | **VERIFIED** | [posthog-python reference](https://posthog.com/docs/references/posthog-python) |
| `privacy_mode=True` omits `$ai_input`/`$ai_output_choices`; for manual capture, simply not setting them is equivalent. PostHog also purges large `$ai_` properties after 30 days | **VERIFIED** | [privacy-mode](https://posthog.com/docs/llm-analytics/privacy-mode) |
| `phc_`-prefixed project key is write-only / publishable (safe to commit); the secret key is the personal API key (`phx_`). EU ingestion host is `https://eu.i.posthog.com` (the `.i.` endpoint; `eu.posthog.com` is the app/private host). EU-hosted data stays in the EU region | **VERIFIED** | [api overview](https://posthog.com/docs/api) |
| `posthog.evaluate_flags(distinct_id).get_flag(key)` returns the variant string, or **`None`** when the flag isn't returned (network error/timeout) — fail-safe. `feature_flag_request_timeout_ms` bounds the request; local evaluation avoids per-call latency but requires a **secret personal API key** | **VERIFIED** | [libraries/python](https://posthog.com/docs/libraries/python) |

### The one refutation — retroactive scoring (Part 3)

| Claim (as drafted in rev 1) | Status | Evidence |
|---|---|---|
| "Post a PostHog **evaluation/score** onto a trace by `verification_id`" | **REFUTED as written** | PostHog **Evaluations** are automated LLM-as-a-judge run at sample time on generations, linked to the source event — not a sink for a human disposition posted after the fact ([evaluations](https://posthog.com/docs/llm-analytics/evaluations)) |
| Retroactive scoring by `$ai_trace_id` is nonetheless achievable | **VERIFIED (empirical)** — two native paths | (a) **Trace Reviews** + a **Categorical Scorer** (`real`/`marginal`/`refuted`/`pass-clean`), one review per trace ([trace-reviews](https://posthog.com/docs/ai-observability/trace-reviews)); (b) a **follow-up event** carrying the same `$ai_trace_id` — `$ai_metric` (trace_id + name + value) or `$ai_feedback` — which PostHog joins into the trace ([user-feedback manual-capture](https://posthog.com/docs/ai-observability/user-feedback/manual-event-capture)) |

Part 3 below is rewritten to use these mechanisms instead of the
Evaluations product.

### Empirical state of the receiving project (212129, 2026-07-04)

Verified live: the `amiable-llm-ops` project and its `phc_` token exist
(`ingested_event: false` — nothing has landed); dashboard 793592 with all
five tiles and the daily spend-spike alert (absolute > $25/day) exist; a
**second producer shares the `$ai_generation` contract** — the official
[Claude Code PostHog plugin](https://posthog.com/docs/ai-observability/installation/claude-code)
(`POSTHOG_LLMA_CC_ENABLED`). The `council-tier-sampling` feature flag
(Part 4) **does not exist yet** — the project has zero flags — so the ADR
*defines* the name; it does not describe an existing flag.

### Caveats

- Single authoritative vendor source (posthog.com). The AI product docs
  alternate between `/docs/ai-observability/*` and `/docs/llm-analytics/*`
  URL namespaces (identical content, no property renames) — re-verify
  links before publishing.
- PostHog's cost auto-calc has open bugs on the OTel path that drop cache
  and reasoning tokens ([posthog#63136](https://github.com/PostHog/posthog/issues/63136)).
  This is a further reason to emit our own ground-truth `$ai_total_cost_usd`
  (ADR-011 `cost_resolver`) rather than rely on PostHog's derivation for
  cache-heavy verify workloads.

### Council review (rev 2, high tier)

The Council reviewed the revised design (3/4 models; gpt-5.4 errored —
infra, not content). It endorsed the two central calls — the gateway as
the single `$ai_generation` choke point, and overriding PostHog's cost
auto-calc with ADR-011 ground truth — and raised four findings, all
folded in above:

1. **Token math** → clamp `$ai_input_tokens = max(0, prompt − cache_read)`
   (negative counts on already-exclusive routes / `cached > prompt`).
2. **Adjudication encoding** → send a numeric `metric_value` **and** a
   text `adjudication_label`; the exact `$ai_metric` value-type and
   trace-vs-generation scope are flagged as verify-before-implementation
   (the council's "numeric-only" assertion is plausible but is NOT
   confirmed by public docs — treated as unverified, per house rigor).
3. **Feature flags** → Part 4 **deferred** to its own ADR (a blocking
   flag read on the tier path violates the observability-only thesis).
4. **Privacy** → opaque `consumer`, opaque/salted `subject_sha`,
   exception-message scrubbing, explicit flush lifecycle.

Net scope after review: a two-part first cut — emit `$ai_generation`
(Part 1) content-free (Part 2), with the adjudication contract (Part 3)
as the cross-repo hook; feature-flag routing (Part 4) leaves this ADR.

## Decision (proposed)

Add an opt-in PostHog LLM Analytics emitter to the gateway layer. After
Council review the scope is **emission-only** — three active parts plus
configuration; the feature-flag routing part is deferred (see Part 4):

### 1. `$ai_generation` emission per member call

Emit one `$ai_generation` event per council-member model call, from the
same code path that already assembles `input_metrics` (post-response in
the gateway routers). Standard properties, mapped from data we already
hold:

| PostHog property | Source |
|---|---|
| `$ai_trace_id` | **`verification_id`** — the existing per-verify ID (e.g. `b10ca705`). This is the cross-repo contract: consumers post evaluations against the same ID. |
| `$ai_span_name` | `round:{n}/member:{model}` |
| `$ai_model`, `$ai_provider` | registry id + gateway route name |
| `$ai_input_tokens`, `$ai_output_tokens` | existing `input_metrics` / `output_metrics` |
| `$ai_cache_read_input_tokens`, `$ai_cache_creation_input_tokens` | ADR-049 D4 `cached_tokens` / `cache_write_tokens` (OpenRouter `prompt_tokens_details`) or Anthropic-native fields. `$ai_cache_creation_input_tokens` is Anthropic-specific (0 elsewhere). |
| `$ai_total_cost_usd` | `usage.cost` (OpenRouter ground truth) or ADR-011 `cost_resolver` output on direct routes. **Optional but supplied**: PostHog auto-derives cost from model+tokens, but we override with our ground truth (it includes the real cache discount, and PostHog's OTel cost path has open cache/reasoning-token bugs). |
| `$ai_latency` | existing call timing (seconds) |
| custom: `tier`, `route`, `round`, `subject_sha`, `consumer` | verification context |

**`$ai_input_tokens` cache-subtraction rule (mandatory).** PostHog's
cost engine and the dashboard hit-rate tile (`cache_read / (cache_read +
input)`) assume **exclusive** counting — cache-read tokens are NOT part
of `$ai_input_tokens` ([calculating-costs](https://posthog.com/docs/llm-analytics/calculating-costs):
Anthropic exclusive, OpenAI/most inclusive). Because we route Anthropic
via OpenRouter, the emitter MUST map `$ai_input_tokens` to the
**non-cached** input count and put cache reads only in
`$ai_cache_read_input_tokens`. Emitting the raw `prompt_tokens` would
double-count the denominator and understate the hit rate — the exact
regression this dashboard exists to catch. **Clamp the subtraction**:
`$ai_input_tokens = max(0, prompt_tokens − cache_read_tokens)` — a route
that already reports exclusively, or a `cached > prompt` reporting
anomaly, must never yield a negative token count (Council rev-2 finding).

**`$ai_trace_id` charset.** PostHog restricts it to letters, digits, and
`- _ ~ . @ ( ) ! ' : |`. Our `verification_id` (hex) and `verify:{sha}`
session keys satisfy this; a raw file path would not.

Transport: the `posthog` Python SDK — `capture()` is non-blocking and
batched by default (background consumer, `flush_at=100`,
`flush_interval=0.5s`). **Emission failures must never fail or delay a
verification** (wrap in soft-fail, ADR-011/024 convention).

**Flush lifecycle (Council rev-2):** the background-consumer batch model
means a short-lived `llm-council gate`/CLI run can exit before the queue
flushes. Register an explicit `shutdown()` (atexit + an explicit call in
the gate/CLI teardown), bounded by a short timeout so flushing never
hangs the process; a serverless/one-shot host should prefer
`sync_mode=True` or a bounded `flush()` at the end of the request rather
than trusting atexit. Dropped events are acceptable (soft-fail), a hung
process is not.

### 2. Privacy default: content-free

`$ai_input` and `$ai_output_choices` are **omitted by default**
(privacy-mode semantics). Council prompts contain customer code and
diffs; metadata, tokens, and cost carry all the analytical value listed
above. A `POSTHOG_LLMA_CONTENT=1` escape hatch may be added later behind
an explicit maintainer decision — it is out of scope here.

**Residual-leakage rules for the metadata that IS sent** (Council rev-2):
- `consumer` must be an opaque identifier, never an email/account id.
- `subject_sha` is a commit/target-path digest — treat it as an opaque
  fingerprint; do not additionally emit raw file paths or repo names as
  properties, and prefer a salted digest if the path set itself is
  sensitive (it can otherwise be confirmed by dictionary attack).
- The soft-fail path must **scrub exception messages** before they touch
  any property or log — provider/gateway errors sometimes echo the prompt.
- Model names and `tier`/`route`/`round` are non-sensitive and stay.

### 3. Adjudication scores on traces (revised — see Research verification)

**Not** PostHog's Evaluations product: that runs automated LLM-as-a-judge
at sample time and links the result to the source generation; it is not a
sink for a human disposition posted after the fact (REFUTED in rev 2).
Retroactive scoring keyed to `$ai_trace_id` is instead done one of two
documented ways, and this ADR fixes the contract for both:

- **Programmatic (epic-loop retro):** emit a follow-up **`$ai_metric`**
  event carrying the same `$ai_trace_id = verification_id`, with
  `metric_name: "adjudication"`. Encode the disposition **both** ways
  (Council rev-2 finding): a numeric `metric_value` (`real=1.0`,
  `marginal=0.5`, `refuted=0.0`, `pass-clean=1.0`) so TPR/FPR renders as
  a trend, **and** a text `adjudication_label` custom property carrying
  the raw category. A small helper (CLI or library function) wraps this;
  epic-loop's retro calls it once per human adjudication, replacing the
  hand-maintained stats table. **To confirm before implementation** (the
  public docs don't pin these): `$ai_metric`'s value type, and whether a
  metric keyed to `$ai_trace_id` renders trace-scoped or generation-
  scoped — verify empirically against the live project (the follow-up-
  event-by-trace_id join itself IS documented via the user-feedback path,
  so the fallback is a plain custom event carrying `$ai_trace_id`).
- **Manual (ad-hoc):** PostHog **Trace Reviews** with a **Categorical
  Scorer** (`real`/`marginal`/`refuted`/`pass-clean`) — one review per
  trace, in the AI-Evals UI, when a human wants to inspect and label a
  specific trace.

(Consumer side is one small ticket; the event contract — `$ai_metric`
name + value vocabulary keyed to `verification_id` — lives here.)

### 4. Feature-flag read for tier selection — DEFERRED (Council rev-2)

**Deferred out of this ADR to a separate proposal.** Reading a PostHog
feature flag in the tier-selection path (ADR-022) to drive a cheap-tier
multi-sampling A/B introduces a **synchronous, blocking hop on the
critical path** — which contradicts this ADR's core thesis (an
observability-only, soft-fail, never-delays-a-verify emitter) and quietly
turns it into an application-routing layer. Those are different risk
profiles and deserve their own ADR (latency budget, fail-open semantics,
local-evaluation posture with its secret personal API key, experiment
design).

Reserved here so the name doesn't drift: flag key **`council-tier-sampling`**
(verified 2026-07-04 as not yet created — 0 flags in the receiving
project). The verified mechanism for the future ADR:
`posthog.evaluate_flags(distinct_id).get_flag("council-tier-sampling")`
returns the variant string or `None` on missing-flag/network-error
(fail-safe → `control`), bounded by `feature_flag_request_timeout_ms`.
Emission (Parts 1–3) does not depend on this and ships without it.

### 5. Configuration

Opt-in and off by default (OSS posture): `POSTHOG_API_KEY` +
`POSTHOG_HOST` enable emission; absent keys mean zero behavior change.
Document in the deployment guide. Amiable's own values: the
`amiable-llm-ops` project key above (a `phc_` key — write-only and
publishable, verified safe to commit, so it may ship as the documented
default), EU ingestion host **`https://eu.i.posthog.com`** (the `.i.`
endpoint — `eu.posthog.com` is the app/private host and is wrong for
capture; the SDK maps app hosts to ingestion hosts but be explicit).
EU-hosted data stays in the EU region. The `council-tier-sampling` flag
read (Part 4) needs only the same project key for the network path; the
personal-key local-evaluation path is out of scope here.

## Consequences

**Positive.** Cost per verify/PR/model becomes a trend with an alert
instead of a grep; the ADR-049 cache guard gets its dashboard (hit-rate
drop = byte-stability regression caught within a day); Council
calibration becomes computable (TPR/FPR, judge-adoption test) from
durable data; the tier A/B runs on real experiment infrastructure; all
of it lands in dashboards that already exist.

**Negative / cost.** A new optional dependency (`posthog` SDK) and a new
egress path (metadata to PostHog EU) that must be documented for OSS
users; the property mapping becomes a compatibility surface (PostHog's
`$ai_*` schema evolves — pinned by the Part-1 golden test). Emission is
soft-fail and off the hot path, so it adds no runtime dependency to
verification itself. (Tier-selection flag reads, which *would* add a
critical-path dependency, are deferred to a separate ADR — Part 4.)

**Neutral.** With no API key configured, behavior is byte-identical to
today. Emission is additive to — not a replacement for — the local
telemetry ADR-040/041 established.

## Compliance / Validation

- Unit: property mapping golden test (given a gateway response fixture,
  the emitted event carries the exact `$ai_*` fields above; content
  fields absent).
- Unit: emitter failure (network down, bad key) does not raise into the
  verification path.
- Unit: `$ai_input_tokens` cache-subtraction — given a cached-round usage
  fixture (Anthropic via OpenRouter), the emitted `$ai_input_tokens`
  excludes cache-read tokens and `$ai_cache_read_input_tokens` carries
  them, so `cache_read / (cache_read + input)` computes the true hit rate.
- Integration: one real `verify()` with a test key → trace visible via
  PostHog `query-llm-traces-list` with `$ai_trace_id == verification_id`;
  cache fields non-zero on a cached second round (ties to ADR-049's
  integration test). Also confirm a manual-capture `$ai_generation`
  renders in the traces UI (set `$ai_trace_id`; `$ai_span_id` optional).
- Consumer: epic-loop retro emits an `$ai_metric` (`adjudication` =
  `real`/`marginal`/`refuted`/`pass-clean`) keyed to the same
  `$ai_trace_id`, and it joins onto the trace and is queryable for
  TPR/FPR — NOT via the automated Evaluations product (rev 2 refutation).

## References (primary sources, checked 2026-07-04)

- Generations schema + property table — <https://posthog.com/docs/llm-analytics/generations>
- Manual capture (Python `capture()` of `$ai_generation`) — <https://posthog.com/docs/llm-analytics/installation/manual-capture>
- Cost calculation + cache-token counting conventions — <https://posthog.com/docs/llm-analytics/calculating-costs>
- Privacy mode (`$ai_input`/`$ai_output_choices` omission) — <https://posthog.com/docs/llm-analytics/privacy-mode>
- Python SDK reference (batching, `shutdown()`, `sync_mode`, `evaluate_flags`) — <https://posthog.com/docs/references/posthog-python>, <https://posthog.com/docs/libraries/python>
- Trace Reviews + Categorical Scorers — <https://posthog.com/docs/ai-observability/trace-reviews>
- User-feedback manual capture (follow-up events keyed to `$ai_trace_id`) — <https://posthog.com/docs/ai-observability/user-feedback/manual-event-capture>
- Evaluations (automated LLM-judge — refutes retroactive scoring) — <https://posthog.com/docs/llm-analytics/evaluations>
- API keys / posture (project `phc_` vs personal, EU hosts) — <https://posthog.com/docs/api>
- Claude Code producer sharing the `$ai_generation` contract — <https://posthog.com/docs/ai-observability/installation/claude-code>
- Cost auto-calc OTel cache/reasoning-drop bug — <https://github.com/PostHog/posthog/issues/63136>
- Empirical: live receiving project 212129 + dashboard 793592 (PostHog MCP, 2026-07-04)
