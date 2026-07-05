"""Structured findings channel (ADR-051) — flag + (later) parser/policy.

C1 (#485) adds only the opt-in flag; C2 adds the chairman findings parser and
C3 the deterministic verdict policy (`policy(findings)`). The whole epic is
gated on ``LLM_COUNCIL_STRUCTURED_FINDINGS`` (default OFF) so it is additive and
non-breaking until a later deliberate default-ON flip (a breaking release).
"""

from __future__ import annotations

import os

__all__ = ["structured_findings_enabled"]


def structured_findings_enabled() -> bool:
    """Opt-in flag for the ADR-051 structured findings channel (default OFF)."""
    return os.getenv("LLM_COUNCIL_STRUCTURED_FINDINGS", "false").strip().lower() not in (
        "false",
        "0",
        "no",
        "",
    )
