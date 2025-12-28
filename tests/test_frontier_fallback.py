"""TDD tests for ADR-027: Frontier Hard Fallback.

Tests for the hard fallback mechanism that automatically degrades
from frontier tier to high tier when frontier models fail.

This implements Issue #114.
"""

from unittest.mock import patch

import pytest


class TestExecuteWithFallback:
    """Test execute_with_fallback() function."""

    @pytest.mark.asyncio
    @pytest.mark.vcr()
    async def test_returns_response_on_success(self):
        """Should return response when frontier model succeeds."""
        from llm_council.frontier_fallback import execute_with_fallback

        with patch("llm_council.openrouter.OPENROUTER_API_KEY", "test-key"):
            response = await execute_with_fallback(
                query="What is 2+2?",
                frontier_model="openai/gpt-4o",
            )

            assert response is not None
            assert "content" in response

    @pytest.mark.asyncio
    async def test_falls_back_on_timeout(self):
        """Should fall back to high tier on timeout."""
        import asyncio

        from llm_council.frontier_fallback import execute_with_fallback

        with patch("llm_council.frontier_fallback.query_model") as mock_query:
            # First call raises timeout, second succeeds
            mock_query.side_effect = [
                asyncio.TimeoutError("Request timed out"),
                {"content": "Fallback response"},
            ]

            with patch("llm_council.frontier_fallback.get_tier_models") as mock_get_models:
                mock_get_models.return_value = ["anthropic/claude-3.5-sonnet"]

                response = await execute_with_fallback(
                    query="What is 2+2?",
                    frontier_model="openai/gpt-5.2-pro",
                )

                assert response is not None
                assert response.get("content") == "Fallback response"

    @pytest.mark.asyncio
    async def test_falls_back_on_rate_limit(self):
        """Should fall back to high tier on rate limit error."""
        from llm_council.frontier_fallback import RateLimitError, execute_with_fallback

        with patch("llm_council.frontier_fallback.query_model") as mock_query:
            # First call raises rate limit, second succeeds
            mock_query.side_effect = [
                RateLimitError("Rate limit exceeded"),
                {"content": "Fallback response"},
            ]

            with patch("llm_council.frontier_fallback.get_tier_models") as mock_get_models:
                mock_get_models.return_value = ["anthropic/claude-3.5-sonnet"]

                response = await execute_with_fallback(
                    query="What is 2+2?",
                    frontier_model="openai/gpt-5.2-pro",
                )

                assert response is not None
                assert response.get("content") == "Fallback response"

    @pytest.mark.asyncio
    async def test_logs_warning_on_fallback(self):
        """Should log warning when falling back."""
        import asyncio

        from llm_council.frontier_fallback import execute_with_fallback

        with patch("llm_council.frontier_fallback.query_model") as mock_query:
            mock_query.side_effect = [
                asyncio.TimeoutError("Request timed out"),
                {"content": "Fallback response"},
            ]

            with patch("llm_council.frontier_fallback.get_tier_models") as mock_get_models:
                mock_get_models.return_value = ["anthropic/claude-3.5-sonnet"]

                with patch("llm_council.frontier_fallback.logger") as mock_logger:
                    await execute_with_fallback(
                        query="What is 2+2?",
                        frontier_model="openai/gpt-5.2-pro",
                    )

                    # Should have logged a warning
                    mock_logger.warning.assert_called()

    @pytest.mark.asyncio
    async def test_configurable_fallback_tier(self):
        """Should use configurable fallback tier."""
        import asyncio

        from llm_council.frontier_fallback import execute_with_fallback

        with patch("llm_council.frontier_fallback.query_model") as mock_query:
            mock_query.side_effect = [
                asyncio.TimeoutError("Request timed out"),
                {"content": "Balanced response"},
            ]

            with patch("llm_council.frontier_fallback.get_tier_models") as mock_get_models:
                mock_get_models.return_value = ["openai/gpt-4o"]

                await execute_with_fallback(
                    query="What is 2+2?",
                    frontier_model="openai/gpt-5.2-pro",
                    fallback_tier="balanced",  # Custom fallback tier
                )

                # Should have called get_tier_models with "balanced"
                mock_get_models.assert_called_with("balanced")


class TestRateLimitError:
    """Test RateLimitError exception class."""

    def test_rate_limit_error_is_exception(self):
        """RateLimitError should be an Exception subclass."""
        from llm_council.frontier_fallback import RateLimitError

        error = RateLimitError("Rate limit exceeded")
        assert isinstance(error, Exception)
        assert str(error) == "Rate limit exceeded"


class TestAPIError:
    """Test APIError exception class."""

    def test_api_error_is_exception(self):
        """APIError should be an Exception subclass."""
        from llm_council.frontier_fallback import APIError

        error = APIError("API unavailable")
        assert isinstance(error, Exception)
        assert str(error) == "API unavailable"


class TestFallbackConfig:
    """Test fallback configuration."""

    def test_default_fallback_tier_is_high(self):
        """Default fallback tier should be 'high'."""
        from llm_council.frontier_fallback import DEFAULT_FALLBACK_TIER

        assert DEFAULT_FALLBACK_TIER == "high"

    def test_default_frontier_timeout(self):
        """Default frontier timeout should be 300 seconds."""
        from llm_council.frontier_fallback import DEFAULT_FRONTIER_TIMEOUT

        assert DEFAULT_FRONTIER_TIMEOUT == 300


class TestFallbackResult:
    """Test FallbackResult dataclass."""

    def test_fallback_result_has_required_fields(self):
        """FallbackResult should have all required fields."""
        from llm_council.frontier_fallback import FallbackResult

        result = FallbackResult(
            response={"content": "Test"},
            used_fallback=True,
            original_error="Timeout",
            fallback_model="anthropic/claude-3.5-sonnet",
        )

        assert result.response == {"content": "Test"}
        assert result.used_fallback is True
        assert result.original_error == "Timeout"
        assert result.fallback_model == "anthropic/claude-3.5-sonnet"

    def test_fallback_result_without_fallback(self):
        """FallbackResult should work without fallback."""
        from llm_council.frontier_fallback import FallbackResult

        result = FallbackResult(
            response={"content": "Frontier response"},
            used_fallback=False,
            original_error=None,
            fallback_model=None,
        )

        assert result.used_fallback is False
        assert result.original_error is None
