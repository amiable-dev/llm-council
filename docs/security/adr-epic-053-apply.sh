#!/usr/bin/env bash
# adr-epic apply script
# Generated: 2026-07-10T00:00:00Z
# Source ADR(s): docs/adr/ADR-053-verify-file-selection-trust-boundary.md
# Source spec(s): docs/adr/ADR-053-implementation-spec.md
# Granularity strategy: per-work-item (spec sub-sections P0.1..P0.4, P1, P3.1..P3.6)
# Tier filter: none
# Epic-marking convention: title-prefix
#   (detected: #505 [priority-high,adr-048], #359 [enhancement,adr-011],
#    #443 [] — no existing epic carries an `epic` label, and no `epic`
#    label exists in the repo vocabulary. Title-prefix it is.)
# Will create: 1 epic + 11 children
#
# PLAN (grouped by tier):
# - Epic: epic: ADR-053 Verify File Selection & Trust Boundary — implementation tracking
#
# === P0 (security fix — blocks disclosure) — 4 children ===
#   1. fix(verify): route every candidate path through one selector (closes #543)
#        — labels: bug, security, priority-high, blocking, tdd
#   2. fix(verify): compiled-in secret-path denylist; drop .env/.npmrc from TEXT_EXTENSIONS (closes #540)
#        — labels: bug, security, priority-high, tdd
#   3. fix(verify): validate snapshot_id at the run_verification boundary + garbage dir-component matching
#        — labels: bug, security, priority-medium, tdd
#   4. chore(release): patch release for the verify secret-transmission fix
#        — labels: priority-high, blocking
#
# === P1 (disclosure — gated on the P0 release) — 1 child ===
#   5. docs(security): publish GHSA, request CVE, ship rotation guidance
#        — labels: security, documentation, priority-high
#
# === P2 (verify trustworthiness) — 0 new children ===
#   (already filed: #544 binary-verdict parse failure, #545 waterfall starvation.
#    The epic references them; this script does NOT recreate them.)
#
# === P3 (ADR-053 design work — no security urgency) — 6 children ===
#   6. feat(verify): Q1 content sniffing — NUL heuristic + .gitattributes, behind LLM_COUNCIL_FILE_SELECTION
#        — labels: enhancement, adr, tdd, priority-medium
#   7. feat(verify): Q2 reviewability — linguist-generated/vendored, path-component garbage matching, .svg
#        — labels: enhancement, adr, priority-medium
#   8. feat(verify): honor the .llmignore family (no seeding) + `llm-council ignore` ergonomics
#        — labels: enhancement, adr, priority-medium
#   9. feat(verify): structural coverage receipt + conservation invariant (part of #542)
#        — labels: enhancement, adr, tdd, priority-medium
#  10. feat(verify): coverage clamp — pass unrepresentable over unreviewed files [BLOCKED on OQ1]
#        — labels: enhancement, adr, blocking, deferred
#  11. feat(verify): shadow-mode telemetry, then flip LLM_COUNCIL_FILE_SELECTION=content
#        — labels: enhancement, adr, priority-medium
#
# MISSING LABELS (user must address before running):
# - adr-053 : the repo uses per-ADR labels (adr-011 … adr-051). Needed by the
#             epic and children 6-11. Create with:
#               gh label create adr-053 --description "ADR-053 verify file selection"
#             Until then this script uses the generic `adr` label.
# - P3      : repo has P0/P1/P2 labels but they read as PRIORITY, not phase.
#             This script deliberately does NOT use them; phase lives in the
#             title and the epic body. No action required.
#
# DUPLICATES (will be skipped at run-time):
# - Epic pre-flight below aborts on an exact-title match.
# - #544 and #545 already exist and are NOT recreated (referenced only).
# - #540, #542, #543 already exist and are NOT recreated (closed by children).

set -euo pipefail

export GH_REPO="amiable-dev/llm-council"

EPIC_TITLE='epic: ADR-053 Verify File Selection & Trust Boundary — implementation tracking'

WORKDIR="$(mktemp -d)"
cleanup() { rm -rf "$WORKDIR"; }
trap cleanup EXIT

# --- helpers ----------------------------------------------------------------

# Abort if a body file contains any @@SENTINEL@@ token we did not emit.
# ADR-derived prose is untrusted; this guarantees every sed replacement below
# targets only a generator-emitted sentinel.
check_sentinels() {
  local file="$1"; shift
  local allowed=" $* "
  local tok
  while read -r tok; do
    [ -z "$tok" ] && continue
    case "$allowed" in
      *" $tok "*) ;;
      *) echo "FATAL: unexpected sentinel '$tok' in $file" >&2; exit 1 ;;
    esac
  done < <(grep -oE '@@[A-Za-z0-9_]+@@' "$file" | sort -u || true)
}

require_int() {
  local name="$1" val="$2"
  case "$val" in
    ''|*[!0-9]*) echo "FATAL: $name is not a bare integer: '$val'" >&2; exit 1 ;;
  esac
}

# Portable literal-string substitution (GNU/BSD sed differ on -i).
# Every replacement value is an ^[0-9]+$-validated integer.
subst() {
  local file="$1"; shift
  local expr=""
  while [ "$#" -gt 0 ]; do
    expr="${expr}s/$1/$2/g; "
    shift 2
  done
  sed "$expr" "$file" > "$file.tmp" && mv "$file.tmp" "$file"
}

# --- pre-flight: duplicate epic ---------------------------------------------

echo "==> Pre-flight: checking for an existing epic with this exact title"
EXISTING="$(gh issue list --search "epic in:title" --state all --limit 50 \
  --json number,title \
  --jq "[.[] | select(.title == \"$EPIC_TITLE\")] | length")"
if [ "$EXISTING" != "0" ]; then
  echo "FATAL: an epic with this exact title already exists. Aborting (no double-create)." >&2
  gh issue list --search "epic in:title" --state all --limit 50 --json number,title \
    --jq ".[] | select(.title == \"$EPIC_TITLE\") | \"  #\(.number)  \(.title)\"" >&2
  exit 1
fi
echo "    none found — proceeding"

# --- referenced pre-existing issues -----------------------------------------
# Not created by this script. Verified read-only at generation time.
ISSUE_LEAK=543        # target_paths=None bypasses all filtering (security)
ISSUE_ENV=540         # .env in TEXT_EXTENSIONS
ISSUE_ALLOWLIST=542   # allowlist drops unlisted languages + buried omissions
ISSUE_VERDICT=544     # binary-verdict parse failure degrades confidence
ISSUE_WATERFALL=545   # waterfall enforces per-model not per-stage deadlines

# --- step 1: create epic placeholder ----------------------------------------

echo "==> Creating epic (placeholder body)"
EPIC_URL="$(gh issue create \
  --title "$EPIC_TITLE" \
  --label security --label priority-high --label adr \
  --body "Pending child creation; will be updated.")"
EPIC_N="${EPIC_URL##*/}"
require_int EPIC_N "$EPIC_N"
echo "    epic #$EPIC_N  $EPIC_URL"

# ============================================================================
# === P0 (security fix — blocks disclosure)
# ============================================================================

echo "==> [P0] child 1/11: selector chokepoint"
cat > "$WORKDIR/child-1-body.md" <<'BODY'
Part of #@@EPIC@@ · Closes #543

## Context

`_is_text_file()` and `_is_garbage_file()` have exactly one call site each:
inside `_expand_target_paths()` (`verification/file_ops.py:332-348`). That
function is only reached from the `if target_paths:` branch of
`_fetch_files_for_verification_async_with_metadata()`. The `else` branch
(`verification/file_ops.py:561-586`) shells out to
`git diff-tree --no-commit-id --name-only -r <sha>` and assigns the result
directly to `files_to_fetch` — no text check, no garbage check, no warning.

`target_paths` defaults to `None` at both public entry points
(`verification/api.py:187`, `mcp_server.py:416`), so this is the DEFAULT path.

Source: ADR-053 § "Q0 — Enforcement: one chokepoint"; spec § P0.1.

## Scope

- `verification/file_ops.py` — new `select_blobs(snapshot_id, candidates)`
  returning `(selected, omitted)`, where `candidates: Iterable[Candidate]` and
  `Candidate = (path, origin)`. **Origin is a property of each candidate, not of
  the call** — a request mixes explicit paths with directory-expanded
  discoveries (ADR-053 § "Q0", council review round 2 `minor`).
- Route ALL three candidate producers through it: the `blob` branch, the `tree`
  branch, and the `git diff-tree` branch.
- `_fetch_file_at_commit_async()` takes a `SelectedBlob` token, not a `str`, so
  an unfiltered fetch is a type error rather than a review miss.

**Out of scope:** do NOT change the text/garbage predicates here.
`TEXT_EXTENSIONS` stays exactly as-is; it simply now runs where it never ran.
That keeps this PR purely narrowing and trivially reviewable.

## Acceptance criteria

- [ ] `target_paths=None` applies the same filters as `target_paths=["<dir>"]`
- [ ] No call to `_fetch_file_at_commit_async()` exists outside the selector module
- [ ] `expansion_warnings` is populated on the `diff-tree` path
- [ ] Behaviour change documented in `CHANGELOG.md` under `### Security`:
      binaries and lockfiles stop appearing in prompts on the default path, so
      some verdicts will move. That is the fix, not a regression.

## TDD plan

Start from a failing red-team fixture — this is the test whose absence let the
bug ship. New `tests/test_verify_file_selection.py`:

- Fixture repo, **non-root** commit (`git diff-tree` emits nothing on a root
  commit) touching `.env`, `.npmrc`, `id_rsa`, `logo.png`, `yarn.lock`, `main.py`.
- Parametrise over `target_paths=None`, `target_paths=["<dir>"]`,
  `target_paths=["<explicit file>"]`.
- Assert the assembled prompt contains `main.py` and NONE of the others.
- The `None` case reds today. Nothing currently covers it.

Plus an architecture test asserting the fetch function has no callers outside
the selector module.

## Dependencies

None. This is the first ticket and blocks #@@CHILD_2@@ and #@@CHILD_4@@.

## References

- ADR-053 § "Q0 — Enforcement", § "The filter does not run on the default code path at all"
- spec § P0.1, § P0.4
- #543 (repro), `verification/file_ops.py:330-348`, `:561-586`
BODY
check_sentinels "$WORKDIR/child-1-body.md" "@@EPIC@@" "@@CHILD_2@@" "@@CHILD_4@@"
# Forward refs to children 2 and 4 cannot be substituted yet; strip to plain text.
subst "$WORKDIR/child-1-body.md" "@@EPIC@@" "$EPIC_N"
sed 's/#@@CHILD_2@@/the denylist ticket/g; s/#@@CHILD_4@@/the release ticket/g' \
  "$WORKDIR/child-1-body.md" > "$WORKDIR/child-1-body.tmp" \
  && mv "$WORKDIR/child-1-body.tmp" "$WORKDIR/child-1-body.md"
CHILD_1_URL="$(gh issue create \
  --title 'fix(verify): route every candidate path through one selector (closes #543)' \
  --label bug --label security --label priority-high --label blocking --label tdd \
  --body-file "$WORKDIR/child-1-body.md")"
CHILD_1="${CHILD_1_URL##*/}"; require_int CHILD_1 "$CHILD_1"
echo "    #$CHILD_1"

echo "==> [P0] child 2/11: secret denylist"
cat > "$WORKDIR/child-2-body.md" <<'BODY'
Part of #@@EPIC@@ · Closes #540

## Context

`TEXT_EXTENSIONS` (`verification/constants.py`) contains `.env`,
`.env.example`, `.env.sample`, `.npmrc`, and `.yarnrc`. `.npmrc`/`.yarnrc`
routinely hold `//registry.npmjs.org/:_authToken=…`, and `secrets.yaml` rides in
on the `.yaml` entry. None of `.npmrc`, `.yarnrc`, `secrets.yaml` were named in
#540 — they were found by executing the real predicate against master.

Conversely `.env.local`, `.env.production`, `id_rsa`, `*.pem`,
`terraform.tfvars`, and `kubeconfig` are excluded **by accident**:
`Path(".env.local").suffix` is `.local`, which is not on the list. No policy
protects them. This is exactly why the trust boundary must be explicit and must
land alongside (never after) any move toward content sniffing.

Source: ADR-053 § "Q3 — Permissibility", § "Why #540 and #542 must ship together";
spec § P0.2.

## Scope

- New compiled-in secret-path denylist, evaluated inside `select_blobs()` BEFORE
  any blob is fetched.
- **Case-insensitive** — a deliberate divergence from gitignore's case-sensitive
  semantics. `Secrets.yaml` and `.Env` are real files, and for a security floor
  over-matching is the safe direction. A legitimate `Credentials.md` excluded by
  this rule surfaces in the receipt as `denied_secret`, which is diagnosable; an
  under-match is a silent leak.
- **Not overridable by any in-repo file.** An ignore file may narrow what is
  reviewed; it may never re-admit a denied secret.
- Remove `.env`, `.env.example`, `.env.sample`, `.npmrc`, `.yarnrc` from
  `TEXT_EXTENSIONS`. Preserve `*.example` / `*.sample` / `*.template` by NAME
  PATTERN, not by a fake extension entry.
- Full pattern list (env, keys/certs, ssh/gpg, package registries, cloud,
  git/docker, unix classics, IaC): ADR-053 § "Q3 — Permissibility".

## Acceptance criteria

- [ ] A commit touching `.env` never transmits it, on any `target_paths` value
- [ ] `.npmrc`, `.yarnrc`, `.pypirc`, `.git-credentials`, `.aws/credentials`,
      `kubeconfig`, `secrets.y*ml`, `terraform.tfvars`, `id_rsa*`, `*.pem` all excluded
- [ ] `.env.example` / `.env.sample` / `*.template` still reviewable
- [ ] Matching is case-insensitive (`.Env`, `Secrets.yaml` excluded)
- [ ] No in-repo file can re-admit a denied path (no `!.env` escape)
- [ ] Denial records the PATH ONLY, never the matched value (mirrors ADR-050 D3 `scrub_exception`)

## TDD plan

Extend `tests/test_verify_file_selection.py` from the selector ticket:
- parametrised denial table over the full pattern list, both cases
- assert `.env.example` survives
- assert a synthetic `.llmignore` containing `!.env` does not re-admit it

## Dependencies

Blocked by the selector chokepoint ticket — the denylist hooks into
`select_blobs()`, which does not exist yet.

## References

- ADR-053 § "Q3 — Permissibility", § "Do we seed the ignore file? No."
- spec § P0.2 · #540 · council review round 1 (`major`, `bff6de55`)
BODY
check_sentinels "$WORKDIR/child-2-body.md" "@@EPIC@@"
subst "$WORKDIR/child-2-body.md" "@@EPIC@@" "$EPIC_N"
CHILD_2_URL="$(gh issue create \
  --title 'fix(verify): compiled-in secret-path denylist; drop .env/.npmrc from TEXT_EXTENSIONS (closes #540)' \
  --label bug --label security --label priority-high --label tdd \
  --body-file "$WORKDIR/child-2-body.md")"
CHILD_2="${CHILD_2_URL##*/}"; require_int CHILD_2 "$CHILD_2"
echo "    #$CHILD_2"

echo "==> [P0] child 3/11: argv hygiene + garbage dir matching"
cat > "$WORKDIR/child-3-body.md" <<'BODY'
Part of #@@EPIC@@

## Context

Two small hardening items found while auditing the selection path.

**1. `snapshot_id` is not validated at the library boundary.**
`validate_snapshot_id()` (`GIT_SHA_PATTERN`, 7-40 hex) is enforced on the
Pydantic `VerificationRequest` and in the HTTP handler (`verification/api.py:1127`),
but NOT at `run_verification()` (`verification/api.py:760`) — which MCP and
`llm-council gate` call directly. `snapshot_id` is interpolated into git argv.

Shell injection is already precluded: all six git calls use
`asyncio.create_subprocess_exec` with argv arrays, and there are zero
`shell=True` / `create_subprocess_shell` calls in the package. The residual risk
is ARGUMENT injection, and it becomes load-bearing once pathspec-style calls
(`git grep … -- <paths>`) are added in P3.1.

**2. `GARBAGE_FILENAMES` directory entries are dead code.**
`_is_garbage_file()` compares `Path(p).name`, so `node_modules`, `__pycache__`,
and `.git` — all DIRECTORIES — never match. `node_modules/react/index.js`
returns `garbage=False, text=True` and is reviewed.

Source: ADR-053 § "Q0 — Argument hygiene", § "Latent bugs fixed in passing";
spec § P0.3, § P0.4.

## Scope

- Call `validate_snapshot_id()` at the `run_verification()` boundary.
- `_is_garbage_file()` matches against EVERY path component, not just the basename.
- Note in code comments that `--` before pathspecs is required for the git calls
  added in P3.1 (no pathspec-style calls exist yet, so no `--` work here).

## Acceptance criteria

- [ ] `run_verification(snapshot_id="--help")` raises rather than reaching git
- [ ] `node_modules/react/index.js` is excluded as garbage
- [ ] `src/__pycache__/x.pyc` is excluded as garbage
- [ ] No behaviour change for well-formed input

## TDD plan

- `tests/test_verify_file_selection.py::test_snapshot_id_validated_at_library_boundary`
- `tests/test_verify_file_selection.py::test_garbage_matches_path_components`

## Dependencies

Independent of the other P0 tickets; may land in parallel.

## References

- ADR-053 § "Q0", § "Latent bugs fixed in passing" items 1 and 3
- spec § P0.3 · council review round 1 (`minor`, `bff6de55`)
- `verification/api.py:760`, `:1127`; `verification/file_ops.py:290-293`
BODY
check_sentinels "$WORKDIR/child-3-body.md" "@@EPIC@@"
subst "$WORKDIR/child-3-body.md" "@@EPIC@@" "$EPIC_N"
CHILD_3_URL="$(gh issue create \
  --title 'fix(verify): validate snapshot_id at the run_verification boundary + garbage dir-component matching' \
  --label bug --label security --label priority-medium --label tdd \
  --body-file "$WORKDIR/child-3-body.md")"
CHILD_3="${CHILD_3_URL##*/}"; require_int CHILD_3 "$CHILD_3"
echo "    #$CHILD_3"

echo "==> [P0] child 4/11: patch release"
cat > "$WORKDIR/child-4-body.md" <<'BODY'
Part of #@@EPIC@@

## Context

**This ticket is the gate for the entire disclosure phase.**

A GitHub Security Advisory published without a `patched_versions` entry causes
Dependabot to alert every downstream user with **no safe version to upgrade to**.
So the fix must be released before the advisory is published, not after.

Source: spec § "The sequencing constraint", § P0 DoD.

## Scope

Cut a patch release containing #@@CHILD_1@@, #@@CHILD_2@@, #@@CHILD_3@@.

Follow the release workflow in `CLAUDE.md` § "Release Workflow" exactly —
never push directly to `master`; release branch → PR → required checks
(Test, Lint, Type Check, DCO) → squash merge → tag from updated master.

## Acceptance criteria

- [ ] #@@CHILD_1@@, #@@CHILD_2@@, #@@CHILD_3@@ all merged
- [ ] `CHANGELOG.md` has a `### Security` entry (this convention already exists in
      the file — 4 prior uses; do not invent a new one). Draft copy: spec § P1.
- [ ] `SECURITY.md` and `docs/guides/verify.md` updated
- [ ] Tag pushed; `publish.yml` green; `pip index versions llm-council-core` shows it
- [ ] Fixed version recorded in `docs/security/advisory-draft-verify-secret-transmission.md`
      (replace every `<FIX_VERSION>` placeholder)

## Dependencies

Blocked by #@@CHILD_1@@, #@@CHILD_2@@, #@@CHILD_3@@.
Blocks the disclosure ticket.

## References

- spec § "The sequencing constraint", § P0.4 DoD
- `CLAUDE.md` § "Release Workflow"
- Note: this epic's normal rule is one release per epic, not per PR. **P0 is the
  deliberate exception** — disclosure cannot proceed without a released fix.
BODY
check_sentinels "$WORKDIR/child-4-body.md" "@@EPIC@@" "@@CHILD_1@@" "@@CHILD_2@@" "@@CHILD_3@@"
subst "$WORKDIR/child-4-body.md" \
  "@@EPIC@@" "$EPIC_N" "@@CHILD_1@@" "$CHILD_1" "@@CHILD_2@@" "$CHILD_2" "@@CHILD_3@@" "$CHILD_3"
CHILD_4_URL="$(gh issue create \
  --title 'chore(release): patch release for the verify secret-transmission fix' \
  --label priority-high --label blocking \
  --body-file "$WORKDIR/child-4-body.md")"
CHILD_4="${CHILD_4_URL##*/}"; require_int CHILD_4 "$CHILD_4"
echo "    #$CHILD_4"

# ============================================================================
# === P1 (disclosure — gated on the P0 release)
# ============================================================================

echo "==> [P1] child 5/11: disclosure"
cat > "$WORKDIR/child-5-body.md" <<'BODY'
Part of #@@EPIC@@

## Context

The mechanism that actually protects users is the **GHSA**, not the CVE and not
a README banner. A published GHSA lands in the GitHub Advisory Database in OSV
format and auto-alerts every downstream repo via Dependabot. No README notice
reaches those people.

Draft text is already written:
`docs/security/advisory-draft-verify-secret-transmission.md`.

Source: spec § P1.

## Scope

1. Confirm the affected-version range. The draft proposes `>= 0.22.0`, traced via
   `git log -S` to `0005fe7` (unfiltered `diff-tree` path, first released v0.22.0)
   and `1f91c08` (`.env` on the allowlist, v0.23.0). **The #380 submodule split
   (`f6db229`) masks earlier history** — verify v0.20.x / v0.21.x contain no
   earlier variant before committing to the range.
2. **Maintainer scores CVSS.** Do not inflate. Not remotely triggerable; requires
   credentials already committed to git. An inflated score costs credibility.
3. Set the fixed version on the draft advisory → request a CVE from GitHub
   (GitHub is a CNA; ~72h review) → publish.
4. Ship the doc surfaces.

## Acceptance criteria

- [ ] Affected range confirmed against v0.20/v0.21
- [ ] CVSS scored by a maintainer (not copied from the draft's placeholder vector)
- [ ] GHSA published WITH a fixed version; CVE requested
- [ ] `CHANGELOG.md` `### Security` entry (draft copy in spec § P1)
- [ ] GitHub release notes link the advisory + rotation guidance
- [ ] `docs/guides/verify.md` security note + the ADR-053 non-goal
- [ ] `README.md` short DATED notice (temporary — see the scheduled removal reminder)
- [ ] `SECURITY.md` already updated (done 2026-07-10, same change as the ADR)

## Rotation guidance (must appear in the advisory and release notes)

> If you committed credentials to your repository and ran `council-verify`,
> `council-gate`, or the MCP `verify` tool over a commit that touched them, those
> credentials were transmitted to your configured LLM provider and may be
> retained under that provider's terms. **Rotate them.**

Be proportionate: anyone affected had already committed secrets to git, so those
secrets were arguably compromised before Council read them. We cannot enumerate
affected users — the prompts went to third parties and we hold no telemetry on
their contents. `docs/security/advisory-draft-...md` contains the self-check
commands users can run against `.council/logs`.

## Process failure to record

`SECURITY.md` says "Do NOT open a public GitHub issue for security
vulnerabilities." #543 was filed publicly anyway, and private vulnerability
reporting was DISABLED on the repo at the time (now enabled), so the documented
channel did not function. Because the exposure is not remotely triggerable, harm
is low — but the private-fix window is gone, so publish promptly.

## Dependencies

Blocked by the P0 patch release, #@@CHILD_4@@. Publishing before a fixed version
exists is actively harmful (Dependabot alerts with no upgrade target).

## References

- spec § P1 · `docs/security/advisory-draft-verify-secret-transmission.md`
- #543, #540 · CWE-200 · precedent CVE-2025-30066 (tj-actions/changed-files)
BODY
check_sentinels "$WORKDIR/child-5-body.md" "@@EPIC@@" "@@CHILD_4@@"
subst "$WORKDIR/child-5-body.md" "@@EPIC@@" "$EPIC_N" "@@CHILD_4@@" "$CHILD_4"
CHILD_5_URL="$(gh issue create \
  --title 'docs(security): publish GHSA, request CVE, ship rotation guidance' \
  --label security --label documentation --label priority-high \
  --body-file "$WORKDIR/child-5-body.md")"
CHILD_5="${CHILD_5_URL##*/}"; require_int CHILD_5 "$CHILD_5"
echo "    #$CHILD_5"

# ============================================================================
# === P3 (ADR-053 design work — no security urgency)
# ============================================================================

echo "==> [P3] child 6/11: Q1 content sniffing"
cat > "$WORKDIR/child-6-body.md" <<'BODY'
Part of #@@EPIC@@ · Part of #542

## Context

`TEXT_EXTENSIONS` is a hand-maintained ~140-entry allowlist. `.zig`, `.gleam`,
`.roc`, `.odin`, `.d`, `.cr`, `.sol`, `.tf`, `.hcl`, `.dart`, `.cu`, `.mojo` are
all missing today (verified against master, post-#539). #533/#539 already paid an
issue, a PR, a review cycle and a release to add four characters (`.lock`).

Extensions are not a function of language: `.v` is Verilog AND V AND Coq; `.m` is
Objective-C AND MATLAB; `.d` is the D language AND a generated Makefile dep file.
No allowlist can be correct.

Source: ADR-053 § "Q1 — Decodability"; spec § P3.1.

## Scope

Reuse git's own heuristic (`buffer_is_binary()`): **a blob is text iff its first
8000 bytes contain no NUL byte.** ripgrep and `file(1)` use the same rule.

Empirically verified against git 2.50.1: `git grep -I --name-only -e '' <sha>`
classifies `main.zig`, `main.tf`, `LICENSE`, `CODEOWNERS`, and an extensionless
shebang script as text, and rejects a NUL-bearing PNG and a `weird.txt` whose
extension lies. A 12-line Python reimplementation matched git exactly on 11 files.

Implement as **(1b)**: sniff the bytes already streamed by
`_fetch_file_at_commit_async()`. Preferred over shelling out to `git grep -I`
(option 1a) on empirically discovered edges: `git grep` does not list EMPTY blobs,
exits **1** on no-match (not an error), and prefixes output `<sha>:<path>`.

- `git ls-tree -r --format='%(objecttype) %(objectsize) %(path)'` pre-pass (one
  call, verified) for a size cap BEFORE fetching. Fallback `git ls-tree -rl` on git < 2.36.
- Honor snapshot `.gitattributes`: `binary` / `-diff` excludes a path, read via
  `git --attr-source=<sha> …` (verified; it is a TOP-LEVEL git option, not a grep flag).
- **Pass `--` before every pathspec.** This is where child #@@CHILD_3@@'s deferred
  half becomes load-bearing.
- **Delete** the `{"makefile","dockerfile","jenkinsfile","cmakelists"}` special
  case. Under content sniffing, extensionless files just work.

Behind `LLM_COUNCIL_FILE_SELECTION = allowlist | shadow | content`, default
`allowlist`, byte-identical when off.

## Known blind spot (document, do not paper over)

UTF-16 source is full of NUL bytes and will classify as binary. **Git has the
identical blind spot** and repos work around it with `.gitattributes …
working-tree-encoding=UTF-16`. The escape hatch is the operator override; the
coverage receipt makes the omission visible rather than invisible. The 8000-byte
window is a heuristic, not a proof — a NUL at byte 9001 classifies as text
(verified). That is git's own risk tolerance, adopted deliberately.

## Acceptance criteria

- [ ] `.zig`, `.tf`, `.dart`, `.sol`, `.gleam` reviewed with no list edit
- [ ] `LICENSE`, `CODEOWNERS`, `Makefile`, `.envrc`, shebang scripts reviewed
- [ ] NUL-bearing blobs excluded with `reason=binary`
- [ ] `.gitattributes` `-diff` / `binary` honored, read from the SNAPSHOT
- [ ] Blob-size cap enforced before fetch
- [ ] `LLM_COUNCIL_FILE_SELECTION=allowlist` ⇒ byte-identical prompts (test-pinned)
- [ ] Every new git call passes `--` before pathspecs

## TDD plan

`tests/test_verify_content_sniffing.py` — fixture repo covering: `.zig`, `.tf`,
extensionless shebang, `LICENSE`, empty blob, NUL-at-byte-3, NUL-at-byte-9001,
UTF-16 file, `.gitattributes -diff`, oversized blob.

## Dependencies

Blocked by the selector chokepoint (needs `select_blobs()`), and by
#@@CHILD_3@@ for the `--` separator groundwork.

## References

- ADR-053 § "Q1 — Decodability", § "Alternatives considered" E
- spec § P3.1 · #542
BODY
check_sentinels "$WORKDIR/child-6-body.md" "@@EPIC@@" "@@CHILD_3@@"
subst "$WORKDIR/child-6-body.md" "@@EPIC@@" "$EPIC_N" "@@CHILD_3@@" "$CHILD_3"
CHILD_6_URL="$(gh issue create \
  --title 'feat(verify): Q1 content sniffing — NUL heuristic + .gitattributes, behind LLM_COUNCIL_FILE_SELECTION' \
  --label enhancement --label adr --label tdd --label priority-medium \
  --body-file "$WORKDIR/child-6-body.md")"
CHILD_6="${CHILD_6_URL##*/}"; require_int CHILD_6 "$CHILD_6"
echo "    #$CHILD_6"

echo "==> [P3] child 7/11: Q2 reviewability"
cat > "$WORKDIR/child-7-body.md" <<'BODY'
Part of #@@EPIC@@

## Context

Content sniffing (Q1) answers "can this go in a prompt". It does not answer "is
this worth spending tokens on". `GARBAGE_FILENAMES` is already the right shape
for the second question — deny known-noise — and stays.

Source: ADR-053 § "Q2 — Reviewability"; spec § P3.2.

## Scope

- Honor `.gitattributes` `linguist-generated` and `linguist-vendored` — GitHub
  Linguist's de-facto standard for "this is not authored source", already present
  in a large fraction of real repos, and exactly the Q2 question.
- Move `.svg` from "text" to noise-by-default: it decodes as text but is usually
  a large generated asset.
- Keep `MAX_FILES_EXPANSION` and the tier char budgets unchanged.

(The dead directory-entry bug in `_is_garbage_file()` is fixed earlier, in
#@@CHILD_3@@ — not here.)

## Acceptance criteria

- [ ] A path marked `linguist-generated` is omitted with `reason=generated`
- [ ] A path marked `linguist-vendored` is omitted with `reason=vendored`
- [ ] Attributes read from the SNAPSHOT (`git --attr-source=<sha>`)
- [ ] `.svg` omitted by default; overridable via operator config
- [ ] Flag-off ⇒ byte-identical

## TDD plan

Extend `tests/test_verify_content_sniffing.py` with a `.gitattributes` carrying
`vendor/** linguist-vendored` and `gen/** linguist-generated`.

## Dependencies

Blocked by the Q1 content-sniffing ticket, #@@CHILD_6@@ (shares the
`--attr-source` plumbing).

## References

- ADR-053 § "Q2 — Reviewability" · spec § P3.2
BODY
check_sentinels "$WORKDIR/child-7-body.md" "@@EPIC@@" "@@CHILD_3@@" "@@CHILD_6@@"
subst "$WORKDIR/child-7-body.md" "@@EPIC@@" "$EPIC_N" "@@CHILD_3@@" "$CHILD_3" "@@CHILD_6@@" "$CHILD_6"
CHILD_7_URL="$(gh issue create \
  --title 'feat(verify): Q2 reviewability — linguist-generated/vendored attributes, .svg as noise' \
  --label enhancement --label adr --label priority-medium \
  --body-file "$WORKDIR/child-7-body.md")"
CHILD_7="${CHILD_7_URL##*/}"; require_int CHILD_7 "$CHILD_7"
echo "    #$CHILD_7"

echo "==> [P3] child 8/11: .llmignore family"
cat > "$WORKDIR/child-8-body.md" <<'BODY'
Part of #@@EPIC@@

## Context

The AI-tool ecosystem has converged on *gitignore syntax in a tool-scoped
denylist file*, and vendors already interoperate: JetBrains AI Assistant reads
`.cursorignore`, `.codeiumignore`, and `.aiexclude`; Gemini Code Assist's
`.aiexclude` uses gitignore syntax. A vendor-neutral `.llmignore` spec exists.

**Do not invent `.councilignore`.** Read the existing family.

Source: ADR-053 § "Q3 (3b)", § "Do we seed the ignore file? No."; spec § P3.3.

## Scope

Read, in precedence order, **from the snapshot** (`git show <sha>:.llmignore`)
for reproducibility:

`.llmignore` → `.aiexclude` → `.aiignore` → `.cursorignore` → `.codeiumignore`

Match with `pathspec` (`GitWildMatchPattern` — the matcher `black` uses; new
runtime dependency, pure-Python). **Do not hand-roll a gitignore matcher.**

### Seeding: NO

The built-in secret denylist is **a floor, not a template**. We do not write an
ignore file into the user's repo:

1. **It would not work.** Ignore files are read from the git snapshot, so a file
   seeded on disk is uncommitted, therefore absent from the snapshot, therefore
   inert for the very run that created it.
2. The default must be safe with ZERO files present. If the answer to "what stops
   my `.env` being transmitted" is "a file you must author and commit", we have
   shipped a footgun with documentation.
3. A seeded template forks on first edit and can never be improved.

The ignore file is **additive narrowing only** — it may exclude more, never
re-admit a Q3-denied path.

### CLI ergonomics (explicitly NOT the security mechanism)

- `llm-council ignore --print-defaults` — emit the effective built-in denylist
- `llm-council ignore --init` — on explicit request, write a COMMENTED starter
  and remind the user to commit it
- `llm-council ignore --explain <path> [--sha …]` — which layer and rule decided,
  without running a council

## Acceptance criteria

- [ ] All five filenames honored, in precedence order, read from the snapshot
- [ ] `pathspec` used; no bespoke matcher
- [ ] `!.env` in any ignore file does NOT re-admit it (Q3 wins)
- [ ] No file is ever written to a user repo without an explicit `--init`
- [ ] `--explain` reports layer + rule for an arbitrary path

## TDD plan

`tests/test_verify_ignore_files.py` — precedence table; a `!`-negation attempting
to re-admit a denied secret; snapshot-vs-worktree divergence.

## Dependencies

Blocked by the secret-denylist ticket (Q3 must exist for the "cannot re-admit"
invariant to be testable).

## References

- ADR-053 § "Q3 (3b)", § "Sources" · spec § P3.3
- https://github.com/llmignore-spec/llmignore-spec
BODY
check_sentinels "$WORKDIR/child-8-body.md" "@@EPIC@@"
subst "$WORKDIR/child-8-body.md" "@@EPIC@@" "$EPIC_N"
CHILD_8_URL="$(gh issue create \
  --title 'feat(verify): honor the .llmignore family (no seeding) + `llm-council ignore` ergonomics' \
  --label enhancement --label adr --label priority-medium \
  --body-file "$WORKDIR/child-8-body.md")"
CHILD_8="${CHILD_8_URL##*/}"; require_int CHILD_8 "$CHILD_8"
echo "    #$CHILD_8"

echo "==> [P3] child 9/11: coverage receipt"
cat > "$WORKDIR/child-9-body.md" <<'BODY'
Part of #@@EPIC@@ · Part of #542

## Context

#542's second, more serious failure mode: when some `target_paths` resolve and
others do not, the call SUCCEEDS and returns a confident PASS/FAIL over partial
coverage. The dropped file appears only as a prose string in
`expansion_warnings` (`"Skipped non-text file: main.zig"`). No CI-gate
integration parses that.

ADR-051 set the precedent: the verdict is a pure function of structured evidence,
with `diagnostics.findings_by_severity` and a defensive
`verdict_evidence_mismatch` marker. Coverage is the same shape of problem.

Source: ADR-053 § "The other half of #542"; spec § P3.4.

## Scope

Additive, default-ON, all fields optional — no type break (the same non-breaking
argument ADR-051 made for `blocking_issues`).

```
coverage: {
  requested: [...],          # verbatim target_paths
  reviewed:  [...],          # blobs actually in the prompt
  omitted:   [{path, reason, origin}],
  explicit_omitted: bool,
  truncated: bool,
  policy: "clamp" | "fail" | "warn",
}
```

- `reason ∈ {binary, denied_secret, ignored, generated, vendored, too_large,
  truncated, not_found}` — the enumerated reason is what makes a `.zig` drop
  DISTINGUISHABLE from a `.png` drop, and therefore actionable.
- `origin ∈ {explicit, discovered}`.
- `reason=denied_secret` records the PATH ONLY, never the matched value
  (mirrors ADR-050 D3 `scrub_exception`).
- `expansion_warnings` retained, additive, demoted from load-bearing signal to
  human-readable prose.

### Conservation invariant

```
set(reviewed) & set(omitted) == {}
set(reviewed) | set(omitted) == set(candidates)
```

Asserted in `build_verification_result()`, with a defensive marker emitted on
violation — the `verdict_evidence_mismatch` pattern from ADR-051 C4. A response
with NO `coverage` block means the gate did not run, and that is detectable by
the caller rather than silent.

## Acceptance criteria

- [ ] `coverage` present on every `VerifyResponse`
- [ ] Conservation invariant asserted; violation emits a marker, never a crash
- [ ] `denied_secret` never leaks the matched value
- [ ] Property test: conservation holds over randomly generated trees
- [ ] `TestVerifyResponseFieldDrift` extended — every new field must appear by
      name in `docs/guides/verify.md` or `api.md` or CI reds (ADR-051 C6 precedent)

## Note

This ticket ships the receipt WITHOUT the clamp. That is deliberate: the receipt
makes omissions visible without making the gate noisy, and it is independently
valuable. The clamp is the next ticket and is blocked.

## Dependencies

Blocked by the selector chokepoint (needs `select_blobs()`'s `omitted` output).
Blocks the clamp ticket.

## References

- ADR-053 § "The other half of #542" · spec § P3.4 · #542 · ADR-051 C4/C6
BODY
check_sentinels "$WORKDIR/child-9-body.md" "@@EPIC@@"
subst "$WORKDIR/child-9-body.md" "@@EPIC@@" "$EPIC_N"
CHILD_9_URL="$(gh issue create \
  --title 'feat(verify): structural coverage receipt + conservation invariant (part of #542)' \
  --label enhancement --label adr --label tdd --label priority-medium \
  --body-file "$WORKDIR/child-9-body.md")"
CHILD_9="${CHILD_9_URL##*/}"; require_int CHILD_9 "$CHILD_9"
echo "    #$CHILD_9"

echo "==> [P3] child 10/11: coverage clamp (BLOCKED)"
cat > "$WORKDIR/child-10-body.md" <<'BODY'
Part of #@@EPIC@@ · Closes #542

## ⚠️ BLOCKED — do not start until ADR-053 Open Question 1 is answered

Under the uniform clamp, **any commit touching a `.png` returns `unclear`**. That
is literally true — the council did not review the PNG — and completely unusable.
**A noisy gate gets switched off, which is worse than no gate.**

Do not implement until the `coverage_ack` mechanism is designed. The receipt
(previous ticket) is independently valuable and ships first.

## Context

The clamp is justified by **honesty, not adversarial defense**. See ADR-053
§ "Threat model and non-goals": `verify()` reads file contents into an LLM
prompt, so an adversary who can commit `evil.py` can also attempt prompt
injection. No file-selection policy prevents that. Two rounds of council review
attacked, in turn, each carve-out an omission taxonomy created — first
`.llmignore` self-exclusion, then a NUL byte injected to force a `binary`
classification. Both findings were mechanically correct. Their lesson is that
**there is no stable partition of "omissions that cannot hide anything", because
the attacker writes the bytes** — so the rule is uniform, with no carve-out to
attack, and we do not claim it stops an adversary.

Source: ADR-053 § "The clamp: one uniform rule, no carve-outs"; spec § P3.5.

## Scope

- **A `pass` verdict may not be returned over a file the council did not read.**
  If any file in the changed set, or any explicitly-named `target_path`, is absent
  from `coverage.reviewed` ⇒ `pass` is not representable ⇒ `unclear` with a new
  `unclear_reason="incomplete_coverage"`, extending ADR-047 P1's
  `infra_failure|low_confidence|timeout`. Exit code stays 2.
- The omission `reason` is an EXPLANATION in the receipt, never a verdict carve-out.
- `denied_secret` on a changed file still clamps — `.envrc` is a shell script, and
  "we refused to read it" is not "we reviewed it".
- `LLM_COUNCIL_COVERAGE_POLICY = clamp (default) | fail | warn`.
- **`llm-council gate` HARD-ERRORS on `warn`.** A CI gate that ignores coverage is
  a foot-gun, and documenting it as unsafe is not a mechanism (council review
  round 2, `major`, `dc7acb57`). `warn` remains available to library callers and
  is always stamped into `coverage.policy`.

## Blocked on: `coverage_ack` design (ADR-053 Open Question 1)

Candidate shapes: a caller-supplied path list; a committed
`.council/coverage-baseline`; an omission-reason allowlist per invocation.
Prior art: mypy / Semgrep / `.gitleaksignore` baselines. Get it wrong and either
the gate is unusable or the clamp is vacuous.

## Acceptance criteria

- [ ] ADR-053 Open Question 1 resolved and the ADR updated FIRST
- [ ] `pass` unrepresentable over an unreviewed changed or explicit file
- [ ] `unclear_reason="incomplete_coverage"` added to the ADR-047 taxonomy, and
      the enum extension called out as a contract change for exhaustive matchers
- [ ] `llm-council gate` exits non-zero on `LLM_COUNCIL_COVERAGE_POLICY=warn`
- [ ] `coverage.policy` stamped on every response
- [ ] Documented as a `### Changed` CHANGELOG entry (behavior change, minor bump)

## Dependencies

Blocked by the coverage-receipt ticket, #@@CHILD_9@@, AND by ADR-053 Open
Question 1.

## References

- ADR-053 § "The clamp", § "Threat model and non-goals", Open Question 1
- spec § P3.5, § "P3.5 is blocked, and should stay blocked"
- ADR-047 P1 (`unclear_reason`) · council reviews `bff6de55`, `dc7acb57`
BODY
check_sentinels "$WORKDIR/child-10-body.md" "@@EPIC@@" "@@CHILD_9@@"
subst "$WORKDIR/child-10-body.md" "@@EPIC@@" "$EPIC_N" "@@CHILD_9@@" "$CHILD_9"
CHILD_10_URL="$(gh issue create \
  --title 'feat(verify): coverage clamp — pass unrepresentable over unreviewed files [BLOCKED on OQ1]' \
  --label enhancement --label adr --label blocking --label deferred \
  --body-file "$WORKDIR/child-10-body.md")"
CHILD_10="${CHILD_10_URL##*/}"; require_int CHILD_10 "$CHILD_10"
echo "    #$CHILD_10"

echo "==> [P3] child 11/11: shadow telemetry + default flip"
cat > "$WORKDIR/child-11-body.md" <<'BODY'
Part of #@@EPIC@@

## Context

`LLM_COUNCIL_FILE_SELECTION=shadow` runs both predicates, logs the delta (what
content-sniffing WOULD have included/excluded) to `.council/`, and acts on the
allowlist. This is the same shadow-mode pattern already used by
`early_consensus` (ADR-044 P2) and `LLM_COUNCIL_SCREENING` (ADR-047 P3):
**measure before flipping.**

Source: ADR-053 § "Rollout"; spec § P3.6.

## Scope

- Implement `shadow` mode; emit the include/exclude delta per run.
- Collect telemetry across real repos.
- Only then flip the default to `content`, in a release AFTER the one that
  introduced it (ADR-053 Open Question 3, recommended answer: one later).

**Note the blast radius grows before it shrinks.** `content` mode admits every
text file in an expanded directory — including files a repo never intended for an
LLM. Q3 (the compiled-in denylist) and the `.llmignore` family are the mitigation;
shadow mode exists to measure the delta on real repos first.

## Acceptance criteria

- [ ] `shadow` logs the delta without changing behavior
- [ ] `allowlist` (default) remains byte-identical (test-pinned)
- [ ] Telemetry reviewed on ≥1 real repo before the flip
- [ ] Default flip is its own PR with a `### Changed` CHANGELOG entry
- [ ] ADR-053 Open Question 3 answered in the ADR before the flip

## Dependencies

Blocked by Q1 content sniffing #@@CHILD_6@@, Q2 reviewability #@@CHILD_7@@, and
the ignore-file family #@@CHILD_8@@.

## References

- ADR-053 § "Rollout", Open Question 3 · spec § P3.6
BODY
check_sentinels "$WORKDIR/child-11-body.md" "@@EPIC@@" "@@CHILD_6@@" "@@CHILD_7@@" "@@CHILD_8@@"
subst "$WORKDIR/child-11-body.md" "@@EPIC@@" "$EPIC_N" \
  "@@CHILD_6@@" "$CHILD_6" "@@CHILD_7@@" "$CHILD_7" "@@CHILD_8@@" "$CHILD_8"
CHILD_11_URL="$(gh issue create \
  --title 'feat(verify): shadow-mode telemetry, then flip LLM_COUNCIL_FILE_SELECTION=content' \
  --label enhancement --label adr --label priority-medium \
  --body-file "$WORKDIR/child-11-body.md")"
CHILD_11="${CHILD_11_URL##*/}"; require_int CHILD_11 "$CHILD_11"
echo "    #$CHILD_11"

# ============================================================================
# === step 3: final epic body
# ============================================================================

echo "==> Updating epic body with real child numbers"
cat > "$WORKDIR/epic-final.md" <<'BODY'
Implementation tracking for ADR-053, which resolves #540 (secrets leak out),
#542 (source files silently dropped), and #543 (no filter runs at all on the
default path) as one design.

## Source documents

- [ADR-053 — Verify File Selection, Decodability, Reviewability, and the Trust Boundary](../blob/master/docs/adr/ADR-053-verify-file-selection-trust-boundary.md)
- [ADR-053 Implementation Spec](../blob/master/docs/adr/ADR-053-implementation-spec.md)
- [Draft security advisory](../blob/master/docs/security/advisory-draft-verify-secret-transmission.md)

## Scope

`verification/file_ops.py::_is_text_file()` conflates three unrelated questions
into one hardcoded extension allowlist:

| | Question | Owner |
|---|---|---|
| **Q1** | Decodability — can this go in a prompt at all? | the bytes |
| **Q2** | Reviewability — is it worth spending tokens on? | the repo |
| **Q3** | Permissibility — may this content leave the machine? | the repo owner |

`.zig` is missing because Q1 is hand-maintained. `.env` is present because
someone answered Q1 correctly (`.env` IS text) and the list has no vocabulary
for Q3. `uv.lock` (#533/#539) was blocked by a Q1 filter when the intended answer
was Q2. Each question gets the mechanism the industry already built for it.

## Critical path / sequencing constraints

**A GHSA published without a fixed version causes Dependabot to alert every
downstream user with no safe version to upgrade to.** Therefore:

```
P0 leak fix ──► patch release ──► P1 disclosure (GHSA + CVE + rotation guidance)
                                        │
P2 verify trustworthiness (#544, #545) ─┤
                                        │
P3 ADR-053 design work (sniffing, receipt, clamp)
```

- **P0 is the smallest change that closes the entire leak surface.** It takes no
  position on allowlist-vs-denylist, receipts, or the clamp. Purely narrowing.
- **P0 gets its own patch release** — the deliberate exception to this repo's
  one-release-per-epic rule, because P1 cannot proceed without a released fix.
- **This ordering front-loads the security fix and back-loads #542's correctness
  fix**, so `.zig` files stay silently dropped for longer. A leak is worse than a
  gap — but that is a judgment call, and it is the maintainer's to overturn.
- **Fixing #542 alone would make #540 strictly worse.** `.env.local`, `id_rsa`,
  `*.pem`, `terraform.tfvars`, and `kubeconfig` are excluded today only by
  accident (`Path(".env.local").suffix` is `.local`, not on the list). Flipping to
  content sniffing without an explicit trust boundary converts an accidental
  protection into an intentional leak. Q3 must land with, or before, Q1.

## Threat model summary

**In scope:** confidentiality against *accident* (a committed `.env` must never be
transmitted); coverage honesty (the caller always knows which files were read);
input hygiene at the API boundary.

**Explicitly out of scope:** defending the verdict against an adversary who
controls the reviewed content. `verify()` reads file contents into an LLM prompt,
so such an adversary has prompt injection, and no file-selection policy prevents
it. Two council reviews attacked, in turn, each carve-out an omission taxonomy
created; the lesson is that no stable partition exists, because the attacker
writes the bytes.

**Corollary: `council-gate` must not be marketed as a defense against malicious
pull requests.** It is a review aid. Recorded in `SECURITY.md` and ADR-053.

## Intersections with other ADRs

- **ADR-034 v2.6** — this epic supersedes its `TEXT_EXTENSIONS` allowlist
- **ADR-051** — the coverage receipt reuses C4's invariant-marker and C6's
  docs-drift patterns; the verdict-as-pure-function-of-evidence precedent
- **ADR-047 P1** — the clamp extends the `unclear_reason` taxonomy
- **ADR-040** — #545 (waterfall starvation) was surfaced while running this epic's
  own council reviews
- **ADR-050 D3** — `denied_secret` records path only, never the matched value

## Children

### P0 — leak fix (blocks disclosure)
- [ ] #@@CHILD_1@@ — route every candidate path through one selector (closes #543)
- [ ] #@@CHILD_2@@ — compiled-in secret-path denylist (closes #540)
- [ ] #@@CHILD_3@@ — validate `snapshot_id` at the library boundary + garbage dir matching
- [ ] #@@CHILD_4@@ — **patch release** (gates everything below)

### P1 — disclosure (gated on the P0 release)
- [ ] #@@CHILD_5@@ — publish GHSA, request CVE, ship rotation guidance

### P2 — make `verify` trustworthy (already filed; not created by this epic)
- [ ] #544 — binary-verdict parse failure silently degrades confidence
- [ ] #545 — ADR-040 waterfall enforces per-model, not per-stage, deadlines

### P3 — ADR-053 design work (no security urgency)
- [ ] #@@CHILD_6@@ — Q1 content sniffing (NUL heuristic + `.gitattributes`)
- [ ] #@@CHILD_7@@ — Q2 reviewability (`linguist-generated`/`vendored`, `.svg`)
- [ ] #@@CHILD_8@@ — `.llmignore` family (no seeding) + `llm-council ignore` CLI
- [ ] #@@CHILD_9@@ — structural coverage receipt + conservation invariant
- [ ] #@@CHILD_10@@ — coverage clamp **[BLOCKED on ADR-053 Open Question 1]**
- [ ] #@@CHILD_11@@ — shadow telemetry, then flip the default to `content`

## Open questions blocking work

1. **`coverage_ack` shape** — blocks #@@CHILD_10@@. Under the uniform clamp any
   commit touching a `.png` returns `unclear`. A noisy gate gets switched off,
   which is worse than no gate. Highest-risk open item in the ADR.
2. **`.env.example` carve-out** — is it worth its cost in the trust boundary?
3. **Timing of the `content` default flip** — same release as Q3, or one later
   after shadow telemetry? Recommended: one later.

## Notes for implementers

- TDD. Gates: `make lint` + `make test-fast`. Draft PR "Part of #@@EPIC@@"
  (bug children may "Closes #<child>"). Mandatory Council gate scoped to changed files.
- **The Council gate depends on a working council.** #544 and #545 both degrade
  `verify` output; landing P2 early makes every later review in this epic
  trustworthy. Two of this epic's own three review rounds were compromised by
  them (one `unclear(infra_failure)` with stage 3 starved to 1.0s of a 360s
  deadline; two runs with confidence collapsed to ~0.27 by a silent parse failure).

## Status

Not started.
BODY
check_sentinels "$WORKDIR/epic-final.md" \
  "@@EPIC@@" "@@CHILD_1@@" "@@CHILD_2@@" "@@CHILD_3@@" "@@CHILD_4@@" "@@CHILD_5@@" \
  "@@CHILD_6@@" "@@CHILD_7@@" "@@CHILD_8@@" "@@CHILD_9@@" "@@CHILD_10@@" "@@CHILD_11@@"
subst "$WORKDIR/epic-final.md" \
  "@@EPIC@@" "$EPIC_N" \
  "@@CHILD_1@@" "$CHILD_1" "@@CHILD_2@@" "$CHILD_2" "@@CHILD_3@@" "$CHILD_3" \
  "@@CHILD_4@@" "$CHILD_4" "@@CHILD_5@@" "$CHILD_5" "@@CHILD_6@@" "$CHILD_6" \
  "@@CHILD_7@@" "$CHILD_7" "@@CHILD_8@@" "$CHILD_8" "@@CHILD_9@@" "$CHILD_9" \
  "@@CHILD_10@@" "$CHILD_10" "@@CHILD_11@@" "$CHILD_11"
gh issue edit "$EPIC_N" --body-file "$WORKDIR/epic-final.md" >/dev/null
echo "    epic body updated"

# ============================================================================
# === summary
# ============================================================================

cat <<SUMMARY

============================================================
 Created 1 epic + 11 children in $GH_REPO
============================================================

  EPIC  #$EPIC_N   $EPIC_URL

  === P0 (leak fix — blocks disclosure) ===
   #$CHILD_1   selector chokepoint (closes #543)
   #$CHILD_2   secret-path denylist (closes #540)
   #$CHILD_3   snapshot_id validation + garbage dir matching
   #$CHILD_4   patch release  <-- gates P1

  === P1 (disclosure) ===
   #$CHILD_5   publish GHSA, request CVE, rotation guidance

  === P2 (verify trustworthiness — pre-existing) ===
   #544        binary-verdict parse failure
   #545        waterfall per-stage deadlines

  === P3 (ADR-053 design work) ===
   #$CHILD_6   Q1 content sniffing
   #$CHILD_7   Q2 reviewability
   #$CHILD_8   .llmignore family + CLI
   #$CHILD_9   coverage receipt
   #$CHILD_10  coverage clamp  [BLOCKED on OQ1]
   #$CHILD_11  shadow telemetry + default flip

  Suggested start:  /epic-loop EPIC=$EPIC_N
  Reminder: create the \`adr-053\` label if you want per-ADR labelling.

SUMMARY
