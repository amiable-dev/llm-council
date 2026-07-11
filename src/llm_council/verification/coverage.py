"""Coverage clamp policy (#556, ADR-053 Open Question 1).

Turns the #555 coverage receipt's omissions into a verdict effect: a `pass` is
not representable over a changed-or-explicit file the council did not review,
unless the omission is acknowledged.

Pure helpers — no I/O, fully unit-testable — consumed by the verify pipeline in
`api.py`. Layers 2/3 of `coverage_ack` (a committed `.council/coverage-ack`
baseline, a per-call list) are deferred; layer 1 (the reason-set below) ships
with the clamp per the ADR's build order.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

# Decisions (2026-07-11): these reasons are acknowledged by default, so the clamp
# fires only on the *surprising* residue — `non-text` (an unlisted language the
# allowlist silently dropped: the #542 bug), `not_found`, `truncated`, and
# `denied_secret` of a changed file. All are content-expected omissions the
# operator already knows about.
DEFAULT_ACK_REASONS = frozenset(
    {"binary", "generated", "vendored", "too_large", "ignored", "noise"}
)

# Rollout dial (#556 / #557). The clamp ships **opt-in**: the default is `warn`
# (receipt only, byte-identical verdicts), so an upgrade changes no verdict. A
# later release flips this to `clamp` after `LLM_COUNCIL_FILE_SELECTION=shadow`
# telemetry (#557) — a ONE-LINE change here that simultaneously (a) makes the
# clamp fire by default and (b) activates `gate`'s refusal of an explicit `warn`
# downgrade. Until then `warn`-as-default is not a foot-gun; it is the status quo.
_DEFAULT_POLICY = "warn"


def coverage_policy() -> str:
    """`LLM_COUNCIL_COVERAGE_POLICY` in {clamp, fail, warn}. Invalid/unset ⇒ `_DEFAULT_POLICY`.

    - `clamp`: a clamped `pass` becomes `unclear(incomplete_coverage)`.
    - `fail`: a clamped `pass` raises (a hard 422) — for callers who want to stop.
    - `warn`: receipt only, no verdict effect. Current default (see `_DEFAULT_POLICY`).
    """
    val = os.getenv("LLM_COUNCIL_COVERAGE_POLICY", _DEFAULT_POLICY).strip().lower()
    return val if val in ("clamp", "fail", "warn") else _DEFAULT_POLICY


def gate_rejects_warn() -> bool:
    """`llm-council gate` refuses `warn` only once it is a DELIBERATE downgrade.

    While `warn` is the default (`_DEFAULT_POLICY == "warn"`), a gate running in
    `warn` is the pre-clamp status quo, not a foot-gun — so it is allowed. After
    the flip to a `clamp` default, an explicit `warn` means "make this gate ignore
    coverage", which IS a foot-gun, so it is refused.
    """
    return coverage_policy() == "warn" and _DEFAULT_POLICY == "clamp"


def coverage_ack_reasons() -> frozenset:
    """`LLM_COUNCIL_COVERAGE_ACK_REASONS` (comma-separated). Unset ⇒ the default set.

    An explicitly empty value acknowledges nothing (every omission clamps).
    """
    raw = os.getenv("LLM_COUNCIL_COVERAGE_ACK_REASONS")
    if raw is None:
        return DEFAULT_ACK_REASONS
    return frozenset(r.strip() for r in raw.split(",") if r.strip())


def clamping_omissions(
    coverage: Optional[Dict[str, Any]], ack_reasons: frozenset
) -> List[Dict[str, Any]]:
    """Omissions that force a clamp.

    - An **explicit**-origin omission always clamps (the caller named that path —
      a contract), regardless of reason. Path-level acknowledgement (layers 2/3)
      is the future escape for those.
    - A **discovered** omission clamps only if its reason is NOT acknowledged.
    """
    if not coverage:
        return []
    clampers: List[Dict[str, Any]] = []
    for o in coverage.get("omitted", []):
        if o.get("origin") == "explicit" or o.get("reason") not in ack_reasons:
            clampers.append(o)
    return clampers


def coverage_clamp_decision(
    verdict: str,
    coverage: Optional[Dict[str, Any]],
    policy: str,
    ack_reasons: frozenset,
) -> Optional[List[Dict[str, Any]]]:
    """Return the omissions that should clamp a `pass`, or None if no clamp applies.

    Only a `pass` is ever clamped; `fail`/`unclear` pass through. `warn` never
    clamps. The caller (api.py) turns a non-None result into
    `unclear(incomplete_coverage)` under `clamp`, or a raise under `fail`.
    """
    if verdict != "pass" or policy == "warn":
        return None
    clampers = clamping_omissions(coverage, ack_reasons)
    return clampers or None
