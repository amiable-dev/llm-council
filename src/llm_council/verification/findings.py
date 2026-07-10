"""Structured findings channel (ADR-051) — flag + (later) parser/policy.

C1 (#485) adds only the opt-in flag; C2 adds the chairman findings parser and
C3 the deterministic verdict policy (`policy(findings)`). The whole epic is
gated on ``LLM_COUNCIL_STRUCTURED_FINDINGS`` (default OFF) so it is additive and
non-breaking until a later deliberate default-ON flip (a breaking release).
"""

from __future__ import annotations

import json
import os
from typing import Any, List, Optional, Tuple, TYPE_CHECKING

from llm_council.json_extract import extract_json_object, matching_brace

if TYPE_CHECKING:
    from .schemas import Finding

__all__ = ["structured_findings_enabled", "parse_findings", "verdict_policy"]

_VALID_SEVERITIES = {"critical", "major", "minor", "info"}

# Explicit NON-critical synonyms → canonical. Everything NOT resolvable to one
# of these (or a canonical value) fails safe to `critical` in _normalize_severity.
_NONCRITICAL_SYNONYMS = {
    "moderate": "major", "medium": "major", "warning": "major", "warn": "major",
    "low": "minor", "nit": "minor", "nitpick": "minor", "trivial": "minor",
    "informational": "info", "note": "info", "notice": "info",
}


def _normalize_severity(raw: Any) -> str:
    """Map a model-supplied severity to a canonical value, **fail-safe** for a gate.

    The mechanical gate (C3) fails only on ``critical``, so anything ambiguous
    must map UP, not down: a missing/blank field, a typo of "critical", a
    "blocker"/"fatal" tag, or any unrecognized label ⇒ ``critical`` — a real
    blocker can never silently false-pass (Council C3 finding, 3-round
    consensus). Only an EXPLICIT known non-critical label is downgraded.
    """
    s = str(raw).strip().lower()
    if s in _VALID_SEVERITIES:
        return s
    if s in _NONCRITICAL_SYNONYMS:
        return _NONCRITICAL_SYNONYMS[s]
    return "critical"  # missing / unrecognized ⇒ fail closed


def verdict_policy(findings: "List[Finding]") -> str:
    """The mechanical gate (ADR-051 C3): the verdict is a PURE function of the
    findings — ``"fail"`` iff any finding is ``critical``, else ``"pass"``.

    This is the whole point of the mechanical gate: the verdict cannot be
    decoupled from the evidence because it is *computed* from it, not generated.
    Confidence-based softening to ``unclear`` is applied by the caller.

    ``Finding.severity`` is a pydantic ``Literal`` so it is already canonical,
    but we normalize defensively here too — should a ``Finding`` ever be built
    outside ``parse_findings`` with a raw label, it must still fail closed.
    """
    return (
        "fail"
        if any(_normalize_severity(f.severity) == "critical" for f in findings)
        else "pass"
    )


def _as_text(value: Any) -> str:
    """Stringify a field, JSON-encoding non-strings so a dict/list doesn't leak
    a Python repr (``str({'a':1})`` → ``"{'a': 1}"``) into a description."""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


# #561: the extractor moved to `llm_council.json_extract` so the ADR-025b
# verdict parser and this findings parser read the same payload with the SAME
# rules. Private aliases retained for the existing tests.
_matching_brace = matching_brace
_extract_json_object = extract_json_object


def structured_findings_enabled() -> bool:
    """Opt-in flag for the ADR-051 structured findings channel (default OFF).

    Explicit true-set (not "anything but false"): a default-OFF flag must
    require a deliberate opt-in, so a typo can never silently enable it.
    """
    return os.getenv("LLM_COUNCIL_STRUCTURED_FINDINGS", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def parse_findings(
    chairman_response: str,
) -> Tuple[List["Finding"], str, Optional[str]]:
    """Parse the chairman JSON's ``findings`` array (ADR-051 C2).

    The chairman's BINARY verdict is already JSON; C2 asks it to include a
    ``findings`` array in that same object. Returns ``(findings, source,
    reason)`` where ``source`` is ``"structured"`` on a clean parse (including a
    legitimately empty list) or ``"fallback"`` with a ``reason`` when the block
    is missing/malformed. Soft-fail: never raises — the verdict path still works
    via the legacy route when this returns fallback.

    Robustness: severity is normalized fail-safe (blocker-ish labels →
    ``critical`` so the mechanical gate can't false-pass them); items without a
    description, or non-dict items, are skipped.
    """
    from .schemas import Finding

    try:
        data = _extract_json_object(chairman_response, preferred_key="findings")
    except Exception as exc:  # unparseable ⇒ legacy fallback
        return [], "fallback", f"json_parse:{type(exc).__name__}"
    if not isinstance(data, dict) or "findings" not in data:
        return [], "fallback", "no_findings_key"
    raw = data["findings"]
    if not isinstance(raw, list):
        return [], "fallback", "findings_not_list"

    findings: List["Finding"] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        description = item.get("description")
        # Fail-safe: NEVER drop a finding for a missing description — a critical
        # with no text would silently vanish and false-pass. Keep it with a
        # placeholder so its severity still gates (Council C3 finding).
        if description is None or str(description).strip() == "":
            description = "(no description provided)"
        severity = _normalize_severity(item.get("severity", ""))
        # `is not None` (not truthiness): keep a present-but-falsy value like
        # 0/false rather than silently discarding it.
        location = item.get("location")
        dimension = item.get("dimension")
        findings.append(
            Finding(
                severity=severity,  # type: ignore[arg-type]
                # A dict/list description would leak a Python repr via str();
                # JSON-encode non-strings so the text stays valid data.
                description=_as_text(description),
                location=_as_text(location) if location is not None else None,
                dimension=_as_text(dimension) if dimension is not None else None,
            )
        )
    return findings, "structured", None
