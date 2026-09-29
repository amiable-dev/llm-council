"""Which model synthesises (#725).

ADR-022 gave every tier its own aggregator (``TIER_AGGREGATORS``), sized to
that tier's budget, and ``create_tier_contract`` put it on every contract as
``aggregator_model``. Nothing read it: stage 3 always used the flat
``council.chairman``, whose default was ``anthropic/claude-opus-5``, so a
balanced verify handed a ~188s chairman a 45s stage (#686, #597).

Precedence, highest first:

1. an explicit ``council.chairman`` (config file or ``LLM_COUNCIL_CHAIRMAN``),
   which applies to every tier — an operator's choice always wins;
2. the tier in scope: its contract's ``aggregator_model``;
3. no tier in scope (``run_full_council``, the health probe, import-time
   exports): the default tier's aggregator.

The tier in scope is request-scoped (a ContextVar, like ``cache_context``), set
by the two orchestrators around the work and reset in their ``finally``.
Test patches on ``llm_council.council.CHAIRMAN_MODEL`` still win: that check
stays in ``council._get_chairman_model``.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Optional

_current_tier: ContextVar[Optional[str]] = ContextVar("llm_council_tier", default=None)


def set_current_tier(tier: Optional[str]) -> Token:
    """Scope ``tier`` to the current request; pass the token to reset it."""
    return _current_tier.set(tier)


def reset_current_tier(token: Token) -> None:
    _current_tier.reset(token)


def current_tier() -> Optional[str]:
    return _current_tier.get()


def resolve_chairman(tier: Optional[str] = None) -> str:
    """The synthesis model for ``tier`` (default: the tier in scope)."""
    from .tier_contract import create_tier_contract
    from .unified_config import get_config

    config = get_config()
    configured = (config.council.chairman or "").strip()
    if configured:
        return configured
    default_tier = config.tiers.default
    try:
        return create_tier_contract(tier or current_tier() or default_tier).aggregator_model
    except ValueError:
        # An unknown tier name: fall back to the default tier's aggregator
        # rather than failing a synthesis over a label.
        return create_tier_contract(default_tier).aggregator_model
