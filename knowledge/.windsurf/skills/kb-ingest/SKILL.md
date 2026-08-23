---
name: kb-ingest
description: "Fetch a URL into the knowledge base's staging area as a reviewable source note. Use when the user shares a link, article or repo they want captured, or says to ingest, capture or save a source."
---

# kb-ingest

`kb ingest <url...>`

Capture a source. This does not judge whether the material is any good — that is `kb-assess`, and keeping the two apart is what makes `staging/` a reviewable buffer rather than a chute into the corpus.

1. `kb ingest <url>` — fetches, extracts readable content, writes `staging/<slug>.md`.
2. Check the slug it chose. Pass `--slug` if the page title produced something unhelpful.
3. Tags land as `#unsorted` by design; classification is `kb-facets`, later.

The note is now staged, not accepted. Run `kb-assess` next.

**Do not** hand-write a staging note to skip the fetch: the `**Source:**` marker is what later becomes the concept's provenance and its revalidation baseline.

---

The contract is `kb verify` in CI, not this file. If a command refuses, read the remedy in its JSON output and act on that. Policy: `.kb/POLICY.md`.
