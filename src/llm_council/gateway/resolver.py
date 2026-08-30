"""Gateway endpoint and model-name resolution.

Centralizes which gateway (URL + API key) and which model id the council
query path uses, based on the unified config. Keeps the OpenRouter/Requesty
URL constants in a single place (their gateway modules) instead of
duplicating them in the query client.
"""

import json
import os
from pathlib import Path
from typing import Tuple

from llm_council.unified_config import get_api_key, get_config

from .openrouter import OPENROUTER_API_URL
from .requesty import REQUESTY_API_URL


def _openclaw_config_path() -> Path:
    """Return the OpenClaw config used by the local OAuth gateway."""
    configured = os.getenv("OPENCLAW_CONFIG_PATH", "").strip()
    return (
        Path(configured).expanduser() if configured else Path.home() / ".openclaw" / "openclaw.json"
    )


def _openclaw_gateway_settings() -> Tuple[str, str]:
    """Resolve local gateway URL/token without copying provider OAuth credentials.

    The bearer value authenticates to the local OpenClaw operator gateway. OpenClaw,
    not LLM Council, owns and refreshes the upstream OpenAI/Gemini OAuth profiles.
    """
    config_path = _openclaw_config_path()
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise RuntimeError(f"Unable to read OpenClaw config at {config_path}: {exc}") from exc

    gateway = data.get("gateway") or {}
    auth = gateway.get("auth") or {}
    port = int(os.getenv("OPENCLAW_GATEWAY_PORT") or gateway.get("port") or 18789)
    token = str(os.getenv("OPENCLAW_GATEWAY_TOKEN") or auth.get("token") or "").strip()
    if not token:
        raise RuntimeError(
            "OpenClaw gateway token is not configured; set gateway.auth.token or "
            "OPENCLAW_GATEWAY_TOKEN"
        )
    return f"http://127.0.0.1:{port}/v1/chat/completions", token


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

    if gw == "openclaw" and provider is not None and getattr(provider, "enabled", False):
        discovered_url, token = _openclaw_gateway_settings()
        url = provider.base_url or discovered_url
        return url, token, "openclaw"

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
