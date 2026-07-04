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

## Operational tips

- Scope `target_paths` to the files that changed — whole-file expansion of
  pre-existing code invites off-scope findings.
- Repeated re-verification of the same scrutinized files hits diminishing
  returns; act on verdicts rather than re-rolling them.
- Every run persists a full transcript under `.council/logs/<timestamp-id>/`
  (the `audit` MCP tool retrieves them).
