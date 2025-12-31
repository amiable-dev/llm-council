"""Tests for MCP audit tool (ADR-034 A6).

TDD tests for the audit tool added to the MCP server.
"""

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestMCPAuditToolRegistration:
    """Test that the audit tool is properly registered with FastMCP."""

    @pytest.mark.asyncio
    async def test_audit_tool_is_registered(self):
        """audit tool should be registered on the MCP server."""
        from llm_council.mcp_server import mcp

        tools = await mcp.list_tools()
        tool_names = [t.name for t in tools]
        assert "audit" in tool_names, f"audit not in tools: {tool_names}"

    @pytest.mark.asyncio
    async def test_audit_tool_has_correct_schema(self):
        """audit tool should accept verification_id and optional parameters."""
        from llm_council.mcp_server import mcp

        tools = await mcp.list_tools()
        audit_tool = next((t for t in tools if t.name == "audit"), None)
        assert audit_tool is not None, "audit tool not found"

        schema = audit_tool.inputSchema
        properties = schema.get("properties", {})

        # verification_id should be a parameter (can be optional for listing)
        assert "verification_id" in properties, "verification_id parameter expected"

        # Optional parameters for filtering
        assert "validate_integrity" in properties, "validate_integrity parameter expected"

    @pytest.mark.asyncio
    async def test_audit_tool_has_docstring(self):
        """audit tool should have a descriptive docstring."""
        from llm_council.mcp_server import mcp

        tools = await mcp.list_tools()
        audit_tool = next((t for t in tools if t.name == "audit"), None)
        assert audit_tool is not None
        assert audit_tool.description is not None
        assert len(audit_tool.description) > 50, "Description should be descriptive"


class TestMCPAuditToolRetrieveById:
    """Test audit tool retrieval by verification_id."""

    @pytest.fixture
    def mock_transcript_data(self):
        """Standard mock transcript data."""
        return {
            "request": {
                "snapshot_id": "abc1234",
                "target_paths": ["src/main.py"],
                "rubric_focus": "security",
                "confidence_threshold": 0.7,
                "timestamp": "2025-12-31T10:30:00",
            },
            "result": {
                "verification_id": "ver_abc123",
                "verdict": "pass",
                "confidence": 0.85,
                "exit_code": 0,
                "rationale": "All checks passed.",
            },
        }

    @pytest.mark.asyncio
    async def test_audit_returns_json_string(self, mock_transcript_data):
        """audit tool should return a JSON-formatted string."""
        from llm_council.mcp_server import audit

        with patch("llm_council.mcp_server.create_transcript_store") as mock_create:
            mock_store = MagicMock()
            mock_store.read_all_stages.return_value = mock_transcript_data
            mock_store.compute_integrity_hash.return_value = "abc123hash"
            mock_create.return_value = mock_store

            result = await audit(verification_id="ver_abc123")

            parsed = json.loads(result)
            assert isinstance(parsed, dict)

    @pytest.mark.asyncio
    async def test_audit_includes_verification_id(self, mock_transcript_data):
        """audit tool response should include verification_id."""
        from llm_council.mcp_server import audit

        with patch("llm_council.mcp_server.create_transcript_store") as mock_create:
            mock_store = MagicMock()
            mock_store.read_all_stages.return_value = mock_transcript_data
            mock_store.compute_integrity_hash.return_value = "abc123hash"
            mock_create.return_value = mock_store

            result = await audit(verification_id="ver_abc123")
            parsed = json.loads(result)

            assert "verification_id" in parsed
            assert parsed["verification_id"] == "ver_abc123"

    @pytest.mark.asyncio
    async def test_audit_includes_stages(self, mock_transcript_data):
        """audit tool response should include stage data."""
        from llm_council.mcp_server import audit

        with patch("llm_council.mcp_server.create_transcript_store") as mock_create:
            mock_store = MagicMock()
            mock_store.read_all_stages.return_value = mock_transcript_data
            mock_store.compute_integrity_hash.return_value = "abc123hash"
            mock_create.return_value = mock_store

            result = await audit(verification_id="ver_abc123")
            parsed = json.loads(result)

            assert "stages" in parsed
            assert "request" in parsed["stages"]
            assert "result" in parsed["stages"]

    @pytest.mark.asyncio
    async def test_audit_includes_integrity_hash(self, mock_transcript_data):
        """audit tool response should include integrity hash."""
        from llm_council.mcp_server import audit

        with patch("llm_council.mcp_server.create_transcript_store") as mock_create:
            mock_store = MagicMock()
            mock_store.read_all_stages.return_value = mock_transcript_data
            mock_store.compute_integrity_hash.return_value = "abc123hash"
            mock_create.return_value = mock_store

            result = await audit(verification_id="ver_abc123")
            parsed = json.loads(result)

            assert "integrity_hash" in parsed
            assert parsed["integrity_hash"] == "abc123hash"


class TestMCPAuditToolIntegrityValidation:
    """Test audit tool integrity validation."""

    @pytest.fixture
    def mock_transcript_data(self):
        """Standard mock transcript data."""
        return {
            "request": {"snapshot_id": "abc1234"},
            "result": {"verdict": "pass"},
        }

    @pytest.mark.asyncio
    async def test_audit_validates_integrity_when_requested(self, mock_transcript_data):
        """audit tool should validate integrity when validate_integrity=True."""
        from llm_council.mcp_server import audit

        with patch("llm_council.mcp_server.create_transcript_store") as mock_create:
            mock_store = MagicMock()
            mock_store.read_all_stages.return_value = mock_transcript_data
            mock_store.compute_integrity_hash.return_value = "expected_hash"
            mock_store.validate_integrity.return_value = None  # No exception = valid
            mock_create.return_value = mock_store

            result = await audit(
                verification_id="ver_abc123",
                validate_integrity=True,
                expected_hash="expected_hash",
            )
            parsed = json.loads(result)

            assert "integrity_valid" in parsed
            assert parsed["integrity_valid"] is True
            mock_store.validate_integrity.assert_called_once()

    @pytest.mark.asyncio
    async def test_audit_reports_integrity_failure(self, mock_transcript_data):
        """audit tool should report when integrity validation fails."""
        from llm_council.mcp_server import audit
        from llm_council.verification.transcript import TranscriptIntegrityError

        with patch("llm_council.mcp_server.create_transcript_store") as mock_create:
            mock_store = MagicMock()
            mock_store.read_all_stages.return_value = mock_transcript_data
            mock_store.compute_integrity_hash.return_value = "actual_hash"
            mock_store.validate_integrity.side_effect = TranscriptIntegrityError("Hash mismatch")
            mock_create.return_value = mock_store

            result = await audit(
                verification_id="ver_abc123",
                validate_integrity=True,
                expected_hash="expected_hash",
            )
            parsed = json.loads(result)

            assert "integrity_valid" in parsed
            assert parsed["integrity_valid"] is False
            assert "integrity_error" in parsed


class TestMCPAuditToolListing:
    """Test audit tool listing functionality."""

    @pytest.fixture
    def mock_verification_list(self):
        """Mock list of verifications."""
        return [
            {
                "verification_id": "ver_001",
                "directory": "2025-12-31T10-30-00-ver_001",
                "path": "/path/to/ver_001",
                "timestamp": "2025-12-31T10-30-00",
            },
            {
                "verification_id": "ver_002",
                "directory": "2025-12-31T11-00-00-ver_002",
                "path": "/path/to/ver_002",
                "timestamp": "2025-12-31T11-00-00",
            },
        ]

    @pytest.mark.asyncio
    async def test_audit_lists_all_when_no_id(self, mock_verification_list):
        """audit tool should list all verifications when no ID provided."""
        from llm_council.mcp_server import audit

        with patch("llm_council.mcp_server.create_transcript_store") as mock_create:
            mock_store = MagicMock()
            mock_store.list_verifications.return_value = mock_verification_list
            mock_create.return_value = mock_store

            result = await audit()
            parsed = json.loads(result)

            assert "verifications" in parsed
            assert len(parsed["verifications"]) == 2
            assert parsed["verifications"][0]["verification_id"] == "ver_001"

    @pytest.mark.asyncio
    async def test_audit_list_includes_count(self, mock_verification_list):
        """audit tool listing should include total count."""
        from llm_council.mcp_server import audit

        with patch("llm_council.mcp_server.create_transcript_store") as mock_create:
            mock_store = MagicMock()
            mock_store.list_verifications.return_value = mock_verification_list
            mock_create.return_value = mock_store

            result = await audit()
            parsed = json.loads(result)

            assert "total_count" in parsed
            assert parsed["total_count"] == 2


class TestMCPAuditToolErrorHandling:
    """Test audit tool error handling."""

    @pytest.mark.asyncio
    async def test_audit_handles_not_found(self):
        """audit tool should handle verification not found gracefully."""
        from llm_council.mcp_server import audit
        from llm_council.verification.transcript import TranscriptNotFoundError

        with patch("llm_council.mcp_server.create_transcript_store") as mock_create:
            mock_store = MagicMock()
            mock_store.read_all_stages.side_effect = TranscriptNotFoundError("Not found")
            mock_create.return_value = mock_store

            result = await audit(verification_id="nonexistent")
            parsed = json.loads(result)

            assert "error" in parsed
            assert "not found" in parsed["error"].lower()

    @pytest.mark.asyncio
    async def test_audit_handles_unexpected_error(self):
        """audit tool should handle unexpected errors gracefully."""
        from llm_council.mcp_server import audit

        with patch("llm_council.mcp_server.create_transcript_store") as mock_create:
            mock_store = MagicMock()
            mock_store.read_all_stages.side_effect = RuntimeError("Unexpected error")
            mock_create.return_value = mock_store

            result = await audit(verification_id="ver_abc123")
            parsed = json.loads(result)

            assert "error" in parsed


class TestMCPAuditToolContextIntegration:
    """Test audit tool integration with MCP context."""

    @pytest.mark.asyncio
    async def test_audit_works_without_context(self):
        """audit tool should work fine without MCP context."""
        from llm_council.mcp_server import audit

        mock_data = {"request": {"snapshot_id": "abc"}, "result": {"verdict": "pass"}}

        with patch("llm_council.mcp_server.create_transcript_store") as mock_create:
            mock_store = MagicMock()
            mock_store.read_all_stages.return_value = mock_data
            mock_store.compute_integrity_hash.return_value = "hash123"
            mock_create.return_value = mock_store

            result = await audit(verification_id="ver_abc123")
            parsed = json.loads(result)
            assert "verification_id" in parsed
