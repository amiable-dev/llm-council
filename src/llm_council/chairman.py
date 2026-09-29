"""Which model synthesises (#725).

ADR-022 gave every tier its own aggregator (``TIER_AGGREGATORS``), sized to
that tier's budget, and ``create_tier_contract`` put it on every contract as
``aggregator_model``. Nothing read it: stage 3 always used the flat
``council.chairman``, whose default was ``anthropic/claude-opus-5``, so a
balanced verify handed a ~188s chairman a 45s stage (#686, #597).

Precedence, highest first:

1. an explicit ``council.chairman`` (config file or ``LLM_COUNCIL_CHAIRMAN``),
   which applies to every tier — an operator's choice always wins;
2. the tier contract in scope: its ``aggregator_model`` (read off the contract
   the orchestrator holds, so a customised contract is honoured);
3. no contract in scope (``run_full_council``, the health probe, import-time
   exports): the default tier's aggregator.

The contract in scope is request-scoped (a ContextVar, like ``cache_context``),
set by the two orchestrators around the work and reset in their ``finally``.
It propagates into asyncio tasks (``wait_for`` copies the context) and
``asyncio.to_thread``, but NOT into a bare ``run_in_executor`` or a manually
started thread: stage 3 run there would read no tier and use the default's.
Test patches on ``llm_council.council.CHAIRMAN_MODEL`` still win: that check
stays in ``council._get_chairman_model``.

Resolution never raises. It runs at import time (``llm_council.CHAIRMAN_MODEL``,
the cache module), so a bad tier name must degrade to a known aggregator — with
a log line, because a silently mis-scoped chairman is the bug #725 fixes.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar, Token
from typing import TYPE_CHECKING, Optional, Union

if TYPE_CHECKING:
    from .tier_contract import TierContract

logger = logging.getLogger(__name__)

#: Used only if even the configured default tier is unknown.
_LAST_RESORT_TIER = "high"

_current_contract: ContextVar[Optional["TierContract"]] = ContextVar(
    "llm_council_tier_contract", default=None
)


def set_current_tier(tier: Union["TierContract", str, None]) -> Token:
    """Scope a tier (a contract, or a tier name) to the current request.

    Pass the returned token to ``reset_current_tier`` in a ``finally``.
    """
    if isinstance(tier, str):
        contract = _contract_for(tier)
        if contract is None:
            logger.warning("chairman: unknown tier %r in scope; using the default tier's", tier)
    else:
        contract = tier
    return _current_contract.set(contract)


def reset_current_tier(token: Token) -> None:
    _current_contract.reset(token)


def current_tier() -> Optional[str]:
    contract = _current_contract.get()
    return contract.tier if contract is not None else None


def _contract_for(tier: str) -> Optional["TierContract"]:
    """The contract for a tier name, or None if the name is unknown."""
    from .tier_contract import TIER_AGGREGATORS, create_tier_contract

    name = tier.lower()
    if name not in TIER_AGGREGATORS:
        return None
    return create_tier_contract(name)


def _default_aggregator() -> str:
    from .tier_contract import TIER_AGGREGATORS
    from .unified_config import get_config

    default = get_config().tiers.default
    contract = _contract_for(default)
    if contract is not None:
        return contract.aggregator_model
    logger.warning(
        "chairman: default tier %r is unknown; using %r's aggregator", default, _LAST_RESORT_TIER
    )
    # A dict lookup, not an assert: `python -O` strips asserts, and this runs at import.
    return TIER_AGGREGATORS[_LAST_RESORT_TIER]


def resolve_chairman(tier: Optional[str] = None) -> str:
    """The synthesis model for ``tier`` (default: the contract in scope)."""
    from .unified_config import get_config

    configured = (get_config().council.chairman or "").strip()
    if configured:
        return configured
    if tier is not None:
        contract = _contract_for(tier)
        if contract is None:
            logger.warning("chairman: unknown tier %r; using the default tier's", tier)
    else:
        contract = _current_contract.get()
        if contract is None:
            logger.debug("chairman: no tier in scope; using the default tier's")
    return contract.aggregator_model if contract is not None else _default_aggregator()
