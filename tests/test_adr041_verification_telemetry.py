"""Tests for ADR-041: Verification Telemetry Wiring.

TDD: Tests written first, then implementation follows.

Covers:
- Step 1: Timing data in pipeline results
- Step 2: Timing data on timeout
- Step 3: Model statuses and aggregate rankings preserved in partial_state
- Step 4: Performance tracker wiring
"""

import asyncio
import time

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any


# =============================================================================
# Helper: Reuse standard mock pattern from test_adr040_timeout_guardrails.py
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
            return_value=(
                "test prompt",
                {"kept": [], "warnings": [], "chars_rendered": 0, "chars_submitted": 0},
            ),
        ),
    }


def _configure_standard_mocks(mocks: Dict[str, Any]):
    """Configure standard return values for mocks."""
    mock_ctx = MagicMock()
    mock_ctx.context_id = "test-ctx"
    mocks["ctx_mgr"].return_value.__enter__ = MagicMock(return_value=mock_ctx)
    mocks["ctx_mgr"].return_value.__exit__ = MagicMock(return_value=False)

    mocks["stage1"].return_value = (
        [{"model": "test/model-a", "response": "ok"}],
        {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        {"test/model-a": {"status": "ok", "latency_ms": 1500}},
    )
    mocks["stage2"].return_value = (
        [{"model": "test/model-a", "parsed_ranking": ["Response A"]}],
        {"Response A": "test/model-a"},
        {},
    )
    mocks["stage3"].return_value = ({"model": "m", "response": "s"}, {}, None)
    mocks["agg"].return_value = [
        {"model": "test/model-a", "borda_score": 0.75, "average_position": 1.0},
    ]
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
# Step 1: Timing Data in Pipeline Result
# =============================================================================


class TestTimingInPipelineResult:
    """Pipeline results should contain timing and input metrics."""

    @pytest.mark.asyncio
    async def test_result_contains_timing_dict(self):
        """Result should have a 'timing' key with a dict value."""
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

            assert "timing" in result
            assert isinstance(result["timing"], dict)

    @pytest.mark.asyncio
    async def test_timing_has_stage_durations(self):
        """Timing should have stage1/2/3_duration_ms as non-negative ints."""
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

            timing = result["timing"]
            for key in ("stage1_elapsed_ms", "stage2_elapsed_ms", "stage3_elapsed_ms"):
                assert key in timing, f"Missing {key}"
                assert isinstance(timing[key], int), f"{key} should be int"
                assert timing[key] >= 0, f"{key} should be non-negative"

    @pytest.mark.asyncio
    async def test_timing_has_total_duration(self):
        """total_elapsed_ms should be >= sum of stage durations."""
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

            timing = result["timing"]
            stage_sum = (
                timing["stage1_elapsed_ms"]
                + timing["stage2_elapsed_ms"]
                + timing["stage3_elapsed_ms"]
            )
            assert timing["total_elapsed_ms"] >= stage_sum

    @pytest.mark.asyncio
    async def test_timing_has_budget_utilization(self):
        """budget_utilization should be a float in [0, 1] for non-timeout case."""
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

            timing = result["timing"]
            assert "budget_utilization" in timing
            assert isinstance(timing["budget_utilization"], float)
            assert 0.0 <= timing["budget_utilization"] <= 1.0
            assert "global_deadline_ms" in timing
            assert timing["global_deadline_ms"] > 0

    @pytest.mark.asyncio
    async def test_result_contains_input_metrics(self):
        """Result should have input_metrics with content_chars, num_models, tier."""
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

            assert "input_metrics" in result
            metrics = result["input_metrics"]
            assert "content_chars" in metrics
            assert "tier_max_chars" in metrics
            assert "num_models" in metrics
            assert "num_reviewers" in metrics
            assert "tier" in metrics
            assert metrics["tier"] == "quick"
            assert metrics["content_chars"] == len("test prompt")
            assert metrics["tier_max_chars"] == 15000  # quick tier limit

    @pytest.mark.asyncio
    async def test_timing_persisted_in_transcript(self):
        """store.write_stage('result', ...) should include timing."""
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

            # Find the write_stage call for "result"
            result_calls = [
                call for call in mock_store.write_stage.call_args_list if call[0][1] == "result"
            ]
            assert len(result_calls) == 1
            result_data = result_calls[0][0][2]
            assert "timing" in result_data


# =============================================================================
# Step 2: Timing Data on Timeout
# =============================================================================


class TestTimingOnTimeout:
    """Timeout results should contain partial timing data."""

    @pytest.mark.asyncio
    async def test_timeout_result_has_partial_timing(self):
        """On timeout after stage1, timing should have stage1_elapsed_ms but not stage3."""
        from llm_council.verification.api import run_verification, VerifyRequest

        request = VerifyRequest(snapshot_id="abc1234", tier="quick")

        async def partial_pipeline(*args, **kwargs):
            partial_state = kwargs.get("partial_state", args[9] if len(args) > 9 else {})
            partial_state["completed_stages"].append("stage1")
            partial_state["stage1_results"] = [{"model": "test", "response": "ok"}]
            partial_state["stage_timings"] = {"stage1_elapsed_ms": 5000}
            await asyncio.sleep(9999)

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

            with patch("llm_council.verification.api.VERIFICATION_TIMEOUT_MULTIPLIER", 0.001):
                result = await run_verification(request, mock_store)

            assert result["timeout_fired"] is True
            timing = result["timing"]
            assert "stage1_elapsed_ms" in timing
            assert timing["stage1_elapsed_ms"] == 5000
            assert "stage3_elapsed_ms" not in timing

    @pytest.mark.asyncio
    async def test_timeout_budget_utilization_is_one(self):
        """On timeout, budget_utilization should be >= 1.0."""
        from llm_council.verification.api import run_verification, VerifyRequest

        request = VerifyRequest(snapshot_id="abc1234", tier="quick")

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
                "llm_council.verification.api.asyncio.wait_for",
                side_effect=asyncio.TimeoutError(),
            ),
        ):
            mock_ctx = MagicMock()
            mock_ctx.context_id = "test-ctx"
            mock_ctx_mgr.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_ctx_mgr.return_value.__exit__ = MagicMock(return_value=False)

            mock_store = MagicMock()
            mock_store.create_verification_directory.return_value = "/tmp/test"

            result = await run_verification(request, mock_store)

            assert result["timeout_fired"] is True
            timing = result["timing"]
            assert timing["budget_utilization"] >= 1.0

    @pytest.mark.asyncio
    async def test_stage_durations_in_partial_state(self):
        """partial_state should accumulate per-stage timing via finally blocks."""
        from llm_council.verification.api import run_verification, VerifyRequest

        request = VerifyRequest(snapshot_id="abc1234", tier="quick")

        captured_partial_state = {}

        async def capturing_pipeline(*args, **kwargs):
            partial_state = kwargs.get("partial_state", args[9] if len(args) > 9 else {})
            partial_state["completed_stages"].append("stage1")
            partial_state["stage_timings"] = {"stage1_elapsed_ms": 3000}
            captured_partial_state.update(partial_state)
            await asyncio.sleep(9999)

        patches = _standard_verification_mocks()
        with (
            patches["ctx_mgr"] as mock_ctx_mgr,
            patches["prompt"],
            patch(
                "llm_council.verification.api._run_verification_pipeline",
                side_effect=capturing_pipeline,
            ),
        ):
            mock_ctx = MagicMock()
            mock_ctx.context_id = "test-ctx"
            mock_ctx_mgr.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_ctx_mgr.return_value.__exit__ = MagicMock(return_value=False)

            mock_store = MagicMock()
            mock_store.create_verification_directory.return_value = "/tmp/test"

            with patch("llm_council.verification.api.VERIFICATION_TIMEOUT_MULTIPLIER", 0.001):
                await run_verification(request, mock_store)

            assert "stage_timings" in captured_partial_state
            assert "stage1_elapsed_ms" in captured_partial_state["stage_timings"]


# =============================================================================
# Step 3: Model Statuses and Aggregate Rankings in partial_state
# =============================================================================


class TestModelStatusesPreserved:
    """Model statuses and aggregate rankings should be saved to partial_state."""

    @pytest.mark.asyncio
    async def test_model_statuses_saved_to_partial_state(self):
        """partial_state['model_statuses'] should be populated after stage1."""
        from llm_council.verification.api import (
            _run_verification_pipeline,
            VerifyRequest,
        )
        from llm_council.tier_contract import create_tier_contract, get_tier_timeout

        request = VerifyRequest(snapshot_id="abc1234", tier="quick")
        tier_contract = create_tier_contract("quick")
        tier_timeout = get_tier_timeout("quick")

        model_statuses = {"test/model-a": {"status": "ok", "latency_ms": 1500}}

        with (
            patch(
                "llm_council.verification.api.stage1_collect_responses_with_status",
                new_callable=AsyncMock,
                return_value=(
                    [{"model": "test/model-a", "response": "ok"}],
                    {},
                    model_statuses,
                ),
            ),
            patch(
                "llm_council.verification.api.stage2_collect_rankings",
                new_callable=AsyncMock,
                return_value=([], {}, {}),
            ),
            patch(
                "llm_council.verification.api.stage3_synthesize_final",
                new_callable=AsyncMock,
                return_value=({"model": "m", "response": "s"}, {}, None),
            ),
            patch(
                "llm_council.verification.api.calculate_aggregate_rankings",
                return_value=[],
            ),
            patch(
                "llm_council.verification.api.build_verification_result",
                return_value={
                    "verdict": "pass",
                    "confidence": 0.9,
                    "rubric_scores": {},
                    "blocking_issues": [],
                    "rationale": "OK",
                },
            ),
        ):
            mock_store = MagicMock()
            partial_state: Dict[str, Any] = {"completed_stages": []}
            deadline_at = time.monotonic() + 60

            await _run_verification_pipeline(
                request=request,
                store=mock_store,
                on_progress=None,
                verification_id="test-id",
                transcript_dir="/tmp/test",
                verification_query="test query",
                tier_contract=tier_contract,
                tier_timeout=tier_timeout,
                ctx=MagicMock(),
                partial_state=partial_state,
                deadline_at=deadline_at,
            )

            assert "model_statuses" in partial_state
            assert partial_state["model_statuses"] == model_statuses

    @pytest.mark.asyncio
    async def test_aggregate_rankings_saved_to_partial_state(self):
        """partial_state['aggregate_rankings'] should be populated after stage2."""
        from llm_council.verification.api import (
            _run_verification_pipeline,
            VerifyRequest,
        )
        from llm_council.tier_contract import create_tier_contract, get_tier_timeout

        request = VerifyRequest(snapshot_id="abc1234", tier="quick")
        tier_contract = create_tier_contract("quick")
        tier_timeout = get_tier_timeout("quick")

        agg_rankings = [
            {"model": "test/model-a", "borda_score": 0.75, "average_position": 1.0},
        ]

        with (
            patch(
                "llm_council.verification.api.stage1_collect_responses_with_status",
                new_callable=AsyncMock,
                return_value=(
                    [{"model": "test/model-a", "response": "ok"}],
                    {},
                    {"test/model-a": {"status": "ok", "latency_ms": 1500}},
                ),
            ),
            patch(
                "llm_council.verification.api.stage2_collect_rankings",
                new_callable=AsyncMock,
                return_value=([], {}, {}),
            ),
            patch(
                "llm_council.verification.api.stage3_synthesize_final",
                new_callable=AsyncMock,
                return_value=({"model": "m", "response": "s"}, {}, None),
            ),
            patch(
                "llm_council.verification.api.calculate_aggregate_rankings",
                return_value=agg_rankings,
            ),
            patch(
                "llm_council.verification.api.build_verification_result",
                return_value={
                    "verdict": "pass",
                    "confidence": 0.9,
                    "rubric_scores": {},
                    "blocking_issues": [],
                    "rationale": "OK",
                },
            ),
        ):
            mock_store = MagicMock()
            partial_state: Dict[str, Any] = {"completed_stages": []}
            deadline_at = time.monotonic() + 60

            await _run_verification_pipeline(
                request=request,
                store=mock_store,
                on_progress=None,
                verification_id="test-id",
                transcript_dir="/tmp/test",
                verification_query="test query",
                tier_contract=tier_contract,
                tier_timeout=tier_timeout,
                ctx=MagicMock(),
                partial_state=partial_state,
                deadline_at=deadline_at,
            )

            assert "aggregate_rankings" in partial_state
            assert partial_state["aggregate_rankings"] == agg_rankings


# =============================================================================
# Step 4: Performance Tracker Wiring
# =============================================================================


class TestPerformanceTrackerWiring:
    """Performance tracker should be called after successful verification."""

    @pytest.mark.asyncio
    async def test_persist_called_after_successful_verification(self):
        """persist_session_performance_data should be called after success."""
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
            patch(
                "llm_council.verification.api.persist_session_performance_data",
            ) as mock_persist,
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

            mock_persist.assert_called_once()

    @pytest.mark.asyncio
    async def test_persist_receives_correct_args(self):
        """persist should receive session_id, model_statuses, aggregate_rankings."""
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
            patch(
                "llm_council.verification.api.persist_session_performance_data",
            ) as mock_persist,
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

            call_kwargs = mock_persist.call_args.kwargs
            assert call_kwargs["session_id"] == result["verification_id"]
            assert isinstance(call_kwargs["model_statuses"], dict)
            assert isinstance(call_kwargs["aggregate_rankings"], dict)
            # aggregate_rankings should be dict keyed by model_id (converted from list)
            assert "test/model-a" in call_kwargs["aggregate_rankings"]

    @pytest.mark.asyncio
    async def test_persist_failure_does_not_fail_verification(self):
        """If persist raises IOError, verification result should still be returned."""
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
            patch(
                "llm_council.verification.api.persist_session_performance_data",
                side_effect=IOError("disk full"),
            ),
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

            assert result["verdict"] == "pass"
            assert result["confidence"] == 0.9

    @pytest.mark.asyncio
    async def test_persist_not_called_on_timeout(self):
        """Timeout path should skip performance persistence (incomplete data)."""
        from llm_council.verification.api import run_verification, VerifyRequest

        request = VerifyRequest(snapshot_id="abc1234", tier="quick")

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
                "llm_council.verification.api.asyncio.wait_for",
                side_effect=asyncio.TimeoutError(),
            ),
            patch(
                "llm_council.verification.api.persist_session_performance_data",
            ) as mock_persist,
        ):
            mock_ctx = MagicMock()
            mock_ctx.context_id = "test-ctx"
            mock_ctx_mgr.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_ctx_mgr.return_value.__exit__ = MagicMock(return_value=False)

            mock_store = MagicMock()
            mock_store.create_verification_directory.return_value = "/tmp/test"

            result = await run_verification(request, mock_store)

            assert result["timeout_fired"] is True
            mock_persist.assert_not_called()


# =============================================================================
# Schema: VerifyResponse has timing and input_metrics fields
# =============================================================================


class TestVerifyResponseSchema:
    """VerifyResponse should have optional timing and input_metrics fields."""

    def test_verify_response_has_timing_field(self):
        """VerifyResponse should have an optional timing field."""
        from llm_council.verification.api import VerifyResponse

        fields = VerifyResponse.model_fields
        assert "timing" in fields

    def test_verify_response_has_input_metrics_field(self):
        """VerifyResponse should have an optional input_metrics field."""
        from llm_council.verification.api import VerifyResponse

        fields = VerifyResponse.model_fields
        assert "input_metrics" in fields
