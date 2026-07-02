"""query_models_with_progress forwards reasoning_params (ADR-026, #365)."""

import pytest

from llm_council.gateway.types import ReasoningParams
from llm_council.openrouter import query_models_with_progress


@pytest.mark.asyncio
async def test_forwards_reasoning_params_to_each_model(monkeypatch):
    rp = ReasoningParams(effort="high", max_tokens=1000)
    captured = {}

    async def _fake_status(model, messages, timeout=120.0, disable_tools=False, reasoning_params=None):
        captured[model] = reasoning_params
        return {"status": "ok", "content": "x", "latency_ms": 1, "usage": {}}

    monkeypatch.setattr("llm_council.openrouter.query_model_with_status", _fake_status)
    await query_models_with_progress(
        ["m1", "m2"], [{"role": "user", "content": "hi"}], reasoning_params=rp
    )
    assert captured == {"m1": rp, "m2": rp}


@pytest.mark.asyncio
async def test_none_reasoning_params_still_works(monkeypatch):
    captured = {}

    async def _fake_status(model, messages, timeout=120.0, disable_tools=False, reasoning_params=None):
        captured[model] = reasoning_params
        return {"status": "ok", "content": "x", "latency_ms": 1, "usage": {}}

    monkeypatch.setattr("llm_council.openrouter.query_model_with_status", _fake_status)
    await query_models_with_progress(["m1"], [{"role": "user", "content": "hi"}])
    assert captured["m1"] is None
