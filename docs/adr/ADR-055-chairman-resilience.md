# ADR-055: Chairman Resilience — Dynamic Fallback for Stage-3 Synthesis

**Status:** Proposed 2026-08-27 — **rev 2** after council review. Review requested.
**Date:** 2026-08-27
**Decision Makers:** llm-council maintainers
**Proposed by:** [#598](https://github.com/amiable-dev/llm-council/issues/598), which is explicit that this needs an ADR before code: it changes deliberation behaviour and cost, and every other resilience mechanism in this repo got one first.
**Relates to:** ADR-012 (MCP reliability), ADR-022 (tier contracts / aggregators), ADR-024 (layer sovereignty, auditable escalation), ADR-027 (frontier hard fallback — the member-level precedent), ADR-030 (circuit breaker), ADR-042 (evidence), ADR-049 (prompt caching), ADR-051 (mechanical gate), ADR-054 (confidence semantics)
**Tracking:** [#598](https://github.com/amiable-dev/llm-council/issues/598)

**Review history:**

- **rev 2** — council review of rev 1 (`verify`, tier=high, structured findings, snapshot `89a3c55a`, **fail** @ 0.86, 4 critical / 8 major / 3 minor, `verification_id` `66ab5ebf`). The review confirmed rev 1's code facts (accuracy 10.0/10) and rejected it on **decision consistency**, which was the right call. All four criticals accepted and fixed; the most consequential change is structural rather than editorial. Rev 1 made `tier_contract.aggregator_model` the *primary* chairman source, which (a) required detecting whether `council.chairman` was "explicitly set" — undetectable, because `unified_config.py:763` gives it a non-`None` default of `anthropic/claude-opus-5`, so a merged config cannot distinguish operator intent from the shipped default — and (b) coupled a MINOR-release model-selection change to a resilience feature. **Rev 2 leaves the primary chairman untouched** and uses `aggregator_model` only as a fallback candidate, which dissolves both problems and the back-compat claim rev 1 could not support. Also accepted: D4's budget rule said "floored" where it meant capped (making the per-model timeout a *lower* bound that extended the very deadline D4 promised not to extend); the one-attempt guarantee was unenforceable across two wiring sites; D2's chain had no defined terminus and collapsed to no candidate at `quick` and for `frontier`→`reasoning` (both map to `claude-opus-5`); D3 forced verdict-derivation and synthesis-provenance into one enum. Rev 1's self-contradiction on member promotion (rejected in D2, reserved in Alternatives) is resolved. **Meta:** three of the four criticals were internal contradictions between sections written minutes apart — the failure mode a single author is worst-placed to catch, which is the case for this review step existing.
- **rev 1** — initial draft.

---

## Context

The council degrades gracefully everywhere except the one place it matters most.

Stages 1 and 2 are N parallel calls whose slow tail is absorbed by design: a
member that times out is dropped, the run continues on whoever answered, and
only an all-member failure fails the request. **Stage 3 is one serial call to
one configured model with no redundancy and no retry.** If it errors or times
out, a run in which every member responded and every reviewer ranked cleanly
produces no verdict at all.

The most important single call in the pipeline is the least redundant one.

### Evidence

**The 2026-07-16 window** (#594/#596/#597): ~1 hour, 4 consecutive verify runs
lost to chairman timeout/error while peer review completed cleanly every time.

**A v0.45.1 field report** (#660): a `high`-tier `consult_council` run lost 2 of
4 models to timeout, one of them `anthropic/claude-opus-5` — which is *both* a
`high`-pool council member and the configured chairman. The user received one
surviving member's raw text under a heading claiming a chairman synthesis.
#660 fixed the *presentation* of that outcome. It did nothing about the outcome.

That report also supplies the observation this ADR has to design around:

> The models that time out are the slowest, which are generally the strongest
> reasoners. So a partial result does not sample the council randomly: it
> systematically over-weights the faster, weaker members.

The corollary for stage 3 is worse than for stage 1. A *member* dropping out
costs one vote out of N. The *chairman* dropping out costs the entire
aggregation step — and the chairman is chosen for capability, which is
correlated with latency, which is what makes it likely to be the one that
drops out.

### A related config defect, deliberately kept separate

`TierContract.aggregator_model` is **dead config**. ADR-022 defined a per-tier
aggregator (`TIER_AGGREGATORS`, `tier_contract.py:122`) and
`create_tier_contract` populates `aggregator_model` on every contract. **No
production code path reads it.** `stage3_synthesize_final` calls
`_get_chairman_model()` — the flat, tier-blind `council.chairman`. So `high`
tier synthesises with `anthropic/claude-opus-5` while its contract says its
aggregator is `openai/gpt-5.6-sol`, and nothing reconciles the two or warns.

The single test that appears to cover this
(`tests/test_tier_council_integration.py::TestTierContractAggregatorIntegration::test_tier_contract_aggregator_used_in_synthesis`,
docstring: *"Synthesis should use tier_contract.aggregator_model when
provided"*) only asserts `contract.aggregator_model == TIER_AGGREGATORS[tier]`
— it tests the constant it was populated from, never the synthesis call. This
is the failure mode tracked in [#607](https://github.com/amiable-dev/llm-council/issues/607).

**Rev 1 tried to fix this defect *inside* this ADR, by promoting
`aggregator_model` to the primary chairman source. The council review was right
to object: that couples a model-selection change affecting every deployment to
a resilience feature, and it is separately valuable.** Rev 2 therefore:

- uses `aggregator_model` **only as a fallback candidate** (below), which
  requires no change to who synthesises today; and
- leaves *reconciling the divergence* — should `high`'s chairman actually be
  `openai/gpt-5.6-sol`? — to a separate ticket, as a #635-class model-selection
  question with its own evidence and its own release note.

### What exists today, and why none of it is this

| Mechanism | What it does | Why it isn't chairman resilience |
|---|---|---|
| `frontier_fallback.py` (ADR-027) | frontier→high hard fallback on timeout/rate-limit/API error | **Members only.** Gated on `tier == "frontier"` by `should_use_fallback_wrapper`; never wraps stage 3. See Alternatives for whether to generalise it |
| `EnhancedCircuitBreaker` (ADR-030) | opens a model's circuit on sliding-window failure rate | L4, *cross-run*. Protects the next run, not this one — and an open chairman circuit today means no synthesis, faster |
| `LLM_COUNCIL_CHAIRMAN_DISABLED` | skips synthesis, returns the top-ranked response | Static, operator-set, all-or-nothing. Not a mid-run fallback and not a substitute chairman |
| `quick_synthesis` | retries the chairman after global timeout | Same model. A model-specific outage defeats it by construction |

---

## Decision

Add a **single-attempt-per-run, infra-triggered, explicitly-labelled fallback
chairman** to stage 3. Six decisions, answering #598's five open questions and
one this ADR adds.

### D1 — Trigger: the first infra-class failure, within the run

Fall back on the **first** stage-3 failure whose cause is infra-class:

| Trigger | Source |
|---|---|
| `timeout`, `rate_limited`, `api_error`, `auth_error` | `query_model_with_status` status (already surfaced as `error_status`, #403) |
| chairman circuit **open** | ADR-030 `EnhancedCircuitBreaker` short-circuit, *before* any of the above statuses is produced |

The circuit-breaker row exists because the review caught a gap in rev 1: an
already-open chairman circuit may short-circuit the call without ever returning
one of the four allowlisted statuses, so a status-only trigger would fail to
fire in **exactly** the scenario this ADR names as one the breaker makes worse
("an open chairman circuit today means no synthesis, faster"). An open circuit
is a first-class trigger, not an absence of one.

**Never** fall back on a substantive-but-poor synthesis. We cannot judge that
without a judge, retrying for quality is a different feature (a second opinion,
not resilience), and a quality-triggered retry is an unbounded loop with no
principled stopping rule.

*Why first-failure and not N-consecutive:* a run has exactly one stage-3
attempt, so "N consecutive within a run" is undefined, and N-consecutive
*across* runs is cross-run health — which `EnhancedCircuitBreaker` already
models at L4. Rebuilding it at L3 would put the same signal in two places with
two thresholds. The failure of the only attempt is the signal.

**Failure scope matters for target selection.** `auth_error` on shared
provider credentials, and `rate_limited` scoped to an account rather than a
model, are **not model-specific** — swapping to another model at the same
provider is deterministically doomed. D2 therefore diversifies by provider for
these statuses.

### D2 — Target: primary unchanged; an ordered, terminating candidate list

**The primary chairman is `council.chairman`, exactly as today.** No change, no
config-provenance detection, no behaviour change for any deployment. Rev 1's
chain is gone.

On an infra trigger, build the **fallback candidate list** by concatenating, in
order:

1. `council.chairman_fallback` — an explicit operator list (new config, default
   empty). Operator intent wins outright.
2. `tier_contract.aggregator_model` — ADR-022's per-tier intent, finally read.
3. `TIER_AGGREGATORS[t]` for each tier `t` in the fixed order
   `["reasoning", "high", "balanced", "quick"]`, starting **after** the running
   tier's position, and wrapping is **not** performed.
4. Members of the running tier's pool.

Then apply, in this order:

- **Canonicalise and dedup.** Compare on the normalised provider-qualified id
  (lowercased, whitespace-stripped `provider/model`). Remove the failed primary
  and any duplicates, keeping first occurrence. This is what makes step 3
  terminate: `quick` (lowest tier) simply contributes no step-3 entries, and
  `reasoning`/`frontier` both mapping to `anthropic/claude-opus-5` collapses to
  one entry rather than yielding "nothing distinct".
- **Provider diversification.** When the trigger is `auth_error` or
  `rate_limited`, drop candidates sharing the failed primary's provider prefix.
  If that empties the list, the run does not fall back (see exhaustion).
- **Self-synthesis preference.** Partition the surviving list into
  non-participants (did not author a stage-1 response in this run) and
  participants; scan non-participants first, participants second. Take the
  **first** candidate overall. Participation is tested on the same canonical id.
- **Exhaustion.** An empty list after all of the above is **not an error**: no
  fallback is attempted, the run degrades exactly as it does today, and
  `L3_CHAIRMAN_FALLBACK` is emitted with `outcome="no_candidate"` and the
  reason. Silence here would recreate the invisibility this ADR exists to fix.

**On member promotion.** Rev 1 contradicted itself, rejecting "use the
highest-Borda member" in D2 while Alternatives reserved member promotion "as
the last resort inside the D2 chain". Resolved: members **are** eligible, at
step 4, but **never ordered by Borda score**. Ranking candidates by Borda
selects the model whose own response the synthesis would most likely centre on
— it maximises self-synthesis bias rather than avoiding it, which is what
anonymised peer review exists to prevent and what multi-agent judges are known
to *amplify* rather than cancel (ADR-047 P4, `bias_amplification.py`). Members
enter in pool order, behind every non-member candidate, and a participating
candidate is always labelled `chairman_fallback_self_reviewing: true`.

### D3 — Verdict integrity: two fields, because these are two dimensions

Rev 1 proposed adding `chairman_fallback` to
`verdict_source: Literal["mechanical", "legacy", "chairman_disabled"]`
(`verification/schemas.py:373`). The review correctly rejected this: `mechanical`
and `legacy` describe **how the verdict was derived**, while `chairman_disabled`
and `chairman_fallback` describe **which model produced the synthesis**. Under
ADR-051 a run can be simultaneously mechanically-derived *and*
fallback-synthesised, which a single-valued enum cannot represent — an
implementer would have to drop one signal, defeating the audit-trail goal.

(Note the existing enum is *already* conflated: `chairman_disabled` is a
provenance value living in a derivation enum. This ADR does not create that
problem, but it should not deepen it.)

**Decision: add a second field.**

- `verdict_source` keeps its current meaning and value set. **Unchanged.**
- New `synthesis_source: Literal["primary", "fallback", "disabled"]`, defaulting
  to `"primary"`, plus `chairman_model_used`, `chairman_fallback_reason`, and
  `chairman_fallback_self_reviewing`.
- `chairman_disabled` in `verdict_source` is **deprecated but still emitted**
  alongside `synthesis_source="disabled"` for a transition period. Removing it
  is a breaking change and belongs to its own release note.
- Rev 1 claimed widening a `Literal` "is additive for consumers". Withdrawn —
  that is not unconditionally true: it breaks strict validators, exhaustive
  `match`/`assert_never` checks, and generated clients pinned to the old value
  set. Adding a *new field* with a default genuinely is additive, which is
  another reason to prefer it.
- `L3_CHAIRMAN_FALLBACK` must likewise be added to `layer_contracts.py`'s L3
  event set. **Open question 3** asks whether any event consumer validates
  against a closed set, which would make even that a breaking change.

**Interaction with ADR-051/054, which is favourable and worth stating:** under
structured findings the verdict is `verdict_policy(findings)`, a pure function
of the findings, and since ADR-054 D3a (#563) no verdict threshold consumes
confidence at all. So a fallback chairman changes *who extracted the findings*
but not *how the gate reads them*. On the legacy prose path the verdict does
come from the chairman's text, so `synthesis_source` is the load-bearing signal
there.

### D4 — Cost and latency: one attempt per run, capped by what remains

- **At most one fallback attempt per run**, enforced by a **run-scoped attempt
  token** created at council entry and consumed by whichever site attempts a
  fallback first. This is not a stylistic detail: the fallback is wired into
  both `stage3_synthesize_final` and `quick_synthesis`, and `quick_synthesis`
  fires *after* the global deadline has already expired. Without run-scoped
  state, a single run could make a primary + fallback in stage 3 and then
  another primary + fallback in `quick_synthesis` — four synthesis calls, all
  outside the deadline this ADR promises not to extend. Rev 1's guarantee was
  unenforceable; the token is what makes it a guarantee.
- **Budget = `min(remaining_global_deadline, tier_per_model_timeout)`.** Rev 1
  said "floored at the tier's per-model timeout", which makes the per-model
  timeout a *lower* bound — `max(...)` — and therefore extends the deadline
  whenever little time remains, contradicting the next rule and making the
  extend flag meaningless. It meant capped. It now says capped.
- **`CHAIRMAN_FALLBACK_MIN_BUDGET` (default 20s): below this, no attempt.** A
  budget too small to complete a synthesis buys a guaranteed second failure —
  the #660 lesson, where a 15s retry of a model that had just exceeded 90s was
  worse than not retrying.
- On the post-deadline `quick_synthesis` path there is by definition no
  remaining global budget, so the fallback there runs at
  `min(CHAIRMAN_FALLBACK_MIN_BUDGET_CEILING, tier_per_model_timeout)` **only**
  when `LLM_COUNCIL_CHAIRMAN_FALLBACK_EXTEND` is set. Default off: that path
  degrades as it does today.
- **Double failure is a defined outcome, not a gap.** If the fallback also
  fails, the response keeps the *primary's* `error_status`/`error_detail`
  (the operator-actionable one), sets `synthesis_source="fallback"`, and
  `L3_CHAIRMAN_FALLBACK` carries `outcome="failed"` with both models and both
  error statuses. Same shape when no candidate exists (`outcome="no_candidate"`)
  or no budget remains (`outcome="no_budget"`).
- Emit `L3_CHAIRMAN_FALLBACK` with primary model, candidate model, trigger
  status, `outcome`, and the self-synthesis flag. Per ADR-024, escalation is
  explicit and auditable; a fallback must never be a silent behaviour change.
- **Cost.** Worst case is **two full synthesis calls**. Rev 1 claimed
  "no evidence re-send under ADR-049 prefix caching" — withdrawn: the candidate
  list routinely crosses providers (`openai/*` ↔ `anthropic/*`) and prefix
  caches are not shared across them, so the fallback call is typically uncached.
  A timed-out primary may also still bill for tokens generated.

### D5 — Config surface: shadow first, then canary, then opt-in

`LLM_COUNCIL_CHAIRMAN_FALLBACK` = `off` | `shadow` | `canary` | `on`, defaulting
to **`shadow`**, plus `council.chairman_fallback` (D2 step 1).

**Shadow** logs would-have-fallen-back decisions to
`.council/chairman/decisions.jsonl` and spends nothing. Rev 1 stopped there; the
review correctly noted that shadow logs a *numerator with no denominator* and
measures *incidence*, never whether a fallback would have **succeeded** — so it
cannot distinguish "insurance worth enabling" from "a second doomed call".
Fixed:

- Every stage-3 attempt writes a record, not only the failing ones, giving the
  denominator. Each record carries tier, trigger status (or `none`), the
  candidate that *would* have been selected, and whether it would have been a
  self-synthesis.
- **Flip criterion, quantified:** ≥ 500 stage-3 attempts observed, and an
  infra-class stage-3 failure rate ≥ 0.5%. Below that, this feature is
  insurance and stays opt-in — a legitimate outcome of the shadow phase, not a
  failure of it.
- **`canary`** answers the success question that shadow structurally cannot: on
  a sampled fraction (`LLM_COUNCIL_CHAIRMAN_FALLBACK_CANARY_PCT`, default 10%)
  of *failing* stage-3 attempts, actually make the fallback call and record the
  outcome. Bounded spend, and it is the only way to measure the success rate
  that justifies `on`.

This mirrors how `LLM_COUNCIL_EARLY_CONSENSUS` and
`LLM_COUNCIL_GRADUATED_DEPTH` were introduced. We have two anecdotes and no
rate; shipping `on` by default on two anecdotes would be the evidence-free move
this repo has consistently declined to make.

### D6 — Role separation: warn, and label symmetrically

The chairman should not be a member of the tier it chairs. The roles have
opposite latency profiles: a member is one of N parallel calls whose slow tail
is absorbed, while the chairman is a serial single-attempt call on the critical
path where the same latency is fatal. Selecting one model for both optimises
against itself and makes the failures correlated — one timeout removes a member
*and* the aggregator, which is exactly what #660 observed. Today
`llm_council.yaml` has `anthropic/claude-opus-5` in both `high`'s pool and
`council.chairman`.

**Decision: emit a config-load warning, surfaced in
`council_health_check.config_warnings`; do not reject the config.** Hard
enforcement would break working deployments over a correlation risk, and
`config_warnings` is already the established channel for exactly this kind of
"your two config surfaces disagree" signal (#608).

**Symmetry (review finding).** Rev 1 labelled self-synthesis only on the
fallback path, so the *primary* chairman synthesising over its own stage-1
response — the live condition at `high` tier, the one #660 observed — would
have been flagged nowhere in the run record. `chairman_self_reviewing` is
therefore set on **both** paths, from the same canonical-id participation test.
An audit trail that flags the rare case and hides the routine one is worse than
no flag.

---

## Consequences

**Positive.** The aggregator role gains the graceful degradation the member role
has had since ADR-027. A chairman-specific outage stops being a total loss.
`aggregator_model` starts being read for the first time since ADR-022 — without
changing who synthesises today. Every degraded verdict is labelled at the point
a consumer reads it, and self-synthesis is visible on both paths.

**Negative / accepted.**

- One more model in the trust path for a fallback run, and a fallback synthesis
  is by construction from a model that was *not* chosen as best-for-this-tier.
  Mitigated by labelling, not by pretending otherwise.
- Worst-case added latency is one per-model timeout, and worst-case added cost
  is one full uncached synthesis call.
- The self-synthesis preference can fail to find a non-participant on a small
  tier (`quick` is 2 models). Accepted, and labelled.
- `synthesis_source` is a new response field on both surfaces. Additive, with a
  default, but it is still a schema change requiring a docs/drift update
  (`TestVerifyResponseFieldDrift`).
- The `verdict_source="chairman_disabled"` deprecation leaves two fields
  carrying one signal during the transition. Deliberate; removing it is its own
  breaking change.

**Neutral.** Flag `off` must be byte-identical to today, test-pinned, as with
every other flag in this repo. **Rev 2 introduces no change to which model
synthesises on a healthy run** — the property rev 1 claimed but could not
support.

---

## Alternatives considered

**Do nothing; rely on `CHAIRMAN_DISABLED`.** It returns the top-ranked stage-1
response with no verdict, and it is static — an operator must flip it *during*
an outage, which requires noticing the outage. That is the workflow #596 already
showed doesn't happen.

**Generalise `frontier_fallback` to stage 3** (relax
`should_use_fallback_wrapper`'s `tier == "frontier"` gate and wrap the
aggregator call). Raised by the council review as the obvious cheaper path, and
worth stating why it is not adopted: `execute_with_fallback` selects
`get_tier_models(fallback_tier)[0]` — first model in a pool, with no dedup
against the failed model, no participation test, no provider diversification,
and no labelling. Every property D2 and D3 exist to provide would have to be
added to it, at which point the shared surface is `try/except → pick another
model`. It also raises on empty pools, where D2 requires a recorded
`no_candidate` outcome. **Adopted in part:** the trigger taxonomy and the
`emit_fallback_event` pattern are reused directly, and if the two mechanisms
converge later, that consolidation should be its own change with its own tests
— not a widened `if` in a member-path helper.

**Retry the same chairman with backoff.** Cheapest to build, and useless against
the dominant failure mode: a model-specific provider outage or a model too slow
for the budget. Both are unchanged by retrying the same model. It also spends
the remaining deadline on the least likely path to succeed.

**Always synthesise with two chairmen and reconcile.** Strictly better verdicts,
roughly double the stage-3 cost on every run, and it needs a reconciliation
policy that is its own ADR. Out of scope; not precluded.

**Promote the highest-Borda responding member.** Provably alive and already in
context, but it *maximises* self-synthesis bias — the highest-Borda member is
the one whose own response the synthesis would most likely centre on. Members
remain eligible at D2 step 4, in pool order, never Borda order.

---

## Open questions for review

1. **Is the D5 flip criterion (≥500 attempts, ≥0.5% infra failure rate) the
   right bar?** It is a first proposal, not a derived threshold. A maintainer
   with a view on acceptable verdict-loss rate should set it.
2. **Should `canary` exist at all,** or is measuring incidence enough to justify
   `on`? Canary is the only way to learn the fallback *success* rate, but it
   spends real money on a sampled fraction of already-failing runs.
3. **Do any `LayerEvent` consumers validate against a closed event-type set?**
   If so, `L3_CHAIRMAN_FALLBACK` is a breaking change for the same reason the
   rev-1 `verdict_source` widening was, and needs the same treatment.
4. **Does the self-synthesis test need to extend to stage-2 reviewers?** A
   fallback chairman that also *reviewed* has seen the anonymisation mapping's
   effects, though not the mapping. Probably immaterial; worth a reviewer's eye.

**Resolved since rev 1.** "Should `high`'s chairman be its declared aggregator
(`openai/gpt-5.6-sol`) rather than `anthropic/claude-opus-5`?" is **removed
from this ADR's scope** — rev 2 no longer makes `aggregator_model` load-bearing
for the primary, so the divergence is not this ADR's to institutionalise or
resolve. It becomes a standalone #635-class model-selection ticket.

---

## Implementation decomposition (post-acceptance)

Do not start before review. Suggested child tickets for the `adr-epic` flow:

- **P0 — Decoupled config hygiene.** Reconcile `TIER_AGGREGATORS` vs
  `council.chairman` (a model-selection decision), and replace the #607-class
  test with one asserting the model the synthesis call *received*. Independent
  of everything below; ships on its own.
- **P1 — Observability first.** `L3_CHAIRMAN_FALLBACK` event type + shadow-mode
  decision log **with the denominator**. No behaviour change; produces the data
  D5's flip criterion needs.
- **P2 — Candidate resolution.** `resolve_fallback_chairman(...)` implementing
  D2 — canonicalisation, dedup, provider diversification, participation
  partition, and the `no_candidate` terminus. Pure and exhaustively testable
  with no model calls.
- **P3 — The fallback path.** D1 trigger (including the open-circuit case), D4
  budget/one-attempt token, wired into `stage3_synthesize_final` and
  `quick_synthesis`. The attempt token is the acceptance criterion, not an
  implementation detail.
- **P4 — Labelling.** `synthesis_source`, `chairman_model_used`,
  `chairman_fallback_reason`, `chairman_self_reviewing` (both paths, per D6)
  through consult metadata, verify diagnostics, the #660 rendering contract,
  and the docs-drift field test.
- **P5 — Canary + config hygiene.** D5 `canary` mode; D6 role-separation
  warning; docs; env reference.
