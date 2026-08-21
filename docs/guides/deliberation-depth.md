# Deliberation Depth

*Since v0.42. Part of ADR-044 (compute-optimal deliberation), issue #618.*

## The idea in one paragraph

Every council question costs the same today: all council members answer, all of
them review each other, the chairman synthesizes. But not every question needs
that. When a small council already agrees strongly, adding more members rarely
changes the answer — it just costs more. **Graduated deliberation depth** is the
plan to spend a small council on questions where models agree, and the full
council only where they disagree. Before that behavior ever turns on, llm-council
first *measures* whether it would help you — that measurement is what ships now.

## What runs today: shadow telemetry (always on, changes nothing)

Every full council run now records one line of telemetry answering the question
**"was full depth necessary?"** — computed purely from data the run already
produced, with no extra model calls, no change to your response, and no file
contents. The record is appended to:

```
.council/depth/decisions.jsonl
```

Each line looks like this:

```json
{"ts": 1755772800.0, "entry_point": "run_council_with_fallback",
 "council_size": 5, "mini_council_models": ["model-a", "model-b", "model-c"],
 "css_full": 0.72, "css_mini_counterfactual": 0.8, "confidence": null,
 "decision": "mini_would_suffice", "hypothetical_saved_models": 2,
 "extra_stage2_reviews_if_escalated": 0, "est_saved_usd": 0.031}
```

### How to read `decision`

| Decision | Meaning | What it tells you |
|---|---|---|
| `mini_would_suffice` | The first 3 models agreed strongly, and so did the full council. | A 3-model council would likely have given you the same answer for less money. The savings candidate. |
| `premature_halt_risk` | The first 3 models agreed — but the full council did **not**. | The dangerous case: a depth ladder would have stopped early and missed real disagreement. If this happens often, the feature should stay off. |
| `would_escalate` | The first 3 models disagreed. | The ladder would have escalated to the full council anyway — same answer as today, plus a small extra review cost (`extra_stage2_reviews_if_escalated`). |
| `ladder_inapplicable` | Your council has 3 or fewer members. | There is no smaller rung to try; depth laddering can't help this configuration. |
| `signals_unavailable` / `counterfactual_unavailable` | Ranking data couldn't be parsed. | No conclusion drawn — unknown signals never count as evidence. |

`css_full` and `css_mini_counterfactual` are Consensus Strength Scores (0–1,
higher = stronger agreement; the escalation threshold is 0.7). The mini value is
an *approximation*: it re-scores the first three models' peer reviews as if they
had been the whole council. `est_saved_usd` appears only when real per-model
cost history exists — it is never a guess.

### Reviewing your data

After a few weeks of normal use, a one-liner tells you whether the ladder would
be worth enabling for your workload:

```bash
jq -r .decision .council/depth/decisions.jsonl | sort | uniq -c
```

- Mostly `mini_would_suffice` → the ladder would save you real money.
- A noticeable count of `premature_halt_risk` → the ladder would degrade your
  answers; leave it off.
- Mostly `would_escalate` → your questions genuinely need the full council;
  the ladder would only add overhead.

## What comes later: the ladder itself

`LLM_COUNCIL_GRADUATED_DEPTH=true` (default **false**) will route eligible
requests through the ladder: start with the first 3 council members, check
consensus, and only escalate to the full council when they disagree — reusing
the already-collected answers, so escalation never re-asks a model. It only
applies when your council is *larger* than 3 members (in practice: the `high`
and `reasoning` tiers). Escalations are auditable events, and the optional
budget enforcer can veto one — visibly, never silently.

The flag exists today but activates nothing yet: enabling the active ladder is
deliberately gated on the shadow telemetry above showing, for real workloads,
that savings outweigh the `premature_halt_risk` rate.

## Privacy & footprint

- The telemetry file contains **numbers and model names only** — never your
  question, the responses, or review text.
- It lives in your working directory under `.council/` (already gitignored in
  this repo's convention) and is yours to inspect, truncate, or delete.
- Recording is soft-fail: if the file can't be written, the council run is
  unaffected.
