---
name: kb-verify
description: Validate the knowledge base and regenerate its index. Use before committing, after any bulk change, or when asked whether the vault is healthy or consistent.
verb: kb verify | kb index
paths: "**/*.md"
---

`kb verify` is the contract. CI runs it; adapters like this one only make a first draft right.

- `kb verify` — schema, required sections and their order, derivation, index freshness, links, card ids, facet conformance, queue staleness.
- `kb index` — regenerates `concepts/_index.md`. Generated; never hand-edit it.

Output is JSON outside a terminal, with a stable code and an explicit remedy per finding. **Act on the remedy, not on the raw text.** Findings carry severity: errors block, warnings are recorded gaps.

An unresolved wikilink is a **warning by design** — the corpus asserting a page should exist. Do not delete or rewrite it to make the warning go away.
