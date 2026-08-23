---
applyTo: "concepts/**"
---

# kb-link

Find isolated or one-way-linked concepts and propose reciprocal cross-links. Use when a concept is unreachable, after promoting a new concept, or when asked to improve connections between notes.

`kb link check | suggest | --draft l.json [--apply]`

1. `kb link check` — isolated notes (nothing links to them) and one-way links.
2. `kb link suggest` — emits a task with candidates for the weakest-connected notes.
3. Answer as JSON matching `link-draft.schema.json`.
   - **The task arrives wrapped in an envelope.** Copy `envelope.task_id` into your answer verbatim as a top-level `task_id` field — an answer without it is refused (KB022.1). If the file changed since the task was emitted, submission is refused as stale (KB022.2): re-emit and re-answer; never edit the file to match your answer. A task already applied refuses replay (KB022.4).
   - Optionally attest who you are: `"supplier": {"class": "model-single", "id": "<model>", "version": "<ver>"}` — recorded in the audit trail, never in notes. If you also produced the material you are judging, say so: `"proposer_overlap": true`.
   - A relationship needs a clause saying **how** the two relate. "Related to X" is rejected by minimum length, deliberately.
   - Only link to slugs in that note's `candidates`.
   - Prefer few strong links to many weak ones. An empty list is a valid answer.
   - Set `reciprocal: true` when the target note benefits equally from linking back — this is usually the point, since a promoted concept starts isolated however well it links outward.
4. `kb link --draft l.json` to preview, then `--apply`.

Additive only. This never rewrites or removes an existing link — that operation corrupted the predecessor vault (`.kb/POLICY.md`).

---

The contract is `kb verify` in CI, not this file. If a command refuses, read the remedy in its JSON output and act on that. Policy: `.kb/POLICY.md`.
