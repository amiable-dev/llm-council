# Verification & CI Gating

LLM Council's most distinctive surface: multi-model **verification** of code,
documents, or any work product, with machine-actionable verdicts (ADR-034).
Four models deliberate over your change; a chairman renders `pass` / `fail` /
`unclear` with confidence, rubric scores, and blocking issues.

## Three ways in

| Surface | Invocation | Use for |
|---|---|---|
| MCP tool | `verify(snapshot_id, target_paths, tier, ...)` | agent sessions (Claude Code, Cursor) |
| CLI | `llm-council gate --snapshot <sha> [--tier ...]` | CI/CD pipelines (exit code 0/1/2) |
| HTTP | `POST /v1/council/verify` | services |

```bash
llm-council gate --snapshot $(git rev-parse HEAD) \
  --file-paths src/module.py --tier balanced --rubric-focus Security
```

Exit codes: `0` PASS · `1` FAIL · `2` UNCLEAR.

## Tiers

| Tier | Budget | Max input | Use |
|---|---|---|---|
| `quick` | ~30s | 15K chars | sanity checks, small diffs |
| `balanced` | ~90s | 30K chars | **default** — routine verification |
| `high` | ~180s | 50K chars | security-critical reviews |
| `reasoning` | ~600s | 50K chars | complex architectural decisions |

## Reading an UNCLEAR verdict (ADR-047)

The exit code stays `2` for **every** UNCLEAR cause — that is a deliberate
compatibility contract (ADR-047): existing automation keying on exit codes
keeps working, and `unclear_reason` is the routing signal you layer policies
on top of:

- **`infra_failure`** — the chairman call itself errored (billing, auth,
  rate limit). Check your gateway/billing, then **retry**; never treat it as
  a review outcome.
- **`low_confidence`** — deliberation completed below the confidence
  threshold. Common policy: accept-and-audit when `blocking_issues` is empty.
- **`timeout`** — the tier deadline fired. Re-tier or reduce input scope.
- **`chairman_disabled`** — `chairman_disabled=true` (config or
  `LLM_COUNCIL_CHAIRMAN_DISABLED`) skipped chairman synthesis, so no verdict
  was ever computed; `rationale` carries the top-ranked peer response for
  reference only. **Never** treat this as a pass/fail review outcome —
  disable `chairman_disabled` for any BINARY-verdict use (`council-verify`,
  `council-gate`, CI approval).

## Calibrated confidence (ADR-047)

Every response carries `confidence` (raw) and `confidence_calibrated` (raw
passed through a monotonic mapping fitted against your recorded human
dispositions). Build the mapping from your own transcript corpus:

```bash
llm-council calibration-report          # analyze .council/logs
llm-council calibration-report --fit    # fit mapping from dispositions
```

The PASS threshold consumes the calibrated value only behind
`LLM_COUNCIL_CALIBRATED_CONFIDENCE=true` (default off).

## Screening judge (ADR-047, opt-in)

A single quick-tier model can pre-screen easy changes
(`LLM_COUNCIL_SCREENING=shadow|active`; default `off`). Blocking-capable
requests (blocking evidence, security focus, risk-glob paths) are **never**
screened — the full council always runs for those. Start with `shadow` and
read `.council/screening/decisions.jsonl` before trusting `active`.

## Evidence injection (ADR-042)

Feed upstream tool output (linters, scanners) as structured evidence; the
council must disposition each item. `strength: blocking` items make the
request blocking-capable.

## Prompt-cache cost note (ADR-049)

Verification prompts are assembled stable-prefix-first and cached on
Anthropic council members (0.1× read price on repeat rounds; verified on
the OpenRouter route). Multi-round verify sessions on the same subject are
therefore much cheaper than round 1. The verify path uses a 1-hour cache
TTL by default (rounds typically land 3–11 minutes apart);
`LLM_COUNCIL_PROMPT_CACHE_TTL=5m|1h` overrides it, and
`LLM_COUNCIL_PROMPT_CACHING=false` disables injection entirely.
`input_metrics` reports `cached_tokens` (reads), `cache_write_tokens`, and
`cache_session_id` — zero reads across rounds means a broken prefix or a
lapsed TTL.

## Structured findings (ADR-051, opt-in)

By default the verdict is derived from the chairman's prose and `blocking_issues`
is scraped from it — which historically left `blocking_issues` empty even on
FAIL. With `LLM_COUNCIL_STRUCTURED_FINDINGS=true` the chairman instead emits a
typed `findings` array (one entry per issue, each with a `severity`), and the
host **computes** the verdict mechanically: `fail` iff any finding is
`critical`, else `pass` (confidence may still soften a `pass` to `unclear`).
The verdict is therefore a provable function of the evidence — it cannot
decouple from `findings`.

- `findings` — the full list across **all** severities.
- `blocking_issues` — the `critical` subset (unchanged shape; now always
  consistent with the verdict).
- `diagnostics.verdict_source` — `mechanical` when the flag drove the verdict,
  else `legacy`.

**Consumer migration.** Stop keying acceptance on `blocking_issues == []`
(empty even on real FAILs under the legacy path). Key on the `verdict` plus the
`findings`/`severity` you care about — e.g. "block on any `critical` or
`major`". This is the durable contract; the flag defaults **off** and this
epic is non-breaking, but the legacy prose-scrape is the path being retired.

## Response fields

Every field on the `verify` response (`VerifyResponse`), the nested `Finding`,
and the telemetry-only `VerifyDiagnostics`. All are additive — older clients
that ignore unknown fields keep working.

### Core verdict

| Field | Type | Meaning |
|---|---|---|
| `verification_id` | string | Unique id for this run. |
| `verdict` | string | `pass` \| `fail` \| `unclear`. |
| `exit_code` | int | `0` PASS · `1` FAIL · `2` UNCLEAR (CLI/`gate`). |
| `confidence` | float | Raw council-agreement confidence, 0–1. |
| `confidence_calibrated` | float? | `confidence` after the fitted monotonic mapping (ADR-047); equals raw until a mapping is fitted. |
| `unclear_reason` | string? | `infra_failure` \| `low_confidence` \| `timeout` \| `chairman_disabled` (see above); `None` for pass/fail. |
| `rationale` | string | Chairman synthesis explanation. |
| `transcript_location` | string | Path to the full `.council/logs/<id>/` transcript. |
| `error` | string? | Non-verdict error marker (e.g. `input_too_large`); `None` for a real verdict (#357). |

### Scores & findings

| Field | Type | Meaning |
|---|---|---|
| `rubric_scores` | object | Per-dimension scores (accuracy/relevance/completeness/conciseness/clarity), 0–10 or null. |
| `blocking_issues` | list | Issues that caused FAIL — the `critical` subset of `findings`. |
| `findings` | list of `Finding` | Full structured findings across all severities (ADR-051; empty unless `LLM_COUNCIL_STRUCTURED_FINDINGS`). |
| `diagnostics` | `VerifyDiagnostics` | Telemetry-only (below) — **not** control flow. |

A `Finding` has: `severity` (`critical` \| `major` \| `minor` \| `info`),
`description` (text), `location` (`file.py:42`, `global`, or null), and
`dimension` (the rubric axis it maps to, when derivable).

### Diagnostics (telemetry only — never gate on these)

| Field | Type | Meaning |
|---|---|---|
| `findings_source` | string | `structured` (clean parse), `fallback` (missing/malformed → legacy path), or `skipped` (`chairman_disabled=true` — no synthesis to parse). |
| `fallback_reason` | string? | Why the fallback fired, when it did. |
| `verdict_source` | string | `mechanical` = `policy(findings)`; `legacy` = prose parse; `chairman_disabled` = synthesis skipped, no verdict computed. |
| `findings_by_severity` | object | Count per severity — surfaces severity mis-labelling over time. |
| `verdict_evidence_mismatch` | string? | Defensive invariant marker; `None` in normal operation (should never fire under the mechanical gate). |
| `inner_verdict` | string? | Structured verdict **before** UNCLEAR softening (nested so consumers can't parse it to bypass the low-confidence gate). |
| `inner_confidence` | float? | Confidence that accompanied `inner_verdict`. |
| `inner_confidence_calibrated` | float? | Calibrated form of `inner_confidence`. |

### Timeout, expansion & telemetry

| Field | Type | Meaning |
|---|---|---|
| `partial` | bool | Result is partial (timeout/error) (ADR-040). |
| `timeout_fired` | bool | Global deadline was exceeded. |
| `completed_stages` | list? | Stages completed before a timeout (e.g. `["stage1","stage2"]`). |
| `expanded_paths` | list? | Files included after directory expansion (#311). |
| `paths_truncated` | bool? | `MAX_FILES_EXPANSION` limit was reached. |
| `expansion_warnings` | list? | Warnings from directory expansion (skipped files, etc.). |
| `timing` | object? | Per-stage and total timing in ms (ADR-041). |
| `input_metrics` | object? | Input-size metrics (`content_chars`, `tier_max_chars`, `num_models`, `num_reviewers`, `tier`, cache fields). |
| `screening` | object? | Screening-judge audit trail (ADR-047); present only when `LLM_COUNCIL_SCREENING` is shadow/active. |
| `evidence_summary` | list? | Per-evidence-item Council disposition (ADR-042); `None` when no evidence supplied. |
| `evidence_warnings` | list? | Structured warnings about evidence handling (truncation, format errors). |

## Operational tips

- Scope `target_paths` to the files that changed — whole-file expansion of
  pre-existing code invites off-scope findings.
- Repeated re-verification of the same scrutinized files hits diminishing
  returns; act on verdicts rather than re-rolling them.
- Every run persists a full transcript under `.council/logs/<timestamp-id>/`
  (the `audit` MCP tool retrieves them).
