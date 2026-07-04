# ADR-049: Prompt Caching Across Gateways

**Status:** Proposed 2026-07-04 (rev 2: research matrix verified — vendor docs via adversarial deep-research + empirical two-call probes on our own OpenRouter key; codebase claims audited against source)
**Date:** 2026-07-04
**Decision Makers:** llm-council maintainers (review requested)
**Proposed by:** epic-loop project (consumer hand-over — Chris / Claude; companion evidence in `epic-loop/docs/assessments/research-2026-07-04-headroom-context-compression.md` and `council-verify-stats.md`)
**Relates to:** ADR-011 (cost tracking), ADR-023 (multi-router gateway support), ADR-024 (unified routing architecture), ADR-026 (reasoning-params injection precedent), ADR-040/041 (verification telemetry), ADR-042 (verify evidence injection)

---

## Context

llm-council makes no use of provider-side prompt caching: no `cache_control`
(or any provider cache directive) appears anywhere in the source, and the
production telemetry proves the consequence — across ~15 real verification
runs on 2026-07-03, `input_metrics.cached_tokens` was **0 on every call but
one** (a stray 128). Every council call pays full input price on every
token, every round.

> Correction from rev 1: the client layer is **httpx**, not
> `litellm.acompletion` — `openrouter.py` and the gateway routers
> (`gateway/openrouter.py`, `direct.py`, `requesty.py`) build requests via
> the shared `build_openrouter_payload()`; LiteLLM is used only on the
> Ollama path. This matters because the implementation point is our own
> payload builder, not a LiteLLM pass-through.

Two codebase facts make the current state *maximally* cache-hostile:

1. **The verification prompt opens with the snapshot SHA**
   (`You are reviewing code at commit \`{snapshot_id}\`.` —
   `verification/api.py::_build_verification_prompt`). Every round verifies
   a new post-fix commit, so the **first bytes of the prompt differ every
   round**, invalidating any exact-prefix cache from byte zero.
2. **The stable content is at the wrong end.** The round-invariant
   instructions/rubric block renders *last*; the volatile subject content
   renders early. Even providers with automatic caching can find no shared
   prefix to reuse.

The consumer-side evidence says this leaves real money on the table. The
epic-loop calibration log (`council-verify-stats.md`) shows the dominant
usage pattern: **multi-round `verify()` on the same PR** (r1→r4 observed on
PR #76), at $0.4–1.1 per call at `high` tier, 1,170 calls in June 2026.
This repo's own 2026-07-03 session ran ~15 rounds at $0.09–0.15 each
(balanced tier, 25–63K prompt tokens per call).

> Correction from rev 1: across rounds the **subject content is not
> byte-identical** — each round verifies a *new* commit (house discipline
> forbids re-verifying the same SHA). The truly round-invariant content is
> the instructions + rubric + (usually) ADR-042 evidence; file content is
> *mostly* stable but byte-shifts at the first fixed line. Savings
> estimates must be based on the stable head, not the whole prompt —
> which is why part 1's ordering and breakpoint placement matter more
> than any single knob.

**Decisive empirical result (2026-07-04, our OpenRouter key, two-call
probes, ~$0.20 total):**

| Probe (via OpenRouter) | Call 1 | Call 2 (same prompt, +3–4s) |
|---|---|---|
| `anthropic/claude-haiku-4.5` **with** `cache_control` | `cache_write_tokens: 36008`, cost **$0.045041** | `cached_tokens: 36008`, cost **$0.0036318** (**−92%**) |
| `anthropic/claude-haiku-4.5` **without** directive | cost $0.036039, no cache fields | identical — full price |
| `openai/gpt-4o-mini` (automatic expected) | `cached_tokens: 0` | `cached_tokens: 0`, same cost |
| `google/gemini-2.5-flash` and `-flash-lite` | no cache fields | identical cost |
| `deepseek/deepseek-chat` | no cache fields | identical cost |

Three conclusions: (a) Anthropic explicit caching through OpenRouter works
end-to-end **today** — directive forwarded, 1.25× write premium and 0.1×
read visible to the cent in `usage.cost` (the field our ADR-011 pipeline
already treats as billing ground truth), fields reported in
`prompt_tokens_details`, on OpenRouter's pooled key (`is_byok: false`);
(b) the directive is **required** on that route — nothing is cached without
it; (c) the "it's automatic elsewhere" belief is **refuted through
OpenRouter** as of today — OpenAI/Gemini/DeepSeek showed zero cache
activity on identical 27–35K-token prompts seconds apart.

## Decision (proposed)

Adopt provider-aware prompt caching in the gateway layer, in five parts:

### 1. Prompt-assembly invariant: stable-prefix-first

Restructure council prompt assembly into ordered stability segments:

1. **Static head** — role, instructions, rubric, focus. Identical across
   rounds AND across subjects.
2. **Evidence** (ADR-042) — stable within a round sequence when evidence is
   re-passed; changes between rounds only if the consumer updates it.
3. **Subject** — file contents; mostly stable across rounds but byte-shifts
   at the first fixed line. Order multi-file content stable-files-first.
4. **Volatile tail** — snapshot SHA, round number, prior-round dispositions,
   timestamps. **The SHA moves from the first line to here.**

Enforce deterministic serialization (sorted keys, no timestamps/UUIDs
above the tail). This is the universal precondition for every vendor's
caching, explicit or implicit, and is free on providers with none.

**Minimum-prefix caveat (verified):** Anthropic silently caches nothing
below a per-model minimum — 1,024 tokens for Opus 4.8/Sonnet 5, **4,096
for Haiku 4.5**, 512 for Fable 5 — with both cache fields reporting 0. The
static head alone (~500 tokens) does NOT clear the bar; the head+evidence
segment usually does. Breakpoint placement must respect this or hits will
silently be zero.

### 2. Capability modeling — per route, with verified values

Extend `RouterCapabilities` (`gateway/base.py`) with a caching descriptor:

```python
caching: CachingCapability
#   semantics: "explicit" | "explicit_auto" | "router_flag" | "implicit" | "none"
#   directive: "anthropic_cache_control" | "requesty_auto_cache" | None
#   billing_passthrough: bool | None   # None = unverified
#   usage_fields: "openrouter_normalized" | "anthropic_native" | "openai_details" | None
```

Verified per-route values (see matrix):

| Route | semantics | directive | billing pass-through | usage fields |
|---|---|---|---|---|
| OpenRouter → anthropic/* | explicit | `cache_control` blocks (≤4 breakpoints, `ttl:"1h"` supported) | **verified** (in `usage.cost`) | `prompt_tokens_details.{cache_write_tokens, cached_tokens}` (empirical) |
| OpenRouter → other vendors | none (as tested 2026-07-04) | — | n/a | fields present, always 0 in probes |
| Direct Anthropic | explicit + optional automatic (top-level `cache_control`, uses 1 of 4 slots) | `cache_control` | n/a (direct) | `cache_creation_input_tokens` (+ per-TTL sub-object), `cache_read_input_tokens` |
| Requesty | router_flag | `requesty.auto_cache: true` (router injects breakpoints for Anthropic/Gemini) | documented "up to 90%", rates unpublished | undocumented |
| Direct OpenAI | implicit (≥1,024 tokens, 128-token increments) | none | n/a | `prompt_tokens_details.cached_tokens` |
| Ollama / local | none (KV reuse = latency only) | — | no billing dimension | — |

**v1 implementation point:** `build_openrouter_payload()` — the single
shared payload builder — injects `cache_control` for `anthropic/*` models
exactly the way ADR-026 injects reasoning params (metadata capability check
→ payload mutation). No new router machinery is required to capture the
verified 92% on the production route; the descriptor generalizes it to
direct/Requesty routes later.

### 3. Cost-model extension (amends ADR-011)

**Correction from rev 1:** on OpenRouter/Requesty the provider-reported
`usage.cost` is ADR-011's ground truth and **already includes the cache
discount** (verified to the cent in the probe) — enabling caching cannot
misreport spend on those routes. The gap is only the **registry-estimate
path** (Direct APIs): add optional `cache_read` / `cache_write_5m` /
`cache_write_1h` per-1K prices to `models/registry.yaml` and teach
`cost_resolver.py` to price the provider cache token fields. Unknown cache
prices default to the `prompt` price (conservative over-estimate, never
under-reported) — consistent with `cost_known` semantics.

### 4. Telemetry (amends ADR-040/041)

**Correction from rev 1:** cache-read telemetry already exists end-to-end —
`openrouter.py::_extract_cached_tokens` reads
`prompt_tokens_details.cached_tokens`, ADR-011 aggregation carries
`cached_tokens` per stage/model/total, and verify `input_metrics` exposes it
(that is how we know production is at zero). What is missing:

- capture **`cache_write_tokens`** (OpenRouter) /
  `cache_creation_input_tokens` (+ per-TTL sub-object) (Anthropic direct);
- record the **route and `session_id`** that served each call;
- surface both in verify `input_metrics` and the ADR-011 usage block, so a
  consumer can reconstruct hit-rate per PR from logs alone. A zero
  cache-read count across rounds is the diagnostic for a broken prefix or
  lapsed TTL — telemetry is the guard, not code review.

### 5. TTL / stickiness policy — resolved

**TTL (policy question B, resolved):** Anthropic publishes the break-even —
5-min write (1.25×) pays for itself after **one** read; 1-hour write (2×)
after **two** reads; the 5-min cache refreshes free on every use. Observed
verification cadence (this repo, 2026-07-03: gaps of 3–11 minutes between
rounds; epic-loop fix cycles similar) straddles the 5-minute boundary, and a
lapsed 5-min cache pays the write premium again every round.
**Recommendation:** `ttl:"1h"` for verification flows (config default for
the verify path), 5-min default for `consult_council`/interactive use.
Config knob: `LLM_COUNCIL_CACHE_TTL` (`5m` | `1h`), verify path defaulting
to `1h`.

**Stickiness (policy question A, resolved):** OpenRouter itself ships
**provider sticky routing keyed on `session_id`** (request body or
`x-session-id` header), designed precisely to preserve cache warmth across
its upstream pool. Adopt it: pass `session_id = <verification subject key>`
(e.g. PR/subject identifier) on verify-path calls. This delegates
stickiness to the router, adds no state to our selection policy, and —
resolving the resilience concern — **never overrides circuit state**: our
circuit breaker and fallback chains behave exactly as today; a failover
simply lands on a cold cache, costing at most one extra cache-write premium
(bounded, ~25% of one prompt) against availability. Homegrown
route-stickiness in `router.py` is **deferred** — the default deployment is
single-gateway, where it is a no-op.

## Research matrix — verified 2026-07-04

Method: primary vendor documentation via adversarial multi-agent research
(claims retained only after 3-vote verification), plus empirical two-call
probes through our own OpenRouter key where we hold credentials. Statuses:
✅ VERIFIED (cited/observed) · ❌ REFUTED (as tested) · ◻ UNDOCUMENTED.

| Vendor / route | Status | Finding | Source |
|---|---|---|---|
| Anthropic direct — mechanics | ✅ | 0.1× read / 1.25× 5-min write / 2× 1-h write, multipliers exact across the current model table; TTL refresh-on-use free; ≤4 breakpoints; NEW optional automatic mode (top-level `cache_control`, consumes one slot); exact-prefix match; org-scoped, workspace-isolated since 2026-02-05 (Claude API/AWS/Foundry) | platform.claude.com/docs/en/build-with-claude/prompt-caching; …/about-claude/pricing (checked 2026-07-04) |
| Anthropic direct — minimums | ✅ | Per-model minimum cacheable prefix: Fable 5/Mythos 5 512; Opus 4.8/Sonnet 5 1,024; **Haiku 4.5 4,096**; below-minimum silently uncached (fields report 0) | same |
| Anthropic direct — usage fields | ✅ | `cache_creation_input_tokens` (+ `cache_creation.{ephemeral_5m,ephemeral_1h}_input_tokens`), `cache_read_input_tokens`; `input_tokens` = uncached remainder | same |
| **Claude via OpenRouter** | ✅ **(docs + empirical)** | `cache_control` forwarded (≤4 breakpoints, `ttl:"1h"`); Anthropic multipliers passed through billing — observed: write $0.045 = 1.25× base $0.036, read −92%; fields `prompt_tokens_details.{cache_write_tokens, cached_tokens}` (empirical — OpenRouter docs don't name them); works on pooled key (`is_byok:false`); **directive REQUIRED — no directive ⇒ zero caching (empirical)** | openrouter.ai/docs/guides/best-practices/prompt-caching + two-call probe 2026-07-04 |
| OpenRouter sticky routing | ✅ | Provider sticky routing after a cached request; explicit `session_id` (body or `x-session-id`, ≤256 chars) controls affinity — the router-native answer to cache-aware stickiness | openrouter.ai docs (checked 2026-07-04) |
| OpenAI via OpenRouter | ❌ (as tested) | Identical 27.6K-token prompt twice, 4s apart: `cached_tokens: 0`, identical cost — automatic caching did not apply or was not passed through | two-call probe 2026-07-04 |
| OpenAI direct | ✅ (docs) | Fully automatic ≥1,024 tokens, hits in 128-token increments, `usage.prompt_tokens_details.cached_tokens`; **no fixed discount ratio published** — per-model cached-input prices on the pricing page ("up to 90%" input-cost reduction) | developers.openai.com/api/docs/guides/prompt-caching (checked 2026-07-04) |
| Gemini via OpenRouter | ❌ (as tested) | 2.5-flash and flash-lite: no discount, no cache fields on identical repeat | two-call probe 2026-07-04 |
| Gemini direct (implicit + explicit context caching) | ◻ | Docs cells did not survive adversarial verification (rates/models/fields unresolved); no direct key held to probe | unresolved 2026-07-04 |
| DeepSeek via OpenRouter | ❌ (as tested) | No cache fields, identical cost (OpenRouter may serve deepseek/* from non-DeepSeek hosts) | two-call probe 2026-07-04 |
| DeepSeek direct | ◻ | Disk-cache hit/miss pricing not verified; no direct key held | unresolved 2026-07-04 |
| Requesty | ✅ (docs) | `requesty.auto_cache: true` — router injects breakpoints (Anthropic/Gemini); "up to 90% savings"; exact rates & usage fields unpublished; no key held to probe | docs.requesty.ai/features/auto-caching (checked 2026-07-04) |
| LiteLLM (Ollama path only) | ✅ (docs) | Passes `cache_control` for 7 named providers; OpenAI stays automatic; **nothing documented for Ollama** — irrelevant to caching economics (local, no billing) | docs.litellm.ai/docs/completion/prompt_caching (checked 2026-07-04) |
| Ollama / local | ✅ (nature of the thing) | KV/prefix reuse is a latency win only; no billing dimension; stable-prefix ordering helps for free | — |

## Consequences

**Positive.** On the production route (OpenRouter), Anthropic council
members get a **verified 92% discount on the cached segment** of every
repeat call within TTL — the largest available cost lever that does not
touch council quality (content unchanged; only its price class). The
stable-prefix restructure also improves determinism and makes prompt diffs
reviewable. Bench matrix runs (same 20 items × several configs, minutes
apart) get full-prompt cache hits per model essentially free.

**Honest scoping.** Only the Anthropic members benefit today via OpenRouter
(typically 1–2 of 4 council seats + the chairman when Anthropic); the
across-round win covers the stable head + evidence + unshifted file bytes,
not the whole prompt. OpenAI/Gemini/DeepSeek routes gain nothing until the
❌/◻ cells change — the descriptor defaults them to `none`, and re-probing
them is a one-script check (the two-call probe pattern) worth re-running
quarterly.

**Negative / cost.** Registry grows cache price classes (direct path only);
routes gain a capability axis to keep accurate; a byte-stability regression
(a stray timestamp above the tail) silently degrades to full price —
telemetry (part 4) is the guard. The 1-hour TTL doubles the write premium
when a sequence ends after one round (bounded loss: 0.75× of one cached
segment).

**Neutral.** Routes with `semantics: none` are unaffected; the assembly
invariant is harmless everywhere.

## Compliance / Validation

- Unit: assembled prompts for rounds r1/r2 of the same subject are
  byte-identical through the declared segment boundaries (golden-file
  test); the SHA and all volatile fields appear only in the tail segment.
- Unit: breakpoint placement respects per-model minimum cacheable prefix
  (no breakpoint marking a segment below the model's minimum).
- Integration (per caching-capable route, opt-in/live): two back-to-back
  calls; assert call 2 reports cache-read tokens > 0 and `usage.cost`
  reflects the discount (the 2026-07-04 probe is the template).
- Cost: `cost_resolver` golden tests for hit, miss, write-5m, write-1h,
  and unknown-cache-price-defaults-to-prompt-price paths (direct route).
- Telemetry: verify `input_metrics` and the ADR-011 usage block expose
  cache read + write tokens and the serving route/session; hit-rate per PR
  reconstructable from logs alone.
