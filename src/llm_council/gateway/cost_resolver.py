"""Per-gateway cost resolution (ADR-011 Phase 1).

Cost fidelity differs by gateway, so a single resolver applies the right
strategy and stamps a ``cost_source`` provenance tag onto each call — a
computed estimate is never presented as a bill:

- OpenRouter / Requesty return an authoritative ``usage.cost`` -> "provider"
- Direct APIs (Anthropic/OpenAI/Google) return tokens only, so cost is
  estimated from the bundled ``models/registry.yaml`` pricing -> "registry_estimate"
- Ollama is local/self-hosted -> "local_zero"
- pricing unknown and no provider figure -> (None, None)

The resolver takes ``pricing_lookup`` by dependency injection (a callable
``model_id -> {"prompt": float, "completion": float}`` per-1K-token dict, the
shape returned by ``MetadataProvider.get_pricing``) so it is unit-testable
without loading the metadata stack. See ADR-011 §1 and ADR-023 §5.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Dict, Optional, Tuple

from .types import UsageInfo

# Gateways that never incur a marginal per-call API cost.
_LOCAL_GATEWAYS = frozenset({"ollama"})

PricingLookup = Callable[[str], Dict[str, float]]


def _safe_price(value: Any) -> Optional[float]:
    """Coerce a registry price to a finite, non-negative float, or None.

    Registry entries can be missing, explicitly null, non-numeric, or malformed;
    none of those must reach the cost arithmetic (a null price would raise a
    TypeError, a negative/NaN price would corrupt the estimate).
    """
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(price) or price < 0:
        return None
    return price


def registry_pricing_lookup(model_id: str) -> Dict[str, float]:
    """Default pricing lookup backed by the metadata provider (registry.yaml).

    Returns a ``{"prompt": ..., "completion": ...}`` per-1K-token dict, or an
    empty dict if pricing is unknown or the provider is unavailable. Imported
    lazily to avoid a gateway->metadata import cycle; never raises.
    """
    try:
        from ..metadata import get_provider

        return get_provider().get_pricing(model_id) or {}
    except Exception:
        return {}


class CostResolver:
    """Resolve ``(cost_usd, cost_source)`` for a single model call."""

    def __init__(self, pricing_lookup: Optional[PricingLookup] = None) -> None:
        # Default to the registry-backed lookup so a bare CostResolver() can
        # still price Direct-API calls; local gateways short-circuit before it.
        # Pass an explicit lookup (e.g. in tests) to override.
        self._pricing_lookup = pricing_lookup or registry_pricing_lookup

    def resolve(
        self,
        *,
        gateway: str,
        model_id: str,
        prompt_tokens: int,
        completion_tokens: int,
        provider_cost_usd: Optional[float] = None,
        cache_read_tokens: int = 0,
        cache_write_5m_tokens: int = 0,
        cache_write_1h_tokens: int = 0,
    ) -> Tuple[Optional[float], Optional[str]]:
        """Return ``(cost_usd, cost_source)`` for one call.

        Ground truth wins; otherwise fall back to a registry estimate; local
        gateways are free; anything unpriced resolves to ``(None, None)``.

        Cache token counts (ADR-049 D3) are the provider's SEPARATE fields —
        e.g. Anthropic direct reports ``input_tokens`` EXCLUDING cache reads
        and writes — so they are priced in ADDITION to ``prompt_tokens``,
        using the registry's ``cache_read`` / ``cache_write_5m`` /
        ``cache_write_1h`` per-1K prices. An entry without a cache price
        bills those tokens at the ``prompt`` price (the documented default:
        consistent, predictable, and exact for providers whose prompt counts
        already include cache traffic since their separate fields stay 0).
        They only affect the registry-estimate path: a provider-reported
        cost already includes any cache discount and wins unconditionally.
        """
        if provider_cost_usd is not None:
            try:
                cost = float(provider_cost_usd)
            except (TypeError, ValueError):
                cost = None
            # Only a finite, non-negative number is valid ground truth; NaN,
            # infinity, negatives, or malformed values fall through to an
            # estimate rather than corrupting accounting metrics.
            if cost is not None and math.isfinite(cost) and cost >= 0:
                return cost, "provider"

        if gateway in _LOCAL_GATEWAYS:
            return 0.0, "local_zero"

        pricing = self._pricing_lookup(model_id) if self._pricing_lookup else {}
        price_in = _safe_price(pricing.get("prompt"))
        price_out = _safe_price(pricing.get("completion"))
        if price_in is not None or price_out is not None:
            # Clamp negative token counts; a bad count must not yield a negative
            # cost. A missing/invalid side of the price contributes 0.
            prompt = max(prompt_tokens, 0)
            completion = max(completion_tokens, 0)
            cost = (prompt / 1000.0) * (price_in or 0.0) + (completion / 1000.0) * (
                price_out or 0.0
            )
            # ADR-049 D3: cache price classes. Unknown class -> prompt price.
            fallback = price_in or 0.0
            for count, key in (
                (cache_read_tokens, "cache_read"),
                (cache_write_5m_tokens, "cache_write_5m"),
                (cache_write_1h_tokens, "cache_write_1h"),
            ):
                price = _safe_price(pricing.get(key))
                cost += (max(count or 0, 0) / 1000.0) * (
                    price if price is not None else fallback
                )
            # 8dp: sub-cent per-call costs must not round to zero.
            return round(cost, 8), "registry_estimate"

        return None, None

    def apply(
        self,
        usage: UsageInfo,
        *,
        gateway: str,
        model_id: str,
        provider_cost_usd: Optional[float] = None,
        cached_tokens: Optional[int] = None,
        cache_read_tokens: int = 0,
        cache_write_5m_tokens: int = 0,
        cache_write_1h_tokens: int = 0,
    ) -> UsageInfo:
        """Populate cost fields on ``usage`` in place and return it.

        Cache token counts (ADR-049 D3) thread through to ``resolve`` so
        registry estimates price them; the provider-cost path ignores them.
        """
        cost, source = self.resolve(
            gateway=gateway,
            model_id=model_id,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            provider_cost_usd=provider_cost_usd,
            cache_read_tokens=cache_read_tokens,
            cache_write_5m_tokens=cache_write_5m_tokens,
            cache_write_1h_tokens=cache_write_1h_tokens,
        )
        usage.cost_usd = cost
        usage.cost_source = source
        if cached_tokens is not None:
            usage.cached_tokens = cached_tokens
        return usage
