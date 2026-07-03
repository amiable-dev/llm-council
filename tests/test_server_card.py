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
