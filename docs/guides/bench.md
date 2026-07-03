# Quality Benchmark

A governed golden dataset guards council quality against silent drift, and a
configuration matrix answers the commercial question — *when does
deliberation pay?* — from real ADR-011 costs (ADR-048).

!!! danger "Real API spend"
    Every bench run costs money. Runs are on-demand or nightly — **never
    per-PR**. Caps: `LLM_COUNCIL_BENCH_MAX_USD` per run (default $2.00,
    enforced against actuals mid-run with graceful partial abort) and
    `LLM_COUNCIL_BENCH_MONTHLY_USD` month-to-date guard (default $30).

## Drift regression

```bash
llm-council bench run                # exit 0 within envelope / 1 drift / 2 aborted
llm-council bench baseline --set     # snapshot the last run as the reference
llm-council bench report [--format json] [--publish docs/bench-results.md]
```

The dataset (`bench/dataset/v1/`, 20 original items across coding /
reasoning / factual / judgment) uses expected-quality **envelopes**: any-of
key-content groups (never exact-string) plus a consensus score floor.
Governance rules — provenance, PR-only changes, no silent goal-post moves —
live in [`bench/dataset/GOVERNANCE.md`](https://github.com/amiable-dev/llm-council/blob/master/bench/dataset/GOVERNANCE.md).

## Quality per dollar

```bash
llm-council bench matrix --configs solo-members,council,graduated
```

Runs the same items across each council member solo, the full council, and
ADR-044 graduated depth, rendering a quality-per-dollar table from actual
costs. Unknown/zero cost renders `n/a` — never a fabricated ratio.
Methodology and the caveats that must accompany published numbers:
[`bench/METHODOLOGY.md`](https://github.com/amiable-dev/llm-council/blob/master/bench/METHODOLOGY.md).

## Published results

`bench report --publish docs/bench-results.md` regenerates the
[results page](../bench-results.md) directly from harness output — dataset
version, run date, spend, and per-item table are stamped by the run that
produced them, never hand-edited.

## Eval-framework bridges

Drive the council as a target from external eval suites — see
`examples/eval_bridges/` (DeepEval and RAGAS round-trips;
`make_council_eval_callable`, `council_to_ragas_row`).
