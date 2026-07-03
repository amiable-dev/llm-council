"""ADR-045 P2: Server Card generated from the tool registry (#405).

Validated against the SEP-2127 experimental-ext RC schema (vendored at
tests/fixtures/server_card_v1_rc.schema.json). RE-CHECK after 2026-07-28:
if Server Cards graduate with the final spec, re-vendor the schema and
re-validate (tracked as a dated follow-up issue).
"""

import json
from pathlib import Path

import pytest

from llm_council.server_card import (
    META_NAMESPACE,
    SERVER_CARD_SCHEMA_URL,
    build_server_card,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
RC_SCHEMA = json.loads(
    (REPO_ROOT / "tests" / "fixtures" / "server_card_v1_rc.schema.json").read_text()
)


def _validate_against_rc_schema(card: dict) -> None:
    jsonschema = pytest.importorskip("jsonschema")
    # The vendored schema is a $defs-only document; validate against the
    # ServerCard definition specifically.
    schema = {**RC_SCHEMA, "$ref": "#/$defs/ServerCard"}
    jsonschema.validate(card, schema)


class TestCardShape:
    def test_required_fields(self):
        card = build_server_card()
        assert card["$schema"] == SERVER_CARD_SCHEMA_URL
        assert card["name"] == "io.github.amiable-dev/llm-council"
        assert isinstance(card["version"], str) and card["version"]
        assert "deliberation" in card["description"].lower() or "council" in card["description"].lower()

    def test_validates_against_rc_schema(self):
        _validate_against_rc_schema(build_server_card())

    def test_repository_and_website(self):
        card = build_server_card()
        assert card["repository"]["url"] == "https://github.com/amiable-dev/llm-council"
        assert card["repository"]["source"] == "github"
        assert card["websiteUrl"].startswith("https://")

    def test_no_top_level_tool_listing(self):
        # SEP-2127 cards intentionally exclude primitive listings at the top
        # level; vendor data lives under namespaced _meta only.
        card = build_server_card()
        assert "tools" not in card
        assert META_NAMESPACE in card["_meta"]


class TestGeneratedFromCode:
    def test_tool_list_matches_mcp_registry(self):
        # Acceptance: generated from code — the card's tool names must match
        # the ACTUAL FastMCP tool registry, not a hand-maintained list.
        pytest.importorskip("mcp")
        import asyncio

        from llm_council.mcp_server import mcp

        registered = {t.name for t in asyncio.run(mcp.list_tools())}
        card_tools = set(build_server_card()["_meta"][META_NAMESPACE]["tools"])
        assert card_tools == registered
        assert "consult_council" in card_tools

    def test_tiers_listed(self):
        meta = build_server_card()["_meta"][META_NAMESPACE]
        assert set(meta["tiers"]) == {"quick", "balanced", "high", "reasoning", "frontier"}


class TestHttpEndpoints:
    @pytest.fixture()
    def client(self):
        fastapi = pytest.importorskip("fastapi")  # noqa: F841
        from fastapi.testclient import TestClient

        from llm_council.http_server import app

        return TestClient(app)

    @pytest.mark.parametrize(
        "path", ["/.well-known/mcp/server-card.json", "/server-card"]
    )
    def test_served_at_discovery_paths(self, client, path):
        resp = client.get(path)
        assert resp.status_code == 200
        card = resp.json()
        assert card["name"] == "io.github.amiable-dev/llm-council"
        _validate_against_rc_schema(card)


class TestStaticCard:
    def test_committed_card_matches_generated(self):
        # Drift guard: the committed registry-submission card must equal the
        # generated card, modulo version (stamped at generation time).
        committed = json.loads((REPO_ROOT / "server-card.json").read_text())
        generated = build_server_card()
        committed["version"] = generated["version"] = "MASKED"
        assert committed == generated


class TestCouncilRound1:
    def test_missing_mcp_extra_omits_tools_gracefully(self, monkeypatch):
        # ImportError (mcp extra not installed) is the ONLY tolerated failure.
        import builtins

        real_import = builtins.__import__

        def no_mcp(name, *a, **kw):
            if name.endswith("mcp_server") or name == "llm_council.mcp_server":
                raise ImportError("mcp extra not installed")
            return real_import(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", no_mcp)
        from llm_council.server_card import _get_tool_names

        assert _get_tool_names() is None

    def test_private_api_breakage_fails_loudly(self, monkeypatch):
        # A FastMCP internals change must raise, not silently drop the tools
        # entry from the card (round-1 council finding).
        pytest.importorskip("mcp")
        import llm_council.mcp_server as mcp_server_mod
        from llm_council.server_card import _get_tool_names

        class NoManager:
            pass

        monkeypatch.setattr(mcp_server_mod, "mcp", NoManager())
        with pytest.raises(AttributeError):
            _get_tool_names()
