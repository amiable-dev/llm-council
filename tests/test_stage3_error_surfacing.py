"""Stage-3 chairman failures must surface the underlying error (#397).

During the 2026-07-02 OpenRouter billing outage, every chairman call failed in
~70–260ms but verify only showed 'Error: Unable to generate final synthesis.'
— the 402 was swallowed (query_model collapses all failures to None), so a
billing outage was misdiagnosed as a dead model. Stage 3 must report status +
error detail on failure.
"""

import pytest

from llm_council import council_stages as council_mod


def _failure_status(status="auth_error", error="Payment required (402): insufficient credits"):
    async def fake(model, messages, disable_tools=False, timeout=120.0, **kw):
        return {"status": status, "error": error, "latency_ms": 81}

    return fake


def _ok_status(content="SYNTHESIS: all good"):
    async def fake(model, messages, disable_tools=False, timeout=120.0, **kw):
        return {
            "status": "ok",
            "content": content,
            "latency_ms": 900,
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }

    return fake


def _stage1():
    return [{"model": "m1", "response": "a"}, {"model": "m2", "response": "b"}]


def _stage2():
    return [
        {"model": "m1", "ranking": "1. Response A", "parsed_ranking": {"ranking": ["Response A"]}}
    ]


def _agg():
    return [{"model": "m1", "borda_score": 1.0, "rank": 1, "vote_count": 1}]


@pytest.mark.asyncio
async def test_failure_surfaces_status_and_detail(monkeypatch):
    monkeypatch.setattr(council_mod, "query_model_with_status", _failure_status())
    result, usage, verdict = await council_mod.stage3_synthesize_final(
        "q", _stage1(), _stage2(), _agg()
    )
    text = result["response"]
    # Backward-compatible prefix retained…
    assert text.startswith("Error: Unable to generate final synthesis")
    # …but the status and the underlying error are now visible.
    assert "auth_error" in text
    assert "402" in text
    # And structured fields for programmatic consumers.
    assert result["error_status"] == "auth_error"
    assert "402" in result["error_detail"]


@pytest.mark.asyncio
async def test_timeout_failure_names_timeout(monkeypatch):
    monkeypatch.setattr(
        council_mod,
        "query_model_with_status",
        _failure_status(status="timeout", error="Timeout after 90.0s"),
    )
    result, usage, verdict = await council_mod.stage3_synthesize_final(
        "q", _stage1(), _stage2(), _agg()
    )
    assert result["error_status"] == "timeout"
    assert "Timeout" in result["response"]
    assert result["error_detail"] == "Timeout after 90.0s"


@pytest.mark.asyncio
async def test_success_path_unchanged(monkeypatch):
    monkeypatch.setattr(council_mod, "query_model_with_status", _ok_status())
    result, usage, verdict = await council_mod.stage3_synthesize_final(
        "q", _stage1(), _stage2(), _agg()
    )
    assert result["response"] == "SYNTHESIS: all good"
    assert "error_status" not in result
    assert usage["prompt_tokens"] == 10
