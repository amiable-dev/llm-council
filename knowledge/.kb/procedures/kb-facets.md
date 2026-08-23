---
name: kb-facets
description: Classify concepts against the repo's closed facet axes — domain, maturity and source type. Use when notes are unclassified, or when asked to categorise, tag or organise concepts.
verb: kb facets [--sample N] [--draft f.json] [--apply]
paths: concepts/**
---

1. `kb facets --sample 25` — a spread across the corpus, not the alphabetical head, which is heavily front-loaded and would exercise one domain.
2. Answer as JSON matching `facet-draft.schema.json`.
   - **The task arrives wrapped in an envelope.** Copy `envelope.task_id` into your answer verbatim as a top-level `task_id` field — an answer without it is refused (KB022.1). If the file changed since the task was emitted, submission is refused as stale (KB022.2): re-emit and re-answer; never edit the file to match your answer. A task already applied refuses replay (KB022.4).
   - Optionally attest who you are: `"supplier": {"class": "model-single", "id": "<model>", "version": "<ver>"}` — recorded in the audit trail, never in notes. If you also produced the material you are judging, say so: `"proposer_overlap": true`.
   - Axis values **must** come from the lists given. Never invent one.
   - Judge `maturity` from **the note**, not from what you know about the field. Those diverge badly: classifying from familiarity produced a 44% emerging rate against a corpus that is genuinely 72%. If the note gives no signal, prefer `emerging`.
   - Nothing fits? Pick the closest **and** file an `axis_proposals` entry. A gap in a closed axis is a defect in the axis, not a missing detail.
   - Uncurated topics are dropped from the write and queued. That is intended.
3. `kb facets --draft f.json` to preview, then `--apply`.

Each value is written twice — a scalar property and a mirrored nested tag — because in Obsidian a nested tag *is* a facet. Both are generated; hand-editing either is a lint failure.

**Sample before any bulk run.** A 25-note sample cut the force-fit rate from 24% to 4% by exposing that the seeded axes were top *tags*, and frequency is not the same property as being a subject area.
