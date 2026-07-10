# GitHub Security Advisory (record): verify() transmits committed credential files to third-party LLM providers

> **Status: PUBLISHED 2026-07-10.** [GHSA-fpxw-qr53-pxfp](https://github.com/amiable-dev/llm-council/security/advisories/GHSA-fpxw-qr53-pxfp)
> — CVE **pending** (GitHub CNA review; the advisory records the CVE id once assigned).
>
> This file is the repo-side record of the advisory. The **Form fields** below map
> to the discrete GHSA form inputs; the **Description** section is verbatim the
> advisory's published Description field (canonical Impact / Patches / Workarounds /
> References template).
>
> Fix released in **v0.39.0** (2026-07-10). Disclosure complete: advisory published,
> CVE requested, README notice added. Tracking: #543, #540, #551.

---

## Form fields

| Field | Value |
|---|---|
| **Title** | verify() transmits committed credential files (.env, .npmrc, .yarnrc) to third-party LLM providers |
| **Ecosystem** | pip (PyPI) |
| **Package** | `llm-council-core` |
| **Affected versions** | `>= 0.22.0, < 0.39.0` |
| **Patched versions** | `0.39.0` |
| **Severity** | Medium — **CVSS 5.3** (`CVSS:3.1/AV:L/AC:H/PR:L/UI:R/S:C/C:H/I:N/A:N`) |
| **Weakness (CWE)** | CWE-200 — Exposure of Sensitive Information to an Unauthorized Actor |

### Severity note

Scored **5.3 (Medium)** deliberately conservatively: two independent preconditions
must both hold (credentials already committed to git **and** a `verify`/`gate` run
over a commit touching them), and the run is victim-initiated — there is no remote
attacker. The alternative reading `AC:L/UI:N` scores **6.5**, still Medium, so the
bucket (and therefore Dependabot severity) is unchanged either way. `S:C` (scope
changed) is the load-bearing metric: the data crosses out of the tool's authority
to a third-party provider.

### Affected-range confirmation

Range `>= 0.22.0` confirmed by **reading the code at each tag** (not `git log -S`):
**v0.21.0** fetched no file contents at all (`_build_verification_prompt` embedded
no `{file_contents}`), so no leak was possible. **v0.22.0** introduced
`_build_verification_prompt`, which embeds `{file_contents}` via the unfiltered
`git diff-tree` branch — a committed `.env` touched by a commit was transmitted.
`TEXT_EXTENSIONS` and the `.env` allowlist entry (#540) arrived at **v0.23.0**;
from v0.22.0–v0.22.x the leak was broader (no filter of any kind), narrowing to the
#540 framing at v0.23.0.

---

## Description (published verbatim)

### Impact

`llm-council-core`'s `verify()` assembles a prompt from file contents read out of a git snapshot and sends it to the configured third-party LLM provider(s) (OpenRouter, Anthropic, OpenAI, …). Two independent defects caused **committed credential files to be included in that prompt**, and therefore transmitted off-machine (CWE-200).

**1. `target_paths=None` bypassed all filtering (#543).** The text/garbage filters ran only when a caller passed an explicit `target_paths`. With `target_paths` omitted — the **default** at both `run_verification()` and the MCP `verify` tool — the pipeline ran `git diff-tree --name-only` and passed the result straight to the file fetcher: no text check, no garbage check, no warning. **Any commit that merely touched a `.env` transmitted its full contents**, along with binary blobs and lockfiles.

**2. Credential files on the text allowlist (#540).** `TEXT_EXTENSIONS` contained `.env`, `.env.example`, `.env.sample`, and — not identified in the original report — **`.npmrc`** and **`.yarnrc`** (which routinely hold `//registry.npmjs.org/:_authToken=…`). `secrets.yaml`/`secrets.yml` rode in via the `.yaml`/`.yml` entries.

**Who is impacted — and the bound.** Only content **committed to git** is reachable: every byte is read via `git cat-file` / `git show <sha>:<path>`, never the filesystem. An untracked or `.gitignore`d `.env` — the common case, holding a developer's real keys — was never readable. There is no remote attacker; disclosure is caused by the operator's own `verify`/`gate` invocation. So the affected party is anyone who **committed a credential file and then ran `verify`/`gate`/MCP `verify` over a commit that touched it**.

**> If that is you, rotate the affected credentials.** They were already in your git history (which is not a secret store) and were arguably compromised before Council read them; Council widened the exposure, it did not create it.

**How to check whether you were affected** (affected users cannot be enumerated — the prompts went to third parties and no telemetry is collected on their contents):

```bash
# 1. Were credential files ever committed?
git log --all --diff-filter=A --name-only --pretty=format: \
  | sort -u | grep -Ei '(^|/)(\.env($|\.)|\.npmrc|\.yarnrc|\.pypirc|secrets\.ya?ml|\.git-credentials|id_rsa)'

# 2. Did a verify run touch a commit that contained them?
#    Local verification transcripts record snapshot_id per run.
ls .council/logs/ 2>/dev/null && grep -rl "snapshot_id" .council/logs/ | head
```

Then review your LLM provider's data-retention / zero-retention settings for the relevant period.

### Patches

Fixed in **`llm-council-core` 0.39.0**. Upgrade to `>= 0.39.0`.

- Every candidate-path producer — including the `git diff-tree` branch — is routed through a single non-bypassable selector; an unfiltered fetch is no longer representable (enforced by an architecture test).
- A compiled-in, case-insensitive, non-overridable secret-path denylist excludes `.env*`, `*.pem`, `*.key`, `id_rsa*`, `.npmrc`, `.yarnrc`, `.pypirc`, `.git-credentials`, `.aws/credentials`, `kubeconfig`, `secrets.y*ml`, `terraform.tfvars`, and others **before any blob is fetched**.

Affected range `>= 0.22.0, < 0.39.0`. v0.21.0 fetched no file contents (no leak possible); v0.22.0 introduced the prompt-building path that embeds file contents via the unfiltered `diff-tree` branch, and `.env`-on-the-allowlist (#540) followed at v0.23.0. Confirmed by reading the code at each tag.

### Workarounds

If you cannot upgrade immediately:

1. Always pass an explicit `target_paths` naming only the files to review (avoids defect 1, not defect 2).
2. Ensure credential files are not committed to the repository.
3. Do not run `verify` / `gate` over commit ranges that touch credential files.

### References

- Design rationale: [ADR-053 — Verify File Selection & Trust Boundary](https://github.com/amiable-dev/llm-council/blob/master/docs/adr/ADR-053-verify-file-selection-trust-boundary.md)
- Fix release: [v0.39.0](https://github.com/amiable-dev/llm-council/releases/tag/v0.39.0)
- Tracking issues: [#543](https://github.com/amiable-dev/llm-council/issues/543) (unfiltered default path), [#540](https://github.com/amiable-dev/llm-council/issues/540) (credential files on the text allowlist)
- CWE-200: Exposure of Sensitive Information to an Unauthorized Actor
- Precedent (secrets rendered readable outside the trust boundary; guidance "assume leaked, rotate"): [CVE-2025-30066 / GHSA-mrrh-fwg8-r2c3](https://github.com/advisories/GHSA-mrrh-fwg8-r2c3)

_Found during maintainer triage while drafting ADR-053, prompted by a Council review of PR #539._

---

## Process note (for maintainers — NOT part of the published advisory)

`SECURITY.md` states "Do NOT open a public GitHub issue for security
vulnerabilities." #543 was nevertheless filed publicly before this advisory
existed. Private vulnerability reporting was also **disabled** on the repository at
the time, so the documented reporting channel did not function. Both were corrected
alongside the fix (PVR enabled 2026-07-10; `SECURITY.md` rewritten). Because the
issue is public there is no private-fix window; publish the advisory promptly.
