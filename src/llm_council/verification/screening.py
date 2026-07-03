"""Lightweight screening judge — opt-in verify pre-gate (ADR-047 P3, #415).

A single quick-tier model scores the change against the rubric in seconds;
unambiguous outcomes short-circuit to a cheap PASS-with-audit-note, everything
else proceeds to the full council unchanged.

Modes (``LLM_COUNCIL_SCREENING``):
- ``off`` (default) — no screen call at all; byte-identical behaviour. Unlike
  ADR-044 P2's free shadow (which observes existing votes), a shadow screen
  ADDS a model call, so it must be explicitly opted into.
- ``shadow`` — run the screen and log its decision + scores (so the screen's
  own precision is measurable), but ALWAYS run the full council.
- ``active`` — short-circuit to PASS when the screen is unanimous.

Hard eligibility invariants (checked BEFORE any model call; env-tunable
thresholds, never the invariants themselves):
- NEVER blocking-capable requests: any evidence item with strength=blocking,
  or ``rubric_focus`` of security — full council always runs.
- content < ``LLM_COUNCIL_SCREEN_MAX_CHARS`` (default 5000)
- no target path matching a risk glob (auth/security/crypto/payment)
- screen passes only if EVERY rubric dimension scores >=
  ``LLM_COUNCIL_SCREEN_MIN_SCORE`` (default 9)

Every decision is appended to ``.council/screening/decisions.jsonl``.
Soft-fail throughout: any screen error means the full council runs.
"""

from __future__ import annotations

import fnmatch
import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_DECISIONS_PATH = Path(".council") / "screening" / "decisions.jsonl"
RISK_GLOBS = ("**/auth*", "**/security*", "**/crypto*", "**/*payment*")
SCREEN_DIMENSIONS = ("accuracy", "relevance", "completeness", "conciseness", "clarity")


def screening_mode() -> str:
    """Resolve the screening mode; unknown values degrade to off."""
    mode = os.getenv("LLM_COUNCIL_SCREENING", "off").lower()
    return mode if mode in ("off", "shadow", "active") else "off"


def _max_chars() -> int:
    try:
        return int(os.getenv("LLM_COUNCIL_SCREEN_MAX_CHARS", "5000"))
    except ValueError:
        return 5000


def _min_score() -> float:
    try:
        return float(os.getenv("LLM_COUNCIL_SCREEN_MIN_SCORE", "9"))
    except ValueError:
        return 9.0


@dataclass
class ScreenDecision:
    """One screening decision — logged whether or not it acted."""

    verification_id: str
    mode: str
    eligible: bool
    reasons: List[str] = field(default_factory=list)
    scores: Optional[Dict[str, float]] = None
    screen_pass: bool = False
    acted: bool = False  # True only when active mode short-circuited
    ts: float = 0.0


def screen_eligibility(
    *,
    content_chars: int,
    target_paths: Optional[List[str]],
    rubric_focus: Optional[str],
    evidence: Optional[List[Dict[str, Any]]],
) -> List[str]:
    """Return the list of ineligibility reasons (empty == eligible).

    These are INVARIANTS, not tunables: a blocking-capable request is never
    screened silently (ADR-047 council feedback, operationalized).
    """
    def _strength(item: Any) -> Optional[str]:
        # Evidence arrives as dicts (HTTP/MCP JSON) OR Pydantic models
        # (validated VerifyRequest) — the invariant must catch both.
        if isinstance(item, dict):
            return item.get("strength")
        return getattr(item, "strength", None)

    reasons: List[str] = []
    if evidence and any(_strength(item) == "blocking" for item in evidence):
        reasons.append("blocking_evidence")
    if (rubric_focus or "").lower() == "security":
        reasons.append("security_focus")
    if content_chars >= _max_chars():
        reasons.append(f"content_too_large({content_chars}>={_max_chars()})")
    for path in target_paths or []:
        lowered = path.lower()
        for pattern in RISK_GLOBS:
            # Match both the full-path glob and the basename form so
            # "src/auth_handler.py" and "auth/handler.py" both trip it.
            if fnmatch.fnmatch(lowered, pattern) or fnmatch.fnmatch(
                lowered, pattern.replace("**/", "")
            ):
                reasons.append(f"risk_path({path})")
                break
    return reasons


def parse_screen_scores(text: str) -> Optional[Dict[str, float]]:
    """Parse the screen model's JSON scores; None when unusable."""
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        raw = json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        return None
    scores: Dict[str, float] = {}
    for dim in SCREEN_DIMENSIONS:
        value = raw.get(dim)
        if not isinstance(value, (int, float)):
            return None  # incomplete scoring cannot justify a short-circuit
        scores[dim] = float(value)
    return scores


def screen_passes(scores: Optional[Dict[str, float]]) -> bool:
    """Unanimity rule: EVERY dimension at or above the minimum."""
    if not scores:
        return False
    minimum = _min_score()
    return all(scores.get(dim, 0.0) >= minimum for dim in SCREEN_DIMENSIONS)


def build_screen_prompt(verification_query: str) -> str:
    return (
        "You are a fast screening judge. Score the following change on each "
        "dimension from 0-10. Respond with ONLY a JSON object of the form "
        '{"accuracy": n, "relevance": n, "completeness": n, "conciseness": n, '
        '"clarity": n} and nothing else.\n\n' + verification_query
    )


async def run_screen(
    verification_id: str,
    verification_query: str,
) -> Optional[Dict[str, float]]:
    """Run the single quick-tier screen call. None on any failure (soft-fail)."""
    try:
        from llm_council.gateway_adapter import query_model
        from llm_council.tier_contract import create_tier_contract

        quick = create_tier_contract("quick")
        model = quick.allowed_models[0]
        response = await query_model(
            model,
            [{"role": "user", "content": build_screen_prompt(verification_query)}],
            timeout=quick.per_model_timeout_ms / 1000,
            disable_tools=True,
        )
        if not response:
            return None
        return parse_screen_scores(response.get("content") or "")
    except Exception as exc:
        logger.warning("screening judge failed (%s); full council runs", exc)
        return None


def log_decision(decision: ScreenDecision, path: Optional[Path] = None) -> None:
    """Append the decision to the JSONL log. Soft-fail."""
    p = path if path is not None else DEFAULT_DECISIONS_PATH
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        record = asdict(decision)
        record["ts"] = decision.ts or time.time()
        with p.open("a") as fh:
            fh.write(json.dumps(record) + "\n")
    except Exception as exc:
        logger.debug("screening decision log failed (%s)", exc)
