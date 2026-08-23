---
trigger: model_decision
description: Create or refresh the spaced-repetition flashcard deck for a concept. Use when asked to make, update or improve flashcards or study material for a concept.
---

`kb cards <slug> [--draft c.json] [--apply]`

Refresh matches cards by their minted id, which is the only reason it can rewrite a card without duplicating or orphaning it.

1. `kb cards <slug>` — emits the concept plus any existing cards with their ids.
2. Answer as JSON matching `card-draft.schema.json`.
   - **The task arrives wrapped in an envelope.** Copy `envelope.task_id` into your answer verbatim as a top-level `task_id` field — an answer without it is refused (KB022.1). If the file changed since the task was emitted, submission is refused as stale (KB022.2): re-emit and re-answer; never edit the file to match your answer. A task already applied refuses replay (KB022.4).
   - Optionally attest who you are: `"supplier": {"class": "model-single", "id": "<model>", "version": "<ver>"}` — recorded in the audit trail, never in notes. If you also produced the material you are judging, say so: `"proposer_overlap": true`.
   - One idea per card; the question must be answerable from the concept alone.
   - **Keep the `id`** of any card you are revising.
   - Set `semantic_change: true` **only** when the card now asks a different question. It drops that card's review history, so never set it for a wording fix.
   - **Omit a card to leave it untouched.** Cards are never deleted automatically, and omission is not a vote against a card.
3. `kb cards <slug> --draft c.json` to preview, then `--apply`.

An unknown id is refused: it means the draft was written against a stale read of the deck. Re-read it.

The contract is `kb verify` in CI, not this file. If a command refuses, read the remedy in its JSON output and act on that. Policy: `.kb/POLICY.md`.
