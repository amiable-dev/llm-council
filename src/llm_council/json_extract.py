"""LLM-resilient JSON object extraction from model prose (#561).

One extractor, one place. Both the ADR-025b verdict parser (``verdict.py``) and
the ADR-051 findings parser (``verification/findings.py``) read **the same
chairman response string**; before this module they used different rules and
disagreed on real payloads.

The old ``verdict._extract_json_from_text`` tried a fenced-code-block regex and
then fell back to ``\\{[^{}]*\\}`` — the first *brace-free* object. Since ADR-051
made the chairman's payload findings-first, that fallback matched ``findings[0]``
(``{"severity", "description", "location"}``) rather than the verdict object, and
``parse_binary_verdict`` raised ``Missing required field: verdict`` on perfectly
well-formed output whose only sin was omitting the closing code fence.

This module lives at package root, not under ``verification/``, because
``verdict.py`` is imported *by* ``verification`` and cannot import back into it.

Kept deliberately dependency-free: ``json`` and ``typing`` only.
"""

from __future__ import annotations

import json
from typing import Any, Optional

__all__ = ["extract_json_object", "matching_brace"]


def matching_brace(text: str, start: int) -> int:
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


def extract_json_object(text: str, preferred_key: Optional[str] = None) -> Any:
    """Extract a JSON object from chairman text (LLM-resilient).

    Tries the whole string first, then walks EVERY ``{`` position with
    string-aware brace matching. When ``preferred_key`` is given it returns the
    first parsed dict that CONTAINS that key — so a decoy object before the real
    payload (a leading ``findings[0]``, or an example object in prose) is
    skipped; if none has the key, it returns the first dict.

    Code fences need no special handling: the brace walk simply starts after
    them, so an unclosed ```` ```json ```` fence is harmless.

    Raises ``ValueError`` when nothing parses.
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
        end = matching_brace(stripped, idx)
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
