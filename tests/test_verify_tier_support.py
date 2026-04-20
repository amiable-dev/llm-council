"""Tests for tier support in verify/review skills (Issue #325).

TDD: Tests written first, then implementation follows.

The verify tool and run_verification() should support tier-appropriate
model selection via TierContract, matching the pattern used by consult_council.
"""

import json
import re
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


def extract_json_from_verify_result(result: str) -> dict:
    """Extract JSON from verify tool output."""
    match = re.search(r"```json\s*\n(.*?)\n```", result, re.DOTALL)
    if match:
        return json.loads(match.group(1))
    return json.loads(result)


class TestVerifyRequestTierField:
    """Test that VerifyRequest model accepts a tier parameter."""

    def test_verify_request_accepts_tier(self):
        """VerifyRequest should accept an optional tier field."""
        from llm_council.verification.api import VerifyRequest

        request = VerifyRequest(
            snapshot_id="abc1234",
            tier="high",
        )
        assert request.tier == "high"

    def test_verify_request_tier_defaults_to_balanced(self):
        """VerifyRequest tier should default to 'balanced'."""
        from llm_council.verification.api import VerifyRequest

        request = VerifyRequest(snapshot_id="abc1234")
        assert request.tier == "balanced"

    def test_verify_request_accepts_valid_tiers(self):
        """VerifyRequest should accept all valid tier values."""
        from llm_council.verification.api import VerifyRequest

        for tier in ["quick", "balanced", "high", "reasoning"]:
            request = VerifyRequest(snapshot_id="abc1234", tier=tier)
            assert request.tier == tier

    def test_verify_request_rejects_invalid_tier(self):
        """VerifyRequest should reject invalid tier values."""
        from llm_council.verification.api import VerifyRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            VerifyRequest(snapshot_id="abc1234", tier="invalid_tier")


class TestRunVerificationTierSupport:
    """Test that run_verification uses tier-appropriate models."""

    @pytest.mark.asyncio
    async def test_run_verification_uses_tier_models(self):
        """run_verification should use models from the tier's model pool."""
        from llm_council.verification.api import run_verification, VerifyRequest
        from llm_council.tier_contract import _get_tier_model_pools

        balanced_models = _get_tier_model_pools()["balanced"]

        request = VerifyRequest(
            snapshot_id="abc1234",
            tier="balanced",
        )

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
            # Setup mocks
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

            await run_verification(request, mock_store)

            # Verify stage1 was called with tier models
            mock_stage1.assert_called_once()
            call_kwargs = mock_stage1.call_args
            # The models kwarg should match balanced tier
            models_arg = call_kwargs.kwargs.get("models") or call_kwargs[1].get("models")
            assert models_arg == balanced_models

    @pytest.mark.asyncio
    async def test_run_verification_default_tier_uses_balanced_models(self):
        """Default tier (balanced) should use balanced tier model pool."""
        from llm_council.verification.api import run_verification, VerifyRequest
        from llm_council.tier_contract import _get_tier_model_pools

        balanced_models = _get_tier_model_pools()["balanced"]

        request = VerifyRequest(snapshot_id="abc1234")  # No tier specified

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

            await run_verification(request, mock_store)

            mock_stage1.assert_called_once()
            call_kwargs = mock_stage1.call_args
            models_arg = call_kwargs.kwargs.get("models") or call_kwargs[1].get("models")
            assert models_arg == balanced_models

    @pytest.mark.asyncio
    async def test_run_verification_uses_tier_timeout(self):
        """run_verification should use tier-appropriate per-model timeout."""
        from llm_council.verification.api import run_verification, VerifyRequest
        from llm_council.tier_contract import get_tier_timeout

        quick_timeout = get_tier_timeout("quick")

        request = VerifyRequest(snapshot_id="abc1234", tier="quick")

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

            await run_verification(request, mock_store)

            mock_stage1.assert_called_once()
            call_kwargs = mock_stage1.call_args
            timeout_arg = call_kwargs.kwargs.get("timeout") or call_kwargs[1].get("timeout")
            assert timeout_arg == quick_timeout["per_model"]


class TestMCPVerifyToolTierParameter:
    """Test that the MCP verify tool accepts and passes tier parameter."""

    @pytest.mark.asyncio
    async def test_verify_tool_accepts_tier_parameter(self):
        """verify tool should accept optional tier parameter."""
        from llm_council.mcp_server import mcp

        tools = await mcp.list_tools()
        verify_tool = next((t for t in tools if t.name == "verify"), None)
        assert verify_tool is not None

        schema = verify_tool.inputSchema
        properties = schema.get("properties", {})
        assert "tier" in properties, "tier parameter should be in verify tool schema"

    @pytest.mark.asyncio
    async def test_verify_tool_passes_tier_to_request(self):
        """verify tool should pass tier to VerifyRequest."""
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

            await verify(snapshot_id="abc1234", tier="balanced")

            mock_run.assert_called_once()
            request_obj = mock_run.call_args[0][0]
            assert request_obj.tier == "balanced"

    @pytest.mark.asyncio
    async def test_verify_tool_tier_defaults_to_balanced(self):
        """verify tool should default tier to 'balanced' when not specified."""
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

            await verify(snapshot_id="abc1234")

            mock_run.assert_called_once()
            request_obj = mock_run.call_args[0][0]
            assert request_obj.tier == "balanced"
