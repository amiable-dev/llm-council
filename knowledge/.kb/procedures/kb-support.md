---
name: kb-support
description: Judge whether a concept's citations actually support its claims. Use when validating a note's evidence, after revalidate reports drift, or when asked whether a source really backs what the note says.
verb: kb support <slug> [--verdicts v.json]
paths: concepts/**, .kb/evidence/**
---

You judge claim-by-claim; the CLI binds every verdict to the exact snapshot you judged. This is an **evidence-verdict** task — panels are excluded by the envelope; answer as a single model or defer to a human.

1. `kb support <slug>` — fetches source snapshots (network; cached under `.kb/cache/`) and emits one task pairing the note's body with each citation's extracted text.
2. Answer as JSON matching `support-verdict.schema.json`.
   - Copy `envelope.task_id` verbatim as `task_id`. A changed snapshot refuses as stale (KB022.2) — re-emit; never edit anything to match your answer.
   - Every `claim_quote` must be a **verbatim substring of the note body** — it is checked mechanically, and a paraphrase is refused.
   - Judge only from the extracted text. `UNCERTAIN` when the source is silent; `CONTRADICTED` when it says otherwise. Never import outside knowledge into a verdict.
3. `kb support <slug> --verdicts v.json` — records verdicts into the append-only evidence store; anything non-SUPPORTED lands in the queue for a human.

The store is history: a wrong verdict is superseded by a later observation, never edited.
