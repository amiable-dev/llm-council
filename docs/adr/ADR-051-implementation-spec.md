# ADR-051 Implementation Spec — Verify Findings Channel

**Companion to:** [ADR-051](ADR-051-verify-findings-channel.md) (Proposed) · **Tracking:** [#482](https://github.com/amiable-dev/llm-council/issues/482)
**Status:** Draft spec 2026-07-05 · resolves the ADR's open implementation forks before `/adr-epic`.

This spec pins the *how* (the ADR pins the *what/why*): the enforcement
mechanism, the concrete response schema, the flagged migration, the exhaustive
documentation surface + a new drift guard, and the child breakdown. It is
written to be deep-read by `/adr-epic`.

---

## 1. Enforcement mechanism — two-phase generation (decided)

**Context.** ADR-051 Part 1 requires the chairman to enumerate `findings[]`
*before* committing its verdict ("Proof-Before-Preference"), because a rationale
emitted *alongside* the verdict does not fix verdict–evidence decoupling. Today
there is **no structured-output plumbing**: `verdict.py:parse_binary_verdict`
regex-parses the chairman's prose. So every option below is net-new.

**Decision: mechanical gate — LLM findings, deterministic verdict.** (Revised
after the Council fork review, 2026-07-05, high tier — it challenged plain
two-phase and 3/4 models converged on this hybrid.)

- **Phase 1 (LLM):** ONE chairman call emits severity-tagged `findings[]`
  (severity, description, cited location) *and* the human-readable synthesis
  prose. No verdict is requested.
- **Phase 2 (deterministic host code):** the verdict is **computed from the
  findings**, not generated — v1 policy: any `severity == "critical"` finding
  (or an ADR-042 blocking-evidence disposition) ⇒ `fail`; otherwise `pass`.
  The policy is explicit, auditable code (tunable later, e.g. "N majors ⇒
  fail"). Confidence continues to come from the existing deliberation/agreement
  signal (`calculate_confidence_from_agreement`), independent of the verdict.

**The one decisive reason:** the verdict is a **provable function of the
findings** — it is literally `verdict = policy(findings)` in code, the strongest
possible form of "findings-first." A generated Phase-2 verdict is only
*hopefully* causal; the Council showed a second LLM call that sees the code
re-judges freshly and can emit `ACCEPT` over its own `CRITICAL` finding (the
"Yes-Man contradiction").

| Option | Verdict genuinely = f(findings)? | LLM hops | Failure mode left open |
|---|---|---|---|
| **Mechanical gate (chosen)** | **Yes — computed in code** | **1** (same as today) | Severity **mis-labelling** by the model (a real "critical" tagged "major" won't fail) — localized, auditable, tunable via the rubric + policy |
| Two-phase (both LLM) | No — Phase 2 can re-judge / Yes-Man contradict | 2 (extra hop, waterfall-budget risk) | Contradiction + latency; needs info-starvation + a code guard anyway → collapses toward the mechanical gate |
| Constrained decoding | No — JSON field order ≠ reasoning order | 1 | Rationalization survives; net-new per-provider adapters |
| Single free-form + parse | No | 1 | Weakest; ≈ today's prose fragility |

**Why this beats plain two-phase (Council):** it is single-hop (no waterfall-
budget penalty — Gemini's objection), makes the Yes-Man contradiction
*structurally impossible* (so the Part-2 guard becomes a defensive invariant,
§below), and makes soft-fail safe (a deterministic verdict from stranded
findings, never an untrusted LLM inference). It also lands the ADR's root fix
maximally: the verdict is no longer *decoupled* from the evidence — it is
*derived* from it.

**Graceful degradation (soft-fail, ADR-011/024).** If the Phase-1 findings
emission fails or won't parse (or the flag is off), fall back to the **legacy
single synthesis + `parse_binary_verdict` + prose-regex** path and mark
`findings_source: fallback`, `fallback_reason: <cause>`. The verdict computation
(Phase 2) is pure code and never fails. Verify never crashes on a bad model
output.

**Constrained decoding is explicitly deferred** to a future per-chairman-model
optimization for how Phase 1 *emits* findings (e.g. json_schema / responseSchema
/ tool-use) — a robustness upgrade to parsing, never the verdict mechanism.

> The Council validation ran 2026-07-05, high tier (OpenRouter billing
> restored). It did not rubber-stamp two-phase — the mechanical-gate pivot is
> its convergent recommendation, folded in here.

## 2. Response schema (concrete)

New Pydantic in `verification/schemas.py` (and mirrored in `types.py`):

```python
class Finding(BaseModel):
    severity: Literal["critical", "major", "minor", "info"]
    description: str
    location: Optional[str] = None          # "file.py:42" or "global"/None for holistic
    dimension: Optional[str] = None          # which rubric axis, when derivable

class VerifyDiagnostics(BaseModel):          # telemetry-only; NOT control flow
    inner_verdict: Optional[str] = None       # "approved"/"rejected" pre-softening
    inner_confidence: Optional[float] = None
    inner_confidence_calibrated: Optional[float] = None
    verdict_evidence_mismatch: Optional[str] = None   # invariant assertion — should never fire
    findings_source: Literal["structured", "fallback"] = "fallback"
    fallback_reason: Optional[str] = None
    verdict_source: Literal["mechanical", "legacy"] = "legacy"   # mechanical = policy(findings)
```

`VerifyResponse` gains:
- `findings: List[Finding]` — the full structured list (all severities).
- `diagnostics: VerifyDiagnostics` — nested, telemetry-only.

**Verdict is derived, not parsed.** On the structured path the verdict is
`verdict_source: mechanical` = `policy(findings)` (v1: any `critical` ⇒ `fail`,
else `pass`); confidence stays from the deliberation/agreement signal. On the
fallback path it is `legacy` (`parse_binary_verdict` + prose regex).

`blocking_issues` is **derived**, unchanged in type
(`List[BlockingIssueResponse]` — already `{severity, description, location}`, so
**no type break**): `blocking_issues = [f for f in findings if f.severity ==
"critical"]` plus any ADR-042 blocking-evidence dispositions. Non-critical
findings live only in `findings[]`.

**Invariants (now structural, not hoped-for).** Because the verdict is
`policy(findings)`, `fail`-with-no-critical and `pass`-with-critical are
**impossible by construction** on the mechanical path — the Part-2
`verdict_evidence_mismatch` marker is a defensive assertion that should never
fire (if it does, it's a code bug in the gate policy, and it's logged). Tests:
`fail` ⇒ `blocking_issues` non-empty; `findings[] ⊇ blocking_issues`; the policy
is a pure function (property test over synthetic findings).

## 3. Migration & versioning — flagged, non-breaking epic; deliberate flip

The blast radius is a **breaking contract change** (`blocking_issues`:
always-`[]` → populated on FAIL; Hyrum's Law — epic-loop keys its green-chase
cap on the count). De-risked as a two-step:

1. **Epic ships behind `LLM_COUNCIL_STRUCTURED_FINDINGS`, default OFF.** Flag off
   ⇒ byte-identical to today (legacy path, `findings: []`, `blocking_issues` via
   regex). This whole epic is therefore a **non-breaking, opt-in minor** —
   consumers (epic-loop) flip it on, migrate their gate logic off "always-empty",
   and validate.
2. **A separate, deliberate flip to default-ON is the breaking release** —
   MAJOR bump (or a clearly-`### BREAKING` minor for a 0.x line) with a
   migration note. Not bundled into the build epic.

New env var (documented in `docs/reference/environment-variables.md`, enforced
by the drift guard): `LLM_COUNCIL_STRUCTURED_FINDINGS` (default `false` in the
epic; the flip changes the default, not the code).

## 4. Documentation surface (the checklist — DoD, not afterthought)

Every child that changes the contract updates its slice; the consolidated docs
child (C6) closes the list. **All of these reference the verify contract and
MUST be reconciled:**

- `docs/guides/verify.md` — findings/diagnostics fields, `findings_source`, the
  consistency-guard marker, the flag, exit-code semantics unchanged.
- `docs/api.md` — `POST /v1/council/verify` response schema (new fields).
- `docs/guides/mcp.md` — the `verify` MCP tool output fields.
- `docs/guides/skills.md`, `docs/blog/12-cicd-quality-gates.md` — gate examples.
- Bundled skills (must stay in sync with the shipped tool, sync-tested):
  `council-verify/SKILL.md` + `references/{rubrics.md, unclear-routing.md}`;
  `council-gate/SKILL.md` + `references/ci-cd-rubric.md`;
  `council-review/SKILL.md` + `references/code-review-rubric.md`.
- `CHANGELOG.md` (with a `### BREAKING` entry on the flip), `CLAUDE.md`
  (verification module note), `docs/reference/environment-variables.md` (flag).
- A consumer **migration guide** (`docs/guides/verify.md#migrating` or a note):
  "stop keying on `blocking_issues == []`; key on `findings`/severity."

**New drift guard (highest-leverage completeness guarantee).** Extend
`tests/test_docs_drift.py`: assert every field on `VerifyResponse` (and each
`Finding`/`VerifyDiagnostics` field) appears by name in `docs/guides/verify.md`
or `docs/api.md`. Turns "did we document the new response fields?" into a red
build — the gap the current guards (env / ADR-nav / snippet) don't cover.

## 5. Child breakdown for `/adr-epic` (sequenced)

Per-decision granularity; foundation-first; the breaking flip is *out* of the
epic. Non-critical/`info` findings are retained in `findings[]`.

1. **C1 — flag + additive schema (foundation, non-breaking).** Add
   `LLM_COUNCIL_STRUCTURED_FINDINGS` (default off), the `Finding` /
   `VerifyDiagnostics` models, and the additive `VerifyResponse` fields
   (empty by default). Flag-off ⇒ byte-identical (test-pinned). Env-reference +
   drift-guard field assertion.
2. **C2 — structured findings emission (behind flag).** One chairman call emits
   severity-tagged `findings[]` (+ synthesis prose); populate `findings[]`;
   soft-fail to the legacy path (`findings_source`/`fallback_reason`).
3. **C3 — mechanical verdict + derive `blocking_issues`.** `verdict =
   policy(findings)` (any `critical` ⇒ `fail`) as a pure host function
   (`verdict_source: mechanical`); `blocking_issues = findings[critical]`; prose
   regex demoted to the flagged fallback; #355 regression pinned (approval prose
   must not fabricate criticals).
4. **C4 — consistency invariant + severity-calibration telemetry.** Assert the
   structural invariant (`fail`⇔critical present) and log
   `verdict_evidence_mismatch` if it ever fires (a gate-policy bug); emit
   findings-count / severity-distribution telemetry so severity **mis-labelling**
   (the named residual failure mode) is observable over time.
5. **C5 — `diagnostics.inner_verdict`/`inner_confidence` on softened UNCLEAR.**
6. **C6 — docs sweep + drift guard + migration guide.** The §4 checklist,
   bundled-skill sync, CHANGELOG (flag), CLAUDE.md. Flag still default-off.

**Out of this epic (per ADR-051 + Council rev-2):**
- **P4 completeness reweight** — a separate follow-up PR; re-measure *after*
  C1–C6 land (it lives in the stage-2 rubric path, `verdict_extractor.py:135`,
  not the findings channel).
- **P5 LLM-as-a-Fuser spike** — a separate research task *after* the epic (needs
  structured findings to exist); pre-registered accept thresholds; produces a
  go/no-go report, spawning its own ADR only if it clears them.
- **Default-ON flip** — a deliberate breaking release after consumers migrate.

## 6. Test plan (across the epic)

- Flag-off byte-identical (C1).
- Findings emission: a Phase-1 failure / unparseable output degrades to the
  legacy path, never crashes (C2).
- **Mechanical verdict is a pure function** — property test over synthetic
  `findings[]`: `policy(findings)` is deterministic; any `critical` ⇒ `fail`;
  no `critical` ⇒ `pass`; verdict never depends on prose (C3).
- `blocking_issues` invariants: FAIL ⇒ non-empty; `findings ⊇ blocking_issues`;
  #355 approval-prose regression (C3).
- Structural invariant: `pass`-with-critical / `fail`-without-critical cannot be
  produced; the `verdict_evidence_mismatch` assertion never fires in normal
  operation (C4).
- Softened UNCLEAR carries `diagnostics.inner_verdict` (C5).
- Drift guard: an undocumented `VerifyResponse` field fails CI (C1/C6).
- **Corpus replay:** re-run the epic-loop 25-call log (verification_ids in
  `council-verify-stats.md`) with the flag on; assert FAILs now carry non-empty
  `findings`. (OpenRouter credits restored 2026-07-05.)
