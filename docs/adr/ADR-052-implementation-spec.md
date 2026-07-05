# ADR-052 Implementation Spec — Structured-Findings Rollout & Enablement

Companion to [ADR-052-structured-findings-rollout.md](ADR-052-structured-findings-rollout.md).
The ADR carries the decision and rationale; this spec pins the mechanism.
**Rev 2** (Council design review folded): the rev-1 "amend byte-identical" change
is withdrawn (the flag-off path signal already ships — `verdict_extractor.py:443`);
enablement is split into a boolean master + a separate mode var; shadow
methodology, adjudicated flip criteria, and divergence-log data handling are added.

## 1. Enablement resolution — boolean master + separate mode var, fail-loud

Two env vars, each cleanly typed (kills the rev-1 tri-state-on-one-bool footgun,
Council #4), with `unified_config` as the preferred typed home (ADR-024):

```python
# verification/findings.py — leaf; reads a resolved value handed in at the edge.
_TRUE  = {"true", "1", "yes", "on"}          # master boolean (ADR-051 semantics, unchanged)
_MODES = {"active", "shadow"}

def structured_findings_mode(resolved_master=None, resolved_mode=None) -> str:
    master = resolved_master if resolved_master is not None else os.getenv("LLM_COUNCIL_STRUCTURED_FINDINGS", "")
    if str(master).strip().lower() not in _TRUE:
        return "off"                          # master off/unset/anything-not-true → off
    mode = (resolved_mode if resolved_mode is not None else os.getenv("LLM_COUNCIL_STRUCTURED_FINDINGS_MODE", "active"))
    m = str(mode).strip().lower()
    if m in _MODES:
        return m
    # Unrecognized mode while master is ON: LOUD, never a silent downgrade to the
    # broken legacy path. Fall to `active` — the operator clearly intended it on.
    logger.warning("Unrecognized LLM_COUNCIL_STRUCTURED_FINDINGS_MODE=%r; defaulting to 'active'", mode)
    emit_layer_event("L1_STRUCTURED_FINDINGS_MODE_INVALID", {"value": str(mode)})
    return "active"

def structured_findings_enabled() -> bool:    # retained — C1–C6 call sites unchanged
    return structured_findings_mode() == "active"
```

- **Back-compat pin:** `LLM_COUNCIL_STRUCTURED_FINDINGS=true` with no mode var ⇒ `active` (today's behavior; this session + epic-loop rely on it).
- **Precedence (ADR-024):** the composition layer resolves `evaluation.structured_findings` (YAML) over the env vars over default `off`, then passes `resolved_master`/`resolved_mode`. The leaf never imports the config singleton.
- **Default:** `off` at introduction (Stage A) → `shadow` (Stage B) → `active` (Stage C). **Default-only changes; the parser never changes** (mirrors ADR-051 §3).

## 2. Response contract — NO flag-off change; shadow adds a nested telemetry block

**Rev-2 correction.** The flag-off response is **unchanged** from shipped 0.37.1,
which *already* carries `diagnostics = {"findings_source":"fallback","verdict_source":"legacy"}`
(initialized at `verdict_extractor.py:443` before the flag gate, attached at `:514`,
surfaced by `api.py:727`). There is **no new field flag-off** and **no invariant to
amend** — rev-1's Decision 3 is deleted.

`shadow` adds a nested, telemetry-only block; no existing field is removed or retyped:

```python
class ShadowDiagnostics(BaseModel):            # ADR-052 — populated only in shadow mode
    mechanical_verdict: str                    # policy(findings) — the would-be governing verdict
    agreed_with_legacy: bool
    divergence: Optional[str] = None           # e.g. "legacy_pass_mechanical_fail" (the false-pass catch)
    findings_by_severity: Dict[str, int] = {}
    model: Optional[str] = None                # stratification (Council #2)
    tier: Optional[str] = None

class VerifyDiagnostics(BaseModel):
    # ... existing ADR-051 fields (verdict_source, findings_source, …) ...
    shadow: Optional[ShadowDiagnostics] = None
```

| Mode | `verdict` / `confidence` / `blocking_issues` | `diagnostics` |
|---|---|---|
| `off` | **byte-identical to 0.37.1** | existing (`verdict_source="legacy"`, `findings_source="fallback"`) — unchanged |
| `shadow` | **identical to `off`** (legacy governs) | above **+** `shadow: {…}` populated |
| `active` | mechanical gate governs (ADR-051) | `verdict_source="mechanical"`, full ADR-051 diagnostics |

In `off`/`shadow`, `build_verification_result` computes the shadow block into
locals and applies **only** the `diagnostics.shadow` key — never touching
`result["verdict"]`/`["confidence"]`/`["blocking_issues"]` (reuse the C5
atomic-mutation structure).

**Fail-closed invariant (Council #5, pinned).** A malformed / truncated chairman
output in `active` degrades to the **legacy path** (`findings_source="fallback"`,
legacy verdict governs) — **never** to an empty-`findings` mechanical `pass`
(which would fail *open*). This is already `parse_findings`' behavior (ADR-051);
§6 adds a named regression test so it can't silently regress.

## 3. Stage-C accept criteria — adjudicated, pre-registered (Council #3)

Raw divergence counts cannot gate the flip: the legacy system is known to
false-fail, so a mechanical *correct pass* of a legacy *false fail* records as
"mechanical more lenient." Gate on **adjudicated** ground truth, fixed before
Stage B ships:

- **Safety (hard gate) — adjudicated true-leniency.** Sample every `legacy_fail ∧ mechanical_pass` divergence; a human labels each as *mechanical-correct* (legacy false-fail) or *mechanical-wrong* (a real regression). Ship only if the **adjudicated** mechanical-wrong-lenient rate ≤ `τ_lenient` (proposed `0` for security-focus verifies; small ε otherwise). Raw counts are reported but **do not** gate.
- **Strictness bound (Council #3, was missing).** Sample `legacy_pass ∧ mechanical_fail`; ship only if the adjudicated **false-critical** rate (mechanical invented a blocker) ≤ `σ_strict`. Prevents an over-aggressive gate paralyzing CI.
- **Value (motivating direction).** Adjudicated *true* `legacy_pass ∧ mechanical_fail` (a real decoupling the scrape missed) ≥ `δ` of FAIL-eligible runs — evidence the gate earns its cost.
- **Parser health.** `findings_source == "fallback"` ≤ `φ` on the active model set.
- **Corpus.** ≥ `N` verifies across ≥ 2 tiers, **stratified per model/tier/severity** (Council #2) — an aggregate can hide one model carrying the result. Use the ADR-051 corpus-replay set (the true legacy-prompt today-baseline) plus live Stage-B shadow traffic.

`τ, σ, δ, φ, N` are proposed in the tracking issue ([#500](https://github.com/amiable-dev/llm-council/issues/500)) and **frozen** when Stage B
ships; the Stage-C PR cites measured, adjudicated values against them. Any hard
gate missing ⇒ Stage C does not ship; Stage B is a valid terminal state.

## 4. Shadow measurement methodology (Council #2)

- **What shadow measures:** mechanical-gate vs prose-scrape **on the structured-prompt output you would ship in `active`** — the right question for "should active govern?", *not* a measurement of drift from today's legacy-prompt production.
- **The today-baseline** for cross-prompt comparison is the **ADR-051 corpus-replay** set (legacy-prompt verifies already logged). A true same-call A/B against the legacy prompt would need a second model call and is **explicitly not** what shadow does; "zero extra model call" is scoped to the single-output comparison.
- **Stratification is mandatory:** every divergence record carries `model(+version)`, `tier`, `severity`. Reports never present a bare aggregate.

## 5. Divergence-log data handling (Council #5)

Finding descriptions can quote vulnerable code — shadow telemetry must not become
a zero-day repository:

- Divergence telemetry stores **`severity` + `verdict` + `location` + counts**, **not** full `description` text. The full findings remain only in the existing `.council/logs` transcript (already access-modelled), not duplicated into the divergence/metrics pipeline.
- Divergence logs inherit the `.council/logs` access model and a **retention bound** (configurable; default aligned with the existing log retention).
- No finding text crosses into any metrics/StatsD/Prometheus/PostHog sink (ADR-030/050) — only the numeric/enum fields above.

## 6. Child breakdown for `/adr-epic` (sequenced, foundation-first)

Stage C (default `active`) is **OUT** — a separate breaking release (mirrors ADR-051 §7).

1. **D1 — mode resolution (foundation).** `structured_findings_mode(master, mode)` + retained `structured_findings_enabled()`; loud-warn + LayerEvent on invalid mode. Property test over the value table (§1). Non-breaking; `off` response byte-identical to 0.37.1.
2. **D2 — shadow mode.** `ShadowDiagnostics`; compute mechanical + legacy verdict, log stratified divergence, `L3_STRUCTURED_FINDINGS_SHADOW` LayerEvent. Query-count test: **no extra model call**. `off`/`shadow` control-field identity test. Fail-closed-to-legacy regression test.
3. **D3 — config + server-card.** `evaluation.structured_findings` in `unified_config` (YAML>env>default), edge resolution; server-card `_meta.structured_findings.mode`; regenerate `server-card.json` (drift-tested). Config + env-reference docs.
4. **D4 — divergence report + data handling.** `llm-council structured-findings-report` (reads Stage-B telemetry → stratified, adjudication-ready divergence table against the pre-registered criteria); enforce the §5 field restriction + retention.
5. **D5 — Stage-B default flip + docs/drift/currency.** Flip default → `shadow`. Reconcile the ADR-051 §4 doc surface for the two-var model + shadow fields; extend `TestVerifyResponseFieldDrift` to `ShadowDiagnostics`; migration note ("`verdict_source` already tells you which path governed — key on it, not `blocking_issues == []`"); flip ADR-052 Status → Implemented (Stages A/B) and add the "superseded-in-part by ADR-052" cross-reference to ADR-051 §3.

## 7. Test plan

- **Mode parser:** master∉true ⇒ `off` regardless of mode; `true`+unset ⇒ `active` (back-compat pin); `true`+`shadow` ⇒ `shadow`; `true`+garbage ⇒ `active` **and** a warning/LayerEvent emitted (assert the loud path).
- **`off` byte-identity:** full response byte-identical to shipped 0.37.1 on a fixed fixture (the *existing* diagnostics included — nothing added).
- **`shadow` identity + telemetry:** `verdict`/`confidence`/`blocking_issues` identical to `off`; `diagnostics.shadow` populated + stratified; **query-count assertion** proves no extra model call.
- **Fail-closed:** malformed chairman output in `active` ⇒ legacy governs, `findings_source="fallback"`, **not** an empty-findings `pass`.
- **`active` unchanged:** all ADR-051 C1–C6 tests green under the retained `structured_findings_enabled()` shim.
- **Config precedence:** YAML beats env beats default; malformed YAML mode ⇒ loud fall to `active` (master on) / `off` (master off).
- **Server card:** `/server-card` + static `server-card.json` include `_meta.structured_findings.mode`; drift test green.
- **Data handling:** divergence telemetry contains no `description` text (assert absence); retention honored.
- **Report:** synthetic shadow-log fixture ⇒ the report reproduces the adjudication-ready metrics (`τ, σ, δ, φ`) stratified per model/tier.

## 8. Out of scope (this epic)

- **Stage C — default `active`.** Separate breaking release gated on §3 (mirrors ADR-051 §7).
- **P4 completeness reweight / P5 Fuser spike** — owned by ADR-051's deferred list.
- **Chairman prompt / findings-schema changes** — the emission path is ADR-051's, unchanged.
