# ADR-053 Implementation Spec — Delivery Plan, Disclosure, and Child Breakdown

**Companion to:** [ADR-053](ADR-053-verify-file-selection-trust-boundary.md)
**Status:** Proposed 2026-07-10
**Tracking issues:** [#543](https://github.com/amiable-dev/llm-council/issues/543) (security), [#540](https://github.com/amiable-dev/llm-council/issues/540), [#542](https://github.com/amiable-dev/llm-council/issues/542), [#544](https://github.com/amiable-dev/llm-council/issues/544), [#545](https://github.com/amiable-dev/llm-council/issues/545)
**Advisory draft:** [`docs/security/advisory-draft-verify-secret-transmission.md`](../security/advisory-draft-verify-secret-transmission.md)

---

## The sequencing constraint

Everything else follows from one fact:

> **A GitHub Security Advisory published without a fixed version causes
> Dependabot to alert every downstream user with no safe version to upgrade to.**

So the leak fix must merge and release *before* disclosure — and the leak fix is
small, purely narrowing, and independent of ADR-053's design work. That splits
delivery cleanly:

```
P0  leak fix ──────────► release ──────────► P1 disclosure
    (no design decisions)                     (GHSA + CVE + docs)
                                                    │
P2  verify trustworthiness (#544, #545) ────────────┤
                                                    │
P3  ADR-053 design work (content sniffing, receipt, clamp)
```

P0 is deliberately the smallest change that closes the entire leak surface. It
takes **no** position on allowlist-vs-denylist, coverage receipts, or the clamp.
Those are P3 and can take as long as they need.

### Why the security fix front-runs the correctness fix

This ordering leaves #542 unfixed for longer: `.zig`, `.tf`, and `.dart` files
stay silently dropped from review until P3. That is a deliberate trade — a leak
is worse than a gap — but it is a judgment call, and it is the maintainer's to
overturn.

---

## P0 — Leak fix (one PR, patch release)

**Goal:** no credential file can be transmitted, on any code path. Nothing else.

Purely narrowing: it can only cause *fewer* files to be sent. It cannot turn a
correct `pass` into a wrong one. Ships unflagged.

### P0.1 — Chokepoint (ADR-053 Q0, closes #543)

- Introduce `select_blobs(snapshot_id, candidates) -> (selected, omitted)`, where
  `candidates: Iterable[Candidate]`, `Candidate = (path, origin)`.
- Route **every** candidate-path producer through it: the `blob` branch, the
  `tree` branch, and — the bug — the `git diff-tree` branch in
  `_fetch_files_for_verification_async_with_metadata()`.
- Change `_fetch_file_at_commit_async()` to accept a `SelectedBlob` token rather
  than a `str`, so an unfiltered fetch is a type error, not a review miss.
- **Do not** change the text/garbage predicates in this PR. `TEXT_EXTENSIONS`
  stays as-is; it simply now runs on the path where it never ran.

### P0.2 — Secret denylist (ADR-053 Q3a, closes #540)

- Compiled-in, **case-insensitive**, evaluated before any blob is fetched, and
  **not overridable** by any in-repo file.
- Remove `.env`, `.env.example`, `.env.sample`, `.npmrc`, `.yarnrc` from
  `TEXT_EXTENSIONS`. Preserve `*.example` / `*.sample` / `*.template` by **name
  pattern**, not by a fake extension entry.
- Full pattern list: ADR-053 § "Q3 — Permissibility".

### P0.3 — Argv hygiene

- Call `validate_snapshot_id()` at the `run_verification()` boundary
  (`api.py:760`), not only on the Pydantic/HTTP path.
- (No `--` separator work needed yet — P0 adds no pathspec-style git calls. This
  becomes load-bearing in P3.1.)

### P0.4 — Tests

- **Red-team fixture**: one commit touching `.env`, `.npmrc`, `id_rsa`,
  `logo.png`, `yarn.lock`, `main.py`. Assert the assembled prompt contains
  `main.py` and **none** of the others. Parametrised over `target_paths=None`,
  `target_paths=["<dir>"]`, `target_paths=["<explicit file>"]`. **The `None`
  case is the one that would have caught #543 and does not exist today.**
- **Architecture test**: no call to `_fetch_file_at_commit_async()` outside the
  selector module.
- Fix the dead `GARBAGE_FILENAMES` directory entries (`node_modules`,
  `__pycache__`, `.git`) — match every path component, not just the basename.

### P0 Definition of Done

- [ ] All of P0.1–P0.4 merged
- [ ] `CHANGELOG.md` `### Security` entry (this convention already exists — 4
      prior uses; do not invent a new one)
- [ ] `docs/guides/verify.md` + `SECURITY.md` updated
- [ ] **Patch release tagged and on PyPI** — this unblocks P1

### Behaviour change to call out in the changelog

On the `target_paths=None` path, binaries and lockfiles stop appearing in
prompts. Some verdicts will move. That is the fix, not a regression.

---

## P1 — Disclosure (gated on P0's release)

The mechanism that actually protects users is the **GHSA**, not the CVE and not
the README. A published GHSA lands in the GitHub Advisory Database in OSV format
and **auto-alerts every downstream repo via Dependabot**. No README notice
reaches those people.

Order:

1. Draft the advisory from
   [`docs/security/advisory-draft-verify-secret-transmission.md`](../security/advisory-draft-verify-secret-transmission.md).
2. **Verify the affected-version range.** The draft proposes `>= 0.22.0`, traced
   via `git log -S`, but the #380 submodule split masks earlier history. Confirm
   v0.20/v0.21 contain no earlier variant.
3. **Maintainer scores CVSS.** Do not inflate. Not remotely triggerable;
   requires secrets already committed to git. An inflated score costs
   credibility.
4. Set the fixed version on the draft → request a CVE from GitHub (CNA; ~72h
   review) → publish.
5. Ship the doc changes below.

### P1 doc changes

| Surface | Change | Durability |
|---|---|---|
| `SECURITY.md` | Supported versions; PVR enabled; `verify()`-is-not-a-gate non-goal; what is sent to providers | permanent |
| `CHANGELOG.md` | `### Security` entry under the fix release | permanent |
| GitHub release notes | Link the advisory + rotation guidance | permanent |
| `docs/guides/verify.md` | Security note + ADR-053 non-goal | permanent |
| `README.md` | Short dated notice linking the advisory | **temporary — remove after 2 material releases** |

### Already done (2026-07-10)

- Private vulnerability reporting **enabled** on the repository. It was disabled,
  so `SECURITY.md`'s "click Report a vulnerability" instruction did not work —
  which is plausibly why #543 had no private channel to take.
- `SECURITY.md` rewritten (stale 0.18/0.19 support table; non-goal; provider
  disclosure).

### Process failure to record

`SECURITY.md` says "Do NOT open a public GitHub issue for security
vulnerabilities." #543 was filed publicly anyway. Because the exposure is not
remotely triggerable and is self-inflicted by the victim's own `verify` run, the
practical harm is low — but the private-fix window is gone, so publish promptly
once P0 ships.

### README notice — draft copy

```markdown
> **Security advisory (2026-07-xx).** Versions `< <FIX_VERSION>` could transmit
> credential files (`.env`, `.npmrc`, …) **that were committed to your git
> repository** to your configured LLM provider during `verify` / `gate` runs.
> Untracked and `.gitignore`d files were never affected. Upgrade to
> `<FIX_VERSION>` and, if you committed credentials and ran a verification over
> a commit touching them, **rotate those credentials**.
> See [GHSA-xxxx-xxxx-xxxx](https://github.com/amiable-dev/llm-council/security/advisories).
```

### CHANGELOG entry — draft copy

```markdown
### Security

- **verify(): credential files could be transmitted to LLM providers**
  ([GHSA-xxxx-xxxx-xxxx], #543, #540). With `target_paths` omitted — the default
  — no file filter ran at all, so any commit touching a `.env` sent its contents
  to the configured provider, along with binaries and lockfiles. Independently,
  `.env`, `.npmrc`, and `.yarnrc` were on the `TEXT_EXTENSIONS` allowlist.
  Only **committed** content was ever reachable (files are read via
  `git show <sha>:<path>`); untracked and gitignored files were never affected.
  All candidate paths now pass a single non-bypassable selector, and a
  compiled-in, non-overridable secret denylist excludes credential files before
  any blob is read. **If you committed credentials and ran a verification over a
  commit touching them, rotate those credentials.**
```

---

## P2 — Make `verify` trustworthy (unblocks using the council on itself)

Do this before leaning on `verify` to review P3.

- **[#544] Binary-verdict parse failure silently degrades confidence.** Cheap,
  high value. On a *clean* artifact this converts a `pass` into
  `unclear(low_confidence)` — indistinguishable from genuine uncertainty when
  the real cause is a parse failure that should route as `infra_failure`.
- **[#545] ADR-040 waterfall enforces per-model, not per-stage, deadlines.**
  Needs the root-cause pass first (retries vs. serialization) — do not fix
  blind. Cost of not fixing: paid runs that return no verdict.

---

## P3 — ADR-053 design work (no security urgency)

Ships behind `LLM_COUNCIL_FILE_SELECTION = allowlist | shadow | content`,
default `allowlist`, byte-identical when off.

- **P3.1 — Q1 content sniffing.** NUL-in-first-8000-bytes; `.gitattributes`
  `-diff`/`binary` via `git --attr-source=<sha>`; `ls-tree` size pre-filter.
  **Must pass `--` before any pathspec** (P0.3's deferred half). Deletes the
  `TEXT_EXTENSIONS` treadmill and the extensionless-file special case.
- **P3.2 — Q2 reviewability.** `linguist-generated` / `linguist-vendored`;
  `.svg` → noise-by-default.
- **P3.3 — Ignore-file family.** `.llmignore` → `.aiexclude` → `.aiignore` →
  `.cursorignore` → `.codeiumignore`, read from the snapshot, matched with
  `pathspec`. **No seeding** — the built-in denylist is the floor, not a
  template. `ignore --print-defaults` / `--init` / `--explain` as ergonomics.
- **P3.4 — Coverage receipt.** Additive, default-ON, no type break. Conservation
  invariant + `TestVerifyResponseFieldDrift` (ADR-051 C6 precedent).
- **P3.5 — The clamp.** `pass` not representable over an unreviewed changed or
  explicitly-named file → `unclear(incomplete_coverage)`.
  `llm-council gate` hard-errors on `LLM_COUNCIL_COVERAGE_POLICY=warn`.
  **Blocked on Open Question 1** — see below.
- **P3.6 — Shadow-mode telemetry**, then flip `content` on in a later release.

### P3.5 is blocked, and should stay blocked

ADR-053 Open Question 1 (`coverage_ack`) is the highest-risk open item. Under the
uniform clamp, *any commit touching a `.png` returns `unclear`*. That is
literally true and completely unusable — and **a noisy gate gets switched off,
which is worse than no gate**. Do not ship P3.5 until the acknowledgement
mechanism is designed. P3.4 (the receipt) is independently valuable and can ship
first: it makes the omission *visible* without making the gate noisy.

---

## Cross-cutting Definition of Done

Per `CLAUDE.md`: the published docs site is part of DoD, not an afterthought.

- [ ] `mkdocs.yml` nav updated for ADR-053 + this spec
- [ ] `docs/guides/verify.md` documents `coverage` fields by name
      (`TestVerifyResponseFieldDrift` will red otherwise)
- [ ] `CHANGELOG.md` per phase
- [ ] One release per epic, not per PR (git-tag driven) — **exception: P0 gets
      its own patch release**, because P1 cannot proceed without it

## Scheduled follow-up

A recurring reminder is registered to remove the temporary README security
notice once two material releases have shipped past `<FIX_VERSION>`, and to
confirm the advisory is published with a fixed version. Permanent surfaces
(`SECURITY.md`, `CHANGELOG.md`, release notes, `verify.md`) stay.
