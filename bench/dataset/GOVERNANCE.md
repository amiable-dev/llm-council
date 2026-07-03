# Bench Dataset Governance (ADR-048)

> Measurement definitions and result caveats: [`../METHODOLOGY.md`](../METHODOLOGY.md).

The golden dataset under `bench/dataset/vN/` guards council quality against
silent drift. Rules (per ADR-048 council feedback):

1. **Versioned in-repo, changed only by PR review.** `v1/` is immutable in
   spirit: fixes to typos are fine; changing an item's substance means a new
   item id (or a new `v2/` when the set is re-baselined).
2. **Original or verifiably licensed.** Every item carries `provenance`.
   No copied benchmark questions, no PII, ever.
3. **Envelope changes require justification.** A PR that widens or moves an
   item's `envelope` must include a note explaining the new expected range —
   no silent goal-post moves.
4. **Balanced domains.** Items span coding / reasoning / factual / judgment;
   additions should keep the spread roughly even.
5. **Assertions are key-content, not exact-string.** `must_contain` holds
   any-of groups (every group needs at least one case-insensitive hit) so
   phrasing freedom never fails a correct answer.

## Item schema

```json
{
  "id": "domain-short-slug",
  "domain": "coding|reasoning|factual|judgment",
  "prompt": "...",
  "envelope": {"must_contain": [["either", "or"], ["required"]], "min_score": 0.3},
  "provenance": "original, authored ... (date)",
  "rationale": "why this item earns its API spend"
}
```

## Spend

Runs cost real money: nightly/scheduled or on-demand only, **never per-PR**.
Caps: `LLM_COUNCIL_BENCH_MAX_USD` per run (default $2.00, enforced before
each item and against actuals after), `LLM_COUNCIL_BENCH_MONTHLY_USD`
month-to-date guard (default $30, summed from run artefacts under
`.council/bench/runs/`).
