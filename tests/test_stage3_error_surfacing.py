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


class TestErrorDetailIsNeverEmpty:
    """#594: the detail was surfaced correctly but arrived empty.

    Observed live on 2026-07-16 during a chairman outage. stage3.json held:

        "response": "Error: Unable to generate final synthesis (error: )",
        "error_status": "error",
        "error_detail": ""

    7 seconds, zero tokens — a provider-boundary error, not a slow generation.
    `council_stages` does the right thing (`status_response.get("error",
    "no detail returned")`), but the default never fires because the value is
    present-and-empty rather than missing. The empty string is produced
    upstream: `query_model_with_status`'s generic handler returns `str(e)`,
    which is `""` for any exception constructed without a message.

    #397 added the status-preserving variant so a billing outage could be told
    from a dead model; #403 added `unclear_reason=infra_failure` for the same
    goal. An empty detail defeats both.
    """

    @pytest.mark.asyncio
    async def test_message_less_exception_still_yields_a_detail(self):
        """`str(IndexError())` is `""` — the exact shape that shipped empty."""
        import httpx
        from unittest.mock import patch
        from llm_council.openrouter import query_model_with_status, STATUS_ERROR

        with (
            patch("llm_council.openrouter._get_openrouter_api_key", return_value="k"),
            patch.object(
                httpx.AsyncClient, "post", side_effect=IndexError()
            ),
        ):
            result = await query_model_with_status("m/a", [{"role": "user", "content": "q"}])

        assert result["status"] == STATUS_ERROR
        detail = result.get("error", "")
        assert detail, "error detail is empty — the #594 bug"
        assert "IndexError" in detail, (
            f"detail must name the exception type to be diagnosable; got {detail!r}"
        )

    @pytest.mark.asyncio
    async def test_exception_with_message_keeps_its_message(self):
        """The common case must not regress into type-only output."""
        import httpx
        from unittest.mock import patch
        from llm_council.openrouter import query_model_with_status

        with (
            patch("llm_council.openrouter._get_openrouter_api_key", return_value="k"),
            patch.object(
                httpx.AsyncClient, "post", side_effect=RuntimeError("upstream 502")
            ),
        ):
            result = await query_model_with_status("m/a", [{"role": "user", "content": "q"}])

        assert "upstream 502" in result["error"]
        assert "RuntimeError" in result["error"]

    @pytest.mark.asyncio
    async def test_failure_is_logged_not_printed(self, caplog):
        """A bare `print` in a library call path is unroutable and untestable."""
        import httpx
        from unittest.mock import patch
        from llm_council.openrouter import query_model_with_status

        with (
            patch("llm_council.openrouter._get_openrouter_api_key", return_value="k"),
            patch.object(
                httpx.AsyncClient, "post", side_effect=RuntimeError("upstream 502")
            ),
            caplog.at_level("WARNING"),
        ):
            await query_model_with_status("m/a", [{"role": "user", "content": "q"}])

        logged = " ".join(r.message for r in caplog.records)
        assert "upstream 502" in logged, f"failure not logged; records={caplog.records!r}"

    @pytest.mark.asyncio
    async def test_stage3_never_renders_empty_parentheses(self, monkeypatch):
        """End-to-end: the operator-facing string the outage actually showed."""
        async def message_less_failure(model, messages, disable_tools=False, timeout=120.0, **kw):
            # What the pre-fix openrouter handler returned for `IndexError()`.
            return {"status": "error", "error": "", "latency_ms": 6944}

        monkeypatch.setattr(council_mod, "query_model_with_status", message_less_failure)
        result, _usage, _ = await council_mod.stage3_synthesize_final(
            "q", _stage1(), _stage2(), _agg()
        )

        assert "(error: )" not in result["response"], (
            f"empty parens are the #594 symptom; got {result['response']!r}"
        )
        assert result["error_detail"], "error_detail must never be empty"
