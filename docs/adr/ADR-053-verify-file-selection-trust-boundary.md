# ADR-053: Verify File Selection — Decodability, Reviewability, and the Trust Boundary

**Status:** Proposed 2026-07-10 (rev 2: revised after a council review of rev 1 — `verify` at tier=high, rubric-focus=Security, `verification_id` `bff6de55`, verdict **fail**, 1 critical / 1 major / 1 minor, all three accepted. The critical finding was a **verification-bypass introduced by rev 1's own design** — see "Self-exclusion".)
**Date:** 2026-07-10
**Decision Makers:** llm-council maintainers (review requested)
**Proposed by:** maintainer triage of [#540](https://github.com/amiable-dev/llm-council/issues/540) (`.env` in `TEXT_EXTENSIONS`) and [#542](https://github.com/amiable-dev/llm-council/issues/542) (allowlist drops unlisted languages; explicit-path omissions buried in `expansion_warnings`); [#543](https://github.com/amiable-dev/llm-council/issues/543) (`target_paths=None` bypasses all filtering) was discovered while drafting this ADR and is scoped as its Q0
**Relates to:** ADR-034 (verification / directory expansion), ADR-042 (evidence injection), ADR-047 P1 (`unclear_reason` taxonomy), ADR-049 (prompt caching / prompt byte-stability), ADR-050 D3 (`scrub_exception`), ADR-051 (findings channel; verdict as a pure function of evidence), ADR-024 (config precedence, layer sovereignty)
**Tracking:** [#543](https://github.com/amiable-dev/llm-council/issues/543) (Q0 — security, lands first), [#540](https://github.com/amiable-dev/llm-council/issues/540) (Q3), [#542](https://github.com/amiable-dev/llm-council/issues/542) (Q1/Q2 + coverage receipt)
**Supersedes (in part):** ADR-034 v2.6 §"Directory Expansion Constants" — the `TEXT_EXTENSIONS` allowlist

---

## Context

`verify()` decides which files enter a verification prompt in one function,
`verification/file_ops.py::_is_text_file()`, backed by one hardcoded ~140-entry
extension allowlist, `verification/constants.py::TEXT_EXTENSIONS`. Anything not
on the list is dropped as "non-text". The same filter runs on both branches of
`_expand_target_paths()` — the `obj_type == "blob"` branch (a path the caller
*explicitly named*) and the `obj_type == "tree"` branch (a path *discovered* by
directory expansion). There is no bypass for explicit caller intent.

Two issues were filed against this mechanism from opposite directions:

- **#540 — over-inclusion.** `.env` is on the allowlist, so a committed `.env`
  is read and transmitted to third-party LLM providers.
- **#542 — under-inclusion.** `.zig`, `.tf`, `.dart`, `.sol`, `.gleam` (and any
  future language) are *not* on the allowlist, so they are dropped. When *some*
  target paths resolve and others don't, the call succeeds and returns a
  confident PASS over partial coverage; the omission appears only as a prose
  string in `expansion_warnings`.

#533/#539 — "`.lock` missing from `TEXT_EXTENSIONS` excludes `uv.lock`" — is the
same defect, already paid for once: an issue, a PR, a review cycle, and a
release, to add four characters to a set literal.

### Root cause: one list answering three unrelated questions

`_is_text_file()` conflates three orthogonal questions that have three different
owners and three different correct mechanisms:

| # | Question | Nature | Who owns the answer |
|---|---|---|---|
| **Q1** | **Decodability** — can this blob go in a prompt at all? | Content | The bytes |
| **Q2** | **Reviewability** — is it worth spending tokens on? | Provenance | The repo (generated? vendored? a lockfile?) |
| **Q3** | **Permissibility** — may this content leave the machine? | Policy / trust boundary | The repo owner |

A single `Set[str]` of extensions is a bad proxy for all three, and the failures
follow directly:

- `.zig` is missing because the list is a **Q1** answer that must be maintained
  by hand for every language that will ever exist. (#542)
- `.env` is present because someone answered **Q1** correctly — `.env` *is*
  text — and the list has no vocabulary for "text, but must never be
  transmitted." (#540)
- `uv.lock` was blocked by a **Q1** filter when the intended answer was a **Q2**
  one (`GARBAGE_FILENAMES`). (#533)

Extensions are also not a function of language, so no allowlist can ever be
correct: `.v` is Verilog *and* V *and* Coq; `.m` is Objective-C *and* MATLAB;
`.pl` is Perl *and* Prolog; `.d` is the D language *and* a generated Makefile
dependency file. `TEXT_EXTENSIONS` already carries `.v` and `.m` for one meaning
each.

### The filter does not run on the default code path at all

**Empirically confirmed** by executing
`_fetch_files_for_verification_async_with_metadata()` against a fixture repo
whose second commit touches `.env`, `logo.png`, and `yarn.lock`:

```
target_paths=None   (the DEFAULT invocation)
  files sent            : ['.env', 'logo.png', 'src/app.py', 'yarn.lock']
  expansion_warnings    : []
  SECRET in prompt?     : True      <- OPENAI_API_KEY=sk-REAL-SECRET-…
  binary PNG in prompt? : True
  yarn.lock in prompt?  : True      <- and it is in GARBAGE_FILENAMES
```

`_is_text_file()` and `_is_garbage_file()` are called from exactly one place:
inside `_expand_target_paths()`. When `target_paths` is `None` — the default at
both `run_verification()` (`api.py:187`) and the MCP `verify` tool
(`mcp_server.py:416`) — control takes the `else` branch, which runs
`git diff-tree --no-commit-id --name-only -r` and assigns the result **directly**
to `files_to_fetch`. No text check. No garbage check. No warning. Binary blobs
are `errors="replace"`-decoded into the prompt.

This reframes #540. The issue supposes an exposure that requires a caller to
pass a directory containing a `.env`. In fact **a commit that merely touches
`.env` sends it**, unfiltered, on the default call — and `expansion_warnings` is
empty, so #542's failure mode 2 is not merely buried here, it is absent.

Selection lives in the *expansion helper* when it belongs at the *fetch
boundary*. Whatever policy this ADR adopts is worthless if it can be bypassed by
omitting an argument.

### The list is also not internally coherent today

Verified against `origin/master` (`7abb68a`) by executing the real predicate:

1. **`GARBAGE_FILENAMES` directory entries are dead code.** `_is_garbage_file()`
   compares `Path(p).name`, so `node_modules`, `__pycache__`, and `.git` — all
   *directories* — never match. `node_modules/react/index.js` returns
   `garbage=False, text=True` and is reviewed.
2. **Three more secret-bearing files are transmitted today**, none named in
   #540: `.npmrc` and `.yarnrc` (which routinely hold
   `//registry.npmjs.org/:_authToken=…`) are on the allowlist, and
   `secrets.yaml` rides in on `.yaml`.
3. **`.env.local`, `.env.production`, `.envrc`, `id_rsa`, `*.pem`,
   `terraform.tfvars`, `.netrc`, `kubeconfig` are excluded *by accident*.**
   `Path(".env.local").suffix` is `.local`, which is not on the list, and the
   full name is not on the list either. Nobody decided this. **This is the
   single most important fact in this ADR** — see "Why these must ship
   together".
4. **`TEXT_EXTENSIONS` is not a set of extensions.** `.env.example`, `.gitignore`,
   `.vimrc`, `.dockerfile` are *filenames*; they match only via the
   `name in TEXT_EXTENSIONS or f".{name}" in TEXT_EXTENSIONS` branch. That
   `f".{name}"` fallback also means a file literally named `env` (no dot) is
   treated as text via the `.env` entry, as are files named `conf`, `toml`, and
   `gitignore`.

### One fact that reframes #540's severity

Every byte the verification pipeline reads comes from git object storage —
`git cat-file -t {sha}:{path}`, `git ls-tree {sha}:{path}`,
`git show {sha}:{path}`. Grepping `verification/` for filesystem reads finds
only `.council/` internal state (transcripts, screening decisions, calibration),
never a target file.

**Therefore `verify()` cannot read an untracked or `.gitignore`d file.** The
overwhelmingly common `.env` — the one holding a developer's real API keys,
gitignored, never committed — is *unreachable today*. #540's actual exposure is
confined to `.env` files that are **committed to the repository**.

That is still worth fixing (people do commit `.env`; once committed it is in
history forever, and a verify against an old snapshot will read it), and
defense-in-depth applies regardless. But it is hardening, not live exfiltration
of local developer secrets, and the ADR should not pretend otherwise.

### Why #540 and #542 must ship together

Fixing #542 in isolation makes #540 **strictly worse**.

The protection people assume exists for `.env.local`, `.env.production`,
`id_rsa`, `*.pem`, `.netrc`, `terraform.tfvars`, and `kubeconfig` is not a
policy. It is a coincidence of `pathlib.Path.suffix` semantics (fact 3 above).
The moment the Q1 filter flips from "allow known extensions" to "allow anything
that decodes as text" — which is exactly what #542 asks for, and what this ADR
recommends — **every one of those files becomes eligible for transmission**.

A denylist for Q1 without an explicit Q3 trust boundary converts an accidental
protection into an intentional leak. This is the load-bearing reason the two
issues are one decision.

---

## Decision

**Split the one predicate into three, and give each question the mechanism the
industry already built for it.** Stop maintaining a language list. **And put all
three behind a single gate that cannot be bypassed.**

### Q0 — Enforcement: one chokepoint, and "unfiltered path" made unrepresentable

> Tracked as [#543](https://github.com/amiable-dev/llm-council/issues/543)
> (bug/security). Lands **before** the rest of this ADR.

A policy that is *remembered* at each call site is a policy that will be skipped
at the next one — as the `target_paths=None` branch already demonstrates. The
selection convention must be structural, not conventional.

1. **Introduce one selector.**
   `select_blobs(snapshot_id, candidates, origin) -> (selected, omitted)` is the
   sole place Q1/Q2/Q3 are evaluated.
2. **Route every producer of candidate paths through it** — the `blob` branch,
   the `tree` branch, **and the `git diff-tree` branch**. There was never a
   reason for the last one to skip the gate; it produces a plain path list like
   the others.
3. **Make the bypass unrepresentable.** `_fetch_file_at_commit_async()` stops
   accepting `str` and accepts a `SelectedBlob` token that only `select_blobs()`
   can mint. A future contributor cannot fetch an unvetted path by forgetting to
   call the filter, because there is no `str` overload to forget. This is the
   only part of this ADR that makes the rest durable.

Because the CLI, HTTP, and MCP surfaces all funnel through `run_verification()`,
one chokepoint covers all three.

**Argument hygiene for the new git calls.** The council review (round 1, `minor`)
flagged command injection. Shell injection is already precluded — all six git
invocations use `asyncio.create_subprocess_exec` with argv arrays and there are
zero `shell=True`/`create_subprocess_shell` calls in the package. Two real gaps
remain, and the new `git grep` / `git ls-tree` pathspec calls widen the second:

- `validate_snapshot_id()` (`GIT_SHA_PATTERN`, 7–40 hex) is enforced on the
  Pydantic `VerificationRequest` and in the HTTP handler, but **not** at the
  `run_verification()` boundary itself (`api.py:760`), which MCP and `gate` call
  directly. Validate there too, defense in depth.
- **No `--` separator appears anywhere in `file_ops.py`.** Today's calls embed
  the path in a `<sha>:<path>` token, so a leading `-` cannot be read as a flag.
  The pathspec-style calls this ADR adds (`git ls-tree … -- <paths>`,
  `git grep … -- <paths>`) have no such protection and **must** pass `--` before
  any path. Argument injection, not shell injection, is the live risk.

### Q1 — Decodability: content sniffing, reusing git's own heuristic

Replace extension matching with the rule git itself uses in `git diff` and
`git grep -I` (`buffer_is_binary()`): **a blob is text iff its first 8000 bytes
contain no NUL byte.** ripgrep and, approximately, `file(1)` use the same rule.

Empirically verified against git 2.50.1 in a scratch repo. `git grep -I
--name-only -e '' <sha>` classified `main.zig`, `main.tf`, `LICENSE`,
`CODEOWNERS`, and an extensionless shebang script as text, and rejected a
NUL-bearing `logo.png` and a `weird.txt` whose *extension* says text but whose
*content* does not. A 12-line Python reimplementation of the NUL rule reproduced
git's classification exactly on all eleven probe files.

Two options for the implementation, both verified:

- **(1a) Shell out to `git grep -I --name-only -e '' <sha> -- <paths>`.** One
  subprocess, uses git's real code. Caveats found by probing: it does **not**
  list empty files (an empty blob matches no line), it exits **1** when nothing
  matches (must not be treated as an error), and its output is prefixed
  `<sha>:<path>` (strip it; use `-z` for filenames containing newlines, as
  `_git_ls_tree_z_name_only` already does).
- **(1b) Sniff the bytes we already read.** `_fetch_file_at_commit_async()`
  already streams the blob in 8 KB chunks. Check the first chunk for `\x00`
  before decoding. No new subprocess, no empty-file edge case, no exit-code
  handling, fully unit-testable without a git fixture.

**Recommend (1b)**, with a `git ls-tree -r --format='%(objecttype) %(objectsize)
%(path)'` pre-pass (one call, verified) to enforce a blob-size cap *before*
fetching, so we never stream a 400 MB blob just to sniff it. Falls back to
`git ls-tree -rl` on git < 2.36.

Additionally, honor the repo's **`.gitattributes`**: a path marked `binary` or
`-diff` is excluded. Read attributes **from the snapshot**, not the worktree —
`git --attr-source=<sha> …` (verified working on 2.50.1; note it is a *top-level
`git` option*, not a `grep` flag) — so verifying a given SHA is reproducible
regardless of the checked-out tree.

**This dissolves the extensionless-file question entirely.** `LICENSE`,
`CODEOWNERS`, `Makefile`, `Dockerfile`, `Jenkinsfile`, `Procfile`, `BUILD`,
`.envrc`, and shebang scripts are all NUL-free and are simply included. No
filename list, no shebang parser, no `{"makefile", "dockerfile", "jenkinsfile",
"cmakelists"}` special case. The existing special case is deleted, not extended.

**Known blind spot, stated plainly:** UTF-16 source files are full of NUL bytes
and will be classified binary. Git has the identical blind spot and repos work
around it with `.gitattributes … working-tree-encoding=UTF-16`. Our escape hatch
is the operator override below, and — critically — the coverage receipt makes
the omission *visible* rather than invisible. The 8000-byte window is a
heuristic, not a proof: a NUL at byte 9001 is classified text (verified). That
is git's own risk tolerance and we adopt it deliberately.

### Q2 — Reviewability: keep the denylist, fix it, and let the repo extend it

`GARBAGE_FILENAMES` is already the right shape (deny known-noise) and stays.

- **Fix the dead directory entries** (`node_modules`, `__pycache__`, `.git`):
  match against **every path component**, not just the basename.
- Honor **`.gitattributes linguist-generated` and `linguist-vendored`** —
  GitHub Linguist's de-facto standard for "this is not authored source," already
  present in a large fraction of real repos, and exactly the Q2 question.
- Keep `MAX_FILES_EXPANSION` and the tier char budgets unchanged.
- Move `.svg` from "text" to "noise-by-default": it decodes as text but is
  usually a large generated asset.

### Q3 — Permissibility: an explicit trust boundary, default-ON

This is where #540 lives, and it must **not** be an entry in an extension list.

**(3a) A curated, high-precision secret-path denylist**, checked before any blob
is fetched, applied to explicit and discovered paths alike:

- **Env**: `.env` and `.env.*` (except `*.example`, `*.sample`, `*.template`), `.envrc`
- **Keys / certs**: `*.pem`, `*.key`, `*.p12`, `*.pfx`, `*.keystore`, `*.jks`, `*.ovpn`, `*.asc`
- **SSH / GPG**: `id_rsa*`, `id_ecdsa*`, `id_ed25519*`, `.ssh/**`, `.gnupg/**`
- **Package registries**: `.npmrc`, `.yarnrc`, `.pypirc`, `.gem/credentials`, `.cargo/credentials*`
- **Cloud**: `.aws/credentials`, `.aws/config`, `*service-account*.json`, `.config/gcloud/**`, `.azure/**`, `kubeconfig`, `*.kubeconfig`, `.kube/config`
- **Git / Docker**: `.git-credentials`, `.dockercfg`, `.docker/config.json`
- **Unix classics**: `.netrc`, `_netrc`, `.pgpass`, `.htpasswd`, `.s3cfg`, `.boto`
- **IaC / misc**: `terraform.tfvars`, `*.auto.tfvars`, `.terraformrc`, `secrets.yaml`, `secrets.yml`, `.databrickscfg`

Additions above the original draft (`.git-credentials`, `.aws/credentials`,
GCP service-account JSON, and the rest) come from the council review, round 1,
`major`.

**Matching is case-insensitive**, a deliberate divergence from gitignore's
case-sensitive semantics: `Secrets.yaml` and `.Env` are real files on
case-preserving filesystems, and for a security floor **over-matching is the
safe direction**. A legitimate `Credentials.md` excluded by this rule shows up
in the coverage receipt as `denied_secret` and is diagnosable in one command —
whereas an under-match is a silent leak. The existing `_is_text_file()` already
lowercases, so this is consistent with the codebase.

Note this **removes `.env`, `.env.example`, `.env.sample`, `.npmrc`, `.yarnrc`
from `TEXT_EXTENSIONS` regardless of anything else in this ADR.** `.npmrc` and
`.yarnrc` are a live leak that #540 did not identify.

`.env.example` and `.env.sample` are conventionally secret-free and are the one
case #540 wanted to preserve. Preserve them by **name pattern** (`*.example`,
`*.sample`, `*.template`), which is the actual convention — not by putting a
non-extension string in a set called `TEXT_EXTENSIONS`.

**(3b) Honor the ecosystem's AI-ignore files** rather than inventing
`.councilignore`. The convention has converged on *gitignore syntax in a
tool-scoped denylist file*, and vendors already interoperate: JetBrains AI
Assistant reads `.cursorignore`, `.codeiumignore`, and `.aiexclude` when present,
and Gemini Code Assist's `.aiexclude` "syntax … is the same as a `.gitignore`
file." A vendor-neutral [`.llmignore` spec](https://github.com/llmignore-spec/llmignore-spec)
exists. Council should read, in precedence order:

`.llmignore` → `.aiexclude` → `.aiignore` → `.cursorignore` → `.codeiumignore`

read **from the snapshot** (`git show <sha>:.llmignore`) for reproducibility,
matched with the [`pathspec`](https://pypi.org/project/pathspec) library
(`GitWildMatchPattern` — the same matcher `black` uses; not currently a
dependency). Do not hand-roll a gitignore matcher.

A repo that already excluded secrets from Cursor gets the same protection from
Council for free, with no Council-specific file to author. This is the direct
answer to "are there already industry-recognised mechanisms to reuse."

**(3c) Content-based secret scanning (gitleaks / detect-secrets): NOT in v1.**
Deferred behind a future `LLM_COUNCIL_SECRET_SCAN`. Rationale:

- A regex/entropy scanner has an unbounded false-negative rate. Shipping one as
  *the* boundary manufactures false confidence; (3a)+(3b) capture nearly all the
  value with zero dependencies and zero false-positive redaction.
- Redaction **mutates prompt bytes**, which collides with ADR-049's byte-stable
  segment assembly and its golden tests, and would silently degrade prompt-cache
  hit rates.
- It is the right *defense-in-depth follow-up*, not the primary control.

When a path is denied, the receipt records the **path only, never the matched
value** — mirroring `scrub_exception` (ADR-050 D3).

#### Do we seed the ignore file? No.

The built-in denylist (3a) is **compiled in, always on, and not overridable by
any in-repo file**. It is a floor, not a template. We do not write a
`.llmignore` into the user's repository, for three reasons — the first of which
is decisive:

1. **It would not work.** Ignore files are read *from the git snapshot*
   (`git show <sha>:.llmignore`) so that verifying a SHA is reproducible. A file
   we seed on disk is uncommitted, therefore absent from the snapshot, therefore
   **inert for the very run that created it**. Auto-seeding is simultaneously
   intrusive and ineffective.
2. **The default must be safe with zero files present.** If the answer to "what
   stops my `.env` from being transmitted" is "a file you have to author and
   commit," we have shipped a footgun with documentation. Protection cannot be
   opt-in.
3. A seeded template forks on first edit, and we can never improve it again.

The ignore file is therefore **additive narrowing only**. It can exclude more; it
can never re-admit a Q3-denied path. A repo cannot `!.env` its way back through
the trust boundary — otherwise the boundary is advisory.

What we ship instead is ergonomics, explicitly *not* the security mechanism:

| Command | Purpose |
|---|---|
| `llm-council ignore --print-defaults` | Emit the effective built-in denylist — auditable, diffable, greppable in CI |
| `llm-council ignore --init` | On explicit request, write a *commented starter* `.llmignore` and remind the user to commit it |
| `llm-council ignore --explain <path> [--sha …]` | Print which layer and which rule decided this path, without running a council |

### The other half of #542: silent partial coverage

#542 correctly identifies failure mode 2 (some paths resolve, some don't →
confident PASS over partial coverage) as more serious than failure mode 1 (all
paths fail → loud 422). Fixing Q1 shrinks this problem; it does not remove it,
because Q2 and Q3 will still legitimately drop files.

The project already has the right precedent. **ADR-051 made the verdict a pure
function of structured evidence** (`verdict_policy()`), added
`diagnostics.findings_by_severity`, and added a defensive
`verdict_evidence_mismatch` invariant marker. Coverage is the same shape of
problem: a verdict is only as good as the evidence it saw, and the caller must
be able to see what it saw without parsing prose.

**Distinguish explicit from discovered targets** — the code today does not.

**Add a structural coverage receipt to `VerifyResponse`** (additive, all fields
optional, no type break — the same non-breaking argument ADR-051 made for
`blocking_issues`):

```python
coverage: {
  "requested": [...],            # verbatim target_paths
  "reviewed": [...],             # blobs actually in the prompt
  "omitted": [                   # every drop, with a machine-readable cause
    {"path": "src/main.zig", "reason": "binary", "origin": "explicit"},
    {"path": ".env",         "reason": "denied_secret", "origin": "discovered"},
  ],
  "explicit_omitted": bool,      # the load-bearing boolean
  "truncated": bool,
}
```

`reason ∈ {binary, denied_secret, ignored, generated, vendored, too_large,
truncated, not_found}`; `origin ∈ {explicit, discovered}`. The enumerated reason
is what makes a `.zig` drop *distinguishable* from a `.png` drop — and therefore
actionable. `expansion_warnings` is retained, additive, and demoted from
load-bearing signal to human-readable prose.

#### Self-exclusion: what may an omission hide?

An earlier draft clamped the verdict on `explicit_omitted` — i.e. keyed on
**who asked for the file**. The council review (round 1, `critical`) showed this
is the wrong axis and opens a **verification bypass**:

> An attacker commits `evil.py` *and* a line adding `evil.py` to `.llmignore`
> (or `evil.py -diff` to `.gitattributes`). A CI gate calls `verify()` with
> `target_paths=None`, so every path is `origin=discovered`. `evil.py` is
> omitted by a repo-attested rule, the `explicit_omitted` clamp never fires, and
> the council returns a confident **PASS** over a diff it never saw.

Note this attack **does not exist on `master` today** — with `target_paths=None`
no filter runs at all (#543), so no ignore file is consulted. Q0 and Q3b
*together introduce it*. It must be closed in the same change that creates it.

The correct axis is **whether the omission was attested by the artifact under
review**:

| Class | Reasons | Can it hide a change? |
|---|---|---|
| **Intrinsic** | `binary`, `too_large`, `not_found`, `truncated` | No — determined by the bytes or by git |
| **Council policy** | `denied_secret` | No — determined by our compiled-in denylist |
| **Repo-attested** | `ignored`, `generated`, `vendored`, `-diff`/`binary` attribute | **Yes** — an assertion the code makes *about itself* |

**Rule: any file in the changed set that is omitted for a repo-attested reason
clamps the verdict**, regardless of `origin`. That is exactly the
"I marked my own malicious file as not-worth-reviewing" move, and it is
independent of whether the caller enumerated paths.

Three mechanisms, all required:

1. **Reason-class clamp.** `pass` is not representable when any changed file was
   omitted for a repo-attested reason → `unclear` with a new
   `unclear_reason="incomplete_coverage"` (extending ADR-047 P1's
   `infra_failure|low_confidence|timeout`). Exit code stays 2; automation
   already routes on `unclear_reason`. Explicit paths omitted for *any* reason
   also clamp — an explicit request is still a caller contract.
2. **Policy files are read from the base ref, not the head.** `run_verification()`
   gains an optional `policy_snapshot` (defaulting to `snapshot_id`); CI gates
   pass the merge target. A PR then **cannot introduce an ignore rule that takes
   effect on its own review.** This is precisely why GitHub Actions runs
   `pull_request` workflows from the base ref rather than the PR head, and the
   precedent is worth following rather than reinventing.
3. **Policy files can never exclude themselves.** `.llmignore`, `.aiexclude`,
   `.aiignore`, `.cursorignore`, `.codeiumignore`, and `.gitattributes` are
   always reviewed when present in the changed set, and a change to any of them
   is surfaced as a finding. Compare GitHub's treatment of `CODEOWNERS` and
   `.github/workflows` changes.

And, as before, the Q3 denylist is compiled in and **never overridable by an
in-repo file** — an ignore file may narrow what is reviewed, never re-admit a
denied secret. A repo cannot `!.env` its way through the boundary.

Governed by `LLM_COUNCIL_COVERAGE_POLICY`:

| Value | Behavior |
|---|---|
| `clamp` (default) | `pass` → `unclear(incomplete_coverage)` on a repo-attested omission of a changed file, or on any omission of an explicit path |
| `fail` | Raise `SnapshotResolutionError` (422) in those same cases |
| `warn` | Receipt only; verdict untouched. **Unsafe for gates** — documented as such |

`clamp` is preferred over `fail` as the default because `fail` breaks the
legitimate mixed call `target_paths=["src/", "assets/logo.png"]`, and because
`clamp` composes with the existing `unclear_reason` routing contract instead of
introducing a new error path.

### How we guarantee the convention is actually applied

Three mutually reinforcing mechanisms, because the empirical finding above shows
that "we wrote it in a helper" is not one.

**1. Structural (Q0).** The `SelectedBlob` token makes an unfiltered fetch a type
error rather than a code review miss.

**2. Invariant.** Conservation of candidates: every candidate path appears in
**exactly one** of `coverage.reviewed` or `coverage.omitted`.

```
set(reviewed) & set(omitted) == ∅
set(reviewed) | set(omitted) == set(candidates)
```

Asserted in `build_verification_result()`, with a defensive marker emitted on
violation — precisely the `verdict_evidence_mismatch` pattern from ADR-051 C4.
A response with no `coverage` block means the gate did not run, and that is
detectable by the caller rather than silent.

**3. Tests.**
- An **architecture test** asserting no call to `_fetch_file_at_commit_async()`
  exists outside the selector module (same spirit as the existing docs-drift
  tests).
- A **red-team fixture**: one commit touching `.env`, `id_rsa`, `logo.png`,
  `yarn.lock`, and `main.zig`; assert the assembled prompt contains `main.zig`
  and **none** of the others — parametrised over `target_paths=None`,
  `target_paths=["<dir>"]`, and `target_paths=["<explicit file>"]`. The
  `None` case is the one that would have caught the bypass, and no existing test
  covers it.
- A **conservation property test** over randomly generated trees.

---

## Rollout

Mirrors the ADR-051/052 and `LLM_COUNCIL_SCREENING` house pattern: flag-gated,
default-OFF, byte-identical when off — **with two deliberate exceptions.**

`LLM_COUNCIL_FILE_SELECTION = allowlist | shadow | content`

- `allowlist` (default, phase 1) — today's behavior, byte-identical.
- `shadow` — run both predicates, log the delta (what content-sniffing *would*
  have included/excluded) to `.council/`, act on the allowlist. Measure before
  flipping, exactly as `early_consensus` shadow mode does.
- `content` — the Q1/Q2 pipeline above.

**Exception 0 — Q0 (the chokepoint) is a bug fix and ships unflagged, first.**
Routing the `diff-tree` branch through the selector is not a new policy; it is
the *existing* policy finally being applied where it was always meant to. It
lands before everything else, because until it does, every other control in this
ADR is optional at the caller's discretion. Note this **is** a visible behavior
change on the `target_paths=None` path: binaries and lockfiles stop appearing in
prompts, which will move some verdicts. That is the fix, not a regression.

**Exception 1 — the Q3 trust boundary ships default-ON immediately.** A security
fix behind an off-by-default flag is not a fix. It is strictly *narrowing*
(fewer files transmitted), so it cannot turn a correct pass into a wrong one;
the worst case is that a caller explicitly targeting `.env` now gets a loud
`denied_secret` omission instead of a silent leak. It must land before
`content` mode is available at all, for the "Why these must ship together"
reason above.

**Exception 2 — the coverage receipt ships default-ON and additive.** It changes
no behavior. The clamp (`LLM_COUNCIL_COVERAGE_POLICY=clamp`) is the one genuine
behavior change and warrants a CHANGELOG "Changed" entry and a minor bump: it
only fires where today's answer is *already wrong*, but callers who relied on a
pass over a mixed file/binary list will now see `unclear`.

Per ADR-051 C6, extend `TestVerifyResponseFieldDrift` so every new `coverage`
field must appear by name in `docs/guides/verify.md` or `api.md` or CI reds.

---

## Consequences

### What an engineer does when `something.zig` is missed

This is the question that motivated the ADR, and the current answer is bad:
notice a suspicious verdict → happen to read `expansion_warnings` (no CI
integration does) → file an issue → a maintainer PRs one string into a set → wait
for a release → upgrade. Median time-to-fix: **one release cycle** (#533 → #539).

Afterwards there are three escape hatches, ordered by who owns them:

1. **Nothing to do.** Content sniffing already included it. This is the ~95% case
   and the entire point.
2. **Repo owner, zero latency.** To *exclude*: `.gitattributes` (`weird.bin
   -diff`) or any supported `.llmignore`-family file. To *include*: nothing.
3. **Operator, zero latency.** For the residual pathological case (UTF-16
   source), `verification.text.include` / `.exclude` in `llm_council.yaml`, or
   `LLM_COUNCIL_TEXT_EXTRA_EXTENSIONS`, under the ADR-024 YAML > env > defaults
   precedence.

And underneath all three: **the coverage receipt means they find out at all**,
from a typed field, without parsing prose. The fix moves from *"PR the library
and wait for a release"* to *"it already works; if it doesn't, the response tells
you why, and you fix it in your own repo."*

### Costs and risks

- **Content sniffing costs a blob read per candidate file.** Bounded by the
  `ls-tree` size pre-pass, `MAX_FILES_EXPANSION=100`, and pathspec-scoped
  expansion. Under (1b) the read is one we already perform.
- **The blast radius grows before it shrinks.** `content` mode admits every text
  file in an expanded directory — including files a repo never intended for an
  LLM. Q3 and the `.llmignore` family are the mitigation, and `shadow` mode
  exists to measure the delta on real repos first.
- **Repo-attested omissions are an attack surface** — see "Self-exclusion" below.
  This was originally dismissed here as "acceptable, the repo controls its own
  contents anyway." That reasoning is wrong for the gate use case and the
  council review caught it.
- **Extending the `unclear_reason` enum** is a contract change for automation
  matching it exhaustively (epic-loop routes on it).
- **`pathspec` becomes a runtime dependency** (pure-Python, no transitive deps).

### Latent bugs fixed in passing

0. **`target_paths=None` applies no filter at all** — secrets, binaries, and
   deny-listed lockfiles enter the prompt on the default invocation, with an
   empty `expansion_warnings`. The most severe defect found; described by
   neither #540 nor #542. Filed separately as
   [#543](https://github.com/amiable-dev/llm-council/issues/543) and scoped as
   Q0, to be fixed ahead of the rest of this ADR.
1. `GARBAGE_FILENAMES` directory entries (`node_modules`, `__pycache__`, `.git`)
   never matched — committed `node_modules` was reviewed.
2. `.npmrc` / `.yarnrc` / `secrets.yaml` transmitted; unnoticed by #540.
3. `_validate_file_path()` guards `_fetch_file_at_commit_async()` but not
   `_expand_target_paths()`'s calls to `_get_git_object_type()` /
   `_git_ls_tree_z_name_only()`. Not exploitable — `git cat-file <sha>:<path>`
   cannot escape the tree, and a `..` path resolves to `None` → "Path not found"
   — but the ordering is inconsistent and should be normalized.

---

## Alternatives considered

**A. Keep the allowlist; just add the missing extensions.** What #539 did. Costs
a release per language, cannot be complete (extensions are not a function of
language), and — decisively — does nothing for #540, because `.env` is text and
an allowlist is the wrong instrument for a trust boundary.

**B. Pure denylist for Q1, no Q3 boundary.** #542 option 1, taken alone. Actively
harmful: it un-protects `.env.local`, `id_rsa`, `*.pem`, `terraform.tfvars`, and
`kubeconfig`, all of which are excluded today only by accident. Rejected.

**C. Hybrid — denylist for directory expansion, allowlist for explicit paths**
(#542 option 3). Preserves the treadmill for the case where the caller was
*most* specific about intent, which is backwards: an explicit
`target_paths=["src/main.zig"]` is the strongest possible signal that the caller
wants that file reviewed. Rejected.

**D. Content secret-scanning as the primary Q3 control** (#540 option 3).
Rejected for v1: unbounded false negatives, manufactures false confidence, and
redaction mutates prompt bytes in conflict with ADR-049's byte-stable segments.
Retained as a flagged follow-up.

**E. Shell out to `git grep -I`** (option 1a). Genuinely attractive — it is
literally git's implementation. Rejected in favor of (1b) on the empirically
discovered edges: empty blobs are not listed, `rc=1` means "no match" not
"error", and output needs `<sha>:` stripping and `-z` handling. (1b) is the same
heuristic with none of the marshalling, on bytes already in hand.

---

## Verification of claims

Probed against **git 2.50.1** in a scratch repository, and against
`origin/master` (`7abb68a`, post-#539) by executing the real `_is_text_file` /
`_is_garbage_file` predicates:

| Claim | Method | Result |
|---|---|---|
| `git grep -I` classifies `.zig`/`.tf`/`LICENSE`/`CODEOWNERS`/shebang-script as text | scratch repo | confirmed |
| NUL-in-first-8000-bytes reproduces git's classification | 12-line Python vs `git grep -I`, 11 files | exact match |
| git sniffs only the first 8000 bytes | NUL at byte 9001 → text | confirmed (heuristic, not proof) |
| `git grep -I` omits **empty** blobs | `empty.py` not listed | confirmed |
| `git grep` exits 1 on no-match | `rc=1` | confirmed |
| `.gitattributes` `-diff` / `binary` excludes a path | `main.tf -diff` → 0 hits | confirmed |
| `git --attr-source=<sha>` reads attributes from the snapshot | worktree `.gitattributes` deleted, snapshot rule still applied | confirmed |
| `git ls-tree -r --format='%(objecttype) %(objectsize) %(path)'` | one call | confirmed |
| `verify()` reads **only** git objects, never the filesystem | grep of `verification/` for `open`/`read_text`/`glob` | confirmed — only `.council/` state |
| **`target_paths=None` bypasses both filters entirely** | ran `_fetch_files_for_verification_async_with_metadata(sha, None)` on a fixture commit touching `.env`/`logo.png`/`yarn.lock` | **confirmed — secret, binary, and lockfile all in prompt; `expansion_warnings == []`** |
| `_is_text_file`/`_is_garbage_file` have exactly one call site | grep | confirmed — both only inside `_expand_target_paths` |
| `.env.local`/`id_rsa`/`*.pem`/`kubeconfig` excluded **by accident** | executed `_is_text_file` | confirmed |
| `.npmrc`/`.yarnrc`/`secrets.yaml` included today | executed `_is_text_file` | confirmed |
| `GARBAGE_FILENAMES` directory entries never match | `node_modules/react/index.js` → `garbage=False, text=True` | confirmed |
| JetBrains AI reads `.cursorignore`/`.codeiumignore`/`.aiexclude`; `.aiexclude` uses gitignore syntax; `.llmignore` spec exists | vendor docs (see Sources) | confirmed |

**Not verified, carried as assumptions:** that `pathspec`'s `GitWildMatchPattern`
matches git's semantics closely enough for the `.llmignore` family (spot-check
before implementing); that `git ls-tree --format` is available on the oldest git
we support (needs ≥ 2.36 — confirm the floor, else use `-rl`); that no current
caller depends on a `pass` verdict over a partially-omitted explicit path (the
`clamp` default assumes not).

---

## Open questions for the decision makers

1. **`clamp` vs `fail` as the `LLM_COUNCIL_COVERAGE_POLICY` default.** `clamp`
   is recommended, but `fail` is more honest and matches what #533 did by
   accident. `fail` breaks `target_paths=["src/", "assets/logo.png"]`.
2. **~~Does `origin=discovered` + `reason=binary` deserve any verdict effect?~~**
   **Resolved by council review, round 1.** The question was mis-posed: `origin`
   is the wrong axis. *Repo-attested* omissions (`ignored`, `generated`,
   `vendored`, `-diff`) clamp regardless of origin, because they are the
   self-exclusion bypass; *intrinsic* omissions (`binary`, `too_large`) do not.
   See "Self-exclusion".
3. **Should `content` mode's default flip in the same release as the Q3
   boundary, or one release later after `shadow`-mode telemetry?** Recommended:
   one later.
4. **Is `.env.example` worth preserving at all**, given it now costs a
   name-pattern carve-out in the trust boundary? #540 assumed yes.
5. **Does `policy_snapshot` (base-ref policy reading) belong in this ADR or its
   own?** It changes the `run_verification()` signature and requires every CI
   gate to pass a base SHA. The self-exclusion clamp closes the bypass without
   it; `policy_snapshot` is defense in depth. *New, from the council fix.*

---

## Sources

- [Exclude files from Gemini Code Assist use — `.aiexclude`, gitignore syntax](https://developers.google.com/gemini-code-assist/docs/create-aiexclude-file)
- [JetBrains AI Assistant — `.aiignore`, and interop with `.cursorignore` / `.codeiumignore` / `.aiexclude`](https://www.jetbrains.com/help/ai-assistant/disable-ai-assistant.html)
- [`llmignore-spec` — vendor-neutral `.llmignore` specification](https://github.com/llmignore-spec/llmignore-spec)
- [`gitattributes` templates — `binary` / `-diff` conventions](https://github.com/gitattributes/gitattributes)
- [`pathspec` — gitignore-style pattern matching for Python](https://pypi.org/project/pathspec)
