---
name: kb-promote
description: Turn an assessed staging note into one or more concept notes. Use after kb-assess routes to promote or split, or when asked to write up a staged source as a concept.
verb: kb promote <slug> [--draft d.json] [--apply]
paths: concepts/**
---

You write the content; the CLI writes the structure. Sections are rendered from validated fields, so a promoted concept cannot have a missing or misordered section.

1. `kb promote <slug>` — emits the drafting task with the prior assessment and the nearest existing concepts.
2. Answer as JSON matching `concept-draft.schema.json`.
   - **The task arrives wrapped in an envelope.** Copy `envelope.task_id` into your answer verbatim as a top-level `task_id` field — an answer without it is refused (KB022.1). If the file changed since the task was emitted, submission is refused as stale (KB022.2): re-emit and re-answer; never edit the file to match your answer. A task already applied refuses replay (KB022.4).
   - Optionally attest who you are: `"supplier": {"class": "model-single", "id": "<model>", "version": "<ver>"}` — recorded in the audit trail, never in notes. If you also produced the material you are judging, say so: `"proposer_overlap": true`.
   - One idea per concept. If the note carries several unrelated ideas, return several concepts — the split is the finding.
   - `definition` is one paragraph. No list markers; the renderer rejects them.
   - Every relationship needs a clause saying **how** the two relate. A bare link is not a relationship.
   - Only reference slugs from `existing_concepts` or from another concept in the same response.
3. `kb promote <slug> --draft d.json` to preview, then `--apply`.

Promotion is refused without a recorded assessment. If you find yourself reaching for `--force`, run `kb-assess` instead.

Afterwards the new concept is **isolated** — it links outward, nothing links back. Run `kb-link` to add reciprocal backlinks.
