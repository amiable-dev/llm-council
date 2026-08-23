---
applyTo: "concepts/**"
---

# kb-query

Ask the knowledge base a question and get back the relevant concepts with their cross-references. Use whenever the answer might already be in the corpus — before researching, before ingesting a new source, or when asked what the vault says about something.

`kb query "<question>" [--domain D] [--maturity M] [--answer a.json]`

Ask before you fetch. If the corpus already covers something, ingesting another source on it is work that ends in a `duplicate` disqualifier.

1. `kb query "<question>"` — returns ranked concepts with their definitions **and their relationship clauses**. Narrow with `--domain` / `--maturity` when the question is clearly within one.
2. Answer as JSON matching `query-answer.schema.json`.
   - The emission includes a stateless `envelope.task_id`; echo it as `task_id` in your answer. It binds the answer to this corpus state — if the corpus changed, submission is refused and you re-query.
   - Use **only** the concepts returned. The `relationships` on each are the corpus's own cross-references — prefer following them to inferring a connection yourself.
   - Cite every concept you rely on, with a clause saying what it supports.
   - If the retrieved concepts cannot answer the question, **say so and record it in `gaps`** rather than filling the hole from your own knowledge. A gap is a finding: it names the next thing worth ingesting.
3. `kb query "<question>" --answer a.json` — validates, and rejects any citation to a concept that was not retrieved.

A rejected answer means it reached past its evidence. Re-query, widen the limit, or record the gap — do not re-cite from memory.

---

The contract is `kb verify` in CI, not this file. If a command refuses, read the remedy in its JSON output and act on that. Policy: `.kb/POLICY.md`.
