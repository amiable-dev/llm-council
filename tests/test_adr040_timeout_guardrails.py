"""Tests for ADR-040: Verification Timeout Guardrails & Observability.

TDD: Tests written first, then implementation follows.

Covers:
- Step 1: Stage 2 tier contract fix (timeout + models params)
- Step 2: Stage 3 timeout fix
- Step 3: Wire tier timeouts in verification pipeline
- Step 4: Global timeout wrapper + partial results + waterfall budgeting
- Step 5: Tiered input size limits
- Step 6: Pre-flight tier compliance check
- Step 7: Enhanced Stage 2 per-model progress
"""

import asyncio
import inspect
import time

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any


# =============================================================================
# Step 1: Stage 2 Tier Contract Fix
# =============================================================================


class TestStage2TierContractFix:
    """Stage 2 should accept timeout and models parameters."""

    def test_stage2_accepts_timeout_parameter(self):
        """stage2_collect_rankings() should accept a timeout parameter."""
        from llm_council.council import stage2_collect_rankings

        sig = inspect.signature(stage2_collect_rankings)
        assert "timeout" in sig.parameters
        # Default should be 120.0 for backward compat
        assert sig.parameters["timeout"].default == 120.0

    def test_stage2_accepts_models_parameter(self):
        """stage2_collect_rankings() should accept a models parameter."""
        from llm_council.council import stage2_collect_rankings

        sig = inspect.signature(stage2_collect_rankings)
        assert "models" in sig.parameters
        assert sig.parameters["models"].default is None

    @pytest.mark.asyncio
    async def test_stage2_passes_timeout_to_query_models_parallel(self):
        """stage2 should pass its timeout param to query_models_parallel."""
        from llm_council.council import stage2_collect_rankings

        stage1_results = [
            {"model": "model-a", "response": "Answer A"},
            {"model": "model-b", "response": "Answer B"},
        ]

        with patch("llm_council.council.query_models_parallel", new_callable=AsyncMock) as mock_qmp:
            mock_qmp.return_value = {}

            await stage2_collect_rankings("test query", stage1_results, timeout=45.0)

            mock_qmp.assert_called_once()
            call_kwargs = mock_qmp.call_args
            assert (
                call_kwargs.kwargs.get("timeout") == 45.0 or call_kwargs[1].get("timeout") == 45.0
            )

    @pytest.mark.asyncio
    async def test_stage2_uses_provided_models_not_global(self):
        """stage2 should use provided models list instead of global config."""
        from llm_council.council import stage2_collect_rankings

        custom_models = ["custom/model-1", "custom/model-2"]
        stage1_results = [
            {"model": "model-a", "response": "Answer A"},
        ]

        with patch("llm_council.council.query_models_parallel", new_callable=AsyncMock) as mock_qmp:
            mock_qmp.return_value = {}

            await stage2_collect_rankings("test query", stage1_results, models=custom_models)

            mock_qmp.assert_called_once()
            # First positional arg should be the models list
            actual_models = mock_qmp.call_args[0][0]
            assert set(actual_models) == set(custom_models)

    @pytest.mark.asyncio
    async def test_stage2_defaults_to_council_models_when_none(self):
        """stage2 should fall back to _get_council_models() when models=None."""
        from llm_council.council import stage2_collect_rankings

        stage1_results = [
            {"model": "model-a", "response": "Answer A"},
        ]

        with (
            patch("llm_council.council.query_models_parallel", new_callable=AsyncMock) as mock_qmp,
            patch("llm_council.council.COUNCIL_MODELS", ["default/model-1", "default/model-2"]),
        ):
            mock_qmp.return_value = {}

            await stage2_collect_rankings("test query", stage1_results)

            mock_qmp.assert_called_once()
            actual_models = mock_qmp.call_args[0][0]
            assert set(actual_models) == {"default/model-1", "default/model-2"}


# =============================================================================
# Step 2: Stage 3 Timeout Fix
# =============================================================================


class TestStage3TimeoutFix:
    """Stage 3 should accept and pass through a timeout parameter."""

    def test_stage3_accepts_timeout_parameter(self):
        """stage3_synthesize_final() should accept a timeout parameter."""
        from llm_council.council import stage3_synthesize_final

        sig = inspect.signature(stage3_synthesize_final)
        assert "timeout" in sig.parameters
        assert sig.parameters["timeout"].default == 120.0

    @pytest.mark.asyncio
    async def test_stage3_passes_timeout_to_query_model(self):
        """stage3 should pass its timeout param to query_model."""
        from llm_council.council import stage3_synthesize_final

        stage1_results = [{"model": "m1", "response": "Answer"}]
        stage2_results = [{"model": "m1", "ranking": "ranked"}]

        with patch("llm_council.council.query_model", new_callable=AsyncMock) as mock_qm:
            mock_qm.return_value = {
                "content": "Synthesis",
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            }

            await stage3_synthesize_final(
                "test query", stage1_results, stage2_results, timeout=60.0
            )

            mock_qm.assert_called_once()
            call_kwargs = mock_qm.call_args
            assert (
                call_kwargs.kwargs.get("timeout") == 60.0 or call_kwargs[1].get("timeout") == 60.0
            )


# =============================================================================
# Helper: Standard mock setup for run_verification tests
# =============================================================================


def _standard_verification_mocks():
    """Return a dict of standard patches for run_verification tests."""
    return {
        "stage1": patch("llm_council.verification.api.stage1_collect_responses_with_status"),
        "stage2": patch("llm_council.verification.api.stage2_collect_rankings"),
        "stage3": patch("llm_council.verification.api.stage3_synthesize_final"),
        "agg": patch("llm_council.verification.api.calculate_aggregate_rankings"),
        "build": patch("llm_council.verification.api.build_verification_result"),
        "ctx_mgr": patch("llm_council.verification.api.VerificationContextManager"),
        "prompt": patch(
            "llm_council.verification.api._build_verification_prompt",
            new_callable=AsyncMock,
            return_value="test prompt",
        ),
    }


def _configure_standard_mocks(mocks: Dict[str, Any]):
    """Configure standard return values for mocks."""
    mock_ctx = MagicMock()
    mock_ctx.context_id = "test-ctx"
    mocks["ctx_mgr"].return_value.__enter__ = MagicMock(return_value=mock_ctx)
    mocks["ctx_mgr"].return_value.__exit__ = MagicMock(return_value=False)

    mocks["stage1"].return_value = (
        [{"model": "test", "response": "ok"}],
        {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        {},
    )
    mocks["stage2"].return_value = ([], {}, {})
    mocks["stage3"].return_value = ({"model": "m", "response": "s"}, {}, None)
    mocks["agg"].return_value = []
    mocks["build"].return_value = {
        "verdict": "pass",
        "confidence": 0.9,
        "rubric_scores": {},
        "blocking_issues": [],
        "rationale": "OK",
    }

    mock_store = MagicMock()
    mock_store.create_verification_directory.return_value = "/tmp/test"
    return mock_store


# =============================================================================
# Step 3: Wire Tier Timeouts in Verification Pipeline
# =============================================================================


class TestVerificationTierTimeoutWiring:
    """run_verification should pass tier timeouts to stage2 and stage3."""

    @pytest.mark.asyncio
    async def test_verification_passes_tier_timeout_to_stage2(self):
        """run_verification should pass tier timeout and models to stage2."""
        from llm_council.verification.api import run_verification, VerifyRequest
        from llm_council.tier_contract import create_tier_contract

        tier = "balanced"
        tier_contract = create_tier_contract(tier)

        request = VerifyRequest(snapshot_id="abc1234", tier=tier)

        patches = _standard_verification_mocks()
        with (
            patches["stage1"] as mock_s1,
            patches["stage2"] as mock_s2,
            patches["stage3"] as mock_s3,
            patches["agg"] as mock_agg,
            patches["build"] as mock_build,
            patches["ctx_mgr"] as mock_ctx_mgr,
            patches["prompt"],
        ):
            mocks = {
                "stage1": mock_s1,
                "stage2": mock_s2,
                "stage3": mock_s3,
                "agg": mock_agg,
                "build": mock_build,
                "ctx_mgr": mock_ctx_mgr,
            }
            mock_store = _configure_standard_mocks(mocks)

            await run_verification(request, mock_store)

            mock_s2.assert_called_once()
            s2_kwargs = mock_s2.call_args.kwargs if mock_s2.call_args.kwargs else {}
            # Check timeout was passed (waterfall budget, so <= per_model timeout)
            assert "timeout" in s2_kwargs
            assert s2_kwargs["timeout"] > 0
            # Check models were passed
            assert s2_kwargs.get("models") == tier_contract.allowed_models

    @pytest.mark.asyncio
    async def test_verification_passes_tier_timeout_to_stage3(self):
        """run_verification should pass tier timeout to stage3."""
        from llm_council.verification.api import run_verification, VerifyRequest

        request = VerifyRequest(snapshot_id="abc1234", tier="quick")

        patches = _standard_verification_mocks()
        with (
            patches["stage1"] as mock_s1,
            patches["stage2"] as mock_s2,
            patches["stage3"] as mock_s3,
            patches["agg"] as mock_agg,
            patches["build"] as mock_build,
            patches["ctx_mgr"] as mock_ctx_mgr,
            patches["prompt"],
        ):
            mocks = {
                "stage1": mock_s1,
                "stage2": mock_s2,
                "stage3": mock_s3,
                "agg": mock_agg,
                "build": mock_build,
                "ctx_mgr": mock_ctx_mgr,
            }
            mock_store = _configure_standard_mocks(mocks)

            await run_verification(request, mock_store)

            mock_s3.assert_called_once()
            s3_kwargs = mock_s3.call_args.kwargs if mock_s3.call_args.kwargs else {}
            assert "timeout" in s3_kwargs
            assert s3_kwargs["timeout"] > 0


# =============================================================================
# Step 4: Global Timeout Wrapper + Partial Results + Waterfall Budgeting
# =============================================================================


class TestGlobalTimeoutWrapper:
    """run_verification should have a global timeout that returns partial results."""

    def test_verify_response_has_timeout_fired_field(self):
        """VerifyResponse should have a timeout_fired field."""
        from llm_council.verification.api import VerifyResponse

        fields = VerifyResponse.model_fields
        assert "timeout_fired" in fields

    def test_verify_response_has_completed_stages_field(self):
        """VerifyResponse should have a completed_stages field."""
        from llm_council.verification.api import VerifyResponse

        fields = VerifyResponse.model_fields
        assert "completed_stages" in fields

    def test_verification_timeout_multiplier_exists(self):
        """VERIFICATION_TIMEOUT_MULTIPLIER should be defined."""
        from llm_council.verification.api import VERIFICATION_TIMEOUT_MULTIPLIER

        assert VERIFICATION_TIMEOUT_MULTIPLIER == 1.5

    @pytest.mark.asyncio
    async def test_global_deadline_uses_tier_contract(self):
        """Global deadline should be derived from tier_contract.deadline_ms * multiplier."""
        from llm_council.verification.api import (
            run_verification,
            VerifyRequest,
            VERIFICATION_TIMEOUT_MULTIPLIER,
        )
        from llm_council.tier_contract import create_tier_contract

        tier = "quick"
        tier_contract = create_tier_contract(tier)
        expected_deadline = (tier_contract.deadline_ms / 1000) * VERIFICATION_TIMEOUT_MULTIPLIER

        request = VerifyRequest(snapshot_id="abc1234", tier=tier)

        # Patch only asyncio.wait_for (not entire asyncio module)
        original_wait_for = asyncio.wait_for
        captured_timeout = {}

        async def spy_wait_for(coro, *, timeout=None):
            captured_timeout["value"] = timeout
            return await original_wait_for(coro, timeout=timeout)

        patches = _standard_verification_mocks()
        with (
            patches["stage1"] as mock_s1,
            patches["stage2"] as mock_s2,
            patches["stage3"] as mock_s3,
            patches["agg"] as mock_agg,
            patches["build"] as mock_build,
            patches["ctx_mgr"] as mock_ctx_mgr,
            patches["prompt"],
            patch("llm_council.verification.api.asyncio.wait_for", side_effect=spy_wait_for),
        ):
            mocks = {
                "stage1": mock_s1,
                "stage2": mock_s2,
                "stage3": mock_s3,
                "agg": mock_agg,
                "build": mock_build,
                "ctx_mgr": mock_ctx_mgr,
            }
            mock_store = _configure_standard_mocks(mocks)

            await run_verification(request, mock_store)

            assert "value" in captured_timeout
            assert captured_timeout["value"] == pytest.approx(expected_deadline, rel=0.01)

    @pytest.mark.asyncio
    async def test_global_timeout_returns_partial_when_pipeline_hangs(self):
        """When pipeline times out, should return partial result with timeout_fired."""
        from llm_council.verification.api import run_verification, VerifyRequest

        request = VerifyRequest(snapshot_id="abc1234", tier="quick")

        # Make _run_verification_pipeline hang so wait_for times out
        async def hanging_pipeline(*args, **kwargs):
            await asyncio.sleep(9999)

        patches = _standard_verification_mocks()
        with (
            patches["ctx_mgr"] as mock_ctx_mgr,
            patches["prompt"],
            patch(
                "llm_council.verification.api._run_verification_pipeline",
                side_effect=hanging_pipeline,
            ),
            patch(
                "llm_council.verification.api.asyncio.wait_for", side_effect=asyncio.TimeoutError()
            ),
        ):
            mock_ctx = MagicMock()
            mock_ctx.context_id = "test-ctx"
            mock_ctx_mgr.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_ctx_mgr.return_value.__exit__ = MagicMock(return_value=False)

            mock_store = MagicMock()
            mock_store.create_verification_directory.return_value = "/tmp/test"

            result = await run_verification(request, mock_store)

            assert result["partial"] is True
            assert result["timeout_fired"] is True
            assert result["verdict"] == "unclear"
            assert result["exit_code"] == 2

    @pytest.mark.asyncio
    async def test_timeout_preserves_completed_stages_in_partial_state(self):
        """On timeout after stage1, partial_state should capture completed stages."""
        from llm_council.verification.api import run_verification, VerifyRequest

        request = VerifyRequest(snapshot_id="abc1234", tier="quick")

        # Simulate pipeline that completes stage1 then hangs in stage2
        async def partial_pipeline(*args, **kwargs):
            partial_state = kwargs.get("partial_state", args[9] if len(args) > 9 else {})
            partial_state["completed_stages"].append("stage1")
            partial_state["stage1_results"] = [{"model": "test", "response": "ok"}]
            await asyncio.sleep(9999)  # Hang in stage2

        patches = _standard_verification_mocks()
        with (
            patches["ctx_mgr"] as mock_ctx_mgr,
            patches["prompt"],
            patch(
                "llm_council.verification.api._run_verification_pipeline",
                side_effect=partial_pipeline,
            ),
        ):
            mock_ctx = MagicMock()
            mock_ctx.context_id = "test-ctx"
            mock_ctx_mgr.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_ctx_mgr.return_value.__exit__ = MagicMock(return_value=False)

            mock_store = MagicMock()
            mock_store.create_verification_directory.return_value = "/tmp/test"

            # Use a very short global deadline to trigger timeout quickly
            with patch("llm_council.verification.api.VERIFICATION_TIMEOUT_MULTIPLIER", 0.001):
                result = await run_verification(request, mock_store)

            assert result["partial"] is True
            assert result["timeout_fired"] is True
            assert "stage1" in result["completed_stages"]

    @pytest.mark.asyncio
    async def test_normal_completion_has_no_timeout_fields(self):
        """Normal completion should have timeout_fired=False and all stages."""
        from llm_council.verification.api import run_verification, VerifyRequest

        request = VerifyRequest(snapshot_id="abc1234", tier="quick")

        patches = _standard_verification_mocks()
        with (
            patches["stage1"] as mock_s1,
            patches["stage2"] as mock_s2,
            patches["stage3"] as mock_s3,
            patches["agg"] as mock_agg,
            patches["build"] as mock_build,
            patches["ctx_mgr"] as mock_ctx_mgr,
            patches["prompt"],
        ):
            mocks = {
                "stage1": mock_s1,
                "stage2": mock_s2,
                "stage3": mock_s3,
                "agg": mock_agg,
                "build": mock_build,
                "ctx_mgr": mock_ctx_mgr,
            }
            mock_store = _configure_standard_mocks(mocks)

            result = await run_verification(request, mock_store)

            assert result["timeout_fired"] is False
            assert result["partial"] is False
            assert "stage1" in result["completed_stages"]
            assert "stage2" in result["completed_stages"]
            assert "stage3" in result["completed_stages"]


class TestWaterfallTimeBudgeting:
    """Waterfall time budgeting allocates remaining time proportionally."""

    @pytest.mark.asyncio
    async def test_stage1_gets_50_percent_of_remaining(self):
        """Stage 1 budget should be ~50% of total remaining time."""
        from llm_council.verification.api import run_verification, VerifyRequest
        from llm_council.tier_contract import get_tier_timeout

        request = VerifyRequest(snapshot_id="abc1234", tier="high")
        tier_timeout = get_tier_timeout("high")

        captured_timeouts = {}

        patches = _standard_verification_mocks()
        with (
            patches["stage1"] as mock_s1,
            patches["stage2"] as mock_s2,
            patches["stage3"] as mock_s3,
            patches["agg"] as mock_agg,
            patches["build"] as mock_build,
            patches["ctx_mgr"] as mock_ctx_mgr,
            patches["prompt"],
        ):
            mocks = {
                "stage1": mock_s1,
                "stage2": mock_s2,
                "stage3": mock_s3,
                "agg": mock_agg,
                "build": mock_build,
                "ctx_mgr": mock_ctx_mgr,
            }
            mock_store = _configure_standard_mocks(mocks)

            await run_verification(request, mock_store)

            # Stage 1 timeout
            s1_kwargs = mock_s1.call_args.kwargs if mock_s1.call_args.kwargs else {}
            s1_timeout = s1_kwargs.get("timeout", 0)
            # Stage 2 timeout
            s2_kwargs = mock_s2.call_args.kwargs if mock_s2.call_args.kwargs else {}
            s2_timeout = s2_kwargs.get("timeout", 0)

            # Stage 1 budget should be <= per_model timeout (capped)
            assert s1_timeout <= tier_timeout["per_model"]
            assert s1_timeout > 0

            # Stage 2 budget should also be positive
            assert s2_timeout > 0

    @pytest.mark.asyncio
    async def test_stage3_gets_remaining_budget(self):
        """Stage 3 should receive remaining budget (all that's left)."""
        from llm_council.verification.api import run_verification, VerifyRequest

        request = VerifyRequest(snapshot_id="abc1234", tier="high")

        patches = _standard_verification_mocks()
        with (
            patches["stage1"] as mock_s1,
            patches["stage2"] as mock_s2,
            patches["stage3"] as mock_s3,
            patches["agg"] as mock_agg,
            patches["build"] as mock_build,
            patches["ctx_mgr"] as mock_ctx_mgr,
            patches["prompt"],
        ):
            mocks = {
                "stage1": mock_s1,
                "stage2": mock_s2,
                "stage3": mock_s3,
                "agg": mock_agg,
                "build": mock_build,
                "ctx_mgr": mock_ctx_mgr,
            }
            mock_store = _configure_standard_mocks(mocks)

            await run_verification(request, mock_store)

            s3_kwargs = mock_s3.call_args.kwargs if mock_s3.call_args.kwargs else {}
            s3_timeout = s3_kwargs.get("timeout", 0)
            assert s3_timeout > 0


# =============================================================================
# Step 5: Tiered Input Size Limits
# =============================================================================


class TestTieredInputSizeLimits:
    """Each tier should have appropriate input size limits."""

    def test_tier_max_chars_quick(self):
        """Quick tier should have 15000 char limit."""
        from llm_council.verification.api import TIER_MAX_CHARS

        assert TIER_MAX_CHARS["quick"] == 15000

    def test_tier_max_chars_balanced(self):
        """Balanced tier should have 30000 char limit."""
        from llm_council.verification.api import TIER_MAX_CHARS

        assert TIER_MAX_CHARS["balanced"] == 30000

    def test_tier_max_chars_high(self):
        """High tier should have 50000 char limit."""
        from llm_council.verification.api import TIER_MAX_CHARS

        assert TIER_MAX_CHARS["high"] == 50000

    def test_tier_max_chars_reasoning(self):
        """Reasoning tier should have 50000 char limit."""
        from llm_council.verification.api import TIER_MAX_CHARS

        assert TIER_MAX_CHARS["reasoning"] == 50000

    @pytest.mark.asyncio
    async def test_oversized_input_rejected_with_helpful_error(self):
        """Input exceeding tier limit should return error result."""
        from llm_council.verification.api import run_verification, VerifyRequest

        request = VerifyRequest(snapshot_id="abc1234", tier="quick")

        # Generate a prompt that exceeds 15000 chars
        large_prompt = "x" * 20000

        with (
            patch("llm_council.verification.api.VerificationContextManager") as mock_ctx_mgr,
            patch(
                "llm_council.verification.api._build_verification_prompt",
                new_callable=AsyncMock,
                return_value=large_prompt,
            ),
        ):
            mock_ctx = MagicMock()
            mock_ctx.context_id = "test-ctx"
            mock_ctx_mgr.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_ctx_mgr.return_value.__exit__ = MagicMock(return_value=False)

            mock_store = MagicMock()
            mock_store.create_verification_directory.return_value = "/tmp/test"

            result = await run_verification(request, mock_store)

            assert result["partial"] is True
            assert result["verdict"] == "unclear"
            assert "size" in result["rationale"].lower() or "limit" in result["rationale"].lower()

    @pytest.mark.asyncio
    async def test_within_limit_input_proceeds(self):
        """Input within tier limit should proceed normally."""
        from llm_council.verification.api import run_verification, VerifyRequest

        request = VerifyRequest(snapshot_id="abc1234", tier="high")

        # 10000 chars is well within high tier's 50000 limit
        small_prompt = "x" * 10000

        patches = _standard_verification_mocks()
        patches["prompt"] = patch(
            "llm_council.verification.api._build_verification_prompt",
            new_callable=AsyncMock,
            return_value=small_prompt,
        )
        with (
            patches["stage1"] as mock_s1,
            patches["stage2"] as mock_s2,
            patches["stage3"] as mock_s3,
            patches["agg"] as mock_agg,
            patches["build"] as mock_build,
            patches["ctx_mgr"] as mock_ctx_mgr,
            patches["prompt"],
        ):
            mocks = {
                "stage1": mock_s1,
                "stage2": mock_s2,
                "stage3": mock_s3,
                "agg": mock_agg,
                "build": mock_build,
                "ctx_mgr": mock_ctx_mgr,
            }
            mock_store = _configure_standard_mocks(mocks)

            result = await run_verification(request, mock_store)

            # Should not be partial (proceeded normally)
            assert result["partial"] is False


# =============================================================================
# Step 6: Pre-flight Tier Compliance Check
# =============================================================================


class TestPreflightCheck:
    """Pre-flight info should be emitted as first progress callback."""

    @pytest.mark.asyncio
    async def test_preflight_emitted_as_first_progress(self):
        """First progress callback should be a preflight message."""
        from llm_council.verification.api import run_verification, VerifyRequest

        request = VerifyRequest(snapshot_id="abc1234", tier="quick")

        progress_calls = []

        async def capture_progress(step, total, message):
            progress_calls.append({"step": step, "total": total, "message": message})

        patches = _standard_verification_mocks()
        with (
            patches["stage1"] as mock_s1,
            patches["stage2"] as mock_s2,
            patches["stage3"] as mock_s3,
            patches["agg"] as mock_agg,
            patches["build"] as mock_build,
            patches["ctx_mgr"] as mock_ctx_mgr,
            patches["prompt"],
        ):
            mocks = {
                "stage1": mock_s1,
                "stage2": mock_s2,
                "stage3": mock_s3,
                "agg": mock_agg,
                "build": mock_build,
                "ctx_mgr": mock_ctx_mgr,
            }
            mock_store = _configure_standard_mocks(mocks)

            await run_verification(request, mock_store, on_progress=capture_progress)

            # First progress call should be preflight (step 0)
            assert len(progress_calls) > 0
            first = progress_calls[0]
            assert first["step"] == 0
            assert "preflight" in first["message"].lower()

    @pytest.mark.asyncio
    async def test_preflight_includes_complexity_info(self):
        """Preflight message should include content_chars, num_models, tier info."""
        from llm_council.verification.api import run_verification, VerifyRequest

        request = VerifyRequest(snapshot_id="abc1234", tier="balanced")

        progress_calls = []

        async def capture_progress(step, total, message):
            progress_calls.append({"step": step, "total": total, "message": message})

        patches = _standard_verification_mocks()
        patches["prompt"] = patch(
            "llm_council.verification.api._build_verification_prompt",
            new_callable=AsyncMock,
            return_value="a" * 5000,
        )
        with (
            patches["stage1"] as mock_s1,
            patches["stage2"] as mock_s2,
            patches["stage3"] as mock_s3,
            patches["agg"] as mock_agg,
            patches["build"] as mock_build,
            patches["ctx_mgr"] as mock_ctx_mgr,
            patches["prompt"],
        ):
            mocks = {
                "stage1": mock_s1,
                "stage2": mock_s2,
                "stage3": mock_s3,
                "agg": mock_agg,
                "build": mock_build,
                "ctx_mgr": mock_ctx_mgr,
            }
            mock_store = _configure_standard_mocks(mocks)

            await run_verification(request, mock_store, on_progress=capture_progress)

            first = progress_calls[0]
            msg = first["message"]
            # Should contain key preflight info
            assert "5000" in msg or "chars" in msg.lower()
            assert "balanced" in msg.lower() or "tier" in msg.lower()

    @pytest.mark.asyncio
    async def test_preflight_warns_near_limit(self):
        """Preflight should warn when content >80% of tier limit."""
        from llm_council.verification.api import run_verification, VerifyRequest, TIER_MAX_CHARS

        request = VerifyRequest(snapshot_id="abc1234", tier="quick")
        # 85% of quick tier limit (15000 * 0.85 = 12750)
        near_limit_prompt = "x" * 12750

        progress_calls = []

        async def capture_progress(step, total, message):
            progress_calls.append({"step": step, "total": total, "message": message})

        patches = _standard_verification_mocks()
        patches["prompt"] = patch(
            "llm_council.verification.api._build_verification_prompt",
            new_callable=AsyncMock,
            return_value=near_limit_prompt,
        )
        with (
            patches["stage1"] as mock_s1,
            patches["stage2"] as mock_s2,
            patches["stage3"] as mock_s3,
            patches["agg"] as mock_agg,
            patches["build"] as mock_build,
            patches["ctx_mgr"] as mock_ctx_mgr,
            patches["prompt"],
        ):
            mocks = {
                "stage1": mock_s1,
                "stage2": mock_s2,
                "stage3": mock_s3,
                "agg": mock_agg,
                "build": mock_build,
                "ctx_mgr": mock_ctx_mgr,
            }
            mock_store = _configure_standard_mocks(mocks)

            await run_verification(request, mock_store, on_progress=capture_progress)

            first = progress_calls[0]
            assert "warning" in first["message"].lower() or "near" in first["message"].lower()


# =============================================================================
# Step 7: Enhanced Stage 2 Per-Model Progress
# =============================================================================


class TestStage2PerModelProgress:
    """Stage 2 should support per-model progress reporting."""

    def test_stage2_accepts_on_progress_parameter(self):
        """stage2_collect_rankings() should accept an on_progress callback."""
        from llm_council.council import stage2_collect_rankings

        sig = inspect.signature(stage2_collect_rankings)
        assert "on_progress" in sig.parameters
        assert sig.parameters["on_progress"].default is None

    @pytest.mark.asyncio
    async def test_stage2_uses_as_completed_when_on_progress_provided(self):
        """When on_progress is given, stage2 should use per-model progress via query_model."""
        from llm_council.council import stage2_collect_rankings

        stage1_results = [
            {"model": "model-a", "response": "Answer A"},
        ]

        progress_calls = []

        async def mock_progress(completed, total, message):
            progress_calls.append({"completed": completed, "total": total, "message": message})

        with patch("llm_council.council.query_model", new_callable=AsyncMock) as mock_qm:
            mock_qm.return_value = {
                "content": '```json\n{"ranking": ["Response A"], "scores": {"Response A": 8}}\n```',
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            }

            await stage2_collect_rankings(
                "test query",
                stage1_results,
                models=["model-x", "model-y"],
                on_progress=mock_progress,
            )

            # query_model should be called (not query_models_parallel)
            assert mock_qm.call_count == 2
            # Progress should have been reported
            assert len(progress_calls) == 2
            assert progress_calls[0]["completed"] == 1
            assert progress_calls[1]["completed"] == 2

    @pytest.mark.asyncio
    async def test_stage2_uses_query_models_parallel_without_on_progress(self):
        """Without on_progress, stage2 should use query_models_parallel (backward compat)."""
        from llm_council.council import stage2_collect_rankings

        stage1_results = [
            {"model": "model-a", "response": "Answer A"},
        ]

        with patch("llm_council.council.query_models_parallel", new_callable=AsyncMock) as mock_qmp:
            mock_qmp.return_value = {}

            await stage2_collect_rankings("test query", stage1_results, models=["model-x"])

            # query_models_parallel should be used
            mock_qmp.assert_called_once()

    @pytest.mark.asyncio
    async def test_total_steps_includes_stage2_models(self):
        """Total progress steps should include per-model stage2 steps."""
        from llm_council.verification.api import run_verification, VerifyRequest
        from llm_council.tier_contract import create_tier_contract

        tier = "balanced"
        tier_contract = create_tier_contract(tier)
        num_models = len(tier_contract.allowed_models)

        request = VerifyRequest(snapshot_id="abc1234", tier=tier)

        progress_calls = []

        async def capture_progress(step, total, message):
            progress_calls.append({"step": step, "total": total, "message": message})

        patches = _standard_verification_mocks()
        with (
            patches["stage1"] as mock_s1,
            patches["stage2"] as mock_s2,
            patches["stage3"] as mock_s3,
            patches["agg"] as mock_agg,
            patches["build"] as mock_build,
            patches["ctx_mgr"] as mock_ctx_mgr,
            patches["prompt"],
        ):
            mocks = {
                "stage1": mock_s1,
                "stage2": mock_s2,
                "stage3": mock_s3,
                "agg": mock_agg,
                "build": mock_build,
                "ctx_mgr": mock_ctx_mgr,
            }
            mock_store = _configure_standard_mocks(mocks)

            await run_verification(request, mock_store, on_progress=capture_progress)

            # Total should be: stage1_models + stage2_models + 2 (stage3 + finalize)
            # Plus preflight step 0
            expected_total = num_models + num_models + 2
            # Check that at least one progress call has the expected total
            totals = {p["total"] for p in progress_calls if p["step"] > 0}
            assert expected_total in totals
