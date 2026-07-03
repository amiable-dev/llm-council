"""MCP Server Card generation (ADR-045 Phase 2, #405).

Builds a Server Card per SEP-2127 (the `experimental-ext-server-card`
extension tracked for the MCP 2026-07-28 spec cycle): identity, repository,
and docs links, with council-specific metadata (tools, tiers) under a
namespaced ``_meta`` key — SEP-2127 cards intentionally exclude top-level
primitive listings, so vendor data belongs in ``_meta`` only.

The card is **generated from code** (the live FastMCP tool registry), never
hand-maintained, so it cannot drift from the actual server surface. It is
served by the HTTP server at both discovery paths (``/server-card`` per the
extension's recommendation and ``/.well-known/mcp/server-card.json`` per
SEP-1649) and committed as a static ``server-card.json`` for registry
submission (drift-tested against the generator).

RE-CHECK after 2026-07-28: the schema referenced below is the RC shape from
``modelcontextprotocol/experimental-ext-server-card``; if Server Cards
graduate with the final spec, re-vendor the schema, re-validate, and update
``SERVER_CARD_SCHEMA_URL`` if the hosted URL changes.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SERVER_CARD_SCHEMA_URL = (
    "https://static.modelcontextprotocol.io/schemas/v1/server-card.schema.json"
)
META_NAMESPACE = "dev.amiable.llm-council"

_REPO_URL = "https://github.com/amiable-dev/llm-council"
_TIERS = ["quick", "balanced", "high", "reasoning", "frontier"]


def _get_version() -> str:
    try:
        from importlib.metadata import version

        return version("llm-council-core")
    except Exception:  # pragma: no cover - not installed (e.g. raw checkout)
        return "0.0.0"


def _get_tool_names() -> Optional[List[str]]:
    """Tool names from the ACTUAL FastMCP registry (no drift by construction).

    Returns None when the ``mcp`` extra is not installed — the card is still
    valid without the tools entry (SEP-2127 requires none).
    """
    try:
        from .mcp_server import mcp

        # FastMCP's public list_tools() is async; the tool manager holds the
        # same registry synchronously. The drift test pins this against the
        # public API, so a private-attr change fails loudly in CI.
        return sorted(t.name for t in mcp._tool_manager.list_tools())
    except Exception as exc:
        logger.debug("mcp tool registry unavailable (%s); card omits tools", exc)
        return None


def build_server_card() -> Dict[str, Any]:
    """Build the Server Card document from code."""
    meta: Dict[str, Any] = {
        "tiers": list(_TIERS),
        "docs": f"{_REPO_URL}#readme",
        "transport": "stdio",
        "install": "uv tool install 'llm-council-core[mcp,secure]'",
    }
    tools = _get_tool_names()
    if tools is not None:
        meta["tools"] = tools
    return {
        "$schema": SERVER_CARD_SCHEMA_URL,
        # Reverse-DNS namespace per the RC schema pattern; io.github.<owner>
        # is the MCP Registry's GitHub-verifiable namespace convention.
        "name": "io.github.amiable-dev/llm-council",
        "title": "LLM Council",
        # RC schema caps description at 100 chars.
        "description": (
            "Multi-model deliberation council with anonymized peer review, "
            "exposed as MCP tools."
        ),
        "version": _get_version(),
        "websiteUrl": _REPO_URL,
        "repository": {"source": "github", "url": _REPO_URL},
        "_meta": {META_NAMESPACE: meta},
    }
