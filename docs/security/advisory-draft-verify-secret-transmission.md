# DRAFT — GitHub Security Advisory: verify() transmits committed credential files to third-party LLM providers

> **Status: DRAFT. Do not publish until the fix is released.**
>
> Publishing a GHSA without a `patched_versions` entry causes Dependabot to
> alert downstream users with **no safe version to upgrade to**. Sequence:
> merge the fix → tag & publish the release → set the fixed version on the
> draft advisory → request a CVE → publish.
>
> Paste the sections below into the GHSA form at
> `https://github.com/amiable-dev/llm-council/security/advisories/new`.
> Tracking: #543, #540. Delivery plan: `docs/adr/ADR-053-implementation-spec.md`.

---

## Title

`llm-council-core` verification pipeline transmits committed credential files to third-party LLM providers

## Ecosystem / package

- **Ecosystem:** pip (PyPI)
- **Package:** `llm-council-core`

## Affected versions

Two independent defects share one remediation. The advisory covers both.

| Defect | Introduced | First released in | Fixed in |
|---|---|---|---|
| `target_paths=None` applies no file filter at all (#543) | `0005fe7` | **v0.22.0** | `<FIX_VERSION>` |
| `.env`, `.npmrc`, `.yarnrc` on the `TEXT_EXTENSIONS` allowlist (#540) | `1f91c08` | **v0.23.0** | `<FIX_VERSION>` |

Proposed range: `>= 0.22.0, < <FIX_VERSION>`.

> **Affected range CONFIRMED by reading the code at each tag (2026-07-10):**
> `>= 0.22.0`. At **v0.21.0** the verification path fetched no file contents at
> all (`_build_verification_prompt` did not exist / embedded no `{file_contents}`),
> so no leak was possible. **v0.22.0** introduced `_build_verification_prompt`,
> which calls `_fetch_files_for_verification_async` and embeds `{file_contents}`
> via the `git diff-tree` branch with **zero filtering** — a committed `.env`
> touched by a commit was transmitted. `TEXT_EXTENSIONS` and the `.env` allowlist
> entry (#540) arrived at **v0.23.0**; from v0.22.0 to v0.22.x the leak was
> *broader* (no filter of any kind), narrowing to the #540 framing at v0.23.0.
> Both collapse to the same advisory statement. Lower bound `>= 0.22.0` is not a
> `git log -S` inference — it is the first release whose code embeds file
> contents in the prompt.

## Severity

**Maintainer to score.** Do not inflate this. The honest characterisation:

- Requires credentials **already committed to the git repository**.
- Requires a `council-verify` / `council-gate` / MCP `verify` run over a commit
  that touches those files.
- **Not remotely triggerable.** There is no attacker who initiates this; the
  disclosure is caused by the victim's own invocation.
- Anyone affected had already committed secrets to version control, so those
  secrets were arguably compromised before Council touched them.

Suggested starting vector for discussion (**not** an assertion):
`CVSS:3.1/AV:L/AC:L/PR:L/UI:N/S:C/C:H/I:N/A:N` — scope-changed because the data
leaves the trust boundary to a third party. Adjust or discard.

## Weakness

**CWE-200: Exposure of Sensitive Information to an Unauthorized Actor.**
The unauthorized actor is the third-party LLM provider (OpenRouter, Anthropic,
OpenAI, etc., depending on gateway configuration).

Nearest precedent in shape: [CVE-2025-30066](https://github.com/advisories/ghsa-mrrh-fwg8-r2c3)
(`tj-actions/changed-files`) — secrets rendered readable in a location outside
the intended trust boundary; guidance was "assume leaked, rotate".

## Description

`verify()` assembles a prompt from file contents read out of a git snapshot and
sends it to the configured LLM provider(s). Which files are included was decided
by `verification/file_ops.py::_is_text_file()`, backed by the hardcoded
`TEXT_EXTENSIONS` allowlist. Two defects caused credential files to be included.

### 1. `target_paths=None` bypasses all filtering (#543)

`_is_text_file()` and `_is_garbage_file()` are called from exactly one place:
inside `_expand_target_paths()`. That function is only reached on the
`if target_paths:` branch of
`_fetch_files_for_verification_async_with_metadata()`. The `else` branch — taken
whenever `target_paths` is omitted, which is the **default** at both
`run_verification()` and the MCP `verify` tool — runs
`git diff-tree --no-commit-id --name-only -r <sha>` and passes the result
directly to the file fetcher.

No text check. No garbage check. No warning. `expansion_warnings` is empty.

Consequently **any commit that touches a `.env` file causes that file's full
contents to be transmitted**, along with binary blobs (decoded with
`errors="replace"`) and deny-listed lockfiles.

### 2. Credential files on the text allowlist (#540)

Independently, `TEXT_EXTENSIONS` contained `.env`, `.env.example`, and
`.env.sample`, so a `.env` inside a directory passed via `target_paths` was
treated as reviewable source. Also on the list, and not identified in the
original report:

- **`.npmrc`** and **`.yarnrc`** — routinely contain
  `//registry.npmjs.org/:_authToken=…`
- **`secrets.yaml` / `secrets.yml`** — matched via the `.yaml` / `.yml` entries

Note that `.env.local`, `.env.production`, `id_rsa`, `*.pem`,
`terraform.tfvars`, and `kubeconfig` were excluded only **by accident** —
`Path(".env.local").suffix` is `.local`, which is not on the list. No policy
protected them.

## Impact — bounded

**Only content committed to git is reachable.** Every byte is read via
`git cat-file` / `git show <sha>:<path>`. There is no filesystem read of target
files anywhere in `verification/`. An untracked or `.gitignore`d `.env` — the
common case, and the one holding a developer's real API keys — was never
readable and is not affected.

Exposure is therefore confined to credential files **committed to the
repository**, on a commit that a `verify` run touched.

## Patches

Fixed in **`<FIX_VERSION>`**:

- All candidate-path producers, including the `git diff-tree` branch, are routed
  through a single selector; an unfiltered path is no longer representable.
- A compiled-in, non-overridable secret-path denylist (case-insensitive) excludes
  `.env*`, `*.pem`, `*.key`, `id_rsa*`, `.npmrc`, `.yarnrc`, `.pypirc`,
  `.git-credentials`, `.aws/credentials`, `kubeconfig`, `secrets.y*ml`,
  `terraform.tfvars`, and others, before any blob is fetched.

Design rationale: `docs/adr/ADR-053-verify-file-selection-trust-boundary.md`.

## Workarounds

For users who cannot upgrade immediately:

1. Always pass an explicit `target_paths` naming only the files to review. This
   avoids the unfiltered `diff-tree` path (defect 1) but **not** defect 2.
2. Ensure credential files are not committed. `git ls-files | grep -E '^\.env|\.npmrc|\.yarnrc'`
3. Do not run `verify` / `gate` over commit ranges that touch credential files.

## Remediation for affected users — rotate

> **If you committed credentials to your repository and ran `council-verify`,
> `council-gate`, or the MCP `verify` tool over a commit that touched them,
> those credentials were transmitted to your configured LLM provider and may be
> retained under that provider's terms. Rotate them.**

Context, so the advice is proportionate: if you are in this position, those
secrets were already in your git history, and git history is not a secret store.
They were arguably compromised before Council read them. Rotation is warranted
regardless; Council widened the exposure, it did not create it.

### How to check whether you were affected

We **cannot** enumerate affected users — the prompts went to third parties and
we collect no telemetry on their contents. You can check your own history:

```bash
# 1. Were credential files ever committed?
git log --all --diff-filter=A --name-only --pretty=format: \
  | sort -u | grep -Ei '(^|/)(\.env($|\.)|\.npmrc|\.yarnrc|\.pypirc|secrets\.ya?ml|\.git-credentials|id_rsa)'

# 2. Did a verify run touch a commit that contained them?
#    Local verification transcripts record snapshot_id per run.
ls .council/logs/ 2>/dev/null && grep -rl "snapshot_id" .council/logs/ | head
```

Then check your LLM provider's data-retention and zero-retention settings for
the relevant period.

## Credit

Discovered during maintainer triage while drafting ADR-053, prompted by a
Council review of PR #539.

## Process note (for maintainers — not part of the published advisory)

`SECURITY.md` states "Do NOT open a public GitHub issue for security
vulnerabilities." #543 was nevertheless filed publicly before this advisory
existed. Private vulnerability reporting was also **disabled** on the repository
at the time, so the documented reporting channel did not function. Both are
corrected in the same change as the fix. Because the issue is public, there is
no private-fix window; publish the advisory promptly once the fix ships.
