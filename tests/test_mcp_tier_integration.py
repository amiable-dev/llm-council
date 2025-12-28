"""Tests for MCP server tier contract integration (ADR-022).

TDD: Write these tests first, then implement the integration.

ADR-032: Updated to use tier_contract instead of config.py.
"""

import pytest
from unittest.mock import patch, AsyncMock

# Skip all tests in this module if mcp is not installed
pytest.importorskip("mcp", reason="MCP package not installed (optional dependency)")


class TestConsultCouncilWithTierContract:
    """Test that consult_council uses TierContract."""

    @pytest.mark.asyncio
    async def test_consult_council_creates_tier_contract(self):
        """consult_council should create TierContract from confidence level."""
        from llm_council.mcp_server import consult_council

        with patch("llm_council.mcp_server.run_council_with_fallback") as mock_council:
            mock_council.return_value = {
                "synthesis": "Test response",
                "metadata": {"status": "complete"},
                "model_responses": {},
            }

            await consult_council("test query", confidence="quick")

            # Verify tier_contract was passed
            call_kwargs = mock_council.call_args.kwargs
            assert "tier_contract" in call_kwargs
            assert call_kwargs["tier_contract"].tier == "quick"

    @pytest.mark.asyncio
    async def test_quick_tier_uses_quick_models(self):
        """Quick confidence should use quick tier models."""
        from llm_council.mcp_server import consult_council
        from llm_council.tier_contract import _get_tier_model_pools

        with patch("llm_council.mcp_server.run_council_with_fallback") as mock_council:
            mock_council.return_value = {
                "synthesis": "Test response",
                "metadata": {"status": "complete"},
                "model_responses": {},
            }

            await consult_council("test query", confidence="quick")

            call_kwargs = mock_council.call_args.kwargs
            tier_contract = call_kwargs["tier_contract"]
            pools = _get_tier_model_pools()
            assert tier_contract.allowed_models == pools["quick"]

    @pytest.mark.asyncio
    async def test_high_tier_uses_high_models(self):
        """High confidence should use high tier models."""
        from llm_council.mcp_server import consult_council
        from llm_council.tier_contract import _get_tier_model_pools

        with patch("llm_council.mcp_server.run_council_with_fallback") as mock_council:
            mock_council.return_value = {
                "synthesis": "Test response",
                "metadata": {"status": "complete"},
                "model_responses": {},
            }

            await consult_council("test query", confidence="high")

            call_kwargs = mock_council.call_args.kwargs
            tier_contract = call_kwargs["tier_contract"]
            pools = _get_tier_model_pools()
            assert tier_contract.allowed_models == pools["high"]

    @pytest.mark.asyncio
    async def test_reasoning_tier_uses_reasoning_models(self):
        """Reasoning confidence should use reasoning tier models."""
        from llm_council.mcp_server import consult_council
        from llm_council.tier_contract import _get_tier_model_pools

        with patch("llm_council.mcp_server.run_council_with_fallback") as mock_council:
            mock_council.return_value = {
                "synthesis": "Test response",
                "metadata": {"status": "complete"},
                "model_responses": {},
            }

            await consult_council("test query", confidence="reasoning")

            call_kwargs = mock_council.call_args.kwargs
            tier_contract = call_kwargs["tier_contract"]
            pools = _get_tier_model_pools()
            assert tier_contract.allowed_models == pools["reasoning"]


class TestHealthCheckWithTierPools:
    """Test that health check includes tier pool information."""

    @pytest.mark.asyncio
    async def test_health_check_includes_tier_pools(self):
        """council_health_check should show tier pool configuration."""
        from llm_council.mcp_server import council_health_check

        with patch("llm_council.mcp_server.query_model_with_status") as mock_query:
            mock_query.return_value = {"status": "ok", "content": "test"}

            result = await council_health_check()

            # Should include tier information
            assert "tier_pools" in result or "tiers" in result or "quick" in result

    @pytest.mark.asyncio
    async def test_health_check_shows_tier_model_counts(self):
        """Health check should show model count per tier."""
        from llm_council.mcp_server import council_health_check
        from llm_council.tier_contract import _get_tier_model_pools

        TIER_MODEL_POOLS = _get_tier_model_pools()

        with patch("llm_council.mcp_server.query_model_with_status") as mock_query:
            mock_query.return_value = {"status": "ok", "content": "test"}

            result = await council_health_check()

            # Should include model counts for tiers
            result_str = str(result)
            assert any(
                str(len(TIER_MODEL_POOLS[tier])) in result_str
                for tier in ["quick", "balanced", "high"]
            )


class TestTierContractTimeoutsUsed:
    """Test that tier contract timeouts are used in MCP calls."""

    @pytest.mark.asyncio
    async def test_quick_tier_uses_quick_timeout(self):
        """Quick tier should use quick timeout values."""
        from llm_council.mcp_server import consult_council
        from llm_council.tier_contract import get_tier_timeout

        quick_timeout = get_tier_timeout("quick")

        with patch("llm_council.mcp_server.run_council_with_fallback") as mock_council:
            mock_council.return_value = {
                "synthesis": "Test response",
                "metadata": {"status": "complete"},
                "model_responses": {},
            }

            await consult_council("test query", confidence="quick")

            call_kwargs = mock_council.call_args.kwargs
            # synthesis_deadline should match tier total timeout
            assert call_kwargs["synthesis_deadline"] == quick_timeout["total"]

    @pytest.mark.asyncio
    async def test_reasoning_tier_uses_reasoning_timeout(self):
        """Reasoning tier should use reasoning timeout values."""
        from llm_council.mcp_server import consult_council
        from llm_council.tier_contract import get_tier_timeout

        reasoning_timeout = get_tier_timeout("reasoning")

        with patch("llm_council.mcp_server.run_council_with_fallback") as mock_council:
            mock_council.return_value = {
                "synthesis": "Test response",
                "metadata": {"status": "complete"},
                "model_responses": {},
            }

            await consult_council("test query", confidence="reasoning")

            call_kwargs = mock_council.call_args.kwargs
            # synthesis_deadline should match tier total timeout
            assert call_kwargs["synthesis_deadline"] == reasoning_timeout["total"]


class TestResultIncludesTierInfo:
    """Test that MCP results include tier information."""

    @pytest.mark.asyncio
    async def test_result_includes_tier_info_when_available(self):
        """MCP result should include tier info from council metadata."""
        from llm_council.mcp_server import consult_council

        with patch("llm_council.mcp_server.run_council_with_fallback") as mock_council:
            mock_council.return_value = {
                "synthesis": "Test response",
                "metadata": {"status": "complete", "tier": "quick"},
                "model_responses": {},
            }

            result = await consult_council("test query", confidence="quick")

            # Result should mention the tier used
            assert "quick" in result.lower() or "tier" in result.lower()
