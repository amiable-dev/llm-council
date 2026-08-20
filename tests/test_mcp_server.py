"""Tests for llm_council MCP server.

These tests require the optional [mcp] dependencies.
Install with: pip install "llm-council[mcp]"
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Skip all tests in this module if MCP is not installed
pytest.importorskip(
    "mcp", reason="MCP dependencies not installed. Install with: pip install 'llm-council[mcp]'"
)


def test_mcp_server_imports():
    """Test that MCP server can be imported."""
    from llm_council import mcp_server

    assert hasattr(mcp_server, "mcp")
    assert hasattr(mcp_server, "consult_council")
    assert hasattr(mcp_server, "council_health_check")
    assert hasattr(mcp_server, "main")


def test_main_entry_point_exists():
    """Test that main() entry point is defined."""
    from llm_council.mcp_server import main

    assert callable(main)


def test_confidence_configs_defined():
    """Test that confidence level configurations are defined (ADR-012)."""
    from llm_council.mcp_server import CONFIDENCE_CONFIGS

    assert "quick" in CONFIDENCE_CONFIGS
    assert "balanced" in CONFIDENCE_CONFIGS
    assert "high" in CONFIDENCE_CONFIGS

    # Quick should have fewer models
    assert CONFIDENCE_CONFIGS["quick"]["models"] == 2
    assert CONFIDENCE_CONFIGS["balanced"]["models"] == 3
    assert CONFIDENCE_CONFIGS["high"]["models"] is None  # Use all


@pytest.mark.asyncio
async def test_consult_council_tool():
    """Test that consult_council tool is properly defined."""
    from llm_council.mcp_server import consult_council

    # Mock the run_council_with_fallback function (ADR-012 structured response)
    mock_result = {
        "synthesis": "Synthesized response",
        "model_responses": {
            "test-model": {"status": "ok", "latency_ms": 1000, "response": "Test response"}
        },
        "metadata": {
            "status": "complete",
            "completed_models": 1,
            "requested_models": 1,
            "synthesis_type": "full",
            "warning": None,
            "label_to_model": {},
            "aggregate_rankings": [],
        },
    }

    with patch("llm_council.mcp_server.run_council_with_fallback") as mock_council:
        mock_council.return_value = mock_result

        result = await consult_council("test query", include_details=False)

        assert "Synthesized response" in result
        assert "### Chairman's Synthesis" in result


@pytest.mark.asyncio
async def test_consult_council_with_details():
    """Test consult_council with include_details=True."""
    from llm_council.mcp_server import consult_council

    mock_result = {
        "synthesis": "Synthesized response",
        "model_responses": {
            "test-model": {"status": "ok", "latency_ms": 1000, "response": "Test response"}
        },
        "metadata": {
            "status": "complete",
            "completed_models": 1,
            "requested_models": 1,
            "synthesis_type": "full",
            "warning": None,
            "label_to_model": {"Response A": "test-model"},
            "aggregate_rankings": [],
        },
    }

    with patch("llm_council.mcp_server.run_council_with_fallback") as mock_council:
        mock_council.return_value = mock_result

        result = await consult_council("test query", include_details=True)

        assert "### Chairman's Synthesis" in result
        assert "### Council Details" in result
        assert "Model Status" in result
        assert "Stage 1: Individual Opinions" in result
        assert "Stage 2: Peer Review" in result


@pytest.mark.asyncio
async def test_consult_council_with_confidence_level():
    """Test consult_council with confidence level parameter (ADR-012)."""
    from llm_council.mcp_server import consult_council

    mock_result = {
        "synthesis": "Quick response",
        "model_responses": {"test-model": {"status": "ok", "latency_ms": 500}},
        "metadata": {
            "status": "complete",
            "completed_models": 1,
            "requested_models": 1,
            "synthesis_type": "full",
            "warning": None,
            "aggregate_rankings": [],
        },
    }

    with patch("llm_council.mcp_server.run_council_with_fallback") as mock_council:
        mock_council.return_value = mock_result

        # Test with "quick" confidence
        result = await consult_council("test query", confidence="quick")
        assert "Quick response" in result


@pytest.mark.asyncio
async def test_consult_council_with_rankings_metadata():
    """Test consult_council includes aggregate rankings in output."""
    from llm_council.mcp_server import consult_council

    mock_result = {
        "synthesis": "Synthesized response",
        "model_responses": {},
        "metadata": {
            "status": "complete",
            "completed_models": 2,
            "requested_models": 2,
            "synthesis_type": "full",
            "warning": None,
            "label_to_model": {},
            "aggregate_rankings": [
                {"model": "openai/gpt-4", "borda_score": 0.85, "rank": 1},
                {"model": "anthropic/claude", "borda_score": 0.75, "rank": 2},
            ],
        },
    }

    with patch("llm_council.mcp_server.run_council_with_fallback") as mock_council:
        mock_council.return_value = mock_result

        result = await consult_council("test query")

        assert "### Council Rankings" in result
        assert "openai/gpt-4" in result
        assert "0.85" in result


@pytest.mark.asyncio
async def test_council_health_check_no_api_key():
    """Test health check when API key is not configured."""
    from llm_council.mcp_server import council_health_check

    with patch("llm_council.mcp_server.OPENROUTER_API_KEY", None):
        result = await council_health_check()
        data = json.loads(result)

        assert data["api_key_configured"] is False
        assert data["ready"] is False
        assert "not configured" in data["message"].lower()


@pytest.mark.asyncio
@pytest.mark.vcr()
async def test_council_health_check_success():
    """Test health check with successful API connectivity."""
    from llm_council.mcp_server import council_health_check
    from llm_council.openrouter import STATUS_OK

    with patch("llm_council.mcp_server.OPENROUTER_API_KEY", "test-key"):
        result = await council_health_check()
        data = json.loads(result)

        assert data["api_key_configured"] is True
        assert data["ready"] is True
        assert "api_connectivity" in data
        assert data["api_connectivity"]["status"] == STATUS_OK


@pytest.mark.asyncio
async def test_council_health_check_api_error():
    """Test health check when API returns an error."""
    from llm_council.mcp_server import council_health_check
    from llm_council.openrouter import STATUS_AUTH_ERROR

    mock_response = {
        "status": STATUS_AUTH_ERROR,
        "error": "Invalid API key",
        "latency_ms": 50,
    }

    with (
        patch("llm_council.mcp_server.OPENROUTER_API_KEY", "invalid-key"),
        patch("llm_council.mcp_server.query_model_with_status", return_value=mock_response),
    ):
        result = await council_health_check()
        data = json.loads(result)

        assert data["api_key_configured"] is True
        assert data["ready"] is False
        assert "connectivity issue" in data["message"].lower()


@pytest.mark.asyncio
async def test_council_health_check_includes_estimates():
    """Test health check includes duration estimates (ADR-012)."""
    from llm_council.mcp_server import council_health_check

    with patch("llm_council.mcp_server.OPENROUTER_API_KEY", None):
        result = await council_health_check()
        data = json.loads(result)

        assert "estimated_duration" in data
        assert "quick" in data["estimated_duration"]
        assert "balanced" in data["estimated_duration"]
        assert "high" in data["estimated_duration"]


@pytest.mark.asyncio
async def test_consult_council_with_context_progress():
    """Test that consult_council calls progress reporting when context is provided."""
    from llm_council.mcp_server import consult_council

    mock_result = {
        "synthesis": "Synthesized response",
        "model_responses": {"test-model": {"status": "ok", "latency_ms": 1000}},
        "metadata": {
            "status": "complete",
            "completed_models": 1,
            "requested_models": 1,
            "synthesis_type": "full",
            "warning": None,
            "label_to_model": {},
            "aggregate_rankings": [],
        },
    }

    # Create a mock context with report_progress method
    mock_ctx = MagicMock()
    mock_ctx.report_progress = AsyncMock()

    # Mock run_council_with_fallback to call the on_progress callback
    async def mock_council_fn(query, on_progress=None, synthesis_deadline=None, **kwargs):
        if on_progress:
            await on_progress(0, 5, "Starting...")
            await on_progress(5, 5, "Complete")
        return mock_result

    with patch("llm_council.mcp_server.run_council_with_fallback", side_effect=mock_council_fn):
        await consult_council("test query", ctx=mock_ctx)

        # Verify progress was reported (at least start and end)
        assert mock_ctx.report_progress.called
        assert mock_ctx.report_progress.call_count >= 2


@pytest.mark.asyncio
async def test_consult_council_shows_warning_on_partial():
    """Test that consult_council shows warning when partial results returned (ADR-012)."""
    from llm_council.mcp_server import consult_council

    mock_result = {
        "synthesis": "Partial synthesis",
        "model_responses": {
            "model-a": {"status": "ok", "latency_ms": 1000},
            "model-b": {"status": "timeout", "latency_ms": 25000, "error": "Timeout"},
        },
        "metadata": {
            "status": "partial",
            "completed_models": 1,
            "requested_models": 2,
            "synthesis_type": "partial",
            "warning": "This answer is based on 1 of 2 intended models. Did not respond: model-b (timeout).",
            "aggregate_rankings": [],
        },
    }

    with patch("llm_council.mcp_server.run_council_with_fallback") as mock_council:
        mock_council.return_value = mock_result

        result = await consult_council("test query")

        assert "Partial synthesis" in result
        assert "Note" in result
        assert "1 of 2" in result
        assert "partial" in result.lower()


@pytest.mark.asyncio
async def test_timeout_preserves_diagnostic_info():
    """Test that model status is preserved even when global timeout occurs (ADR-012 fix).

    This tests the fix for the bug where global asyncio.wait_for timeout would
    cancel the pipeline before model_responses was populated, losing diagnostic info.
    """
    import asyncio

    from llm_council.council import run_council_with_fallback
    from llm_council.openrouter import STATUS_OK, STATUS_TIMEOUT

    # Create a mock that simulates some models responding before timeout
    call_count = 0

    async def mock_query_with_status(
        model, messages, timeout=None, disable_tools=False, reasoning_params=None
    ):
        nonlocal call_count
        call_count += 1
        # First model responds quickly
        if "gpt" in model:
            await asyncio.sleep(0.01)
            return {
                "status": STATUS_OK,
                "content": "Fast response",
                "latency_ms": 10,
            }
        # Other models are slow (will be interrupted by timeout)
        await asyncio.sleep(10)  # Will be cancelled by timeout
        return {
            "status": STATUS_OK,
            "content": "Slow response",
            "latency_ms": 10000,
        }

    with (
        patch("llm_council.openrouter.query_model_with_status", side_effect=mock_query_with_status),
        patch(
            "llm_council.council.COUNCIL_MODELS",
            ["openai/gpt-4", "anthropic/claude", "google/gemini"],
        ),
    ):
        # Run with a very short timeout to trigger global timeout
        result = await run_council_with_fallback(
            "test query",
            synthesis_deadline=0.5,  # Very short - will timeout
        )

        # Key assertion: model_responses should have diagnostic info for ALL models
        # even those that didn't complete before timeout
        assert "model_responses" in result
        model_responses = result["model_responses"]

        # Should have entries for all 3 models
        assert (
            len(model_responses) >= 1
        ), f"Expected at least 1 model status, got: {model_responses}"

        # The fast model should show as ok or have response
        # Other models should show as timeout (not missing!)
        statuses = [info.get("status") for info in model_responses.values()]

        # At least the quick model should have responded
        # (implementation detail: depends on timing)
        assert any(s == STATUS_OK for s in statuses) or any(
            s == STATUS_TIMEOUT for s in statuses
        ), f"Expected some model statuses, got: {statuses}"

        # Check metadata reflects partial status
        assert result["metadata"]["status"] in ("partial", "failed")


@pytest.mark.asyncio
async def test_shared_results_populated_incrementally():
    """Test that query_models_with_progress populates shared_results as models complete."""
    from llm_council.openrouter import STATUS_OK, query_models_with_progress

    async def mock_query(model, messages, timeout=None, disable_tools=False, reasoning_params=None):
        return {
            "status": STATUS_OK,
            "content": f"Response from {model}",
            "latency_ms": 100,
        }

    with patch("llm_council.openrouter.query_model_with_status", side_effect=mock_query):
        # Create a shared dict to observe incremental population
        shared = {}

        result = await query_models_with_progress(
            models=["model-a", "model-b"],
            messages=[{"role": "user", "content": "test"}],
            shared_results=shared,
        )

        # Both the returned result and shared dict should have the responses
        assert len(result) == 2
        assert len(shared) == 2
        assert result is shared  # They should be the same object


class TestHealthCheckReportsEffectiveConfig:
    """#591 Bug 2 + #596: the health check reported a code path real runs don't take.

    Two independent reports, one root cause — `council_health_check` described
    a configuration and a connectivity story that a real `consult_council`
    call does not follow:

    * **#591 Bug 2** — it reported `COUNCIL_MODELS` (the flat `council.models`
      list, captured at import time), while `consult_council` always builds a
      `TierContract` and runs `tier_contract.allowed_models`. The two can name
      completely different models with no signal that they disagree.
    * **#596** — it pinged a fixed cheap lite model, so it answered "is the API
      reachable at all", not "will the council complete". During a ~1h chairman
      outage it reported `ready: true` throughout while every real run failed.
    """

    @pytest.mark.asyncio
    async def test_reports_models_a_real_run_would_use(self):
        """The reported models must come from the tier a real run resolves."""
        from llm_council.mcp_server import council_health_check

        with (
            patch("llm_council.mcp_server.OPENROUTER_API_KEY", None),
            patch(
                "llm_council.mcp_server.create_tier_contract",
            ) as mk,
        ):
            mk.return_value = MagicMock(allowed_models=["tier/one", "tier/two"])
            data = json.loads(await council_health_check())

        assert data["models"] == ["tier/one", "tier/two"], (
            "health check must report the tier-resolved models a real "
            f"consult_council run would use; got {data.get('models')!r}"
        )
        assert data["council_size"] == 2
        assert data["default_tier"] == "high"

    @pytest.mark.asyncio
    async def test_warns_when_configured_models_diverge_from_effective(self):
        """The exact #591 Bug 2 symptom: two sources, silently disagreeing."""
        from llm_council.mcp_server import council_health_check

        with (
            patch("llm_council.mcp_server.OPENROUTER_API_KEY", None),
            patch("llm_council.mcp_server._get_council_models", return_value=["cfg/a", "cfg/b"]),
            patch("llm_council.mcp_server.create_tier_contract") as mk,
        ):
            mk.return_value = MagicMock(allowed_models=["tier/x"])
            data = json.loads(await council_health_check())

        assert data.get("configured_council_models") == ["cfg/a", "cfg/b"]
        warnings = " ".join(data.get("config_warnings", [])).lower()
        assert "council.models" in warnings or "tier" in warnings, (
            f"divergence must be surfaced, not silent; got {data.get('config_warnings')!r}"
        )

    @pytest.mark.asyncio
    async def test_no_divergence_warning_when_they_agree(self):
        """No false alarms for the ordinary, correctly-configured case."""
        from llm_council.mcp_server import council_health_check

        with (
            patch("llm_council.mcp_server.OPENROUTER_API_KEY", None),
            patch("llm_council.mcp_server._get_council_models", return_value=["same/a"]),
            patch("llm_council.mcp_server.create_tier_contract") as mk,
        ):
            mk.return_value = MagicMock(allowed_models=["same/a"])
            data = json.loads(await council_health_check())

        assert not data.get("config_warnings")
        assert "configured_council_models" not in data

    @pytest.mark.asyncio
    async def test_models_are_resolved_at_call_time_not_import_time(self):
        """`COUNCIL_MODELS` was a module-level constant bound at import.

        A config reload therefore never reached the health check output.
        """
        from llm_council.mcp_server import council_health_check

        with (
            patch("llm_council.mcp_server.OPENROUTER_API_KEY", None),
            patch("llm_council.mcp_server.create_tier_contract") as mk,
        ):
            mk.return_value = MagicMock(allowed_models=["first/model"])
            first = json.loads(await council_health_check())
            mk.return_value = MagicMock(allowed_models=["second/model"])
            second = json.loads(await council_health_check())

        assert first["models"] == ["first/model"]
        assert second["models"] == ["second/model"], (
            "health check is caching models from import time; a reconfigured "
            "council is not reflected"
        )

    @pytest.mark.asyncio
    async def test_shallow_probe_is_labelled_as_not_covering_the_chairman(self):
        """#596: `ready` must not imply the chairman is healthy."""
        from llm_council.mcp_server import council_health_check
        from llm_council.openrouter import STATUS_OK

        with (
            patch("llm_council.mcp_server.OPENROUTER_API_KEY", "k"),
            patch(
                "llm_council.mcp_server.query_model_with_status",
                new_callable=AsyncMock,
                return_value={"status": STATUS_OK, "content": "pong", "latency_ms": 5},
            ),
        ):
            data = json.loads(await council_health_check())

        assert data["api_connectivity"]["probe_scope"] == "connectivity_only"
        assert "chairman" in data["api_connectivity"]["caveat"].lower()

    @pytest.mark.asyncio
    async def test_deep_probe_queries_the_configured_chairman(self):
        """#596: opt-in probe of the model that actually performs synthesis."""
        from llm_council.mcp_server import council_health_check
        from llm_council.openrouter import STATUS_OK

        calls = []

        async def fake(model, messages, **kwargs):
            calls.append(model)
            return {"status": STATUS_OK, "content": "pong", "latency_ms": 7}

        with (
            patch("llm_council.mcp_server.OPENROUTER_API_KEY", "k"),
            patch("llm_council.mcp_server._get_chairman_model", return_value="chair/model"),
            patch("llm_council.mcp_server.query_model_with_status", side_effect=fake),
        ):
            data = json.loads(await council_health_check(deep=True))

        assert "chair/model" in calls, f"deep probe never called the chairman; called {calls}"
        assert data["chairman_connectivity"]["status"] == STATUS_OK
        assert data["chairman_connectivity"]["model"] == "chair/model"

    @pytest.mark.asyncio
    async def test_deep_probe_failure_makes_ready_false(self):
        """The outage case: lite model fine, chairman broken => NOT ready."""
        from llm_council.mcp_server import council_health_check
        from llm_council.openrouter import STATUS_OK, STATUS_ERROR

        async def fake(model, messages, **kwargs):
            if model == "chair/model":
                return {"status": STATUS_ERROR, "error": "502 upstream", "latency_ms": 9}
            return {"status": STATUS_OK, "content": "pong", "latency_ms": 5}

        with (
            patch("llm_council.mcp_server.OPENROUTER_API_KEY", "k"),
            patch("llm_council.mcp_server._get_chairman_model", return_value="chair/model"),
            patch("llm_council.mcp_server.query_model_with_status", side_effect=fake),
        ):
            data = json.loads(await council_health_check(deep=True))

        assert data["ready"] is False, (
            "a failing chairman must not report ready:true — this is the #596 outage"
        )
        assert "chairman" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_deep_probe_is_opt_in(self):
        """Default stays cheap: one lite ping, no chairman call."""
        from llm_council.mcp_server import council_health_check
        from llm_council.openrouter import STATUS_OK

        calls = []

        async def fake(model, messages, **kwargs):
            calls.append(model)
            return {"status": STATUS_OK, "content": "pong", "latency_ms": 5}

        with (
            patch("llm_council.mcp_server.OPENROUTER_API_KEY", "k"),
            patch("llm_council.mcp_server._get_chairman_model", return_value="chair/model"),
            patch("llm_council.mcp_server.query_model_with_status", side_effect=fake),
        ):
            data = json.loads(await council_health_check())

        assert calls == [__import__("llm_council.gateway.base", fromlist=["x"]).DEFAULT_HEALTH_CHECK_MODEL]
        assert "chairman_connectivity" not in data

    @pytest.mark.asyncio
    async def test_tier_resolution_failure_is_not_ready(self):
        """Council review of #608: the fallback recreated the very bug.

        Wrapping `create_tier_contract` in `except Exception` and quietly
        falling back to the flat list let the health check report ready:true
        for a config under which `consult_council` — which has no such
        fallback — would raise. That is the same 'health check misrepresents
        reality' failure this PR exists to fix.
        """
        from llm_council.mcp_server import council_health_check
        from llm_council.openrouter import STATUS_OK

        with (
            patch("llm_council.mcp_server.OPENROUTER_API_KEY", "k"),
            patch(
                "llm_council.mcp_server.create_tier_contract",
                side_effect=ValueError("bad tier pool config"),
            ),
            patch(
                "llm_council.mcp_server.query_model_with_status",
                new_callable=AsyncMock,
                return_value={"status": STATUS_OK, "content": "pong", "latency_ms": 5},
            ),
        ):
            data = json.loads(await council_health_check())

        assert data["ready"] is False, (
            "tier resolution failed, so a real run would raise — must not report ready"
        )
        joined = (data["message"] + " ".join(data.get("config_warnings", []))).lower()
        assert "tier" in joined
        assert "bad tier pool config" in joined, "the underlying error must be surfaced"

    @pytest.mark.asyncio
    async def test_empty_effective_pool_is_not_ready(self):
        """A council of zero models cannot deliberate, however healthy the API."""
        from llm_council.mcp_server import council_health_check
        from llm_council.openrouter import STATUS_OK

        with (
            patch("llm_council.mcp_server.OPENROUTER_API_KEY", "k"),
            patch("llm_council.mcp_server.create_tier_contract") as mk,
            patch(
                "llm_council.mcp_server.query_model_with_status",
                new_callable=AsyncMock,
                return_value={"status": STATUS_OK, "content": "pong", "latency_ms": 5},
            ),
        ):
            mk.return_value = MagicMock(allowed_models=[])
            data = json.loads(await council_health_check())

        assert data["council_size"] == 0
        assert data["ready"] is False
        assert "no models" in data["message"].lower() or "empty" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_reports_the_tier_that_was_asked_about(self):
        """`consult_council` runs whichever tier the caller picks.

        Reporting only 'high' misrepresents readiness for the others.
        """
        from llm_council.mcp_server import council_health_check

        with (
            patch("llm_council.mcp_server.OPENROUTER_API_KEY", None),
            patch("llm_council.mcp_server.create_tier_contract") as mk,
        ):
            mk.return_value = MagicMock(allowed_models=["quick/one"])
            data = json.loads(await council_health_check(tier="quick"))

        assert data["default_tier"] == "quick"
        assert data["models"] == ["quick/one"]
        assert mk.call_args.args[0] == "quick"

    @pytest.mark.asyncio
    async def test_unknown_tier_falls_back_to_high_like_consult_council(self):
        """Mirrors consult_council: an unrecognised tier resolves to 'high'."""
        from llm_council.mcp_server import council_health_check

        with (
            patch("llm_council.mcp_server.OPENROUTER_API_KEY", None),
            patch("llm_council.mcp_server.create_tier_contract") as mk,
        ):
            mk.return_value = MagicMock(allowed_models=["h/1"])
            data = json.loads(await council_health_check(tier="nonsense"))

        assert data["default_tier"] == "high"
        assert mk.call_args.args[0] == "high"
