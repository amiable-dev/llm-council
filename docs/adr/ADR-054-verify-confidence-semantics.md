# ADR-054: What `confidence` Means in verify() — and How to Calibrate It

**Status:** Proposed 2026-07-11 (rev 2 — council review 2026-07-12)
**Date:** 2026-07-11

**Review history:**
- **rev 2** — council review of rev 1 (`verify`, tier=reasoning, structured findings, `b270c7f3`, **fail**, 1 critical / 1 major / 1 info) on v0.40.0 code. Accepted both substantive findings: (critical) the `verdict_source` table described the *pre-#562* mechanical confidence while a later section described *post-#562* — a self-contradiction, now reconciled (the table states the current conditional, the corpus is labelled pre-#562); (major) **D2** was mislabelled "additive" when it is a value-semantics change (identity-passthrough → `None`) — reworded, with the note that the field is already `Optional[float]` so it is not a type-break. The `info` finding (the doc is a proposal with an open fork) is by design. **Meta:** the review verdict was itself `fail @ confidence 0.26` on the mechanical path — a live instance of this ADR's thesis (a mechanical `fail` carrying a saturated-agreement confidence that means nothing). It also confirmed the v0.40.0 fixes in production: `verdict_source=mechanical`, all stages completed, stage 3 got 16.7s of the deadline (no starvation — #545), and the verdict came from `policy(findings)` not a collapsed confidence (#560/#562).
**Decision Makers:** llm-council maintainers (review requested)
**Proposed by:** maintainer triage of [#563](https://github.com/amiable-dev/llm-council/issues/563), surfaced while fixing [#560](https://github.com/amiable-dev/llm-council/issues/560) (mechanical-gate confidence)
**Relates to:** ADR-047 P2 (confidence calibration), ADR-051 (mechanical gate — verdict as a pure function of findings), ADR-016 (rubric scoring), ADR-025b (BINARY verdict)
**Tracking:** [#563](https://github.com/amiable-dev/llm-council/issues/563)

---

## Context

Every `verify` response carries `confidence` (0–1) and `confidence_calibrated`
(that value passed through a fitted monotonic mapping, ADR-047 P2). The PASS
threshold consumes the calibrated value behind `LLM_COUNCIL_CALIBRATED_CONFIDENCE`
(default off). `confidence_calibrated` is **always reported**, whether or not the
flag is on.

The problem, in one sentence: **`confidence` is not one quantity, so the thing
ADR-047 calibrates is a category error.**

### `confidence` is three different numbers wearing one name

Depending on which path produced the verdict, `confidence` is:

| `verdict_source` | what `confidence` actually is (current, post-#562) |
|---|---|
| structured verdict parsed | the **chairman's self-reported** confidence |
| `mechanical` (ADR-051, as of #562) | **conditional**: the chairman's self-report when its verdict concords with `policy(findings)`, **else** `calculate_confidence_from_agreement` — a stage-2 reviewer-agreement heuristic over rubric means |
| `legacy` (prose fallback) | `0.4 × prose-regex signal + 0.6 × the agreement heuristic` |

This is *worse* than one heuristic per path, not better: the mechanical path is
itself a **conditional between two of these quantities** (self-report or
agreement), chosen per-run by whether the chairman happened to concord — so its
distribution is bimodal by construction. Before #562 the mechanical path was
purely the agreement heuristic; that is the state the corpus below was collected
under, and it is what makes the pre/post-#562 distinction load-bearing (see
"#560/#562 moved the target again").

These are not the same measurement lightly rescaled — they are different
quantities with different supports. Measured across **539 local verify
transcripts** (the **pre-#562** corpus from the #560 investigation, when the
mechanical path was purely the agreement heuristic), for the **same verdict**
(`fail`, chairman said `rejected`):

- median reported confidence on the **legacy** path: **0.95**
- median reported confidence on the **mechanical** path: **0.29**

And the chairman's self-report — the input on the structured path — is
**saturated**: across the corpus it never drops below 0.85 (stdev 0.034;
`0.95` alone accounts for 345 of 539 runs). A variable with almost no spread
carries almost no information to calibrate.

### Why this makes ADR-047's calibration unsound

`fit_from_dispositions` (`verification/calibration.py`) pairs `(r.confidence,
disposition)` and fits a PAV/isotonic mapping — **with no record of which
`verdict_source` produced each `confidence`.** So a single monotonic curve is
fitted across a mixture of three distributions whose medians differ by 0.66 for
identical verdicts. The curve learns the *mixture proportions of your corpus*,
not a calibrated probability. This is very likely why calibration ships
**off by default with an identity fallback** — it cannot learn anything useful
from a category error, so the safe default is to not use it.

### #560/#562 moved the target again

The mechanical-gate fix ([#560](https://github.com/amiable-dev/llm-council/issues/560)/[#562](https://github.com/amiable-dev/llm-council/issues/562))
replaced the mechanical path's pure agreement heuristic with the **conditional**
described in the table above (self-report when concordant, else agreement; the raw
agreement figure is still published as `diagnostics.deliberation_agreement`). So
the 539-transcript corpus below, collected *before* #562, is on a different — and
simpler, unimodal-per-verdict — distribution than one collected after. Fortunately `.council/calibration/dispositions.jsonl` is empty
everywhere today — nothing is lost, and this is the cheapest possible moment to
fix the schema.

### The deeper question ADR-051 forces

ADR-051 made the verdict a **pure function of the findings**
(`verdict_policy`). If the verdict is deterministic given the findings, then
"confidence" can only sensibly mean **uncertainty about the findings** — did the
council actually agree that these are the issues? But none of the three current
`confidence` numbers measure that: the self-report is the chairman's feeling, the
agreement heuristic scores *how well the reviews were written* (ADR-016 rubric
means), and the prose blend mixes both. **We do not currently compute a
confidence in the evidence the verdict is built from.**

---

## Decision

This ADR settles the cheap, clearly-correct parts now and frames the one genuine
fork for the maintainer. It does **not** claim to have found a calibrated
confidence signal — it claims we do not have one, and says what to do about that.

### D1 — Stop calibrating across a mixture (do now)

Record provenance on every calibration record and refuse to fit across sources:

- `CalibrationRecord` and `.council/calibration/dispositions.jsonl` gain
  `verdict_source` and `confidence_source`
  (`self_report | agreement | prose_blend`) plus a `schema_version`.
- `fit_from_dispositions` **fits per `confidence_source`** (returning a mapping
  keyed by source), or refuses / loudly warns when asked to fit a mixed-source
  corpus without an explicit override. A mapping fitted on `self_report` data is
  never applied to a `mechanical`/`agreement` confidence.
- `calibration-report` surfaces the per-source breakdown so the mixture is
  visible, not hidden.

This is small, purely additive, and — because the corpus is empty everywhere —
free to schema-change now. It makes any *future* calibration honest without
deciding what confidence means.

### D2 — `confidence_calibrated = None`, not an identity passthrough (do now)

Today `confidence_calibrated` echoes the raw value when the loaded mapping is the
identity fallback — which reads as "calibrated" when nothing calibrated it. Report
**`None`** when no valid mapping exists for the active `confidence_source`, so a
consumer can tell "calibrated to X" from "not calibrated".

This is a **value-semantics change, not an additive one** — flagged so it is not
undersold (council review, `major`). The field is *already* `Optional[float]` and
*already* `None` in some paths today (`schemas.py`; `verdict_extractor.py`), so it
is type-compatible and introduces no new nullability. But it changes the *value*
in the identity-mapping case from `raw_confidence` to `None`, which breaks a
consumer that assumes `confidence_calibrated` is always numeric. It is not a
type-break; it *is* a behavior change, and it ships as a `### Changed` entry with
a migration note ("`confidence_calibrated` may be `None`; fall back to
`confidence`"). No verdict effect.

### D3 — The fork: demote, or redefine (maintainer decides)

There is no usable confidence signal today. Two honest ways forward; they are not
mutually exclusive (D3a is the short-term truth, D3b the long-term direction).

**D3a — Demote confidence to telemetry (recommended short-term).** Accept that
`confidence` is not a calibrated probability, keep reporting it (labelled as what
it is), and **remove `LLM_COUNCIL_CALIBRATED_CONFIDENCE` as a PASS gate**. The
low-confidence UNCLEAR softening (ADR-051 C5) is the one place confidence changes
a verdict; under a mechanical gate that softening is already suspect (#560 removed
it from the mechanical path). Demoting is the honest reading of the evidence and
costs nothing — calibration already ships off.

**D3b — Redefine confidence as uncertainty about the findings (long-term,
ADR-scale in its own right).** Compute confidence from **inter-reviewer agreement
about the presence of the blocking findings**, not from rubric means or a
self-report. This requires structuring **stage-1** findings (today only the
chairman's stage-3 findings are structured, ADR-051), so it is a real design
change with its own delivery — flagged here, not designed here. If pursued, it is
the only option that yields a confidence that *means something* under the
mechanical gate.

**Recommendation:** ship D1 + D2 now; adopt **D3a** (demote) as the current
default posture; open a follow-up for **D3b** to be scoped when/if stage-1
findings are structured. Do not fit or enable calibration until D1 lands and a
provenance-tagged corpus exists.

---

## Consequences

- **Low risk.** Calibration is already off-by-default; D1/D2 are additive and the
  corpus is empty. D3a removes a gate that is off by default.
- **`confidence_calibrated` semantics change** (D2: identity → `None` when
  uncalibrated). A consumer reading it as a number must tolerate `None` — but it
  was never a *calibrated* number before, so this corrects a mislabel.
- **Dispositions schema versioned** (D1), so a future corpus is fittable per
  source. Pre-#562 records (none exist) would be `schema_version < N` and excluded.
- **D3a is a posture, not code churn** — it is mostly "do not build a gate on
  this" plus documentation. D3b is deferred and explicitly out of scope here.

## What this is not

- **Not a security or adversarial concern.** This is signal validity — whether a
  reported number means what its name implies — not a threat model.
- **Not a claim that the council is miscalibrated.** The council may or may not
  be; we cannot tell, because we never measured a coherent quantity. That is the
  point.
- **Not a decision to remove `confidence` from the response.** It stays, reported
  and (D1) provenance-tagged; it simply stops pretending to be a calibrated gate
  input until one exists.

## Verification of claims

| Claim | Source |
|---|---|
| `confidence` is 3 quantities by `verdict_source` | `verification/verdict_extractor.py` (self-report vs `calculate_confidence_from_agreement` vs prose blend) |
| median 0.95 (legacy) vs 0.29 (mechanical) for the same `fail` | 539 local `.council/logs` transcripts, #560 investigation |
| chairman self-report saturated (min 0.85, stdev 0.034) | same corpus (0.85:19, 0.9:88, 0.95:345, 0.98:1, 1.0:86) |
| `fit_from_dispositions` records no `verdict_source` | `verification/calibration.py:198-202` — pairs `(r.confidence, disposition)` only |
| dispositions corpus empty everywhere | no `.council/calibration/dispositions.jsonl` found on any local repo |
| calibration ships off-by-default, identity fallback | `calibrated_confidence_enabled()` default false; `load_mapping()` → identity when absent |

## Open questions for the decision makers

1. **D3a vs D3b as the stated direction.** Recommended: adopt D3a now, scope D3b
   as a follow-up. Is confidence worth the stage-1-findings investment D3b needs,
   or is "verdict + findings, no confidence gate" (D3a) sufficient for the gate
   use case?
2. **Keep or delete `LLM_COUNCIL_CALIBRATED_CONFIDENCE`.** D3a removes it as a
   gate; do we keep the flag as a no-op for one release, or delete it outright?
3. **Rename `confidence` on the response?** e.g. surface `deliberation_agreement`
   (already in `diagnostics`) as the primary signal and mark `confidence` legacy.
   Cosmetic but reduces the mislabel; may break consumers.
