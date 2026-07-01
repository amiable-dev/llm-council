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

from typing import Callable, Dict, Optional, Tuple

from .types import UsageInfo

# Gateways that never incur a marginal per-call API cost.
_LOCAL_GATEWAYS = frozenset({"ollama"})

PricingLookup = Callable[[str], Dict[str, float]]


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
        self._pricing_lookup = pricing_lookup

    def resolve(
        self,
        *,
        gateway: str,
        model_id: str,
        prompt_tokens: int,
        completion_tokens: int,
        provider_cost_usd: Optional[float] = None,
    ) -> Tuple[Optional[float], Optional[str]]:
        """Return ``(cost_usd, cost_source)`` for one call.

        Ground truth wins; otherwise fall back to a registry estimate; local
        gateways are free; anything unpriced resolves to ``(None, None)``.
        """
        if provider_cost_usd is not None:
            return float(provider_cost_usd), "provider"

        if gateway in _LOCAL_GATEWAYS:
            return 0.0, "local_zero"

        pricing = self._pricing_lookup(model_id) if self._pricing_lookup else {}
        if pricing and ("prompt" in pricing or "completion" in pricing):
            price_in = pricing.get("prompt", 0.0)
            price_out = pricing.get("completion", 0.0)
            cost = (prompt_tokens / 1000.0) * price_in + (
                completion_tokens / 1000.0
            ) * price_out
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
    ) -> UsageInfo:
        """Populate cost fields on ``usage`` in place and return it."""
        cost, source = self.resolve(
            gateway=gateway,
            model_id=model_id,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            provider_cost_usd=provider_cost_usd,
        )
        usage.cost_usd = cost
        usage.cost_source = source
        if cached_tokens is not None:
            usage.cached_tokens = cached_tokens
        return usage
