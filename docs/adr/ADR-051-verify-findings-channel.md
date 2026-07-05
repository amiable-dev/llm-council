# ADR-051: Verify Findings Channel & Verdict–Evidence Consistency

**Status:** Proposed 2026-07-04 (rev 2: literature claims verified via adversarial deep-research, 105 agents, 3-vote, checked 2026-07-04, with the anchor paper's numbers independently confirmed against the primary arXiv source. See "Research verification".)
**Date:** 2026-07-04
**Decision Makers:** llm-council maintainers (review requested)
**Proposed by:** maintainer triage of a downstream field report (amiable-dev/epic-loop)
**Relates to:** ADR-025b (Jury Mode / binary verdict), ADR-034 (verification), ADR-042 (evidence injection), ADR-047 (verifier calibration & unclear taxonomy), ADR-016 (rubric scoring)
**Tracking:** [#482](https://github.com/amiable-dev/llm-council/issues/482)
**Implementation spec:** [ADR-051-implementation-spec.md](ADR-051-implementation-spec.md) (enforcement mechanism, response schema, flagged migration, doc checklist, child breakdown)

---

## Context

`verify()`'s primary machine-readable contract is its verdict plus a
`blocking_issues` list — automation (CI gates, epic-loop's green-chase cap)
routes on the blocking count. Field data from a downstream consumer
(amiable-dev/epic-loop: 27 calls / 25 completed across two tiers, every
`verification_id` logged in `docs/assessments/council-verify-stats.md`) plus
an independent second corpus (this repo's ADR-049/050 delivery epics, same
council config) show a correctness defect:

> **`blocking_issues` is `[]` on effectively every call** — pass, fail, and
> unclear alike — including FAILs whose own rationale names findings the
> council calls "critical".

### Root cause — verdict and findings are decoupled by construction

The two fields come from **different, unlinked sources**:

- **Verdict** — the structured ADR-025b BINARY `VerdictResult`
  (`verification/verdict_extractor.py::_verdict_from_structured`),
  authoritative since #355. A clean go/no-go + confidence.
- **`blocking_issues`** — a regex scrape of the chairman's **prose**
  (`extract_blocking_issues`), matching only severity tokens anchored at
  line start: `^\s*[-*]?\s*\**(CRITICAL|MAJOR|MINOR)\**:\s+…`.

Modern chairmen (gemini-3.1-pro, opus-4.8) write findings as prose, which the
strict regex never matches, so `blocking_issues == []` even when the verdict
is `fail`. There is **no structured `findings[]`** anywhere in the pipeline,
and blocking-strength *evidence* (ADR-042) does not feed `blocking_issues`
(it drives screening/budget only). This is the classic LLM-judge
**verdict–evidence decoupling** pathology: a rejection with no machine-readable
justification.

**#355 backstory (why it swung to never-fires):** the regex was originally
loose (`(CRITICAL|MAJOR|MINOR)[:\s]+` anywhere), which fabricated blocking
issues from *approval* prose ("the critical issues have been resolved"). #355
tightened it to strict line-anchored markers — trading false positives for
**universal false negatives**. A third regex is not the fix; a structured
channel is.

### Secondary observations from the same corpus

- **UNCLEAR discards the inner verdict.** `verdict_extractor.py` softens
  `pass→unclear` when the calibrated confidence is below threshold, but drops
  the fact that the structured verdict was e.g. "approved @ 0.85". The
  `unclear_reason` taxonomy (ADR-047 P1) exists; the inner verdict/confidence
  do not surface.
- **`completeness` does not discriminate.** Scores sit in a narrow 5.3–6.6
  band across trivial and complex changes (or fall to the synthetic
  `mean_score * 0.9` estimate), yet carry **0.20 rubric weight** — a
  Q&A-oriented axis acting as a constant drag on code-review verdicts.
- **Balanced tier churns; high tier converges.** Balanced-tier FAILs surfaced
  fresh marginal findings each round instead of confirming fixes (7/9 failed,
  one arithmetically false, one re-litigated). High tier (+ a factual
  informational evidence item) produced substantively real findings every
  time and twice gave explicit fix-acknowledgement. Consistent with the
  overconfidence / calibration literature (arXiv 2508.06225; see Research
  verification).
- **ADR-042 evidence firewall: flag-then-penalize.** The council correctly
  firewalled imperative language inside an *informational* evidence item, then
  cited that flagged "steering" sentence *in the rejection rationale* —
  counting it against the submission rather than flag-and-ignore.
- **Structured non-verdicts work.** `input_too_large` and
  `unclear_reason=low_confidence` were clean, routable outcomes — keep them.

## Research verification (rev 2)

The literature scaffolding was checked by adversarial deep-research (105
agents, 3-vote) against primary sources; the load-bearing statistic was then
independently confirmed by the maintainer against the arXiv HTML.

| Claim | Status | Evidence |
|---|---|---|
| The cited "86.3% acc / 6.4% ECE vs 77.4%" figures are real | **VERIFIED** | arXiv [2508.06225](https://arxiv.org/abs/2508.06225) (Tian et al., *Overconfidence in LLM-as-a-Judge*): **LLM-as-a-Fuser** = 86.29% / 6.42% ECE vs single-judge Self-Confidence baseline 77.43% / 11.78% on JudgeBench (Tables 1 & 4, confirmed against the [v3 HTML](https://arxiv.org/html/2508.06225v3)). Majority-vote / confidence-weighted-vote = 80.00%. |
| Method name "critique-fusion" | **CORRECTED** | The method is **LLM-as-a-Fuser** (fuses decisions *and* rationales; ships a `TH-Score` calibration metric). The ADR's "critique-fusion" label was a misremember; the decoy papers 2508.16889 (ObjexMT) and 2601.05420 (single-judge debiasing) report neither the method nor these numbers. |
| Verdict–evidence decoupling / post-hoc rationalization is an established LLM-judge pathology | **VERIFIED** | Multi-paper finding: superficial cues drive verdicts the rationale never mentions; judges trust asserted reasoning over observable evidence. Directly supports Parts 1–3. |
| Structured rationale *alone* fixes it | **REFUTED (important nuance)** | Free-text/JSON rationale does **not** close the gap; a protocol that **locks cited evidence BEFORE scoring** ("Proof-Before-Preference") substantially reduces rationalization. ⇒ Part 1 must emit findings *before* the verdict, not alongside it. |
| LLM judges are overconfident / miscalibrated; reasoning models are better-calibrated judges | **VERIFIED** | Overconfidence documented (2508.06225 + others); reasoning/extended-CoT models strictly better calibrated in 33/36 model×dataset settings — corroborates the observed "high tier converges, balanced tier churns". |
| Critique/evidence **fusion is *necessary*** to beat independent tallying | **MIXED — do not overclaim** | Some fusion aggregators beat tallying, but PoLL ("Replacing Judges with Juries", arXiv [2404.18796](https://arxiv.org/abs/2404.18796)) shows a **diverse panel with simple independent voting already beats a single strong judge, ~7× cheaper**. llm-council already does diverse-panel tallying. ⇒ Part 5 is "does the Fuser beat our *existing panel*", not "adopt fusion". |

### Council review (rev 2, high tier)

The Council endorsed the core diagnosis and the structured-findings fix, and
raised amendments, all folded in above:
1. **Proof-Before-Preference needs enforcement, not a prompt** → Part 1
   commits to two-phase / constrained decoding.
2. **Bidirectional consistency guard** → Part 2 now also guards `pass` +
   critical findings; zero-finding FAILs survive; any re-run is non-coercive.
3. **`inner_verdict` is a footgun as a top-level field** → Part 3 nests it
   under `diagnostics`, telemetry-only.
4. **P4 (completeness) is orthogonal** → deferred to its own follow-up.
5. **P5 must be bounded** → pre-registered accept thresholds.
6. **Breaking change** → MAJOR bump / feature flag, not a CHANGELOG line.
One council claim was **rejected on the code**: `blocking_issues` is not
`List[str]` (no type-crash risk) — it is already `List[BlockingIssueResponse]`,
the exact object shape `findings[]` produces.

## Decision (proposed)

Five parts, ordered by leverage. Parts 1–3 are the core structural fix; 4 is
deferred to a follow-up; 5 is a bounded spike.

### 1. Structured findings channel (P0)

Have the chairman emit findings as **structured data**, not prose to be
scraped. Extend the ADR-025b verdict output (or add a sibling structured
field the chairman is prompted to fill) with:

```
findings: [ { severity: critical|major|minor,
              description: str,
              location: str | null,        # file:line where derivable
              dimension: str | null } ]     # which rubric axis it maps to
```

Populate `blocking_issues` from `findings` filtered to
`severity == critical` (and any ADR-042 blocking-evidence dispositions),
**not** from the prose regex. Non-critical findings (`major`/`minor`/`info`)
stay in `findings[]` (not dropped) but do not gate. **No type break** (Council
rev-2): `blocking_issues` is already `List[BlockingIssueResponse]`
(`{severity, description, location: Optional[str]}`, `schemas.py`), the exact
shape `findings[]` produces — this is object→object, and `location` already
permits `null` (a holistic finding with no line). Keep `extract_blocking_issues`
only as a fallback for models that don't return structured findings, and set
`findings_source: structured|fallback` + `fallback_reason` on the response so
consumers see when the channel degraded.

**Findings precede the verdict — and it must be *enforced*, not just
prompted (Council rev-2).** Research verification refuted the weaker version:
a structured rationale emitted *alongside* the verdict does not fix decoupling.
But JSON has no ordering guarantee and generation order alone is brittle, so
"findings first" must be enforced by one of: **constrained decoding / structured
outputs** (schema topological order), **two-phase generation** (emit findings,
then a second call renders the verdict from them), or at minimum a **parse-time
co-emission + ordering check**. The ADR commits to two-phase or constrained
decoding — not a bare prompt instruction ("Proof-Before-Preference").

### 2. Verdict–evidence consistency guard

Guard **both directions** (Council rev-2): `fail`/`unclear` with empty
`findings` (rejection with no justification), AND `pass` with any
`severity == critical` finding (approval over a stated blocker). Either
inconsistency emits a structured `verdict_evidence_mismatch` marker and is
logged. This makes the pathology **observable** instead of silently producing
`blocking_issues: []`.

**A zero-finding FAIL is legitimate and must survive** (Council rev-2): a
holistic rejection ("fundamentally wrong approach") may have no line-level
finding. The marker is observability, never a forced flip. If a bounded re-run
is enabled behind a flag it must be **non-coercive** — it may ask the model to
*localize its existing failure* (fill `findings`), never to *reconsider the
verdict*. Coercing localization risks fabricated findings or a false `pass`
just to satisfy the parser.

### 3. Surface the inner verdict on UNCLEAR

When a structured "approved @ c" is softened to `unclear` because
`c < threshold`, carry `inner_verdict` and `inner_confidence` (and the
calibrated value) so automation can distinguish "approved but under threshold"
from "genuinely undecided" without parsing prose. **Nest these under a
`diagnostics: {}` object** (Council rev-2) and document them as telemetry-only,
so consumers don't parse `inner_verdict` to bypass the low-confidence safety
gate — the softening to `unclear` is the contract; the inner state is for
threshold tuning and observability, not control flow.

### 4. Recalibrate `completeness` — DEFERRED to a follow-up (Council rev-2)

`completeness` (0.20 weight) does not discriminate for code review — drop its
weight in the code-review rubric profile or redefine it as a code-relevant axis
("tests/edge-cases covered"). But this is a **scoring-heuristic tweak,
orthogonal to the evidence-plumbing defect** (it lives in the stage-2 rubric
path, `verdict_extractor.py:135`, not the `blocking_issues` regex), so it is
**deferred out of this ADR** to keep the P0/P1 structural fix unblocked.
Re-measure `completeness` *after* P0/P1 lands to confirm the flatness isn't
entangled with the findings channel, then reweight in its own change.

### 5. (Spike) evaluate a fuser aggregator against our existing panel

Evaluate whether an **LLM-as-a-Fuser** aggregator (one strong model fusing the
panel's decisions *and* rationales — Tian et al., arXiv 2508.06225: 86.29% acc
/ 6.42% ECE vs 77.43% for the best single judge on JudgeBench) beats
llm-council's **current** diverse-panel independent tallying.

Framed carefully, because the research verification found the "fusion is
necessary" premise is **mixed**: PoLL ("Replacing Judges with Juries", arXiv
2404.18796) shows a diverse panel with *simple independent voting* already
beats a single strong judge ~7× cheaper — and that is essentially what
llm-council already does. So the question is not "single judge → fusion" (a
straw man; we don't use a single judge) but "existing panel-tallying → fusion:
does it add enough calibration/accuracy to justify the extra synthesis cost?"
A research spike, not a committed change — and **pre-registered** to keep it
bounded (Council rev-2): before running it, fix the thresholds that would
justify adopting a Fuser — a minimum accuracy/calibration delta over the
existing panel, a maximum added latency, and a maximum cost multiple. If the
spike doesn't clear all three, the incumbent panel-tallying stays. Note the
2508.06225 baseline is *Self-Confidence* (a per-judge confidence method), not
self-consistency.

## Consequences

**Positive.** Gates key on structured findings instead of prose regex, so
`blocking_issues` reflects reality; the verdict–evidence mismatch becomes
observable; UNCLEAR carries the inner verdict for cleaner routing; the rubric
stops dragging on a non-signal. Directly unblocks consumers whose automation
keys on blocking count (the reported downstream pain).

**Negative / cost.** The chairman prompt gains a structured-output
requirement (a compatibility surface across models; needs the same
JSON-won't-parse fallback the rubric already has). **`blocking_issues`
semantics change is a breaking change under Hyrum's Law** (Council rev-2):
consumers built gating logic against always-`[]`, and populating it on FAIL
wakes that dormant logic. It warrants a **MAJOR version bump** (or a transition
feature flag defaulting to the new behavior with an opt-out) — not just a
CHANGELOG line. Parts 1–3 touch the verdict-extraction hot path and need golden
tests against both the structured and fallback paths; the two-phase/constrained
enforcement adds one generation hop on the chairman path.

**Neutral.** `input_too_large` / `unclear_reason` structured outcomes are
unchanged (keep). No new external dependency.

## Compliance / Validation

- Unit: chairman returns structured `findings` ⇒ `blocking_issues` =
  critical-severity findings; a FAIL with findings never yields
  `blocking_issues: []`.
- Unit: prose-only chairman (no structured findings) ⇒ fallback regex path,
  response flags `findings_source: fallback`.
- Unit: `verdict=fail` + empty findings ⇒ `verdict_evidence_mismatch` marker
  present.
- Unit: softened UNCLEAR carries `inner_verdict`/`inner_confidence`.
- Regression: the #355 corpus (approval prose like "critical issues resolved")
  must NOT fabricate blocking issues under the structured or fallback path.
- Corpus replay: re-run the epic-loop 25-call log (verification_ids in
  `council-verify-stats.md`) and assert FAILs now carry non-empty findings.
