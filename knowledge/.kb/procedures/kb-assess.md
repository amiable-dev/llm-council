---
name: kb-assess
description: Judge whether a staged source is worth promoting into a concept, using the repo's promotion rubric. Use after kb-ingest, or when asked whether something is worth keeping, promoting or discarding.
verb: kb assess <file> [--verdict v.json]
paths: staging/**
---

You supply the judgment; the CLI supplies the routing. It never calls a model.

1. `kb assess staging/<slug>.md` — emits a self-contained task: disqualifiers, ordinal dimensions with exemplars drawn from real notes, and the nearest existing concepts.
2. Answer it as JSON matching `rubric-verdict.schema.json`.
   - **The task arrives wrapped in an envelope.** Copy `envelope.task_id` into your answer verbatim as a top-level `task_id` field — an answer without it is refused (KB022.1). If the file changed since the task was emitted, submission is refused as stale (KB022.2): re-emit and re-answer; never edit the file to match your answer. A task already applied refuses replay (KB022.4).
   - Optionally attest who you are: `"supplier": {"class": "model-single", "id": "<model>", "version": "<ver>"}` — recorded in the audit trail, never in notes. If you also produced the material you are judging, say so: `"proposer_overlap": true`.
   - **Answer the disqualifiers honestly and first.** Any one of them true discards the note regardless of how good it otherwise is. Do not soften a true disqualifier because the dimensions look strong — that is exactly the failure this rubric shape exists to prevent.
   - Rate dimensions on the ordinal scale only. Never a number.
   - Every judgment needs a one-sentence rationale; a queued item is reviewed from the rationale, not by re-reading the source.
3. `kb assess staging/<slug>.md --verdict v.json` — validates and routes.

Routing is a lookup table, not arithmetic. `promote` and `split` proceed; `queue` waits for a human; `discard` is a recommendation — **never delete the file yourself** (`.kb/POLICY.md`).
