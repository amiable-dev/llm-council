"""High-level Python facade: ``consult_council`` (#444, docs-as-spec).

The published quickstart documented ``from llm_council import consult_council``
returning an object with ``.synthesis`` before any such API existed. The
documented shape is better library UX than tuple-unpacking
``run_full_council``, so this ships it: one awaitable call, tier semantics
identical to the MCP ``consult_council`` tool (confidence → tier contract →
tier-sovereign timeouts, unknown values falling back to ``high``).

Usage::

    from llm_council import consult_council

    result = await consult_council(
        "What are the best practices for error handling in Python?",
        confidence="balanced",
    )
    print(result.synthesis)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from llm_council.council import run_council_with_fallback
from llm_council.tier_contract import TIER_MODEL_POOLS, create_tier_contract
from llm_council.verdict import VerdictType

__all__ = ["CouncilResult", "consult_council"]


@dataclass
class CouncilResult:
    """The documented result shape.

    ``raw`` carries the full ADR-012 structured dict for anything not lifted
    to an attribute (usage/cost per ADR-011 lives in ``metadata['usage']``).
    """

    synthesis: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    model_responses: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)


async def consult_council(
    query: str,
    confidence: str = "high",
    *,
    verdict_type: str = "synthesis",
    include_dissent: bool = False,
    models: Optional[List[str]] = None,
    bypass_cache: bool = False,
) -> CouncilResult:
    """Run the 3-stage council and return the synthesized result.

    Args:
        query: The question to deliberate.
        confidence: quick | balanced | high | reasoning — selects the tier
            (models + timeouts). Unknown values fall back to ``high``, the
            same forgiving semantics as the MCP tool.
        verdict_type: synthesis | binary | tie_breaker (ADR-025b Jury Mode).
        include_dissent: Extract minority opinions from the peer review.
        models: Optional explicit council override (else tier pool).
        bypass_cache: Skip the response cache.

    Raises:
        ValueError: on an unknown ``verdict_type`` (unlike ``confidence``,
            a bad verdict type changes the OUTPUT CONTRACT, so it must not
            be silently coerced).
    """
    # Accept the enum directly or its string value (#450 review) — any other
    # type is a ValueError, never an AttributeError.
    if isinstance(verdict_type, VerdictType):
        verdict = verdict_type
    else:
        try:
            verdict = VerdictType(str(verdict_type).lower())
        except ValueError:
            valid = ", ".join(v.value for v in VerdictType)
            raise ValueError(
                f"unknown verdict_type {verdict_type!r}; expected one of: {valid}"
            ) from None

    tier = confidence if confidence in TIER_MODEL_POOLS else "high"
    tier_contract = create_tier_contract(tier)

    # Public-API hardening (#450 review): a misconfigured tier could carry
    # None timeouts; omit the kwargs and let the orchestrator's defaults
    # apply rather than crashing on arithmetic.
    timeout_kwargs = {}
    if tier_contract.deadline_ms:
        timeout_kwargs["synthesis_deadline"] = tier_contract.deadline_ms / 1000
    if tier_contract.per_model_timeout_ms:
        timeout_kwargs["per_model_timeout"] = tier_contract.per_model_timeout_ms / 1000

    raw = await run_council_with_fallback(
        query,
        models=models,
        bypass_cache=bypass_cache,
        tier_contract=tier_contract,
        verdict_type=verdict,
        include_dissent=include_dissent,
        **timeout_kwargs,
    )
    return CouncilResult(
        synthesis=raw.get("synthesis", ""),
        metadata=raw.get("metadata", {}),
        model_responses=raw.get("model_responses", {}),
        raw=raw,
    )
