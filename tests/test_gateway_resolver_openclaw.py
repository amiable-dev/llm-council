import json
from unittest.mock import AsyncMock

import pytest

from llm_council import unified_config
from llm_council.gateway.resolver import _openclaw_gateway_settings, resolve_endpoint
from llm_council.unified_config import load_config


def test_openclaw_gateway_reads_local_operator_token_without_provider_keys(tmp_path, monkeypatch):
    openclaw_config = tmp_path / "openclaw.json"
    openclaw_config.write_text(
        json.dumps({"gateway": {"port": 19999, "auth": {"token": "local-operator-token"}}})
    )
    monkeypatch.setenv("OPENCLAW_CONFIG_PATH", str(openclaw_config))
    monkeypatch.delenv("OPENCLAW_GATEWAY_PORT", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    assert _openclaw_gateway_settings() == (
        "http://127.0.0.1:19999/v1/chat/completions",
        "local-operator-token",
    )


def test_openclaw_gateway_environment_overrides_port_and_operator_token(tmp_path, monkeypatch):
    openclaw_config = tmp_path / "openclaw.json"
    openclaw_config.write_text(
        json.dumps({"gateway": {"port": 18789, "auth": {"token": "config-token"}}})
    )
    monkeypatch.setenv("OPENCLAW_CONFIG_PATH", str(openclaw_config))
    monkeypatch.setenv("OPENCLAW_GATEWAY_PORT", "19789")
    monkeypatch.setenv("OPENCLAW_GATEWAY_TOKEN", "environment-token")

    assert _openclaw_gateway_settings() == (
        "http://127.0.0.1:19789/v1/chat/completions",
        "environment-token",
    )


def test_openclaw_gateway_fails_closed_without_operator_token(tmp_path, monkeypatch):
    openclaw_config = tmp_path / "openclaw.json"
    openclaw_config.write_text(json.dumps({"gateway": {"port": 18789}}))
    monkeypatch.setenv("OPENCLAW_CONFIG_PATH", str(openclaw_config))
    monkeypatch.delenv("OPENCLAW_GATEWAY_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="gateway token is not configured"):
        _openclaw_gateway_settings()


def test_openclaw_gateway_reports_unreadable_configuration(tmp_path, monkeypatch):
    missing_config = tmp_path / "missing-openclaw.json"
    monkeypatch.setenv("OPENCLAW_CONFIG_PATH", str(missing_config))

    with pytest.raises(RuntimeError, match="Unable to read OpenClaw config"):
        _openclaw_gateway_settings()


def test_resolve_endpoint_supports_openclaw_oauth_broker(tmp_path, monkeypatch):
    openclaw_config = tmp_path / "openclaw.json"
    openclaw_config.write_text(
        json.dumps({"gateway": {"port": 18789, "auth": {"token": "gateway-token"}}})
    )
    council_config = tmp_path / "llm_council.yaml"
    council_config.write_text(
        """
gateways:
  default: openclaw
  providers:
    openclaw:
      enabled: true
"""
    )
    monkeypatch.setenv("OPENCLAW_CONFIG_PATH", str(openclaw_config))
    monkeypatch.delenv("OPENCLAW_GATEWAY_PORT", raising=False)
    monkeypatch.setattr(unified_config, "_global_config", load_config(council_config))

    assert resolve_endpoint() == (
        "http://127.0.0.1:18789/v1/chat/completions",
        "gateway-token",
        "openclaw",
    )


def test_resolve_endpoint_honors_explicit_openclaw_base_url(tmp_path, monkeypatch):
    openclaw_config = tmp_path / "openclaw.json"
    openclaw_config.write_text(
        json.dumps({"gateway": {"port": 18789, "auth": {"token": "gateway-token"}}})
    )
    council_config = tmp_path / "llm_council.yaml"
    council_config.write_text(
        """
gateways:
  default: openclaw
  providers:
    openclaw:
      enabled: true
      base_url: http://127.0.0.1:28789/v1/chat/completions
"""
    )
    monkeypatch.setenv("OPENCLAW_CONFIG_PATH", str(openclaw_config))
    monkeypatch.setattr(unified_config, "_global_config", load_config(council_config))

    assert resolve_endpoint() == (
        "http://127.0.0.1:28789/v1/chat/completions",
        "gateway-token",
        "openclaw",
    )


async def test_health_check_probes_every_openclaw_oauth_member(tmp_path, monkeypatch):
    from llm_council import mcp_server

    openclaw_config = tmp_path / "openclaw.json"
    openclaw_config.write_text(
        json.dumps({"gateway": {"port": 18789, "auth": {"token": "gateway-token"}}})
    )
    council_config = tmp_path / "llm_council.yaml"
    council_config.write_text(
        """
council:
  models: [openclaw/council-gpt, openclaw/council-gemini]
  chairman: openclaw/council-gpt
tiers:
  default: balanced
  pools:
    balanced:
      models: [openclaw/council-gpt, openclaw/council-gemini]
      timeout_seconds: 180
gateways:
  default: openclaw
"""
    )
    monkeypatch.setenv("OPENCLAW_CONFIG_PATH", str(openclaw_config))
    monkeypatch.delenv("OPENCLAW_GATEWAY_PORT", raising=False)
    monkeypatch.setattr(unified_config, "_global_config", load_config(council_config))
    monkeypatch.setattr(
        mcp_server,
        "query_model_with_status",
        AsyncMock(
            side_effect=[
                {"status": "ok", "response": "pong"},
                {"status": "auth_error", "error": "Gemini OAuth missing"},
                {"status": "ok", "response": "chairman pong"},
            ]
        ),
    )

    data = json.loads(await mcp_server.council_health_check(tier="balanced"))

    assert data["ready"] is False
    assert data["model_connectivity"]["openclaw/council-gpt"]["status"] == "ok"
    assert data["model_connectivity"]["openclaw/council-gemini"]["status"] == "auth_error"
    assert data["chairman_connectivity"]["status"] == "ok"
    assert "openclaw/council-gemini" in data["message"]


async def test_deep_health_check_covers_members_and_chairman(tmp_path, monkeypatch):
    from llm_council import mcp_server

    openclaw_config = tmp_path / "openclaw.json"
    openclaw_config.write_text(
        json.dumps({"gateway": {"port": 18789, "auth": {"token": "gateway-token"}}})
    )
    council_config = tmp_path / "llm_council.yaml"
    council_config.write_text(
        """
council:
  models: [openclaw/council-gpt, openclaw/council-gemini]
  chairman: openclaw/council-gpt
tiers:
  default: balanced
  pools:
    balanced:
      models: [openclaw/council-gpt, openclaw/council-gemini]
      timeout_seconds: 180
gateways:
  default: openclaw
"""
    )
    monkeypatch.setenv("OPENCLAW_CONFIG_PATH", str(openclaw_config))
    monkeypatch.setattr(unified_config, "_global_config", load_config(council_config))
    query = AsyncMock(
        side_effect=[
            {"status": "ok", "response": "gpt pong"},
            {"status": "ok", "response": "gemini pong"},
            {"status": "ok", "response": "chairman pong"},
        ]
    )
    monkeypatch.setattr(mcp_server, "query_model_with_status", query)

    data = json.loads(await mcp_server.council_health_check(deep=True, tier="balanced"))

    assert data["ready"] is True
    assert data["ready_scope"] == "chairman_probed"
    assert data["key_source"] == "openclaw_gateway"
    assert data["model_connectivity"] == {
        "openclaw/council-gpt": {"status": "ok"},
        "openclaw/council-gemini": {"status": "ok"},
    }
    assert data["chairman_connectivity"]["status"] == "ok"
    assert query.await_count == 3


async def test_health_check_skips_extra_oauth_probes_after_connectivity_failure(
    tmp_path, monkeypatch
):
    from llm_council import mcp_server

    openclaw_config = tmp_path / "openclaw.json"
    openclaw_config.write_text(
        json.dumps({"gateway": {"port": 18789, "auth": {"token": "gateway-token"}}})
    )
    council_config = tmp_path / "llm_council.yaml"
    council_config.write_text(
        """
council:
  models: [openclaw/council-gpt, openclaw/council-gemini]
  chairman: openclaw/council-gpt
tiers:
  default: balanced
  pools:
    balanced:
      models: [openclaw/council-gpt, openclaw/council-gemini]
      timeout_seconds: 180
gateways:
  default: openclaw
"""
    )
    monkeypatch.setenv("OPENCLAW_CONFIG_PATH", str(openclaw_config))
    monkeypatch.setattr(unified_config, "_global_config", load_config(council_config))
    query = AsyncMock(return_value={"status": "server_error", "error": "gateway unavailable"})
    monkeypatch.setattr(mcp_server, "query_model_with_status", query)

    data = json.loads(await mcp_server.council_health_check(deep=True, tier="balanced"))

    assert data["ready"] is False
    assert data["ready_scope"] == "connectivity_only"
    assert "model_connectivity" not in data
    assert "chairman_connectivity" not in data
    assert query.await_count == 1
