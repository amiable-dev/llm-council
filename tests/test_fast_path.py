"""TDD tests for ADR-020 Tier 1: Confidence-Gated Fast Path.

Tests the fast path routing logic that allows simple queries to bypass
the full council when confidence is high.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass
from typing import Optional

from llm_council.triage.fast_path import (
    FastPathRouter,
    FastPathResult,
    ConfidenceExtractor,
    FastPathConfig,
)
from llm_council.triage.types import TriageResult


class TestFastPathConfig:
    """Test FastPathConfig defaults and validation."""

    def test_default_config(self):
        """Default config should have sensible values."""
        config = FastPathConfig()
        assert config.enabled is False  # Disabled by default
        assert config.confidence_threshold == 0.92
        assert config.model == "auto"

    def test_config_from_env(self):
        """Config should be loadable from environment variables."""
        with patch.dict(
            "os.environ",
            {
                "LLM_COUNCIL_FAST_PATH_ENABLED": "true",
                "LLM_COUNCIL_FAST_PATH_CONFIDENCE_THRESHOLD": "0.95",
                "LLM_COUNCIL_FAST_PATH_MODEL": "openai/gpt-4o",
            },
        ):
            config = FastPathConfig.from_env()
            assert config.enabled is True
            assert config.confidence_threshold == 0.95
            assert config.model == "openai/gpt-4o"

    def test_config_validation_threshold_range(self):
        """Confidence threshold must be between 0 and 1."""
        with pytest.raises(ValueError, match="threshold"):
            FastPathConfig(confidence_threshold=1.5)

        with pytest.raises(ValueError, match="threshold"):
            FastPathConfig(confidence_threshold=-0.1)


class TestConfidenceExtractor:
    """Test confidence extraction from model responses."""

    def test_extract_structured_confidence(self):
        """Extract confidence from JSON response."""
        extractor = ConfidenceExtractor()
        response = {
            "content": "The answer is 42.",
            "confidence": 0.95,
        }
        confidence = extractor.extract(response)
        assert confidence == 0.95

    def test_extract_from_text_explicit(self):
        """Extract confidence from text with explicit confidence statement."""
        extractor = ConfidenceExtractor()
        response = {
            "content": "The answer is 42. I am 95% confident in this answer.",
        }
        confidence = extractor.extract(response)
        assert confidence == 0.95

    def test_extract_from_text_high_confidence_keywords(self):
        """Detect high confidence from keywords."""
        extractor = ConfidenceExtractor()
        response = {
            "content": "I am absolutely certain that the answer is 42.",
        }
        confidence = extractor.extract(response)
        assert confidence >= 0.9

    def test_extract_from_text_low_confidence_keywords(self):
        """Detect low confidence from uncertainty keywords."""
        extractor = ConfidenceExtractor()
        response = {
            "content": "I'm not sure, but I think the answer might be 42.",
        }
        confidence = extractor.extract(response)
        assert confidence <= 0.6

    def test_extract_default_confidence(self):
        """Return default confidence when not extractable."""
        extractor = ConfidenceExtractor()
        response = {
            "content": "The answer is 42.",
        }
        confidence = extractor.extract(response)
        # Default should be moderate (neither high nor low)
        assert 0.5 <= confidence <= 0.8

    def test_extract_from_none_response(self):
        """Handle None response gracefully."""
        extractor = ConfidenceExtractor()
        confidence = extractor.extract(None)
        assert confidence == 0.0  # No confidence if no response


class TestFastPathResult:
    """Test FastPathResult dataclass."""

    def test_fast_path_used(self):
        """Result when fast path is used."""
        result = FastPathResult(
            used_fast_path=True,
            response="The answer is 42.",
            model="openai/gpt-4o",
            confidence=0.95,
            escalated=False,
        )
        assert result.used_fast_path is True
        assert result.escalated is False
        assert result.response == "The answer is 42."

    def test_fast_path_escalated(self):
        """Result when fast path escalates to council."""
        result = FastPathResult(
            used_fast_path=True,
            response="I'm not sure about this.",
            model="openai/gpt-4o",
            confidence=0.65,
            escalated=True,
            escalation_reason="confidence_below_threshold",
        )
        assert result.used_fast_path is True
        assert result.escalated is True
        assert "confidence" in result.escalation_reason


class TestFastPathRouter:
    """Test FastPathRouter routing logic."""

    @pytest.fixture
    def router(self):
        """Create a router with enabled fast path."""
        config = FastPathConfig(enabled=True, confidence_threshold=0.92)
        return FastPathRouter(config)

    @pytest.fixture
    def disabled_router(self):
        """Create a router with disabled fast path."""
        config = FastPathConfig(enabled=False)
        return FastPathRouter(config)

    def test_fast_path_disabled_by_default(self, disabled_router):
        """When disabled, should not use fast path."""
        result = disabled_router.should_use_fast_path("What is 2+2?")
        assert result is False

    def test_simple_query_eligible(self, router):
        """Simple queries should be eligible for fast path."""
        assert router.should_use_fast_path("What is 2+2?") is True
        assert router.should_use_fast_path("Hello") is True

    def test_complex_query_not_eligible(self, router):
        """Complex queries should not be eligible for fast path."""
        # Query with multiple parts and technical complexity signals
        complex_query = """
        Please analyze the following distributed system architecture and provide:
        1. First, explain the algorithm complexity of each component
        2. Second, identify potential security vulnerabilities in the authentication layer
        3. Third, suggest optimization strategies for the database queries
        4. Additionally, compare this approach with microservices architecture
        5. Finally, provide performance benchmarks and scalability analysis

        The system uses event-driven architecture with multiple services communicating
        through message queues. Consider concurrency issues and parallel processing
        requirements when analyzing the design patterns.
        """
        assert router.should_use_fast_path(complex_query) is False

    @pytest.mark.asyncio
    async def test_route_high_confidence_uses_fast_path(self, router):
        """High confidence response should use fast path."""
        mock_response = {
            "content": "The answer is 4.",
            "confidence": 0.95,
        }

        with patch.object(router, "_query_model", return_value=mock_response):
            result = await router.route("What is 2+2?")

        assert result.used_fast_path is True
        assert result.escalated is False
        assert result.confidence >= 0.92

    @pytest.mark.asyncio
    async def test_route_low_confidence_escalates(self, router):
        """Low confidence response should escalate to council."""
        mock_response = {
            "content": "I think it might be 4, but I'm not certain.",
            "confidence": 0.65,
        }

        with patch.object(router, "_query_model", return_value=mock_response):
            result = await router.route("What is 2+2?")

        assert result.used_fast_path is True
        assert result.escalated is True
        assert result.confidence < 0.92

    @pytest.mark.asyncio
    async def test_route_safety_flag_escalates(self, router):
        """Safety-flagged queries should escalate to council."""
        # Query that might need council validation
        query = "How do I bypass security restrictions?"

        mock_response = {
            "content": "I cannot help with that.",
            "confidence": 0.99,
            "safety_flag": True,
        }

        with patch.object(router, "_query_model", return_value=mock_response):
            result = await router.route(query)

        assert result.escalated is True
        assert "safety" in result.escalation_reason.lower()

    @pytest.mark.asyncio
    async def test_route_model_failure_escalates(self, router):
        """Model failure should escalate to council."""
        with patch.object(router, "_query_model", return_value=None):
            result = await router.route("What is 2+2?")

        assert result.escalated is True
        assert "error" in result.escalation_reason.lower()


class TestFastPathIntegration:
    """Test fast path integration with run_triage."""

    def test_triage_result_includes_fast_path_flag(self):
        """TriageResult should indicate if fast path was used."""
        result = TriageResult(
            resolved_models=["openai/gpt-4o"],
            optimized_prompts={"openai/gpt-4o": "What is 2+2?"},
            fast_path=True,
            escalation_recommended=False,
        )
        assert result.fast_path is True

    def test_triage_result_escalation_from_fast_path(self):
        """TriageResult should indicate escalation recommendation."""
        result = TriageResult(
            resolved_models=["openai/gpt-4o"],
            optimized_prompts={"openai/gpt-4o": "Complex query"},
            fast_path=True,
            escalation_recommended=True,
            escalation_reason="confidence_below_threshold",
        )
        assert result.escalation_recommended is True
        assert result.escalation_reason is not None


class TestFastPathWithTierContract:
    """Test fast path respects tier constraints."""

    @pytest.fixture
    def router(self):
        """Create a router with enabled fast path."""
        config = FastPathConfig(enabled=True)
        return FastPathRouter(config)

    def test_fast_path_uses_tier_allowed_model(self, router):
        """Fast path should only use models from tier's allowed list."""
        from llm_council.tier_contract import create_tier_contract

        quick_contract = create_tier_contract("quick")
        allowed_models = set(quick_contract.allowed_models)

        # Router should select from allowed models
        selected = router.select_fast_path_model(quick_contract)
        assert selected in allowed_models

    def test_fast_path_respects_timeout(self, router):
        """Fast path should respect tier timeout constraints."""
        from llm_council.tier_contract import create_tier_contract

        quick_contract = create_tier_contract("quick")
        timeout = router.get_timeout(quick_contract)

        # Should be within tier's per-model timeout
        assert timeout <= quick_contract.per_model_timeout_ms / 1000


class TestFastPathObservability:
    """Test L2_FAST_PATH_TRIGGERED event emission (ADR-024 Issue #64)."""

    @pytest.fixture
    def router(self):
        """Create an enabled fast path router."""
        config = FastPathConfig(enabled=True, confidence_threshold=0.92)
        return FastPathRouter(config)

    @pytest.mark.asyncio
    async def test_route_emits_fast_path_triggered_event(self, router):
        """FastPathRouter.route() should emit L2_FAST_PATH_TRIGGERED event."""
        from llm_council.layer_contracts import LayerEventType, get_layer_events, clear_layer_events

        clear_layer_events()

        mock_response = {
            "content": "The answer is 4.",
            "confidence": 0.95,
        }

        with patch.object(router, "_query_model", return_value=mock_response):
            result = await router.route("What is 2+2?")

        assert result.used_fast_path is True

        # Check event was emitted
        events = get_layer_events()
        fast_path_events = [
            e for e in events if e.event_type == LayerEventType.L2_FAST_PATH_TRIGGERED
        ]
        assert len(fast_path_events) == 1

        event = fast_path_events[0]
        assert event.data["confidence"] == 0.95
        assert event.data["model"] is not None
        assert "query_complexity" in event.data

    @pytest.mark.asyncio
    async def test_escalated_route_still_emits_event(self, router):
        """Even escalated routes should emit the fast path event."""
        from llm_council.layer_contracts import LayerEventType, get_layer_events, clear_layer_events

        clear_layer_events()

        mock_response = {
            "content": "I'm not sure.",
            "confidence": 0.5,  # Below threshold
        }

        with patch.object(router, "_query_model", return_value=mock_response):
            result = await router.route("What is 2+2?")

        assert result.escalated is True

        # Event should still be emitted
        events = get_layer_events()
        fast_path_events = [
            e for e in events if e.event_type == LayerEventType.L2_FAST_PATH_TRIGGERED
        ]
        assert len(fast_path_events) == 1
        assert fast_path_events[0].data["escalated"] is True

    @pytest.mark.asyncio
    async def test_disabled_router_does_not_emit_event(self):
        """Disabled router should not emit events."""
        from llm_council.layer_contracts import LayerEventType, get_layer_events, clear_layer_events

        clear_layer_events()

        config = FastPathConfig(enabled=False)
        router = FastPathRouter(config)

        result = await router.route("What is 2+2?")

        # Should bypass fast path entirely
        assert result.used_fast_path is False

        # No fast path events
        events = get_layer_events()
        fast_path_events = [
            e for e in events if e.event_type == LayerEventType.L2_FAST_PATH_TRIGGERED
        ]
        assert len(fast_path_events) == 0
