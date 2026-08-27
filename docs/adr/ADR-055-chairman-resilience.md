# ADR-055: Chairman Resilience — Dynamic Fallback for Stage-3 Synthesis

**Status:** Proposed 2026-08-27 — review requested
**Date:** 2026-08-27
**Decision Makers:** llm-council maintainers
**Proposed by:** [#598](https://github.com/amiable-dev/llm-council/issues/598), which is explicit that this needs an ADR before code: it changes deliberation behaviour and cost, and every other resilience mechanism in this repo got one first.
**Relates to:** ADR-012 (MCP reliability), ADR-022 (tier contracts / aggregators), ADR-024 (layer sovereignty, auditable escalation), ADR-027 (frontier hard fallback — the member-level precedent), ADR-051 (mechanical gate), ADR-054 (confidence semantics)
**Tracking:** [#598](https://github.com/amiable-dev/llm-council/issues/598)

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

### Two findings from the current code that reshape the options

**1. `TierContract.aggregator_model` is dead config.** ADR-022 defined a
per-tier aggregator (`TIER_AGGREGATORS`, `tier_contract.py:122`) and
`create_tier_contract` populates `aggregator_model` on every contract. **No
production code path reads it.** `stage3_synthesize_final` calls
`_get_chairman_model()` — the flat, tier-blind `council.chairman` value. So
today `high` tier synthesises with `anthropic/claude-opus-5` while its contract
says its aggregator is `openai/gpt-5.6-sol`, and nothing reconciles the two or
warns.

The single test that appears to cover this
(`tests/test_tier_council_integration.py::TestTierContractAggregatorIntegration::test_tier_contract_aggregator_used_in_synthesis`,
docstring: *"Synthesis should use tier_contract.aggregator_model when
provided"*) only asserts `contract.aggregator_model == TIER_AGGREGATORS[tier]`
— it tests the constant it was populated from, never the synthesis call. This
is the failure mode tracked in [#607](https://github.com/amiable-dev/llm-council/issues/607):
a test that doesn't constrain what it names, which is why the gap survived.

This matters for the decision below: **the fallback target question is half
already answered in config that nothing reads.**

**2. The existing degraded path is weaker than it looks.** On global timeout,
`quick_synthesis` retries the chairman. Until #660 it did so with a hard-coded
15s, so a chairman that had just exceeded a 90s stage-1 budget was asked again
with 15s. #660 made that budget tier-derived; it did not make the *model*
redundant. One unreachable model still means one unreachable synthesis.

### What exists today, and why none of it is this

| Mechanism | What it does | Why it isn't chairman resilience |
|---|---|---|
| `frontier_fallback.py` (ADR-027) | frontier→high hard fallback on timeout/rate-limit/API error | **Members only.** Gated on `tier == "frontier"` by `should_use_fallback_wrapper`; never wraps stage 3 |
| `EnhancedCircuitBreaker` (ADR-030) | opens a model's circuit on sliding-window failure rate | L4, *cross-run*. Protects the next run, not this one — and an open chairman circuit today means no synthesis, faster |
| `LLM_COUNCIL_CHAIRMAN_DISABLED` | skips synthesis, returns the top-ranked response | Static, operator-set, all-or-nothing. Not a mid-run fallback and not a substitute chairman |
| `quick_synthesis` | retries the chairman after global timeout | Same model. A model-specific outage defeats it by construction |

---

## Decision

Add a **single-attempt, infra-triggered, explicitly-labelled fallback chairman**
to stage 3, plus the config hygiene that makes the primary chairman choice
coherent in the first place. Six decisions, answering #598's five open questions
and one this ADR adds.

### D1 — Trigger: the first infra-class failure, within the run

Fall back on the **first** stage-3 failure, restricted to infra-class statuses:
`timeout`, `rate_limited`, `api_error`, `auth_error` — the same taxonomy
`query_model_with_status` already returns and that `error_status` already
surfaces (#403).

**Never** fall back on a substantive-but-poor synthesis. We cannot judge that
without a judge, retrying for quality is a different feature (a second opinion,
not resilience), and a quality-triggered retry is an unbounded loop with no
principled stopping rule.

*Why first-failure and not N-consecutive:* a run has exactly one stage-3
attempt, so "N consecutive within a run" is undefined, and N-consecutive
*across* runs is cross-run health — which `EnhancedCircuitBreaker` already
models at L4. Rebuilding it at L3 would put the same signal in two places with
two thresholds. The failure of the only attempt is the signal.

### D2 — Target: resurrect the tier aggregator, then an explicit chain

Resolve the stage-3 model through an ordered chain, first hit wins:

1. `council.chairman` — **only when the operator set it explicitly.** Preserves
   today's behaviour for every existing config.
2. `tier_contract.aggregator_model` — ADR-022's per-tier intent, finally read.
3. `TIER_AGGREGATORS[<next tier down>]` — mirrors `frontier_fallback`'s
   frontier→high shape.

The **fallback** chairman is the next distinct entry in that chain, subject to
one guard.

**Self-synthesis guard.** A fallback candidate that authored a stage-1 response
in this run would be synthesising over its own answer — which is precisely what
anonymised peer review exists to prevent, and the bias literature says
multi-agent judges *amplify* rather than cancel shared bias (ADR-047 P4,
`bias_amplification.py`). So: prefer a candidate that did not participate; if
none is available, accept a participant but **label it**
(`chairman_fallback_self_reviewing: true`) rather than silently degrade the
anonymisation invariant. Refusing outright would trade a labelled weak verdict
for no verdict, which is the trade #598 exists to stop making.

*Rejected: "use the highest-Borda member that responded."* Tempting — it is
provably alive this run and its context is already loaded — but it maximises
self-synthesis rather than avoiding it: the highest-Borda member is the one
whose own response the synthesis is most likely to centre on.

### D3 — Verdict integrity: label it, and let the mechanical gate stay chairman-agnostic

- Extend `verdict_source` (`verification/schemas.py:373`) with
  `chairman_fallback`. It is currently
  `Literal["mechanical", "legacy", "chairman_disabled"]`; adding a member is
  additive for consumers that branch on the existing values.
- Add `chairman_model_used` and `chairman_fallback_reason` to consult metadata
  and verify diagnostics, so a fallback verdict is distinguishable from a
  primary one in the audit trail — not merely in the moment.
- **Interaction with ADR-051/054, which is favourable and worth stating:** under
  structured findings the verdict is `verdict_policy(findings)`, a pure function
  of the findings, and since ADR-054 D3a (#563) no verdict threshold consumes
  confidence at all. So a fallback chairman changes *who extracted the findings*
  but not *how the gate reads them*. On the legacy prose path the verdict does
  come from the chairman's text, so `verdict_source=chairman_fallback` is the
  load-bearing signal there.
- The `single_model_raw` heading and `peer_review: false` machinery from #660
  already renders a labelled degraded result honestly; `chairman_fallback` slots
  into the same rendering contract.

### D4 — Cost and latency: exactly one extra call, inside the existing deadline

- **At most one** fallback attempt per run. Never a chain, never a retry ladder.
- Budget = whatever remains of the run's global deadline, floored at the tier's
  per-model timeout. **If nothing remains, no fallback is attempted** and the
  run degrades exactly as it does today, with the reason recorded. The deadline
  is not extended by default — a resilience feature that quietly doubles worst-
  case latency has moved the failure rather than fixed it.
- `LLM_COUNCIL_CHAIRMAN_FALLBACK_EXTEND` (default off) allows an operator to
  opt into extending the deadline by one per-model budget for the attempt.
- Emit a new `L3_CHAIRMAN_FALLBACK` LayerEvent carrying primary model, fallback
  model, `error_status`, and whether the self-synthesis guard fired. Per
  ADR-024, escalation is explicit and auditable; a fallback must never be a
  silent behaviour change.
- Worst-case added cost is one synthesis call, which is the cheapest stage by
  token count (no evidence re-send under ADR-049 prefix caching).

### D5 — Config surface: shadow first, then opt-in, then default

`LLM_COUNCIL_CHAIRMAN_FALLBACK` = `off` | `shadow` | `on`, defaulting to
**`shadow`**, plus `council.chairman_fallback` for an explicit model list.

Shadow mode logs *would-have-fallen-back* decisions to
`.council/chairman/decisions.jsonl` and spends nothing. This mirrors how
`LLM_COUNCIL_EARLY_CONSENSUS` and `LLM_COUNCIL_GRADUATED_DEPTH` were introduced,
and it answers the question that actually gates the default flip: **how often
does stage 3 fail for infra reasons?** We have anecdotes (one ~1-hour window,
one field report) and no rate. Shipping `on` by default on two anecdotes would
be the same evidence-free move this repo has consistently declined to make.

Flip criterion: a measured infra-class stage-3 failure rate materially above
zero over a representative period. If the rate is ~0, this feature is
insurance and stays opt-in; that is a legitimate outcome of the shadow phase,
not a failure of it.

### D6 — Role separation: warn, don't break

The chairman should not be a member of the tier it chairs. The roles have
opposite latency profiles: a member is one of N parallel calls whose slow tail
is absorbed, while the chairman is a serial single-attempt call on the critical
path where the same latency is fatal. Selecting one model for both optimises
against itself, and makes the failures correlated — one timeout removes a
member *and* the aggregator, which is exactly what #660 observed.

Today `llm_council.yaml` has `anthropic/claude-opus-5` in both `high`'s pool and
`council.chairman`.

**Decision: emit a config-load warning, surfaced in
`council_health_check.config_warnings`; do not reject the config.** Hard
enforcement would break working deployments over a correlation risk, and
`config_warnings` is already the established channel for exactly this kind of
"your two config surfaces disagree" signal (#608). Whether to promote it to an
error is deferred until the shadow data says how much the correlation costs.

---

## Consequences

**Positive.** The aggregator role gains the graceful degradation the member role
has had since ADR-027. A chairman-specific outage stops being a total loss.
ADR-022's per-tier aggregator intent becomes real instead of decorative. Every
degraded verdict is labelled at the point a consumer reads it.

**Negative / accepted.**

- One more model in the trust path for a fallback run, and a fallback synthesis
  is by construction from a model that was *not* chosen as best-for-this-tier.
  Mitigated by labelling, not by pretending otherwise.
- The self-synthesis guard can fail to find a clean candidate on a small tier
  (`quick` is 2 models). Accepted with a label.
- Reading `tier_contract.aggregator_model` changes which model synthesises for
  any deployment that never set `council.chairman` explicitly. **This is a
  behaviour change and must ship in a MINOR release with a migration note** —
  it is why D2's chain puts explicit operator config first.
- Shadow mode delays the benefit by one measurement period. Deliberate.

**Neutral.** Flag `off` must be byte-identical to today, test-pinned, as with
every other flag in this repo.

---

## Alternatives considered

**Do nothing; rely on `CHAIRMAN_DISABLED`.** It returns the top-ranked stage-1
response with no verdict, and it is static — an operator must flip it *during*
an outage, which requires noticing the outage. That is the workflow #596 already
showed doesn't happen.

**Retry the same chairman with backoff.** Cheapest to build, and useless against
the dominant failure mode: a model-specific provider outage or a model too slow
for the budget. Both are unchanged by retrying the same model. It also spends
the remaining deadline on the least likely path to succeed.

**Always synthesise with two chairmen and reconcile.** Strictly better verdicts,
roughly double the stage-3 cost on every run, and it needs a reconciliation
policy that is its own ADR. Out of scope; not precluded.

**Promote a council member to chairman on failure.** Zero extra model surface
and provably-alive, but maximises self-synthesis bias (see D2). Available as
the last resort inside the D2 chain, labelled.

---

## Open questions for review

1. **Should `high`'s chairman actually be `openai/gpt-5.6-sol` (its declared
   aggregator) rather than `anthropic/claude-opus-5`?** D2 preserves the current
   value because it is explicitly set, but the divergence between the two
   surfaces is unreviewed and predates this ADR. Resolving it is a #635-class
   model-selection question, not a resilience one.
2. **Is `shadow` the right default, or is `on` justified now?** The argument for
   `on`: two documented total-loss windows, and the failure is a lost verdict on
   work the user already paid for. The argument for `shadow`: we still have no
   rate, and this repo's consistent practice is to measure first.
3. **Does the self-synthesis guard need to extend to stage 2?** A fallback
   chairman that also *reviewed* in stage 2 has seen the anonymisation mapping's
   effects, though not the mapping. Probably immaterial; worth a reviewer's eye.

---

## Implementation decomposition (post-acceptance)

Do not start before review. Suggested child tickets for the `adr-epic` flow:

- **P1 — Observability first.** `L3_CHAIRMAN_FALLBACK` event type + shadow-mode
  decision log. No behaviour change, produces the data D5's flip criterion needs.
- **P2 — Chain resolution.** `resolve_chairman(tier_contract)` implementing D2,
  reading `aggregator_model` at last. Includes a real integration test for the
  #607-class gap — asserting the model the synthesis call *received*, not the
  contract field's value.
- **P3 — The fallback path.** D1 trigger, D4 budget/one-attempt discipline, the
  self-synthesis guard, wired into `stage3_synthesize_final` and
  `quick_synthesis`.
- **P4 — Labelling.** `verdict_source="chairman_fallback"`,
  `chairman_model_used`, `chairman_fallback_reason` through consult metadata,
  verify diagnostics, and the #660 rendering contract.
- **P5 — Config hygiene.** D6 role-separation warning; docs; env reference.
