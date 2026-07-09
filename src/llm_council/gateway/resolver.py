"""Gateway endpoint and model-name resolution.

Centralizes which gateway (URL + API key) and which model id the council
query path uses, based on the unified config. Keeps the OpenRouter/Requesty
URL constants in a single place (their gateway modules) instead of
duplicating them in the query client.
"""

from typing import Tuple

from llm_council.unified_config import get_api_key, get_config

from .openrouter import OPENROUTER_API_URL
from .requesty import REQUESTY_API_URL


def resolve_endpoint() -> Tuple[str, str, str]:
    """Resolve (api_url, api_key, route_label) from the configured gateway.

    Honors gateways.default and providers.<gw>.base_url / api_key. Falls back
    to OpenRouter defaults when the configured gateway is unknown or disabled,
    so behavior is unchanged for existing OpenRouter deployments.
    """
    config = get_config()
    gw = config.gateways.default
    providers = config.gateways.providers or {}
    provider = providers.get(gw)

    if gw == "requesty" and provider is not None and getattr(provider, "enabled", False):
        url = provider.base_url or REQUESTY_API_URL
        key = get_api_key("requesty") or (provider.api_key or "")
        return url, key, "requesty"

    # Check if openrouter provider is configured with custom settings
    openrouter_provider = providers.get("openrouter")
    if openrouter_provider is not None:
        url = openrouter_provider.base_url or OPENROUTER_API_URL
        key = get_api_key("openrouter") or (openrouter_provider.api_key or "")
    else:
        url = OPENROUTER_API_URL
        key = get_api_key("openrouter") or ""
    return url, key, "openrouter"


def resolve_model_name(model: str, route: str) -> str:
    """Translate a model id to the name expected by the active gateway.

    OpenRouter uses a ":free" suffix to select free variants; Requesty rejects
    that suffix (HTTP 400) and expects provider-prefixed names for some models.
    A per-gateway model_name_map in config rewrites ids; unknown ids pass
    through unchanged.
    """
    if route:
        config = get_config()
        mapping = (config.gateways.model_name_map or {}).get(route, {})
        if mapping:
            return mapping.get(model, model)
    return model
