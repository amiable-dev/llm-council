"""Tests for MCP verify tool (ADR-034 A5).

TDD tests for the verify tool added to the MCP server.
"""

import json
import re
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


def extract_json_from_verify_result(result: str) -> dict:
    """Extract JSON from verify tool output.

    The verify tool returns formatted markdown with embedded JSON in a details block:
    ```
    ...formatted content...

    ---

    <details>
    <summary>Raw JSON</summary>

    ```json
    {...}
    ```
    </details>
    ```

    For error cases, it returns pure JSON.

    Args:
        result: The raw output from the verify tool

    Returns:
        Parsed JSON dictionary
    """
    # Try to extract JSON from the details block first
    match = re.search(r"```json\s*\n(.*?)\n```", result, re.DOTALL)
    if match:
        return json.loads(match.group(1))

    # Fallback: try to parse as pure JSON (error cases)
    return json.loads(result)


class TestMCPVerifyToolRegistration:
    """Test that the verify tool is properly registered with FastMCP."""

    @pytest.mark.asyncio
    async def test_verify_tool_is_registered(self):
        """verify tool should be registered on the MCP server."""
        from llm_council.mcp_server import mcp

        # FastMCP uses list_tools() to enumerate registered tools
        tools = await mcp.list_tools()
        tool_names = [t.name for t in tools]
        assert "verify" in tool_names, f"verify not in tools: {tool_names}"

    @pytest.mark.asyncio
    async def test_verify_tool_has_correct_schema(self):
        """verify tool should accept snapshot_id and optional parameters."""
        from llm_council.mcp_server import mcp

        tools = await mcp.list_tools()
        verify_tool = next((t for t in tools if t.name == "verify"), None)
        assert verify_tool is not None, "verify tool not found"

        # Check the input schema for required/optional params
        schema = verify_tool.inputSchema
        properties = schema.get("properties", {})
        required = schema.get("required", [])

        # Required parameter
        assert "snapshot_id" in properties, "snapshot_id parameter required"
        assert "snapshot_id" in required, "snapshot_id should be required"

        # Optional parameters
        assert "target_paths" in properties, "target_paths parameter expected"
        assert "rubric_focus" in properties, "rubric_focus parameter expected"
        assert "confidence_threshold" in properties, "confidence_threshold parameter expected"

    @pytest.mark.asyncio
    async def test_verify_tool_has_docstring(self):
        """verify tool should have a descriptive docstring."""
        from llm_council.mcp_server import mcp

        tools = await mcp.list_tools()
        verify_tool = next((t for t in tools if t.name == "verify"), None)
        assert verify_tool is not None
        assert verify_tool.description is not None
        assert len(verify_tool.description) > 50, "Description should be descriptive"


class TestMCPVerifyToolExecution:
    """Test verify tool execution and response format."""

    @pytest.fixture
    def mock_verification_result(self):
        """Standard mock verification result."""
        return {
            "verification_id": "ver_abc123",
            "verdict": "pass",
            "confidence": 0.85,
            "exit_code": 0,
            "rubric_scores": {
                "correctness": 9.0,
                "completeness": 8.5,
                "code_quality": 8.0,
            },
            "blocking_issues": [],
            "rationale": "All verification checks passed. Code is well-structured.",
            "transcript_location": ".council/logs/2025-12-31T10-30-00-abc123",
        }

    @pytest.mark.asyncio
    async def test_verify_returns_json_string(self, mock_verification_result):
        """verify tool should return a JSON-formatted string."""
        from llm_council.mcp_server import verify

        with (
            patch("llm_council.mcp_server.run_verification") as mock_run,
            patch("llm_council.mcp_server.create_transcript_store"),
        ):
            mock_run.return_value = mock_verification_result

            result = await verify(snapshot_id="abc1234")

            # Should be valid JSON (extracted from formatted output)
            parsed = extract_json_from_verify_result(result)
            assert isinstance(parsed, dict)

    @pytest.mark.asyncio
    async def test_verify_includes_verdict(self, mock_verification_result):
        """verify tool response should include verdict."""
        from llm_council.mcp_server import verify

        with (
            patch("llm_council.mcp_server.run_verification") as mock_run,
            patch("llm_council.mcp_server.create_transcript_store"),
        ):
            mock_run.return_value = mock_verification_result

            result = await verify(snapshot_id="abc1234")
            parsed = extract_json_from_verify_result(result)

            assert "verdict" in parsed
            assert parsed["verdict"] == "pass"

    @pytest.mark.asyncio
    async def test_verify_includes_exit_code(self, mock_verification_result):
        """verify tool response should include exit_code for CI/CD."""
        from llm_council.mcp_server import verify

        with (
            patch("llm_council.mcp_server.run_verification") as mock_run,
            patch("llm_council.mcp_server.create_transcript_store"),
        ):
            mock_run.return_value = mock_verification_result

            result = await verify(snapshot_id="abc1234")
            parsed = extract_json_from_verify_result(result)

            assert "exit_code" in parsed
            assert parsed["exit_code"] == 0

    @pytest.mark.asyncio
    async def test_verify_includes_confidence(self, mock_verification_result):
        """verify tool response should include confidence score."""
        from llm_council.mcp_server import verify

        with (
            patch("llm_council.mcp_server.run_verification") as mock_run,
            patch("llm_council.mcp_server.create_transcript_store"),
        ):
            mock_run.return_value = mock_verification_result

            result = await verify(snapshot_id="abc1234")
            parsed = extract_json_from_verify_result(result)

            assert "confidence" in parsed
            assert 0.0 <= parsed["confidence"] <= 1.0

    @pytest.mark.asyncio
    async def test_verify_includes_rationale(self, mock_verification_result):
        """verify tool response should include rationale for transparency."""
        from llm_council.mcp_server import verify

        with (
            patch("llm_council.mcp_server.run_verification") as mock_run,
            patch("llm_council.mcp_server.create_transcript_store"),
        ):
            mock_run.return_value = mock_verification_result

            result = await verify(snapshot_id="abc1234")
            parsed = extract_json_from_verify_result(result)

            assert "rationale" in parsed
            assert len(parsed["rationale"]) > 0

    @pytest.mark.asyncio
    async def test_verify_includes_transcript_location(self, mock_verification_result):
        """verify tool response should include transcript_location for audit."""
        from llm_council.mcp_server import verify

        with (
            patch("llm_council.mcp_server.run_verification") as mock_run,
            patch("llm_council.mcp_server.create_transcript_store"),
        ):
            mock_run.return_value = mock_verification_result

            result = await verify(snapshot_id="abc1234")
            parsed = extract_json_from_verify_result(result)

            assert "transcript_location" in parsed
            assert ".council/logs" in parsed["transcript_location"]

    @pytest.mark.asyncio
    async def test_verify_passes_target_paths(self, mock_verification_result):
        """verify tool should pass target_paths to run_verification."""
        from llm_council.mcp_server import verify

        with (
            patch("llm_council.mcp_server.run_verification") as mock_run,
            patch("llm_council.mcp_server.create_transcript_store"),
        ):
            mock_run.return_value = mock_verification_result
            target_paths = ["src/main.py", "tests/test_main.py"]

            await verify(snapshot_id="abc1234", target_paths=target_paths)

            mock_run.assert_called_once()
            # run_verification takes (request, store) - check request object
            call_args = mock_run.call_args
            request_obj = call_args[0][0]  # First positional arg is the request
            assert request_obj.target_paths == target_paths

    @pytest.mark.asyncio
    async def test_verify_passes_rubric_focus(self, mock_verification_result):
        """verify tool should pass rubric_focus to run_verification."""
        from llm_council.mcp_server import verify

        with (
            patch("llm_council.mcp_server.run_verification") as mock_run,
            patch("llm_council.mcp_server.create_transcript_store"),
        ):
            mock_run.return_value = mock_verification_result

            await verify(snapshot_id="abc1234", rubric_focus="security")

            mock_run.assert_called_once()
            call_args = mock_run.call_args
            request_obj = call_args[0][0]
            assert request_obj.rubric_focus == "security"

    @pytest.mark.asyncio
    async def test_verify_passes_confidence_threshold(self, mock_verification_result):
        """verify tool should pass confidence_threshold to run_verification."""
        from llm_council.mcp_server import verify

        with (
            patch("llm_council.mcp_server.run_verification") as mock_run,
            patch("llm_council.mcp_server.create_transcript_store"),
        ):
            mock_run.return_value = mock_verification_result

            await verify(snapshot_id="abc1234", confidence_threshold=0.9)

            mock_run.assert_called_once()
            call_args = mock_run.call_args
            request_obj = call_args[0][0]
            assert request_obj.confidence_threshold == 0.9


class TestMCPVerifyToolErrorHandling:
    """Test verify tool error handling."""

    @pytest.mark.asyncio
    async def test_verify_handles_invalid_snapshot(self):
        """verify tool should handle invalid snapshot_id gracefully."""
        from llm_council.mcp_server import verify
        from llm_council.verification.context import InvalidSnapshotError

        with (
            patch("llm_council.mcp_server.run_verification") as mock_run,
            patch("llm_council.mcp_server.create_transcript_store"),
        ):
            mock_run.side_effect = InvalidSnapshotError("Invalid snapshot ID")

            result = await verify(snapshot_id="abc1234")
            parsed = extract_json_from_verify_result(result)

            assert "error" in parsed
            assert parsed["exit_code"] == 2  # UNCLEAR for errors

    @pytest.mark.asyncio
    async def test_verify_handles_verification_failure(self):
        """verify tool should handle verification failures with exit_code 1."""
        from llm_council.mcp_server import verify

        with (
            patch("llm_council.mcp_server.run_verification") as mock_run,
            patch("llm_council.mcp_server.create_transcript_store"),
        ):
            mock_run.return_value = {
                "verification_id": "ver_fail123",
                "verdict": "fail",
                "confidence": 0.75,
                "exit_code": 1,
                "rubric_scores": {"correctness": 4.0},
                "blocking_issues": [{"severity": "high", "description": "Critical bug found"}],
                "rationale": "Verification failed due to critical issues.",
                "transcript_location": ".council/logs/2025-12-31T10-30-00-fail",
            }

            result = await verify(snapshot_id="abc1234")
            parsed = extract_json_from_verify_result(result)

            assert parsed["verdict"] == "fail"
            assert parsed["exit_code"] == 1
            assert len(parsed["blocking_issues"]) > 0

    @pytest.mark.asyncio
    async def test_verify_handles_api_timeout(self):
        """verify tool should handle API timeouts gracefully."""
        from llm_council.mcp_server import verify
        import asyncio

        with (
            patch("llm_council.mcp_server.run_verification") as mock_run,
            patch("llm_council.mcp_server.create_transcript_store"),
        ):
            mock_run.side_effect = asyncio.TimeoutError("Verification timed out")

            result = await verify(snapshot_id="abc1234")
            parsed = extract_json_from_verify_result(result)

            assert "error" in parsed
            assert parsed["exit_code"] == 2  # UNCLEAR for timeouts

    @pytest.mark.asyncio
    async def test_verify_handles_unexpected_error(self):
        """verify tool should handle unexpected errors gracefully."""
        from llm_council.mcp_server import verify

        with (
            patch("llm_council.mcp_server.run_verification") as mock_run,
            patch("llm_council.mcp_server.create_transcript_store"),
        ):
            mock_run.side_effect = RuntimeError("Unexpected internal error")

            result = await verify(snapshot_id="abc1234")
            parsed = extract_json_from_verify_result(result)

            assert "error" in parsed
            assert parsed["exit_code"] == 2


class TestMCPVerifyToolContextIntegration:
    """Test verify tool integration with MCP context for progress reporting."""

    @pytest.mark.asyncio
    async def test_verify_reports_progress(self):
        """verify tool should report progress via MCP context when available."""
        from llm_council.mcp_server import verify

        mock_ctx = MagicMock()
        mock_ctx.report_progress = AsyncMock()

        mock_result = {
            "verification_id": "ver_prog123",
            "verdict": "pass",
            "confidence": 0.9,
            "exit_code": 0,
            "rubric_scores": {},
            "blocking_issues": [],
            "rationale": "Test passed",
            "transcript_location": ".council/logs/test",
        }

        with (
            patch("llm_council.mcp_server.run_verification") as mock_run,
            patch("llm_council.mcp_server.create_transcript_store"),
        ):
            mock_run.return_value = mock_result

            await verify(snapshot_id="abc1234", ctx=mock_ctx)

            # Progress should be reported at least once
            assert mock_ctx.report_progress.call_count >= 1

    @pytest.mark.asyncio
    async def test_verify_works_without_context(self):
        """verify tool should work fine without MCP context."""
        from llm_council.mcp_server import verify

        mock_result = {
            "verification_id": "ver_noctx",
            "verdict": "pass",
            "confidence": 0.9,
            "exit_code": 0,
            "rubric_scores": {},
            "blocking_issues": [],
            "rationale": "Test passed",
            "transcript_location": ".council/logs/test",
        }

        with (
            patch("llm_council.mcp_server.run_verification") as mock_run,
            patch("llm_council.mcp_server.create_transcript_store"),
        ):
            mock_run.return_value = mock_result

            # No ctx passed - should work without error
            result = await verify(snapshot_id="abc1234")
            parsed = extract_json_from_verify_result(result)
            assert parsed["verdict"] == "pass"
