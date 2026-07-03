# Bench Methodology (ADR-048)

## What is measured

- **Quality**: pass rate against the dataset's expected-quality envelopes —
  any-of key-content groups (never exact-string) plus, for council
  configurations, a consensus `min_score` floor from the Borda-aggregated
  peer review.
- **Cost**: ADR-011 **actuals** (`cost_source=provider` where available).
  `cost_known=false` figures are never presented as bills; quality-per-dollar
  renders `n/a` rather than dividing by an estimate or zero.
- **quality/$** = pass_rate / known_cost_usd.

## Configurations

| kind | what runs | score floor |
|------|-----------|-------------|
| `solo:<model>` | one member answers alone | skipped — no consensus signal exists |
| `council` | full 3-stage deliberation | applied |
| `graduated` | council with ADR-044 graduated depth flag on | applied |

## Caveats (read before quoting numbers)

1. **Judge bias**: envelope key-content checks are mechanical, but the
   `min_score` floor inherits the council's own scoring; ADR-047 calibration
   caveats apply (confidence/scores are being calibrated, not ground truth).
2. **Small N**: the v1 dataset has 20 items; per-domain slices are 5 — treat
   deltas under ~2 items as noise.
3. **Fixed configuration**: results are only comparable within a run
   (same models, same dataset version, same day); record
   `bench/dataset/vN` + model pool + date when publishing.
4. **Spend caps can truncate**: aborted/partial runs are marked and are not
   comparable to complete runs; baselines refuse them.

## Reproducing

```bash
# Drift regression against the committed baseline (exit 0/1/2):
llm-council bench run
llm-council bench baseline --set          # snapshot a COMPLETE run as baseline
llm-council bench report [--format json] [--publish docs/bench-results.md]

# Quality-per-dollar matrix:
llm-council bench matrix --configs solo-members,council,graduated --max-usd 2.00
```

Dataset authoring rules (provenance, envelope changes, domain balance):
[`dataset/GOVERNANCE.md`](dataset/GOVERNANCE.md).
