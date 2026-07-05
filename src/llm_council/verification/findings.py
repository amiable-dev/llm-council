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
    """
    return "fail" if any(f.severity == "critical" for f in findings) else "pass"


def _as_text(value: Any) -> str:
    """Stringify a field, JSON-encoding non-strings so a dict/list doesn't leak
    a Python repr (``str({'a':1})`` → ``"{'a': 1}"``) into a description."""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


def _matching_brace(text: str, start: int) -> int:
    """Index of the ``}`` matching the ``{`` at ``start``, string-aware, or -1.

    Braces inside JSON string values and escaped quotes are ignored, so a
    description like ``"use {x}"`` doesn't miscount.
    """
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        c = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                in_string = False
            continue
        if c == '"':
            in_string = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _extract_json_object(text: str, preferred_key: Optional[str] = None) -> Any:
    """Extract a JSON object from chairman text (LLM-resilient).

    Unlike the flat verdict extractor (`verdict._extract_json_from_text`, whose
    `\\{[^{}]*\\}` pattern breaks on nested arrays), this tries the whole string,
    then walks EVERY ``{`` position with string-aware brace matching. When
    ``preferred_key`` is given it returns the first parsed dict that CONTAINS
    that key (so a decoy object before the real verdict payload — which would
    cause a silent empty-findings false pass, Council C3 finding — is skipped);
    if none has the key, it returns the first dict. Raises when nothing parses.
    """
    stripped = text.strip()
    first_dict: Any = None

    def _consider(obj: Any) -> Optional[Any]:
        nonlocal first_dict
        if not isinstance(obj, dict):
            return None
        if preferred_key is None or preferred_key in obj:
            return obj
        if first_dict is None:
            first_dict = obj
        return None

    try:
        hit = _consider(json.loads(stripped))  # fast path: the whole thing is JSON
        if hit is not None:
            return hit
    except json.JSONDecodeError:
        pass
    idx = stripped.find("{")
    while idx != -1:
        end = _matching_brace(stripped, idx)
        if end != -1:
            try:
                hit = _consider(json.loads(stripped[idx : end + 1]))
                if hit is not None:
                    return hit
            except json.JSONDecodeError:
                pass
            # Advance PAST this whole object, not to idx+1 (which would rescan
            # its nested braces — an O(n^2) walk).
            idx = stripped.find("{", end + 1)
        else:
            idx = stripped.find("{", idx + 1)  # unbalanced from here: step by one
    if first_dict is not None:
        return first_dict
    raise ValueError("no JSON object found")


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
        # Skip only genuinely-empty descriptions (None / blank) — a useless
        # finding, not data loss. Anything else is stringified below.
        if description is None or str(description).strip() == "":
            continue
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
