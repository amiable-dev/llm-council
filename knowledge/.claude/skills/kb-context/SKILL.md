---
name: kb-context
description: "Compile the exact context a task needs — target notes, binding policy, graph neighbours, prior artifacts — as one deterministic bundle. Use before drafting cards, reviewing a promotion, judging an audit pair, or answering from the corpus."
---

# kb-context

`kb context --for <task> <args>`

Run `kb context` and work from the bundle instead of assembling context by hand — every harness then judges from identical input, and the bundle refuses to compile against a stale index rather than silently varying.

- `kb context --for cards-refresh <slug>` · `--for promote-review <slug>` · `--for audit-pair <a> <b>` · `--for research-brief --query "<q>"` · `--for query-answer --query "<q>"`
- The bundle is JSON: targets, the policy excerpts that bind the task, ranked 1-hop neighbours, prior artifacts (deck, evidence verdicts, assessment), and the response schema for your answer. Everything run-variant lives in the `tail`; the rest is byte-stable (same corpus, same bundle).
- `--budget <chars>` trims whole items by priority (artifacts, then edges, then policy — never targets or the schema) and reports every trim in the tail. An impossible budget fails with the minimum viable size.

If it refuses with `CONTEXT_STALE_INDEX`, run `kb index` first. If it refuses with KB020, an anchor in `.kb/context-anchors.yml` dangles — fix the anchor, never delete the policy heading.

---

The contract is `kb verify` in CI, not this file. If a command refuses, read the remedy in its JSON output and act on that. Policy: `.kb/POLICY.md`.
