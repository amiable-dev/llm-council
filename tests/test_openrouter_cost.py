"""OpenRouter query path captures the authoritative usage.cost (ADR-011 #360).

The council collects usage via query_models_parallel -> query_model ->
query_model_with_status, which previously discarded OpenRouter's inline cost.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _ok_response(usage):
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "choices": [{"message": {"content": "hi"}}],
        "usage": usage,
    }
    return resp


@pytest.mark.asyncio
async def test_query_model_with_status_captures_cost_and_cached():
    from llm_council.openrouter import STATUS_OK, query_model_with_status

    usage = {
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "total_tokens": 150,
        "cost": 0.0012,
        "cached_tokens": 20,
    }
    with (
        patch("llm_council.openrouter.OPENROUTER_API_KEY", "test-key"),
        patch("httpx.AsyncClient") as mock_client,
    ):
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=_ok_response(usage)
        )
        result = await query_model_with_status("openai/gpt-4o", [{"role": "user", "content": "hi"}])

    assert result["status"] == STATUS_OK
    assert result["usage"]["cost"] == 0.0012
    assert result["usage"]["cached_tokens"] == 20


@pytest.mark.asyncio
async def test_cost_absent_is_none_not_error():
    from llm_council.openrouter import query_model

    usage = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
    with (
        patch("llm_council.openrouter.OPENROUTER_API_KEY", "test-key"),
        patch("httpx.AsyncClient") as mock_client,
    ):
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=_ok_response(usage)
        )
        result = await query_model("openai/gpt-4o", [{"role": "user", "content": "hi"}])

    # query_model passes usage through; cost is None when the API omits it.
    assert result is not None
    assert result["usage"]["cost"] is None
    assert result["usage"]["cached_tokens"] == 0
