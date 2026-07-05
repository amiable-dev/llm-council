# ADR-052: Structured-Findings Rollout & Enablement

**Status:** Proposed 2026-07-05 (rev 2: Council design review folded — the "always-emit diagnostic / amend byte-identical" decision was **removed** after a code check showed the signal already ships flag-off; enablement split to a separate mode var; shadow measurement, flip criteria, and data-handling hardened. See "Council review (rev 2)".)
**Date:** 2026-07-05
**Decision Makers:** llm-council maintainers (review requested)
**Proposed by:** dogfooding ADR-051 in-session — the enablement-mechanism gap surfaced while enabling the flag user-scoped (project-vs-user scope had no single home)
**Relates to:** ADR-051 (**supersedes** its §3 Migration & the binary flag), ADR-024 (unified_config single source of truth), ADR-045 (SEP-2127 server card), ADR-047 (calibration / UNCLEAR taxonomy — sibling shadow patterns), ADR-044 (early-consensus / graduated-depth — shadow-mode precedent), ADR-030 (LayerEvents)
**Tracking:** [#500](https://github.com/amiable-dev/llm-council/issues/500)
**Implementation spec:** [ADR-052-implementation-spec.md](ADR-052-implementation-spec.md) (mode resolution, response contract, config + server-card wiring, shadow methodology, adjudicated flip criteria, data handling, child breakdown, test plan)

---

## Context

ADR-051 shipped the structured-findings **mechanical gate** — the chairman emits severity-tagged `findings[]`, host code computes `verdict = policy(findings)` — behind `LLM_COUNCIL_STRUCTURED_FINDINGS` (default **OFF**), and deferred the default-ON flip to "a separate, deliberate breaking release … not bundled into the build epic" (spec §3, §7). It modelled that rollout as a **bare binary**: flag off → flag on, with the flip described as one that "changes the default, **not the code**."

Dogfooding the feature — enabling the flag user-scoped across projects — exposed that the binary framing is insufficient on two axes that survive scrutiny (a third, "discoverability of the runtime path signal", turned out to be **already solved in the shipped code** — see the correction below):

1. **The default is the known-broken behavior.** Structured findings is not a feature; it is the **fix** for a correctness defect (`blocking_issues == []` on effectively every FAIL — the decoupling pathology that motivated ADR-051). Shipping the fix default-OFF means every un-migrated user keeps getting the defect, and — because the flip is a single undefined "separate release" — there is no measured, evidence-gated path from here to there.

2. **It breaks the codebase's own convention.** Every other behavior-changing feature here ships **shadow-first with always-on reporting**: `early_consensus` (flag-OFF *is* shadow mode — logs the would-have-terminated point), `screening` (explicit `off | shadow | active`), `calibration` (always reports `confidence_calibrated`; only the threshold gates), `performance_selection` (route receipt only when the selection changed). Structured findings is the lone outlier — a hard binary flag, no shadow state, no measured flip. Aligning it lets the eventual breaking flip be decided on **data from real traffic**, not a calendar.

### Correction (rev 2): the runtime path signal already ships

The rev-1 draft claimed a third gap — "a flag-off consumer gets no runtime signal they're on the legacy path" — and proposed *always-emitting* `diagnostics.verdict_source`, framed as **amending ADR-051's flag-off byte-identical guarantee**. A code check refuted this: `build_verification_result` initializes `diagnostics = {"findings_source": "fallback", "verdict_source": "legacy"}` **before** the flag gate (`verdict_extractor.py:443`) and attaches it unconditionally (`:514`), surfaced by `api.py:727`. **Shipped 0.37.1 already emits `diagnostics.verdict_source="legacy"` and `findings_source="fallback"` on flag-off responses.** The migration lever a consumer needs *already exists*; there is nothing to add and no invariant to amend. This ADR therefore introduces **zero new field to the flag-off response** — it only documents the existing signal as the migration lever and makes the *feature and its mode* discoverable via config and the server card. (This correction removed the rev-1 change the Council rated most dangerous — see rev-2 review #1.)

### Why this is an ADR, not a tracking issue

Not because it amends an invariant (rev-1's justification, now withdrawn), but because it **adds a new code path on the verdict route** — a `shadow` mode that *computes the mechanical verdict for measurement without governing* — and **supersedes ADR-051 §3's binary rollout** with an evidence-gated, pre-registered flip. New governing-adjacent code plus a superseding rollout decision is ADR-shaped; a bare issue would under-capture the flip criteria and the measurement methodology.

## Decision (proposed)

Four parts. Parts 1–3 ship with **zero verdict change and zero flag-off response change**; Part 4 is the staged path that eventually *is* the ADR-051 deferred flip, now with a defined, adjudicated mechanism.

### 1. Enablement: keep the boolean master, add a separate mode var (rev 2 — Council #4)

Rev-1 overloaded the existing boolean `LLM_COUNCIL_STRUCTURED_FINDINGS` into a tri-state `off|shadow|active`. The Council flagged this as an operational footgun: a typo (`shdaow`) silently downgrades to the known-broken path, and boolean-coercing config systems (Helm/Terraform) mis-handle string enums on a var they've typed as bool. **Revised:**

- `LLM_COUNCIL_STRUCTURED_FINDINGS` stays a **boolean master** with its *exact current semantics* (`true`→governing, else off). No back-compat risk for the current users (this session, epic-loop).
- A **separate** `LLM_COUNCIL_STRUCTURED_FINDINGS_MODE ∈ {active, shadow}` refines behavior *when the master is on* (default `active`, so `=true` alone is unchanged = active).
- Resolved mode = `off` if master off; else the mode var. An **unrecognized mode value is loud** — a startup `WARNING` + an `L1` LayerEvent — and falls to `active` (the safe governing choice when the operator clearly intended the feature on), **never a silent downgrade to the broken path**.

The mode also lives in `unified_config` (Part 3), which is the preferred, typed home; the env vars are the override.

### 2. Shadow mode — measure divergence, honestly (rev 2 — Council #2)

In `shadow`, compute the mechanical verdict **and** the legacy prose verdict from the chairman output, log the divergence (esp. `legacy_pass ∧ mechanical_fail` — a false-pass the prose-scrape missed), but let **legacy govern** the response. Two honesty caveats the Council raised, now explicit:

- **It is not a clean baseline, and the ADR must not claim it is.** To produce `findings[]`, the chairman prompt already carries the structured-output instruction (ADR-051). So in shadow the legacy scraper runs on **structured-prompt output**, not the pre-ADR-051 prose distribution. Shadow therefore measures **"mechanical gate vs. prose-scrape *on the output you would actually ship in active mode*"** — which is the right question for "should active govern?", but is **not** a measurement of "how do verdicts differ from today's production (legacy prompt)". The **today-baseline** is the ADR-051 corpus-replay set (legacy-prompt verifies already logged); the flip analysis compares shadow's mechanical verdicts against *that*, cross-prompt, and says so.
- **Stratify or it lies.** Divergence is logged **per model (+version), per tier, per severity** — an aggregate rate hides that (e.g.) one model's JSON discipline is carrying the result. The "zero extra model call" claim is true **only** for the mechanical-vs-scrape comparison on one output; a true legacy-prompt A/B would cost a second call and is explicitly **not** what shadow does.

### 3. Discoverable home — `unified_config` + server-card advertisement

- **Config (ADR-024):** `evaluation.structured_findings ∈ {off, shadow, active}` in `llm_council.yaml`, resolved **YAML > env > default(off)**. Resolve to a single mode **at the edge**; `findings.py` stays a leaf that reads the resolved mode (no config-singleton import in the leaf).
- **Server card (ADR-045 / SEP-2127):** advertise `{ available: true, mode: "<resolved>" }` under the council-namespaced `_meta`, so an agent/consumer can detect the capability **and its state** from `/server-card` without a verify call.

This gives the feature a single discoverable home instead of an invisible env var duplicated across N MCP config blocks (the friction that surfaced this ADR).

### 4. Staged path to default-`active` — adjudicated, not raw-counted (rev 2 — Council #3)

- **Stage A — Transparency (Part 3).** Config home + server-card advertisement. No verdict change, no flag-off response change. Any minor.
- **Stage B — Shadow default.** Flip the *default* to `shadow`. Still legacy-governed (no verdict change), now measuring on all traffic. Ships after Stage A has been out ≥1 release.
- **Stage C — Default `active` (breaking, OUT of the epic).** Gated on **adjudicated** criteria, because raw divergence counts are untrustworthy: the legacy system is *known* to false-fail, so a mechanical *correct pass* of a legacy *false fail* records as "mechanical more lenient." The gate therefore uses a **human-adjudicated true-leniency rate** on a sample of divergences, plus — the Council's overlooked bound — **an upper limit on new strictness** (mechanical assigning `critical` too aggressively paralyzes CI). Criteria are **pre-registered** and frozen when Stage B ships (spec §3). MAJOR bump (or `### BREAKING` minor on 0.x). Stage B (shadow default) is a valid terminal state if the criteria don't clear.

## Consequences

**Positive.** The correctness fix becomes discoverable (config + server card) and its eventual breaking flip becomes **evidence-gated** on adjudicated real-traffic data rather than a calendar. Stages A/B carry **zero verdict change and zero flag-off response change**, so nearly all value lands before any breaking release. The feature stops being the convention outlier. The rev-2 code check also **shrank** the ADR — the runtime path signal already ships, so there is no invariant to amend and no flag-off shape change to defend.

**Negative / cost.** (1) **Shadow runs the parser + legacy scrape every call** — CPU only, no model spend (query-count test), plus telemetry volume. (2) **Divergence logs are sensitive** (rev 2 — Council #5): they record findings that *describe vulnerabilities in the code under review* — a shadow-log pipeline becomes a repository of latent zero-days. Mitigation is a decision, not an afterthought: divergence telemetry stores **severity + verdict + location, not full finding descriptions**, inherits the `.council/logs` access model, and is retention-bounded (spec §5). (3) **Two env vars** (master + mode) is marginally more surface than one, but each is cleanly typed (bool + enum) — the deliberate trade for killing the tri-state-coercion footgun. (4) **Fail-closed is now explicit** (rev 2 — Council #5): a malformed/truncated chairman output must degrade to the **legacy path** (`findings_source="fallback"`), never to an empty-`findings` mechanical `pass` (which would fail *open*). This is already ADR-051's `parse_findings` behavior; the ADR now pins it as a named invariant with a test.

**Neutral.** No chairman-prompt change (emission path is ADR-051's). Exit-code semantics unchanged. No new field on the flag-off response.

## Council review (rev 2)

High-tier `consult_council` design review (partial synthesis — some models timed out; transcript `.council/logs/2026-07-05T…`). Five findings; dispositions:

1. **"Always-emit diagnostics amends byte-identity — Hyrum's Law risk" → RESOLVED BY CODE (change withdrawn).** A code check (`verdict_extractor.py:443/514`, `api.py:727`) showed the signal **already ships flag-off** in 0.37.1. Rev-1's Decision 3 was based on a false premise and is deleted; the flag-off response is genuinely unchanged. This removed the Council's highest-severity objection at the source.
2. **"Zero-extra-call hides a prompt semantic shift" → FOLDED (Decision 2).** Correct: the legacy scraper in shadow runs on structured-prompt output, not the pre-ADR-051 distribution. The ADR now states shadow measures mechanical-vs-scrape *on the shippable output*, names the ADR-051 corpus as the true today-baseline, and mandates per-model/tier/severity stratification. "Zero extra call" is scoped to that comparison, not a legacy-prompt A/B.
3. **"τ_lenient=0 on a raw corpus never ships; missing a strictness bound" → FOLDED (Decision 4 / spec §3).** Criteria move from raw counts to a **human-adjudicated true-leniency rate**, and gain an **upper bound on new strictness** (over-aggressive `critical`).
4. **"Tri-state on one boolean env var is a footgun" → FOLDED (Decision 1).** Split into a boolean master + a separate `_MODE` enum; unrecognized mode values warn loudly and fall to `active` (never a silent downgrade to the broken path).
5. **"Fail-open parsing + divergence-log data sensitivity overlooked" → FOLDED (Consequences).** Fail-closed-to-legacy pinned as a named invariant with a test; divergence telemetry restricted to severity/verdict/location (not finding descriptions), access-controlled and retention-bounded.

One rev-1 claim was **withdrawn on the code** (#1) — the mirror of ADR-051 rev-2, where a Council claim (`blocking_issues` type-crash) was likewise rejected against the actual types.

## Research verification

None load-bearing beyond ADR-051's. The calibration / verdict–evidence-decoupling literature justifying the mechanical gate (arXiv 2508.06225; 2404.18796) was verified in ADR-051 rev 2 and is not re-litigated. ADR-052 is a **process/mechanism** decision whose evidence base is **in-repo precedent** (the shadow-mode convention of `early_consensus`/`screening`/`calibration`/`performance_selection`) plus **one code fact verified in this rev** (the flag-off path signal already ships, `verdict_extractor.py:443`). The one empirical input this ADR *creates* — the Stage-B adjudicated divergence data that gates Stage C — has pre-registered accept criteria (spec §3) fixed before the data is collected.
