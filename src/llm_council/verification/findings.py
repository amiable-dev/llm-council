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

__all__ = ["structured_findings_enabled", "parse_findings"]

_VALID_SEVERITIES = {"critical", "major", "minor", "info"}


def _extract_json_object(text: str) -> Any:
    """Extract a (possibly nested) JSON object from chairman text.

    Unlike the flat verdict extractor (`verdict._extract_json_from_text`, whose
    `\\{[^{}]*\\}` pattern breaks on nested arrays of objects), this handles the
    `findings` array. It first tries the whole string, then scans for the first
    balanced ``{…}`` with a **string-aware** matcher (braces inside JSON string
    values, and escaped quotes, are ignored — a naive brace count miscounts a
    description like ``"use {x}"``). No greedy regex (which spans multiple
    fenced blocks). Raises on no valid object; the caller soft-fails.
    """
    stripped = text.strip()
    try:
        return json.loads(stripped)  # fast path: the whole thing is JSON
    except json.JSONDecodeError:
        pass
    start = stripped.find("{")
    if start == -1:
        raise ValueError("no JSON object found")
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(stripped)):
        c = stripped[i]
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
                return json.loads(stripped[start : i + 1])
    raise ValueError("unbalanced JSON object")


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

    Robustness rules: an unknown severity is coerced to ``"major"`` (visible,
    never silently dropped — the C3 mechanical gate can't act on what it can't
    see); items without a description, or non-dict items, are skipped.
    """
    from .schemas import Finding

    try:
        data = _extract_json_object(chairman_response)
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
        severity = str(item.get("severity", "")).strip().lower()
        if severity not in _VALID_SEVERITIES:
            severity = "major"  # visible, never dropped
        # `is not None` (not truthiness): keep a present-but-falsy value like
        # 0/false rather than silently discarding it.
        location = item.get("location")
        dimension = item.get("dimension")
        findings.append(
            Finding(
                severity=severity,  # type: ignore[arg-type]
                description=str(description),
                location=str(location) if location is not None else None,
                dimension=str(dimension) if dimension is not None else None,
            )
        )
    return findings, "structured", None
