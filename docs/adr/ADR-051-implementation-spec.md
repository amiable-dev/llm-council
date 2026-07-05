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

**Decision: two-phase generation for v1.**

- **Phase 1 (findings):** the chairman is called with the code + evidence and a
  prompt that asks *only* for `findings[]` (severity, description, cited
  location) — **no verdict requested, none in context.**
- **Phase 2 (verdict):** a second, compact chairman call receives *its own
  Phase-1 findings* (not the code again) and renders `approved|rejected` +
  confidence **as a function of those findings.**

**The one decisive reason:** only two-phase makes the verdict *causally* depend
on the findings. Phase 1 cannot backfill findings to a verdict it has not made;
Phase 2 has the findings as its input. The alternatives give **cosmetic**
ordering at best.

| Option | Causal findings-first? | Portability | Failure mode left open |
|---|---|---|---|
| **A. Two-phase (chosen)** | **Yes** — Phase 1 has no verdict | High (reuses the chairman call twice; provider-agnostic) | Phase-1/Phase-2 drift (mitigated: Phase 2 sees the findings verbatim; a mismatch trips the Part-2 guard) |
| B. Constrained decoding | No — JSON field order ≠ reasoning order; model may decide verdict-first and emit findings to match | Low — needs per-provider structured-output adapters (OpenAI json_schema / Gemini responseSchema / Anthropic tool-use) built + maintained | Rationalization survives; the exact pathology we're fixing |
| C. Single free-form + parse | No | High | Weakest; ~= today's prose fragility |

**Cost.** One extra chairman hop inside stage-3's waterfall budget (ADR-040:
stage 3 gets the remaining time). Phase 2's input is compact (findings only, not
the code), so it is short and cheap. Acceptable for a quality gate where
correctness dominates a ~1–2 s latency add.

**Graceful degradation (soft-fail, ADR-011/024).** If Phase 2 fails or times
out, fall back to a verdict derived from Phase-1 findings (critical present ⇒
lean fail) and mark `findings_source: structured`, `verdict_source: degraded`.
If Phase 1 itself fails or the flag is off, fall back to the **legacy single
synthesis + `parse_binary_verdict` + prose-regex** path and mark
`findings_source: fallback`, `fallback_reason: <cause>`. Verify never crashes on
a bad model output.

**Constrained decoding is explicitly deferred** to a future per-chairman-model
optimization — considered only if a provider's structured output empirically
adds value over two-phase, and never as the sole enforcement (it is cosmetic on
the causal property).

> Note: a Council validation of this fork was attempted 2026-07-05 but the
> council could not run (OpenRouter `402 Payment Required` — account credits).
> Re-validate once billing is restored; the decision does not block on it.

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
    verdict_evidence_mismatch: Optional[str] = None   # "fail_without_findings" | "pass_with_critical"
    findings_source: Literal["structured", "fallback"] = "fallback"
    fallback_reason: Optional[str] = None
    verdict_source: Literal["two_phase", "degraded", "legacy"] = "legacy"
```

`VerifyResponse` gains:
- `findings: List[Finding]` — the full structured list (all severities).
- `diagnostics: VerifyDiagnostics` — nested, telemetry-only.

`blocking_issues` is **derived**, unchanged in type
(`List[BlockingIssueResponse]` — already `{severity, description, location}`, so
**no type break**): `blocking_issues = [b for f in findings if f.severity ==
"critical"]` plus any ADR-042 blocking-evidence dispositions. Non-critical
findings live only in `findings[]`.

**Invariant tests:** a FAIL with a critical finding never yields
`blocking_issues == []`; `findings[]` ⊇ `blocking_issues` (by severity filter).

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
2. **C2 — two-phase chairman emission (behind flag).** Phase-1 findings-first
   prompt, Phase-2 verdict-from-findings; populate `findings[]`; soft-fail
   ladder (degraded → legacy) with `findings_source`/`verdict_source`.
3. **C3 — derive `blocking_issues` from `findings[critical]`.** Prose regex
   demoted to the flagged fallback; `findings_source`/`fallback_reason` set;
   #355 regression pinned (approval prose must not fabricate criticals).
4. **C4 — bidirectional verdict–evidence consistency guard.** `fail`+no findings
   and `pass`+critical both emit `diagnostics.verdict_evidence_mismatch`;
   zero-finding FAIL survives; any re-run is non-coercive (localize only).
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
- Two-phase: Phase-1 prompt contains no verdict; Phase-2 input is the findings;
  Phase-2 failure degrades, never crashes (C2).
- `blocking_issues` invariants: FAIL+critical ⇒ non-empty; `findings ⊇
  blocking_issues`; #355 approval-prose regression (C3).
- Bidirectional guard fires on both mismatches; zero-finding FAIL passes through
  untouched (C4).
- Softened UNCLEAR carries `diagnostics.inner_verdict` (C5).
- Drift guard: an undocumented `VerifyResponse` field fails CI (C1/C6).
- **Corpus replay:** re-run the epic-loop 25-call log (verification_ids in
  `council-verify-stats.md`) with the flag on; assert FAILs now carry non-empty
  `findings`. (Requires OpenRouter credits — currently blocked by the 402.)
