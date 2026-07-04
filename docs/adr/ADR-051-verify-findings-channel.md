# ADR-051: Verify Findings Channel & Verdict–Evidence Consistency

**Status:** Draft 2026-07-04
**Date:** 2026-07-04
**Decision Makers:** llm-council maintainers (review requested)
**Proposed by:** maintainer triage of a downstream field report (amiable-dev/epic-loop)
**Relates to:** ADR-025b (Jury Mode / binary verdict), ADR-034 (verification), ADR-042 (evidence injection), ADR-047 (verifier calibration & unclear taxonomy), ADR-016 (rubric scoring)
**Tracking:** [#482](https://github.com/amiable-dev/llm-council/issues/482)

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
  overconfidence / aggregation literature (arXiv 2508.06225v2, 2508.06225).
- **ADR-042 evidence firewall: flag-then-penalize.** The council correctly
  firewalled imperative language inside an *informational* evidence item, then
  cited that flagged "steering" sentence *in the rejection rationale* —
  counting it against the submission rather than flag-and-ignore.
- **Structured non-verdicts work.** `input_too_large` and
  `unclear_reason=low_confidence` were clean, routable outcomes — keep them.

## Decision (proposed)

Five parts, ordered by leverage. Parts 1–3 are the core; 4 is a rider; 5 is a
spike.

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
**not** from the prose regex. Keep `extract_blocking_issues` only as a
fallback for models that don't return structured findings, and mark that
fallback in the response so consumers know the channel degraded.

### 2. Verdict–evidence consistency guard

When `verdict == fail` (or `unclear`) but `findings` is empty, the result is
internally inconsistent (rejection with no justification). Emit a structured
`verdict_evidence_mismatch` marker on the response and log it; optionally,
behind a flag, trigger a single bounded re-run. This makes the pathology
**observable** instead of silently producing `blocking_issues: []`.

### 3. Surface the inner verdict on UNCLEAR

When a structured "approved @ c" is softened to `unclear` because
`c < threshold`, carry `inner_verdict` and `inner_confidence` (and the
calibrated value) as structured fields on the response. Automation can then
distinguish "the council approved but under threshold" from "the council was
genuinely undecided" without parsing prose.

### 4. Recalibrate `completeness` for code-review verification

`completeness` (0.20 weight) does not discriminate for code review. Either
drop its weight in the code-review rubric profile, or redefine it as a
code-relevant axis (e.g. "tests/edge-cases covered"). A non-signal dimension
must not carry a fifth of the weighted score.

### 5. (Spike) critique-fusion aggregation

Evaluate replacing independent-verdict tallying with a critique-fusion
aggregator (one strong fuser synthesizing member critiques). The literature
(arXiv 2508.06225v2: 86.3% acc / 6.4% ECE vs 77.4% best-single) and the
corpus (high-tier synthesis quality drove verdict quality) both point this
way. Scoped as a research spike, not part of the core change.

## Consequences

**Positive.** Gates key on structured findings instead of prose regex, so
`blocking_issues` reflects reality; the verdict–evidence mismatch becomes
observable; UNCLEAR carries the inner verdict for cleaner routing; the rubric
stops dragging on a non-signal. Directly unblocks consumers whose automation
keys on blocking count (the reported downstream pain).

**Negative / cost.** The chairman prompt gains a structured-output
requirement (a compatibility surface across models; needs the same
JSON-won't-parse fallback the rubric already has). `blocking_issues`
semantics change — a **behavior change for consumers** that must be versioned
and documented (today they receive `[]`; after, they receive real findings on
FAIL). Parts 1–3 touch the verdict-extraction hot path and need golden tests
against both the structured and fallback paths.

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
