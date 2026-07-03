# ADR-047: Verifier Calibration & Judge Reliability

**Status:** Draft 2026-07-03
**Date:** 2026-07-03
**Decision Makers:** Chris Joseph, LLM Council
**Related:** ADR-036 (Phase 2 calibration report — this implements that slice), ADR-034 (verify), ADR-015/017 (bias), ADR-022 (tiers), #397/#403 (error surfacing)

---

## Context

Operational evidence from driving five release epics through the verify gate
(2026-07-01→03):

1. **Confidence is miscalibrated.** On real code with zero blocking issues,
   confidence pins at 0.49–0.6 — below the 0.7 PASS threshold — producing
   multi-round "asymptotes" where each re-verify surfaces finer or inverting
   nits instead of converging (documented across PRs #364/#387/#395…). PASS is
   effectively unreachable for scrutinized prose/code even when reviewers find
   nothing blocking.
2. **UNCLEAR conflates three unlike things:** infra failure (chairman call
   errored — billing outage, #397), genuine low confidence, and global
   timeout. Callers (CI gates, epic-loop) need to treat these differently;
   today they all read as exit code 2.
3. **Cost asymmetry:** every gate spends a full council (~4 models × 3 stages)
   even for changes a cheap screen could pass/flag in seconds.

2026 judge research matches: multi-agent judges can *amplify* rather than
cancel bias; lightweight sub-second screening judges are production practice;
confidence signals require calibration against observed outcomes. We own the
calibration corpus: every verify run persists a full transcript + verdict to
`.council/logs`.

## Decision

### Phase 1 — UNCLEAR disambiguation (semantics first)
Split UNCLEAR into machine-readable causes on `VerifyResponse`:
`unclear_reason ∈ {infra_failure, low_confidence, timeout}` (infra detection
uses the #403 `error_status`; timeout uses `timeout_fired`). Exit code stays 2
(compat); the reason field lets automation apply distinct policies (retry
infra, accept-and-audit low-confidence, re-tier timeout). Loop/skill docs
updated to consume it.

### Phase 2 — Confidence calibration from the transcript corpus
Build a calibration analysis over `.council/logs` (verdict, confidence, rubric
scores, blocking count vs. eventual disposition where recorded): fit a simple
monotonic recalibration mapping (e.g. isotonic/binned) and surface BOTH raw
and calibrated confidence on responses. The PASS rule may then use calibrated
confidence — behind a flag, default off, until the mapping is validated
(ADR-036 P2's cross-model calibration report is a by-product).

### Phase 3 — Lightweight screening judge
An opt-in pre-gate: a single quick-tier model scores the change against the
rubric in seconds; unambiguous outcomes (screen says clean AND diff is small/
low-risk) short-circuit to a cheap PASS-with-audit-note, everything else
proceeds to the full council unchanged. Default OFF; every screen decision is
logged with the screen's score so its own calibration can be measured before
trusting it (shadow-first, like ADR-044 P2).

### Phase 4 — Bias-amplification check (report only)
Extend the ADR-015/018 bias pipeline with a reviewer-agreement decomposition
per ADR-036 P2 (do reviewers converge because the work is good, or because of
shared bias/position effects?). Report-only; no gating.

## Consequences

**Positive:** the flagship CI-gate feature becomes trustworthy (distinct
UNCLEAR causes; confidence that means something); screening cuts gate cost for
easy changes; aligns with current judge-reliability research; the asymptote
pattern gets a principled fix instead of a per-session cap heuristic.

**Negative / risks:** calibration data is observational and modest-N
(mitigation: publish CIs, flag-gated adoption, keep raw confidence);
a screening judge is itself a judge (mitigation: shadow-first with logged
decisions; never screens BLOCKING-capable paths silently); changing PASS
semantics affects automation (mitigation: compat exit codes + additive fields
only).

## Definition of Done (per phase)
Code + tests; docs (README verify section, CLAUDE.md, CHANGELOG); LLM-facing
verify tool description documents `unclear_reason` and calibrated confidence;
epic-loop guidance updated to consume the new fields.

## References
- `docs/roadmap-2026-h2.md` item 4 (sources: agent-as-judge survey, bias
  amplification, lightweight judges); memory: verify asymptote + #397 infra
  misdiagnosis; ADR-036 §Phase 2.
