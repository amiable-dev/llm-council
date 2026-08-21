# ADR-044: Compute-Optimal Deliberation

**Status:** Implemented 2026-07-03 (Phases 1–3, epic #394) — was Draft 2026-07-02
**Date:** 2026-07-02
**Decision Makers:** Chris Joseph, LLM Council
**Related:** ADR-026 (Phase 3 — the index this wires in), ADR-011 (Phase 3 — cost-per-quality), ADR-040 (Options E/F), ADR-020 (Tier-1 fast path), ADR-024 (layer sovereignty), ADR-036 (CSS)
**Supersedes:** ADR-039 (LLMRouter — external router no longer needed), ADR-043 (Pareto Router — folded in as an optional pool source)

---

## Context

### The write-only index

The internal performance index (ADR-026 Phase 3) records per-model, per-session
quality (Borda), latency, parse success, and — since v0.25.0 (ADR-011 Phase 3) —
**cost**, deriving a Borda-per-dollar `quality_per_cost` signal with an opt-in
cost-aware ranking (`get_all_cost_aware_scores`, `LLM_COUNCIL_COST_AWARE_SELECTION`).

**None of it influences selection.** Verified 2026-07-02: `metadata/selection.py`
scores candidates purely from *static* metadata (`calculate_model_score`,
`_estimate_quality_score` → registry benchmarks), with zero references to
`InternalPerformanceTracker`. Two epics of telemetry (v0.25.x–v0.27.x) are a
dormant asset. ADR-040's Options E (tiered Stage 2) and F (early consensus
termination) were deferred "pending observability data" — that data now exists
(ADR-041 timing + ADR-011 cost).

### The field (July 2026)

- **Learned routing/cascades**: RouteLLM-class routers cut ~85% of cost while
  retaining ~95% of top-model quality; production gateways report 30–50% spend
  reduction from routing alone.
- **Compute-optimal test-time scaling**: spending inference compute adaptively
  (more deliberation only where the query needs it) dominates fixed-depth
  strategies; heterogeneous-model ensembles are explicitly called out as
  underexplored — this project is one.
- **Route auditability** ("route receipts") is emerging as a trust requirement —
  aligning with ADR-024's explicit/auditable-escalation principle.

### Why the drafts die

ADR-039 (NVIDIA LLMRouter) and ADR-043 (OpenRouter Pareto) both outsourced
routing intelligence to external dependencies. With the in-house index now
carrying real quality/latency/cost history per model, an internal, auditable
wiring is simpler, offline-capable (Sovereign Orchestrator, ADR-026), and keeps
the routing signal aligned with the council's own Borda ground truth rather
than a third party's benchmark. ADR-039 is superseded outright; ADR-043's
`openrouter/pareto-code` remains available as an ordinary pool entry if wanted.

## Decision

Make deliberation **compute-optimal** in three opt-in, individually-shippable
phases. Sovereignty guardrail (ADR-024): every behaviour below is **default
OFF**, flag-gated, emits an auditable `LayerEvent` when it changes an outcome,
and soft-fails to today's behaviour on any error. Cost/quality history may
influence routing **only** through these audited paths.

### Phase 1 — Performance-aware selection (ADR-026 P3 completion)

Blend the live index into candidate scoring in `metadata/selection.py`:

- `_estimate_quality_score` consults `InternalPerformanceTracker` when the
  model's `confidence_level` is ≥ PRELIMINARY (≥10 samples): blend
  `live = tracker score`, `static = registry estimate` as
  `w·live + (1−w)·static`, with `w` stepping up by confidence tier
  (PRELIMINARY 0.3, MODERATE 0.6, HIGH 0.8). INSUFFICIENT → static only
  (cold-start safe).
- When `LLM_COUNCIL_COST_AWARE_SELECTION=true` (the existing ADR-011 flag),
  the blended quality feeds the cost-aware ranking so value-for-money
  reorders within the quality span (cohort-floor rule from v0.27.1 applies).
- Master flag: `LLM_COUNCIL_PERFORMANCE_SELECTION` (default **false**).
- Emit `L2_PERFORMANCE_SELECTION_APPLIED` LayerEvent whenever blending
  changes the selected set vs. static-only (auditable route receipt).

### Phase 2 — Early consensus termination (ADR-040 Option F)

In `stage2_collect_rankings`, when the Borda margin of the leader is
**mathematically unassailable** given the reviewers still outstanding
(worst-case remaining votes cannot change the top ranking), cancel the
outstanding reviewer calls and proceed to Stage 3.

- Flag: `LLM_COUNCIL_EARLY_CONSENSUS` (default **false**).
- Never cancels a call already in flight past its first token where the
  gateway cannot cancel cleanly; cancellation is cooperative (asyncio).
- Emits `L3_EARLY_CONSENSUS_TERMINATION` with votes-saved + est. cost saved
  (from ADR-011 per-model history).
- Shadow mode first: when the flag is off, still *detect and log* the
  would-have-terminated point so savings are measurable before enabling.

### Phase 3 — Graduated deliberation depth (cascade)

Extend the ADR-020 Tier-1 confidence-gated fast path from binary
(single model vs. full council) to graduated depth:

- Depth ladder: `single → mini-council (2–3) → full council`.
- Escalation signal: Consensus Strength Score (ADR-036 CSS) + verdict
  confidence from the shallower pass; low consensus ⇒ escalate one rung,
  reusing the already-collected responses as Stage-1 members of the deeper
  pass (no wasted spend).
- Budget integration: the ADR-011 estimator prices each rung; the opt-in
  `BudgetEnforcer` can veto an escalation (auditable WARN/REJECT, never a
  silent downgrade).
- Flag: `LLM_COUNCIL_GRADUATED_DEPTH` (default **false**).
- Escalations emit the existing `L2_DELIBERATION_ESCALATION` event.

### ADR housekeeping

Mark ADR-039 and ADR-043 **Superseded by ADR-044**; ADR-040 Options E/F and
ADR-026 Phase 3 notes updated to point here.

## Consequences

**Positive**
- Activates two epics of dormant telemetry into the largest available
  cost/quality lever (field evidence: 30–85% spend reduction from routing and
  adaptive depth), while quality is protected by confidence-tiered blending
  and consensus-gated escalation.
- Kills two stale draft ADRs and completes two deferred ones with a single
  coherent mechanism, all in-house and offline-capable.
- Route receipts (LayerEvents) make every routing influence auditable.

**Negative / risks**
- Feedback loops: selection favouring historically-good models starves
  challengers of samples → mitigated by the existing anti-herding penalty
  (`apply_anti_herding_penalty`), the audition/graduation pipeline
  (ADR-027/029) as the sanctioned entry path, and capped blend weight (≤0.8).
- Early termination could suppress dissent → it only fires on *mathematical*
  unassailability of the ranking, never on score similarity; dissent
  extraction (ADR-025b) still runs on collected reviews.
- Miscalibrated history misroutes → all phases default OFF; shadow-mode
  logging precedes enablement; blending is bounded, never a replacement.

## Definition of Done (per phase)

Code + tests (cold-start, flag-off no-op byte-identical, event emission,
cancellation safety); user docs (CLAUDE.md env index + module map, README,
CHANGELOG); LLM-facing text where surfaced; flag defaults documented
(everything off). A phase that changes flag-off behaviour fails DoD.

## Compliance / Validation

- Grep-able invariant: outside `metadata/selection.py` blending, the budget
  enforcer, and the graduated-depth escalator, no L1/L2 code reads the
  performance tracker or cost history.
- Flag-off test suite proves byte-identical selection to pre-ADR-044.
- Shadow-mode metrics (would-have-saved) recorded before any default flips.

## References

- [ADR-026 Dynamic Model Intelligence](./ADR-026-dynamic-model-intelligence.md) · [ADR-011 Cost & Token Accounting](./ADR-011-cost-tracking.md) · [ADR-040 Timeout Guardrails](./ADR-040-verification-timeout-observability.md) · [ADR-020 Not Diamond Strategy](./ADR-020-not-diamond-integration-strategy.md)
- RouteLLM-class routing results; compute-optimal test-time scaling; route-receipt auditability (see `docs/roadmap-2026-h2.md` sources)

## Implementation note — P3 wiring & shadow instrumentation (2026-08-21, #618)

Phase 3 shipped `graduated_depth.py` as a bounded decision engine; nothing
called `plan_escalation`. This note records the wiring design, honoring the
mitigation above: shadow-mode logging precedes enablement. A council design
review (2026-08-21) materially corrected two of the original proposals; the
corrections are credited inline.

### Slice 1 (shipped with this note): shadow instrumentation, zero behavior change

Today's behavior is always full depth, so shadow cannot observe real
escalations; it measures the counterfactual instead. After aggregate rankings
are computed, both orchestrators (`run_full_council` — HTTP;
`run_council_with_fallback` — MCP/webhooks) call a soft-fail hook
(`evaluate_and_log_shadow_depth`) that:

1. **Computes CSS internally** (pure-Python over in-memory Stage-2 data, no
   model calls, response unchanged) — deliberately independent of
   `LLM_COUNCIL_QUALITY_METRICS`, which is an *output-annotation* flag.
   Binding routing/telemetry control flow to a presentation flag would
   silently disable the ladder for flag-off users. *(Council correction:
   the original proposal had the hook respect the flag.)*
2. **Computes a counterfactual mini-rung CSS** by subsetting the full run's
   Stage-2 rankings to the prefix-3 mini models (their reviews, restricted to
   their responses, relative order preserved) and re-running the Borda + CSS
   math on the subset. This is an approximation — the rankings were elicited
   in an N-candidate context — but it observes *both* error directions.
   *(Council correction: the original plan treated the counterfactual as
   unobservable and logged only an upper bound.)*
3. Classifies the run:
   - `mini_would_suffice` — mini CSS and full CSS both strong: the ladder
     would have stopped at 3 models and full depth added little. The savings
     candidate.
   - `premature_halt_risk` — mini CSS strong but full CSS weak: the ladder
     would have stopped while the full council disagreed. The degradation
     hazard; slice 2 must be judged on this rate.
   - `would_escalate` — mini CSS weak: the ladder would have escalated,
     costing an *extra* mini Stage-2 pass over today's single full pass
     (logged as `extra_stage2_reviews_if_escalated`; not priced in USD —
     per-stage cost history does not exist and is never fabricated).
   - `ladder_inapplicable` — council size ≤ mini size (see eligibility).
   - `signals_unavailable` / `counterfactual_unavailable` — parse failures;
     the unknown-never-escalates rule keeps these out of savings math.
4. Appends one JSON line to `.council/depth/decisions.jsonl` — durable file,
   not a log line (#595 lesson): `{ts, entry_point, council_size,
   mini_council_models, css_full, css_mini_counterfactual, confidence,
   decision, hypothetical_saved_models, extra_stage2_reviews_if_escalated,
   est_saved_usd?}`. Numeric signals and model names only, never response
   content. `est_saved_usd` (ADR-011 estimator over the models beyond the
   mini rung) only when positive — an all-unknown 0.0 is omitted, never
   presented as "$0 savings".
5. Soft-fails everywhere; telemetry never breaks a council run. The response
   payload is unchanged (flag-off results byte-identical, test-pinned).

### Eligibility (corrected)

The ladder applies only where the council is *larger* than the mini rung —
size-based (`len(models) > 3`), which in practice means the high/reasoning
tiers. *(Council correction: the original proposal excluded high/reasoning to
honor the tier "promise" — but quick(2) is smaller than the mini rung and
balanced(3) equals it, so that exclusion would have made the ladder a no-op
everywhere. The tier promise is the quality of the final synthesis, which the
consensus gate protects; that premise is ADR-044 itself.)*

### Slice 2 (follow-up, gated on slice-1 data): active ladder

`LLM_COUNCIL_GRADUATED_DEPTH=true` routes eligible requests to a separate
graduated orchestrator composing the existing stage functions (mini rung →
Stage 2 → `plan_escalation` → added models' Stage 1 only → full Stage 2 →
single Stage 3); `run_full_council`'s hot path stays untouched. Recorded
hazards for that work, from the same review: (a) an escalated run costs
strictly more than a straight full run (the mini Stage-2 pass is wasted) —
the shadow `would_escalate` rate bounds this overhead before enablement;
(b) stale mini-rung ranking artifacts must not leak into the final Stage 3
context; (c) the added-models fan-out is a partial-parallel orchestration
change with no slice-1 test coverage; (d) slice 2's schema adds
`latency_penalty_ms` (unmeasurable in shadow). Enablement criteria: review
`decisions.jsonl` for the `mini_would_suffice` vs `premature_halt_risk`
ratio; a material premature-halt rate at the 0.7 threshold blocks the flag
default and re-opens threshold tuning.
