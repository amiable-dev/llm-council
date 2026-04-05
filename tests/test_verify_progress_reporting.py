"""Tests for verify tool progress reporting (Issue #326).

TDD: Tests written first, then implementation follows.

The verify tool should report meaningful progress during council deliberation,
including per-model completions in Stage 1 and stage transitions.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestRunVerificationProgressCallback:
    """Test that run_verification accepts and uses on_progress callback."""

    @pytest.mark.asyncio
    async def test_run_verification_accepts_on_progress(self):
        """run_verification should accept an optional on_progress callback."""
        from llm_council.verification.api import run_verification, VerifyRequest

        progress_calls = []

        async def track_progress(step, total, message):
            progress_calls.append((step, total, message))

        request = VerifyRequest(snapshot_id="abc1234")

        with (
            patch(
                "llm_council.verification.api.stage1_collect_responses_with_status"
            ) as mock_stage1,
            patch("llm_council.verification.api.stage2_collect_rankings") as mock_stage2,
            patch("llm_council.verification.api.stage3_synthesize_final") as mock_stage3,
            patch("llm_council.verification.api.calculate_aggregate_rankings") as mock_agg,
            patch("llm_council.verification.api.build_verification_result") as mock_build,
            patch("llm_council.verification.api.VerificationContextManager") as mock_ctx_mgr,
            patch(
                "llm_council.verification.api._build_verification_prompt",
                new_callable=AsyncMock,
                return_value="test prompt",
            ),
        ):
            mock_ctx = MagicMock()
            mock_ctx.context_id = "test-ctx"
            mock_ctx_mgr.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_ctx_mgr.return_value.__exit__ = MagicMock(return_value=False)

            mock_stage1.return_value = (
                [{"model": "test", "content": "ok"}],
                {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                {},
            )
            mock_stage2.return_value = ([], {}, {})
            mock_stage3.return_value = ("synthesis", {}, None)
            mock_agg.return_value = []
            mock_build.return_value = {
                "verdict": "pass",
                "confidence": 0.9,
                "rubric_scores": {},
                "blocking_issues": [],
                "rationale": "OK",
            }

            mock_store = MagicMock()
            mock_store.create_verification_directory.return_value = "/tmp/test"

            # Should accept on_progress without error
            await run_verification(request, mock_store, on_progress=track_progress)

            # Should have received progress calls
            assert len(progress_calls) > 0

    @pytest.mark.asyncio
    async def test_run_verification_reports_stage_transitions(self):
        """run_verification should report progress for each stage transition."""
        from llm_council.verification.api import run_verification, VerifyRequest

        progress_calls = []

        async def track_progress(step, total, message):
            progress_calls.append((step, total, message))

        request = VerifyRequest(snapshot_id="abc1234")

        with (
            patch(
                "llm_council.verification.api.stage1_collect_responses_with_status"
            ) as mock_stage1,
            patch("llm_council.verification.api.stage2_collect_rankings") as mock_stage2,
            patch("llm_council.verification.api.stage3_synthesize_final") as mock_stage3,
            patch("llm_council.verification.api.calculate_aggregate_rankings") as mock_agg,
            patch("llm_council.verification.api.build_verification_result") as mock_build,
            patch("llm_council.verification.api.VerificationContextManager") as mock_ctx_mgr,
            patch(
                "llm_council.verification.api._build_verification_prompt",
                new_callable=AsyncMock,
                return_value="test prompt",
            ),
        ):
            mock_ctx = MagicMock()
            mock_ctx.context_id = "test-ctx"
            mock_ctx_mgr.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_ctx_mgr.return_value.__exit__ = MagicMock(return_value=False)

            mock_stage1.return_value = (
                [{"model": "test", "content": "ok"}],
                {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                {},
            )
            mock_stage2.return_value = ([], {}, {})
            mock_stage3.return_value = ("synthesis", {}, None)
            mock_agg.return_value = []
            mock_build.return_value = {
                "verdict": "pass",
                "confidence": 0.9,
                "rubric_scores": {},
                "blocking_issues": [],
                "rationale": "OK",
            }

            mock_store = MagicMock()
            mock_store.create_verification_directory.return_value = "/tmp/test"

            await run_verification(request, mock_store, on_progress=track_progress)

            # Extract messages
            messages = [call[2] for call in progress_calls]

            # Stage 1 per-model progress is tested separately (via on_progress to stage1)
            # Here we verify inter-stage transitions are reported
            assert any("Stage 2" in m or "Peer" in m for m in messages), (
                f"No Stage 2 message in: {messages}"
            )
            assert any("Stage 3" in m or "Synth" in m for m in messages), (
                f"No Stage 3 message in: {messages}"
            )
            assert any("Finaliz" in m for m in messages), f"No finalization message in: {messages}"

    @pytest.mark.asyncio
    async def test_run_verification_passes_on_progress_to_stage1(self):
        """run_verification should pass on_progress to stage1_collect_responses_with_status."""
        from llm_council.verification.api import run_verification, VerifyRequest

        async def dummy_progress(step, total, message):
            pass

        request = VerifyRequest(snapshot_id="abc1234")

        with (
            patch(
                "llm_council.verification.api.stage1_collect_responses_with_status"
            ) as mock_stage1,
            patch("llm_council.verification.api.stage2_collect_rankings") as mock_stage2,
            patch("llm_council.verification.api.stage3_synthesize_final") as mock_stage3,
            patch("llm_council.verification.api.calculate_aggregate_rankings") as mock_agg,
            patch("llm_council.verification.api.build_verification_result") as mock_build,
            patch("llm_council.verification.api.VerificationContextManager") as mock_ctx_mgr,
            patch(
                "llm_council.verification.api._build_verification_prompt",
                new_callable=AsyncMock,
                return_value="test prompt",
            ),
        ):
            mock_ctx = MagicMock()
            mock_ctx.context_id = "test-ctx"
            mock_ctx_mgr.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_ctx_mgr.return_value.__exit__ = MagicMock(return_value=False)

            mock_stage1.return_value = (
                [{"model": "test", "content": "ok"}],
                {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                {},
            )
            mock_stage2.return_value = ([], {}, {})
            mock_stage3.return_value = ("synthesis", {}, None)
            mock_agg.return_value = []
            mock_build.return_value = {
                "verdict": "pass",
                "confidence": 0.9,
                "rubric_scores": {},
                "blocking_issues": [],
                "rationale": "OK",
            }

            mock_store = MagicMock()
            mock_store.create_verification_directory.return_value = "/tmp/test"

            await run_verification(request, mock_store, on_progress=dummy_progress)

            # stage1 should have received an on_progress callback
            mock_stage1.assert_called_once()
            call_kwargs = mock_stage1.call_args
            on_progress_arg = call_kwargs.kwargs.get("on_progress")
            assert on_progress_arg is not None, (
                "stage1_collect_responses_with_status should receive on_progress"
            )

    @pytest.mark.asyncio
    async def test_run_verification_works_without_on_progress(self):
        """run_verification should work fine without on_progress (backward compat)."""
        from llm_council.verification.api import run_verification, VerifyRequest

        request = VerifyRequest(snapshot_id="abc1234")

        with (
            patch(
                "llm_council.verification.api.stage1_collect_responses_with_status"
            ) as mock_stage1,
            patch("llm_council.verification.api.stage2_collect_rankings") as mock_stage2,
            patch("llm_council.verification.api.stage3_synthesize_final") as mock_stage3,
            patch("llm_council.verification.api.calculate_aggregate_rankings") as mock_agg,
            patch("llm_council.verification.api.build_verification_result") as mock_build,
            patch("llm_council.verification.api.VerificationContextManager") as mock_ctx_mgr,
            patch(
                "llm_council.verification.api._build_verification_prompt",
                new_callable=AsyncMock,
                return_value="test prompt",
            ),
        ):
            mock_ctx = MagicMock()
            mock_ctx.context_id = "test-ctx"
            mock_ctx_mgr.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_ctx_mgr.return_value.__exit__ = MagicMock(return_value=False)

            mock_stage1.return_value = (
                [{"model": "test", "content": "ok"}],
                {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                {},
            )
            mock_stage2.return_value = ([], {}, {})
            mock_stage3.return_value = ("synthesis", {}, None)
            mock_agg.return_value = []
            mock_build.return_value = {
                "verdict": "pass",
                "confidence": 0.9,
                "rubric_scores": {},
                "blocking_issues": [],
                "rationale": "OK",
            }

            mock_store = MagicMock()
            mock_store.create_verification_directory.return_value = "/tmp/test"

            # Should not raise - backward compatible
            result = await run_verification(request, mock_store)
            assert result["verdict"] == "pass"

    @pytest.mark.asyncio
    async def test_progress_step_count_reflects_model_count(self):
        """Total steps should be based on actual model count, not hardcoded."""
        from llm_council.verification.api import run_verification, VerifyRequest

        progress_calls = []

        async def track_progress(step, total, message):
            progress_calls.append((step, total, message))

        request = VerifyRequest(snapshot_id="abc1234")

        with (
            patch(
                "llm_council.verification.api.stage1_collect_responses_with_status"
            ) as mock_stage1,
            patch("llm_council.verification.api.stage2_collect_rankings") as mock_stage2,
            patch("llm_council.verification.api.stage3_synthesize_final") as mock_stage3,
            patch("llm_council.verification.api.calculate_aggregate_rankings") as mock_agg,
            patch("llm_council.verification.api.build_verification_result") as mock_build,
            patch("llm_council.verification.api.VerificationContextManager") as mock_ctx_mgr,
            patch(
                "llm_council.verification.api._build_verification_prompt",
                new_callable=AsyncMock,
                return_value="test prompt",
            ),
        ):
            mock_ctx = MagicMock()
            mock_ctx.context_id = "test-ctx"
            mock_ctx_mgr.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_ctx_mgr.return_value.__exit__ = MagicMock(return_value=False)

            mock_stage1.return_value = (
                [{"model": "test", "content": "ok"}],
                {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                {},
            )
            mock_stage2.return_value = ([], {}, {})
            mock_stage3.return_value = ("synthesis", {}, None)
            mock_agg.return_value = []
            mock_build.return_value = {
                "verdict": "pass",
                "confidence": 0.9,
                "rubric_scores": {},
                "blocking_issues": [],
                "rationale": "OK",
            }

            mock_store = MagicMock()
            mock_store.create_verification_directory.return_value = "/tmp/test"

            await run_verification(request, mock_store, on_progress=track_progress)

            # Total should NOT be 3 (the old hardcoded value)
            totals = [call[1] for call in progress_calls]
            assert all(t != 3 for t in totals), (
                f"Total steps should not be hardcoded to 3, got: {totals}"
            )

            # Total should reflect model count + stage overhead
            # high tier = 4 models, so total should be > 4
            assert all(t > 3 for t in totals), (
                f"Total should reflect model count + stages, got: {totals}"
            )


class TestMCPVerifyProgressReporting:
    """Test that MCP verify tool bridges progress to run_verification."""

    @pytest.mark.asyncio
    async def test_verify_passes_on_progress_to_run_verification(self):
        """verify tool should pass progress callback to run_verification."""
        from llm_council.mcp_server import verify

        mock_ctx = MagicMock()
        mock_ctx.report_progress = AsyncMock()

        mock_result = {
            "verification_id": "ver_test",
            "verdict": "pass",
            "confidence": 0.9,
            "exit_code": 0,
            "rubric_scores": {},
            "blocking_issues": [],
            "rationale": "OK",
            "transcript_location": ".council/logs/test",
        }

        with (
            patch("llm_council.mcp_server.run_verification") as mock_run,
            patch("llm_council.mcp_server.create_transcript_store"),
        ):
            mock_run.return_value = mock_result

            await verify(snapshot_id="abc1234", ctx=mock_ctx)

            mock_run.assert_called_once()
            call_kwargs = mock_run.call_args
            # Should pass on_progress kwarg
            on_progress_arg = call_kwargs.kwargs.get("on_progress")
            assert on_progress_arg is not None, "verify should pass on_progress to run_verification"

    @pytest.mark.asyncio
    async def test_verify_progress_callback_bridges_to_mcp_context(self):
        """The on_progress callback should call ctx.report_progress."""
        from llm_council.mcp_server import verify

        mock_ctx = MagicMock()
        mock_ctx.report_progress = AsyncMock()

        mock_result = {
            "verification_id": "ver_test",
            "verdict": "pass",
            "confidence": 0.9,
            "exit_code": 0,
            "rubric_scores": {},
            "blocking_issues": [],
            "rationale": "OK",
            "transcript_location": ".council/logs/test",
        }

        with (
            patch("llm_council.mcp_server.run_verification") as mock_run,
            patch("llm_council.mcp_server.create_transcript_store"),
        ):
            # Capture the on_progress callback and invoke it
            async def capture_and_run(request, store, on_progress=None):
                if on_progress:
                    await on_progress(1, 7, "Test message")
                return mock_result

            mock_run.side_effect = capture_and_run

            await verify(snapshot_id="abc1234", ctx=mock_ctx)

            # ctx.report_progress should have been called with the bridged values
            progress_calls = [
                call
                for call in mock_ctx.report_progress.call_args_list
                if call[0][2] == "Test message"
            ]
            assert len(progress_calls) == 1

    @pytest.mark.asyncio
    async def test_verify_works_without_ctx(self):
        """verify should work without MCP context (no progress reporting)."""
        from llm_council.mcp_server import verify

        mock_result = {
            "verification_id": "ver_test",
            "verdict": "pass",
            "confidence": 0.9,
            "exit_code": 0,
            "rubric_scores": {},
            "blocking_issues": [],
            "rationale": "OK",
            "transcript_location": ".council/logs/test",
        }

        with (
            patch("llm_council.mcp_server.run_verification") as mock_run,
            patch("llm_council.mcp_server.create_transcript_store"),
        ):
            mock_run.return_value = mock_result

            # No ctx - should still pass on_progress=None or omit it
            result = await verify(snapshot_id="abc1234")
            assert "pass" in result
