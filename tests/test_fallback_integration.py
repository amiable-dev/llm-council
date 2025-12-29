"""TDD tests for ADR-027: Fallback Integration (Issue #118).

Tests for integrating execute_with_fallback into stage1 execution,
including event emission for FRONTIER_FALLBACK_TRIGGERED.

These tests implement the RED phase of TDD - they should FAIL initially.
"""

import pytest

from llm_council.layer_contracts import (
    LayerEventType,
    emit_layer_event,
    get_layer_events,
    clear_layer_events,
)


class TestFallbackEventEmission:
    """Test FRONTIER_FALLBACK_TRIGGERED event emission."""

    def setup_method(self):
        """Clear events before each test."""
        clear_layer_events()

    def teardown_method(self):
        """Clear events after each test."""
        clear_layer_events()

    def test_emit_fallback_event(self):
        """FRONTIER_FALLBACK_TRIGGERED event should be emittable."""
        from llm_council.frontier_fallback import emit_fallback_event

        emit_fallback_event(
            frontier_model="openai/gpt-5-preview",
            fallback_model="anthropic/claude-3.5-sonnet",
            reason="timeout",
        )

        events = get_layer_events()
        assert len(events) == 1
        assert events[0].event_type == LayerEventType.FRONTIER_FALLBACK_TRIGGERED
        assert events[0].data["model_id"] == "openai/gpt-5-preview"
        assert events[0].data["fallback_model"] == "anthropic/claude-3.5-sonnet"
        assert events[0].data["reason"] == "timeout"

    def test_fallback_event_includes_all_reasons(self):
        """Fallback events should support various failure reasons."""
        from llm_council.frontier_fallback import emit_fallback_event

        reasons = ["timeout", "rate_limit", "api_error"]
        for reason in reasons:
            clear_layer_events()
            emit_fallback_event(
                frontier_model="openai/gpt-5-preview",
                fallback_model="anthropic/claude-3.5-sonnet",
                reason=reason,
            )
            events = get_layer_events()
            assert events[0].data["reason"] == reason


class TestShouldUseFallbackWrapper:
    """Test helper to determine if fallback wrapper should be used."""

    def test_should_use_fallback_for_frontier(self):
        """Frontier tier should use fallback wrapper."""
        from llm_council.frontier_fallback import should_use_fallback_wrapper
        from llm_council.tier_contract import create_tier_contract

        tier_contract = create_tier_contract("frontier")
        assert should_use_fallback_wrapper(tier_contract) is True

    def test_should_not_use_fallback_for_high(self):
        """High tier should not use fallback wrapper."""
        from llm_council.frontier_fallback import should_use_fallback_wrapper
        from llm_council.tier_contract import create_tier_contract

        tier_contract = create_tier_contract("high")
        assert should_use_fallback_wrapper(tier_contract) is False

    def test_should_not_use_fallback_when_none(self):
        """No tier_contract should not use fallback wrapper."""
        from llm_council.frontier_fallback import should_use_fallback_wrapper

        assert should_use_fallback_wrapper(None) is False


class TestExecuteWithFallbackDetailed:
    """Test execute_with_fallback_detailed with event emission."""

    def setup_method(self):
        """Clear events before each test."""
        clear_layer_events()

    def teardown_method(self):
        """Clear events after each test."""
        clear_layer_events()

    @pytest.mark.asyncio
    async def test_execute_success_no_event(self):
        """Successful execution should not emit fallback event."""
        from llm_council.frontier_fallback import execute_with_fallback_detailed
        from unittest.mock import AsyncMock, patch

        with patch("llm_council.frontier_fallback.query_model") as mock_query:
            mock_query.return_value = {"content": "Success!"}

            result = await execute_with_fallback_detailed(
                query="Test query",
                frontier_model="openai/gpt-5-preview",
            )

            assert result.used_fallback is False
            events = get_layer_events()
            fallback_events = [
                e for e in events if e.event_type == LayerEventType.FRONTIER_FALLBACK_TRIGGERED
            ]
            assert len(fallback_events) == 0

    @pytest.mark.asyncio
    async def test_execute_fallback_emits_event(self):
        """Fallback should emit FRONTIER_FALLBACK_TRIGGERED event."""
        from llm_council.frontier_fallback import (
            execute_with_fallback_detailed,
        )
        import asyncio
        from unittest.mock import AsyncMock, patch

        with patch("llm_council.frontier_fallback.query_model") as mock_query:
            # First call raises timeout, second call succeeds
            mock_query.side_effect = [
                asyncio.TimeoutError("Frontier timeout"),
                {"content": "Fallback response"},
            ]

            with patch("llm_council.frontier_fallback.get_tier_models") as mock_tier:
                mock_tier.return_value = ["anthropic/claude-3.5-sonnet"]

                result = await execute_with_fallback_detailed(
                    query="Test query",
                    frontier_model="openai/gpt-5-preview",
                )

                assert result.used_fallback is True

                events = get_layer_events()
                fallback_events = [
                    e for e in events if e.event_type == LayerEventType.FRONTIER_FALLBACK_TRIGGERED
                ]
                assert len(fallback_events) == 1
                assert fallback_events[0].data["model_id"] == "openai/gpt-5-preview"
                assert fallback_events[0].data["reason"] == "timeout"


class TestFallbackIntegrationEndToEnd:
    """End-to-end tests for fallback integration."""

    def setup_method(self):
        """Clear events before each test."""
        clear_layer_events()

    def teardown_method(self):
        """Clear events after each test."""
        clear_layer_events()

    def test_get_fallback_tier_from_config(self):
        """Should be able to get fallback tier from config."""
        from llm_council.frontier_fallback import get_fallback_tier_from_config

        # Default fallback tier is "high"
        tier = get_fallback_tier_from_config()
        assert tier == "high"

    def test_fallback_config_from_tier_contract(self):
        """Tier contract should include fallback configuration."""
        from llm_council.tier_contract import create_tier_contract

        contract = create_tier_contract("frontier")

        # Frontier tier should have extended timeout
        # Per ADR-027: frontier timeout is 300s
        assert contract.per_model_timeout_ms >= 120000  # At least 2 minutes
