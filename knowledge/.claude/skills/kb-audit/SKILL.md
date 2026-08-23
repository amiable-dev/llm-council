---
name: kb-audit
description: "Semantic lint — contradictions, stale claims, concept gaps, graph rot. Use after a batch of promotions, when the corpus feels inconsistent, or on a maintenance pass."
---

# kb-audit

`kb audit [--only <check>] [--findings f.json]`

Candidates are mechanical (parameters pinned and hashed into the task); the judgment is yours; nothing is ever edited by this verb.

1. `kb audit [--only contradictions|stale-claims|concept-gaps|graph-rot] [--limit N]` — emits candidates with the excerpts needed to judge them.
2. Answer as JSON matching `audit-finding.schema.json`.
   - Copy `envelope.task_id` verbatim as `task_id`.
   - Every quote must be a **verbatim substring of the named note** — checked mechanically; a reconstructed quote is refused.
   - `cannot-tell` is a legitimate verdict. Your rationale explains the judgment; it is never treated as evidence (internal citations are navigation, never corroboration).
3. `kb audit --findings f.json` — validates, queues actionable findings (stable identity: reruns dedupe), and writes a derived report under `maintenance/`.

Findings age in the queue (KB011). A tension worth keeping is resolved with `kb queue accept-tension <id> --why "<rationale>"` — governed as open, without reddening the corpus.

---

The contract is `kb verify` in CI, not this file. If a command refuses, read the remedy in its JSON output and act on that. Policy: `.kb/POLICY.md`.
