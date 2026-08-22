"""#648: consult-path stage 2/3 budgets must be tier-aware (ADR-012 / ADR-040).

TDD: tests written first.

The consult orchestrators called ``stage2_collect_rankings`` and
``stage3_synthesize_final`` WITHOUT a ``timeout`` argument, so both ran at
their own hard-coded 120s defaults regardless of tier — and
``LLM_COUNCIL_TIMEOUT_MULTIPLIER``, which feeds ``timeouts.multiplier`` and
therefore ``TierContract.per_model_timeout_ms``, never reached either stage.
Latent until the 0.45.0 chairman moved to ``anthropic/claude-opus-5`` (#635),
which reliably exceeds 120s on a reasoning-tier synthesis.

ADR-040 fixed this class of bug on the verify path (#545). These tests pin the
consult path.

Budget policy (#648): ``max(per_model_timeout, TIMEOUT_STAGE_FLOOR)``. The
tier value raises the budget; the 120s floor guarantees the fix can never
SHRINK a stage below the historical default (high tier's per_model is 90s and
balanced's is 45s — capping at per_model would have created fresh instances of
the very failure being fixed). The global ``synthesis_deadline`` wait_for
remains the outer bound.
"""

import inspect
import os
from unittest.mock import AsyncMock, patch

import pytest


# =============================================================================
# The budget helper
# =============================================================================


class TestResolveStageTimeout:
    """``resolve_stage_timeout`` derives a stage budget from the tier value."""

    def test_tier_value_wins_when_above_floor(self):
        from llm_council.council_usage import resolve_stage_timeout

        assert resolve_stage_timeout(300.0) == 300.0

    def test_floor_wins_when_tier_value_below_it(self):
        """high=90s and balanced=45s must NOT shrink stage 2/3 below 120s."""
        from llm_council.council_usage import TIMEOUT_STAGE_FLOOR, resolve_stage_timeout

        assert resolve_stage_timeout(90.0) == TIMEOUT_STAGE_FLOOR
        assert resolve_stage_timeout(45.0) == TIMEOUT_STAGE_FLOOR

    def test_floor_is_the_historical_default(self):
        """The floor must equal the old hard-coded default (byte-identical)."""
        from llm_council.council_stages import stage2_collect_rankings, stage3_synthesize_final
        from llm_council.council_usage import TIMEOUT_STAGE_FLOOR

        assert TIMEOUT_STAGE_FLOOR == 120.0
        assert inspect.signature(stage3_synthesize_final).parameters["timeout"].default == 120.0
        assert inspect.signature(stage2_collect_rankings).parameters["timeout"].default == 120.0

    @pytest.mark.parametrize("bad", [None, 0, 0.0, -1.0])
    def test_missing_or_nonpositive_falls_back_to_floor(self, bad):
        """A misconfigured tier must not produce a zero/negative budget."""
        from llm_council.council_usage import TIMEOUT_STAGE_FLOOR, resolve_stage_timeout

        assert resolve_stage_timeout(bad) == TIMEOUT_STAGE_FLOOR

    def test_nan_does_not_propagate_through_the_floor(self):
        """max(nan, 120.0) is nan in CPython — the guard must be explicit.

        asyncio.wait_for(timeout=nan) is not a 120s budget, so a NaN slipping
        through would silently defeat the floor the whole fix rests on.
        """
        from llm_council.council_usage import TIMEOUT_STAGE_FLOOR, resolve_stage_timeout

        assert max(float("nan"), TIMEOUT_STAGE_FLOOR) != TIMEOUT_STAGE_FLOOR  # the trap
        assert resolve_stage_timeout(float("nan")) == TIMEOUT_STAGE_FLOOR

    @pytest.mark.parametrize("bad", [float("inf"), float("-inf")])
    def test_infinities_fall_back_to_floor(self, bad):
        from llm_council.council_usage import TIMEOUT_STAGE_FLOOR, resolve_stage_timeout

        assert resolve_stage_timeout(bad) == TIMEOUT_STAGE_FLOOR

    def test_non_numeric_falls_back_to_floor(self):
        """The helper documents a fallback, so it must not raise on garbage."""
        from llm_council.council_usage import TIMEOUT_STAGE_FLOOR, resolve_stage_timeout

        assert resolve_stage_timeout("not-a-number") == TIMEOUT_STAGE_FLOOR

    @pytest.mark.parametrize("ms_value", [45_000.0, 90_000.0, 300_000.0])
    def test_millisecond_slip_is_rejected_not_trusted(self, ms_value):
        """A raw TierContract._ms field must not become a multi-hour budget.

        The argument is SECONDS. Passing per_model_timeout_ms would yield a
        300,000s (3.5-day) budget — i.e. silently disable the stage timeout.
        A unit slip is always a bug, so it lands on the floor.
        """
        from llm_council.council_usage import TIMEOUT_STAGE_FLOOR, resolve_stage_timeout

        assert resolve_stage_timeout(ms_value) == TIMEOUT_STAGE_FLOOR

    def test_largest_legitimate_configuration_is_accepted(self):
        """The ceiling must not clip a real config: reasoning 300s x max 10.0."""
        from llm_council.council_usage import _MAX_STAGE_TIMEOUT, resolve_stage_timeout

        assert resolve_stage_timeout(3000.0) == 3000.0
        assert _MAX_STAGE_TIMEOUT >= 3000.0

    def test_ceiling_boundary_is_inclusive(self):
        """Exactly _MAX_STAGE_TIMEOUT is accepted; just above it is rejected.

        Rejection goes to the FLOOR, not to the ceiling: above this line the
        value is a unit slip, and 120s is the safe reading of a slip. Pinned
        because the difference is a silent, large downgrade (#650 gate).
        """
        from llm_council.council_usage import (
            _MAX_STAGE_TIMEOUT,
            TIMEOUT_STAGE_FLOOR,
            resolve_stage_timeout,
        )

        assert resolve_stage_timeout(_MAX_STAGE_TIMEOUT) == _MAX_STAGE_TIMEOUT
        assert resolve_stage_timeout(_MAX_STAGE_TIMEOUT + 0.1) == TIMEOUT_STAGE_FLOOR

    def test_overflowing_value_falls_back_to_floor(self):
        """float() raises OverflowError on huge ints — the contract says fallback."""
        from llm_council.council_usage import TIMEOUT_STAGE_FLOOR, resolve_stage_timeout

        assert resolve_stage_timeout(10**400) == TIMEOUT_STAGE_FLOOR

    def test_rejection_is_logged_never_silent(self, caplog):
        """ADR-024 ethos: a downgrade must be auditable."""
        import logging

        from llm_council.council_usage import resolve_stage_timeout

        with caplog.at_level(logging.WARNING, logger="llm_council.council_usage"):
            resolve_stage_timeout(300_000.0)

        assert any("per_model_timeout_ms" in r.getMessage() for r in caplog.records)

    def test_reexported_from_council(self):
        """council.py re-exports moved names (ADR-046 P0 convention)."""
        import llm_council.council as council_module
        import llm_council.council_usage as source_module

        assert council_module.resolve_stage_timeout is source_module.resolve_stage_timeout
        assert council_module.TIMEOUT_STAGE_FLOOR == source_module.TIMEOUT_STAGE_FLOOR


class TestTierDerivedBudgets:
    """The helper composed with the real tier contracts."""

    def test_reasoning_tier_gets_its_full_per_model_budget(self):
        from llm_council.council_usage import resolve_stage_timeout
        from llm_council.tier_contract import create_tier_contract

        contract = create_tier_contract("reasoning")
        budget = resolve_stage_timeout(contract.per_model_timeout_ms / 1000)

        assert budget == 300.0
        assert budget > 120.0, "the reported regression: reasoning capped at 120s"

    def test_timeout_multiplier_reaches_the_stage_budget(self):
        """LLM_COUNCIL_TIMEOUT_MULTIPLIER=3 must scale the chairman budget."""
        from llm_council.council_usage import resolve_stage_timeout
        from llm_council.tier_contract import create_tier_contract
        from llm_council.unified_config import reload_config

        try:
            with patch.dict(os.environ, {"LLM_COUNCIL_TIMEOUT_MULTIPLIER": "3"}):
                reload_config()
                contract = create_tier_contract("reasoning")
                assert resolve_stage_timeout(contract.per_model_timeout_ms / 1000) == 900.0
        finally:
            # Must reload OUTSIDE patch.dict — a reload while the env var is
            # still patched would leave the multiplier in the process-wide
            # config and silently retime every later test.
            reload_config()


# =============================================================================
# run_council_with_fallback (facade + MCP consult_council)
# =============================================================================


def _stage1_stub(models):
    """(stage1_results, usage, model_statuses) for N models."""
    results = [{"model": m, "response": f"Answer from {m}"} for m in models]
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    statuses = {m: {"status": "ok", "latency_ms": 1, "response": r["response"]} for m, r in zip(models, results)}
    return results, usage, statuses


class TestRunCouncilWithFallbackPassesTierBudgets:
    @pytest.mark.asyncio
    async def test_stage3_receives_tier_derived_timeout(self):
        from llm_council.council import run_council_with_fallback
        from llm_council.tier_contract import create_tier_contract

        contract = create_tier_contract("reasoning")
        models = contract.allowed_models

        with (
            patch(
                "llm_council.council.stage1_collect_responses_with_status", new_callable=AsyncMock
            ) as mock_stage1,
            patch(
                "llm_council.council.stage1_5_normalize_styles", new_callable=AsyncMock
            ) as mock_stage1_5,
            patch(
                "llm_council.council.stage2_collect_rankings", new_callable=AsyncMock
            ) as mock_stage2,
            patch(
                "llm_council.council.stage3_synthesize_final", new_callable=AsyncMock
            ) as mock_stage3,
        ):
            stage1_results, usage, statuses = _stage1_stub(models)
            mock_stage1.return_value = (stage1_results, usage, statuses)
            mock_stage1_5.return_value = (stage1_results, usage)
            mock_stage2.return_value = ([], {}, usage)
            mock_stage3.return_value = ({"model": "chair", "response": "Final"}, usage, None)

            await run_council_with_fallback(
                "Test query",
                tier_contract=contract,
                synthesis_deadline=contract.deadline_ms / 1000,
                per_model_timeout=contract.per_model_timeout_ms / 1000,
            )

            assert mock_stage3.await_args.kwargs["timeout"] == 300.0

    @pytest.mark.asyncio
    async def test_stage2_receives_tier_derived_timeout(self):
        from llm_council.council import run_council_with_fallback
        from llm_council.tier_contract import create_tier_contract

        contract = create_tier_contract("reasoning")
        models = contract.allowed_models

        with (
            patch(
                "llm_council.council.stage1_collect_responses_with_status", new_callable=AsyncMock
            ) as mock_stage1,
            patch(
                "llm_council.council.stage1_5_normalize_styles", new_callable=AsyncMock
            ) as mock_stage1_5,
            patch(
                "llm_council.council.stage2_collect_rankings", new_callable=AsyncMock
            ) as mock_stage2,
            patch(
                "llm_council.council.stage3_synthesize_final", new_callable=AsyncMock
            ) as mock_stage3,
        ):
            stage1_results, usage, statuses = _stage1_stub(models)
            mock_stage1.return_value = (stage1_results, usage, statuses)
            mock_stage1_5.return_value = (stage1_results, usage)
            mock_stage2.return_value = ([], {}, usage)
            mock_stage3.return_value = ({"model": "chair", "response": "Final"}, usage, None)

            await run_council_with_fallback(
                "Test query",
                tier_contract=contract,
                synthesis_deadline=contract.deadline_ms / 1000,
                per_model_timeout=contract.per_model_timeout_ms / 1000,
            )

            assert mock_stage2.await_args.kwargs["timeout"] == 300.0

    @pytest.mark.asyncio
    async def test_default_call_keeps_the_120s_floor(self):
        """No tier ⇒ per_model default 25s must NOT shrink stage 2/3."""
        from llm_council.council import run_council_with_fallback

        models = ["m-a", "m-b", "m-c"]

        with (
            patch(
                "llm_council.council.stage1_collect_responses_with_status", new_callable=AsyncMock
            ) as mock_stage1,
            patch(
                "llm_council.council.stage1_5_normalize_styles", new_callable=AsyncMock
            ) as mock_stage1_5,
            patch(
                "llm_council.council.stage2_collect_rankings", new_callable=AsyncMock
            ) as mock_stage2,
            patch(
                "llm_council.council.stage3_synthesize_final", new_callable=AsyncMock
            ) as mock_stage3,
        ):
            stage1_results, usage, statuses = _stage1_stub(models)
            mock_stage1.return_value = (stage1_results, usage, statuses)
            mock_stage1_5.return_value = (stage1_results, usage)
            mock_stage2.return_value = ([], {}, usage)
            mock_stage3.return_value = ({"model": "chair", "response": "Final"}, usage, None)

            await run_council_with_fallback("Test query", models=models, synthesis_deadline=600)

            assert mock_stage2.await_args.kwargs["timeout"] == 120.0
            assert mock_stage3.await_args.kwargs["timeout"] == 120.0


class TestReasoningConsultRegression:
    """The reported failure, end-to-end through the real stage functions.

    A chairman that needs more than 120s must produce a real synthesis at
    reasoning tier instead of
    ``"Error: Unable to generate final synthesis (timeout: ...)"``.
    """

    @pytest.mark.asyncio
    async def test_slow_chairman_is_not_cut_off_at_120s(self):
        from llm_council.council import run_council_with_fallback
        from llm_council.tier_contract import create_tier_contract

        contract = create_tier_contract("reasoning")
        models = contract.allowed_models
        seen_timeouts = []

        async def fake_chairman(model, messages, disable_tools=False, timeout=120.0, **kwargs):
            # Stands in for a chairman whose synthesis takes ~150s: succeeds
            # only when its budget exceeds the old hard-coded default.
            seen_timeouts.append(timeout)
            if timeout < 150.0:
                return {
                    "status": "timeout",
                    "error": f"Timeout after {timeout}s",
                    "latency_ms": int(timeout * 1000),
                }
            return {"status": "ok", "content": "Synthesised answer", "usage": {}}

        with (
            patch(
                "llm_council.council.stage1_collect_responses_with_status", new_callable=AsyncMock
            ) as mock_stage1,
            patch(
                "llm_council.council.stage1_5_normalize_styles", new_callable=AsyncMock
            ) as mock_stage1_5,
            patch(
                "llm_council.council.stage2_collect_rankings", new_callable=AsyncMock
            ) as mock_stage2,
            patch("llm_council.council_stages.query_model_with_status", side_effect=fake_chairman),
        ):
            stage1_results, usage, statuses = _stage1_stub(models)
            mock_stage1.return_value = (stage1_results, usage, statuses)
            mock_stage1_5.return_value = (stage1_results, usage)
            mock_stage2.return_value = ([], {}, usage)

            result = await run_council_with_fallback(
                "Test query",
                tier_contract=contract,
                synthesis_deadline=contract.deadline_ms / 1000,
                per_model_timeout=contract.per_model_timeout_ms / 1000,
            )

        assert seen_timeouts == [300.0]
        assert "Unable to generate final synthesis" not in result["synthesis"]
        assert result["synthesis"] == "Synthesised answer"


# =============================================================================
# run_full_council (HTTP /council)
# =============================================================================


class TestRunFullCouncilTimeoutParameter:
    def test_accepts_per_model_timeout(self):
        from llm_council.council import run_full_council

        params = inspect.signature(run_full_council).parameters
        assert "per_model_timeout" in params
        assert params["per_model_timeout"].default is None

    def test_per_model_timeout_is_keyword_only(self):
        """A new positional parameter would silently rebind existing callers.

        run_full_council(query, bypass_cache, models) has positional callers in
        the wild; inserting anything ahead of them would bind the wrong value.
        """
        from llm_council.council import run_full_council

        param = inspect.signature(run_full_council).parameters["per_model_timeout"]
        assert param.kind is inspect.Parameter.KEYWORD_ONLY

    def test_positional_callers_are_unaffected(self):
        """The historical positional call shape must still mean what it did."""
        from llm_council.council import run_full_council

        bound = inspect.signature(run_full_council).bind("query", True, ["m-a"])
        assert bound.arguments["user_query"] == "query"
        assert bound.arguments["bypass_cache"] is True
        assert bound.arguments["models"] == ["m-a"]
        assert "per_model_timeout" not in bound.arguments


class TestUnitsContractAtEveryCaller:
    """Every caller must hand resolve_stage_timeout SECONDS, not milliseconds.

    TierContract stores the figure as per_model_timeout_ms. A caller forwarding
    it raw would ask for a 300,000s budget. The helper now rejects that, but the
    real defence is that no caller makes the mistake — pinned here structurally,
    since it is exactly the kind of slip a future edit reintroduces silently.
    """

    @pytest.mark.parametrize(
        "module_name", ["llm_council.facade", "llm_council.http_server"]
    )
    def test_contract_derived_callers_divide_by_1000(self, module_name):
        import ast
        import importlib
        from pathlib import Path

        module = importlib.import_module(module_name)
        source = Path(module.__file__).read_text()
        tree = ast.parse(source)

        # A bare truthiness guard (`if contract.per_model_timeout_ms:`) reads the
        # field without consuming its magnitude, so it needs no conversion.
        # Only the test EXPRESSION ITSELF is exempt — exempting everything
        # inside the test would also excuse a real magnitude use such as
        # `x = c.per_model_timeout_ms if flag else 0` (#650 gate).
        guard_only = {
            id(stmt.test)
            for stmt in ast.walk(tree)
            if isinstance(stmt, (ast.If, ast.IfExp))
        }
        divided = {
            id(node.left)
            for node in ast.walk(tree)
            if isinstance(node, ast.BinOp)
            and isinstance(node.op, ast.Div)
            and getattr(node.right, "value", None) == 1000
        }

        uses = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and node.attr == "per_model_timeout_ms"
        ]
        assert uses, f"expected {module_name} to read per_model_timeout_ms"

        value_uses = [u for u in uses if id(u) not in guard_only]
        assert value_uses, f"expected {module_name} to consume per_model_timeout_ms"

        for use in value_uses:
            assert id(use) in divided, (
                f"{module_name}:{use.lineno} consumes per_model_timeout_ms without "
                "'/ 1000' — a milliseconds value would reach a seconds-denominated "
                "timeout (#648 council review)"
            )

    def test_every_caller_passes_a_plausible_seconds_value(self):
        """The real per-tier values must survive the helper's sanity ceiling."""
        from llm_council.council_usage import resolve_stage_timeout
        from llm_council.tier_contract import create_tier_contract

        for tier in ("quick", "balanced", "high", "reasoning", "frontier"):
            contract = create_tier_contract(tier)
            seconds = contract.per_model_timeout_ms / 1000
            resolved = resolve_stage_timeout(seconds)
            assert resolved >= 120.0
            assert resolved == max(seconds, 120.0), (
                f"{tier}: a real tier value was rejected by the sanity ceiling"
            )

    @pytest.mark.asyncio
    async def test_passes_resolved_timeout_to_stage3(self):
        from llm_council.council import run_full_council

        models = ["m-a", "m-b", "m-c"]
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        with (
            patch(
                "llm_council.council.stage1_collect_responses", new_callable=AsyncMock
            ) as mock_stage1,
            patch(
                "llm_council.council.stage1_5_normalize_styles", new_callable=AsyncMock
            ) as mock_stage1_5,
            patch(
                "llm_council.council.stage2_collect_rankings", new_callable=AsyncMock
            ) as mock_stage2,
            patch(
                "llm_council.council.stage3_synthesize_final", new_callable=AsyncMock
            ) as mock_stage3,
        ):
            stage1_results = [{"model": m, "response": "r"} for m in models]
            mock_stage1.return_value = (stage1_results, usage)
            mock_stage1_5.return_value = (stage1_results, usage)
            mock_stage2.return_value = ([], {}, usage)
            mock_stage3.return_value = ({"model": "chair", "response": "Final"}, usage, None)

            await run_full_council("Test query", models=models, per_model_timeout=270.0)

            assert mock_stage3.await_args.kwargs["timeout"] == 270.0
            assert mock_stage2.await_args.kwargs["timeout"] == 270.0

    @pytest.mark.asyncio
    async def test_omitting_the_kwarg_keeps_the_floor(self):
        from llm_council.council import run_full_council

        models = ["m-a", "m-b", "m-c"]
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        with (
            patch(
                "llm_council.council.stage1_collect_responses", new_callable=AsyncMock
            ) as mock_stage1,
            patch(
                "llm_council.council.stage1_5_normalize_styles", new_callable=AsyncMock
            ) as mock_stage1_5,
            patch(
                "llm_council.council.stage2_collect_rankings", new_callable=AsyncMock
            ) as mock_stage2,
            patch(
                "llm_council.council.stage3_synthesize_final", new_callable=AsyncMock
            ) as mock_stage3,
        ):
            stage1_results = [{"model": m, "response": "r"} for m in models]
            mock_stage1.return_value = (stage1_results, usage)
            mock_stage1_5.return_value = (stage1_results, usage)
            mock_stage2.return_value = ([], {}, usage)
            mock_stage3.return_value = ({"model": "chair", "response": "Final"}, usage, None)

            await run_full_council("Test query", models=models)

            assert mock_stage3.await_args.kwargs["timeout"] == 120.0


class TestHttpCouncilEndpointWiring:
    """/council has no tier parameter; it already documents the high tier."""

    def test_endpoint_passes_high_tier_per_model_timeout(self):
        from fastapi.testclient import TestClient

        from llm_council.http_server import app
        from llm_council.tier_contract import create_tier_contract

        expected = create_tier_contract("high").per_model_timeout_ms / 1000

        with patch("llm_council.http_server.run_full_council", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (
                [],
                [],
                {"model": "chair", "response": "Final"},
                {"usage": {}},
            )
            client = TestClient(app)
            response = client.post(
                "/v1/council/run",
                json={"prompt": "Test query", "api_key": "sk-test-key"},
            )

        assert response.status_code == 200
        assert mock_run.await_args.kwargs["per_model_timeout"] == expected


# =============================================================================
# Call-site guard — the defect was an OMITTED argument, so pin it structurally
# =============================================================================


class TestNoStageCallSiteRelaxesToTheDefault:
    """Every council.py call to stage 2/3 must pass an explicit timeout.

    The original bug was invisible in review: the call simply left the kwarg
    off and silently inherited 120.0. An AST check makes a regression loud.
    """

    @pytest.mark.parametrize("func", ["stage2_collect_rankings", "stage3_synthesize_final"])
    def test_every_call_site_passes_timeout(self, func):
        import ast
        from pathlib import Path

        import llm_council.council as council_module

        tree = ast.parse(Path(council_module.__file__).read_text())
        def _names(node):
            """The stage function's name, however the call spells it.

            Matching only ast.Name would let a future module-qualified call
            (``council_stages.stage2_collect_rankings(...)``) evade the guard
            entirely while the remaining direct calls kept it green (#650 gate).
            """
            if isinstance(node, ast.Name):
                return node.id
            if isinstance(node, ast.Attribute):
                return node.attr
            return None

        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and _names(node.func) == func
        ]

        assert calls, f"no {func} call sites found in council.py"
        for call in calls:
            kwargs = {kw.arg for kw in call.keywords}
            assert "timeout" in kwargs, (
                f"{func} called at council.py:{call.lineno} without an explicit "
                f"timeout — it would silently inherit the 120s default (#648)"
            )
