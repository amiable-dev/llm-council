"""Regression tests for pre-existing openrouter gateway debt (#367)."""

from unittest.mock import AsyncMock, MagicMock, patch

import llm_council.gateway.openrouter as gw_mod
from llm_council.gateway.openrouter import OpenRouterGateway
from llm_council.gateway.types import CanonicalMessage, ContentBlock, GatewayRequest


def _req(model="openai/gpt-4o"):
    return GatewayRequest(
        model=model,
        messages=[CanonicalMessage(role="user", content=[ContentBlock(type="text", text="hi")])],
    )


def _resp(message_content="hi"):
    r = MagicMock()
    r.status_code = 200
    r.raise_for_status = MagicMock()
    r.json.return_value = {
        "choices": [{"message": {"content": message_content}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }
    return r


class TestRequestTimeKey:
    async def test_key_resolved_at_request_time_honors_byok(self, monkeypatch):
        # No explicit key -> resolve via get_api_key at REQUEST time (so a
        # request-scoped BYOK key is honored, not a value frozen at import).
        monkeypatch.setattr(gw_mod, "get_api_key", lambda p: "reqkey" if p == "openrouter" else None)
        captured = {}

        async def _post(url, headers=None, json=None):
            captured["auth"] = headers["Authorization"]
            return _resp()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(side_effect=_post)
            await OpenRouterGateway().complete(_req())  # no explicit key

        assert captured["auth"] == "Bearer reqkey"

    async def test_explicit_key_takes_precedence(self, monkeypatch):
        monkeypatch.setattr(gw_mod, "get_api_key", lambda p: "should-not-be-used")
        captured = {}

        async def _post(url, headers=None, json=None):
            captured["auth"] = headers["Authorization"]
            return _resp()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(side_effect=_post)
            await OpenRouterGateway(api_key="explicit").complete(_req())

        assert captured["auth"] == "Bearer explicit"


class TestNullableContent:
    async def test_null_content_coerced_to_empty_string(self, monkeypatch):
        monkeypatch.setattr(gw_mod, "get_api_key", lambda p: "k")
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=_resp(message_content=None)
            )
            resp = await OpenRouterGateway().complete(_req())
        assert resp.content == ""  # never None


class TestToolCallPreservation:
    def test_convert_message_preserves_tool_calls(self):
        gw = OpenRouterGateway()
        msg = CanonicalMessage(
            role="assistant",
            content=[ContentBlock(type="text", text="")],
            tool_calls=[{"id": "1", "function": {"name": "f", "arguments": "{}"}}],
            tool_call_id="tc1",
        )
        out = gw._convert_message(msg)
        assert out["tool_calls"] == [{"id": "1", "function": {"name": "f", "arguments": "{}"}}]
        assert out["tool_call_id"] == "tc1"

    def test_convert_message_without_tools_has_no_tool_keys(self):
        gw = OpenRouterGateway()
        msg = CanonicalMessage(role="user", content=[ContentBlock(type="text", text="hi")])
        out = gw._convert_message(msg)
        assert "tool_calls" not in out
        assert "tool_call_id" not in out
