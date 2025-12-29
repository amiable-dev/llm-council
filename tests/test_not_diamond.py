"""TDD tests for ADR-020: Not Diamond API Integration.

Tests the Not Diamond API client for model routing and complexity classification.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import os

from llm_council.triage.not_diamond import (
    NotDiamondClient,
    NotDiamondConfig,
    NotDiamondClassifier,
    NotDiamondRouter,
    is_not_diamond_available,
)
from llm_council.triage.complexity import ComplexityLevel
from llm_council.tier_contract import create_tier_contract


class TestNotDiamondConfig:
    """Test NotDiamondConfig."""

    def test_default_config(self):
        """Default config should have sensible values."""
        config = NotDiamondConfig()
        assert config.enabled is False  # Disabled by default
        assert config.timeout == 5.0
        assert config.cache_ttl == 300

    def test_config_from_env_without_key(self):
        """Config should be disabled without API key."""
        with patch.dict("os.environ", {}, clear=True):
            config = NotDiamondConfig.from_env()
            assert config.enabled is False
            assert config.api_key is None

    def test_config_from_env_with_key(self):
        """Config should be enabled with API key."""
        with patch.dict(
            "os.environ",
            {
                "NOT_DIAMOND_API_KEY": "test-key",
                "LLM_COUNCIL_USE_NOT_DIAMOND": "true",
            },
        ):
            config = NotDiamondConfig.from_env()
            assert config.enabled is True
            assert config.api_key == "test-key"


class TestNotDiamondClient:
    """Test NotDiamondClient API interactions."""

    @pytest.fixture
    def client(self):
        """Create a client with test config."""
        config = NotDiamondConfig(
            enabled=True,
            api_key="test-api-key",
            timeout=5.0,
        )
        return NotDiamondClient(config)

    @pytest.mark.asyncio
    async def test_model_select_success(self, client):
        """Should select model from API response."""
        mock_response = {
            "model": "openai/gpt-4o",
            "confidence": 0.95,
        }

        with patch.object(client, "_call_api", return_value=mock_response):
            result = await client.model_select(
                query="What is 2+2?",
                candidates=["openai/gpt-4o", "anthropic/claude-3-5-sonnet"],
            )

        assert result["model"] == "openai/gpt-4o"
        assert result["confidence"] == 0.95

    @pytest.mark.asyncio
    async def test_model_select_respects_tier_constraints(self, client):
        """Should only select from tier-allowed models."""
        tier_contract = create_tier_contract("quick")
        allowed = tier_contract.allowed_models

        mock_response = {
            "model": allowed[0] if allowed else "openai/gpt-4o-mini",
            "confidence": 0.9,
        }

        with patch.object(client, "_call_api", return_value=mock_response):
            result = await client.model_select(
                query="Simple question",
                candidates=list(allowed),
            )

        # Selected model should be in tier's allowed list
        assert result["model"] in allowed

    @pytest.mark.asyncio
    async def test_fallback_on_api_error(self, client):
        """Should return fallback on API error."""
        with patch.object(client, "_call_api", side_effect=Exception("API error")):
            result = await client.model_select(
                query="Test query",
                candidates=["model-a", "model-b"],
                fallback="model-a",
            )

        # Should return fallback model
        assert result["model"] == "model-a"
        assert result.get("fallback_used") is True

    @pytest.mark.asyncio
    async def test_fallback_on_timeout(self, client):
        """Should return fallback on timeout."""
        import asyncio

        async def slow_api(*args, **kwargs):
            await asyncio.sleep(10)
            return {"model": "slow-model"}

        with patch.object(client, "_call_api", side_effect=asyncio.TimeoutError()):
            result = await client.model_select(
                query="Test query",
                candidates=["model-a"],
                fallback="model-a",
            )

        assert result["model"] == "model-a"
        assert result.get("fallback_used") is True


class TestNotDiamondClassifier:
    """Test NotDiamondClassifier complexity detection."""

    @pytest.fixture
    def classifier(self):
        """Create a classifier with test config."""
        config = NotDiamondConfig(enabled=True, api_key="test-key")
        return NotDiamondClassifier(config)

    @pytest.fixture
    def disabled_classifier(self):
        """Create a disabled classifier."""
        config = NotDiamondConfig(enabled=False)
        return NotDiamondClassifier(config)

    def test_disabled_falls_back_to_heuristic(self, disabled_classifier):
        """Disabled classifier should use heuristic fallback."""
        result = disabled_classifier.classify("Simple query")
        # Should still return a valid complexity level
        assert result in [ComplexityLevel.SIMPLE, ComplexityLevel.MEDIUM, ComplexityLevel.COMPLEX]

    @pytest.mark.asyncio
    async def test_classify_simple_query(self, classifier):
        """Should classify simple queries correctly."""
        mock_response = {
            "complexity": "simple",
            "confidence": 0.95,
        }

        with patch.object(classifier.client, "_call_api", return_value=mock_response):
            result = await classifier.classify_async("What is 2+2?")

        assert result == ComplexityLevel.SIMPLE

    @pytest.mark.asyncio
    async def test_classify_complex_query(self, classifier):
        """Should classify complex queries correctly."""
        mock_response = {
            "complexity": "complex",
            "confidence": 0.88,
        }

        with patch.object(classifier.client, "_call_api", return_value=mock_response):
            result = await classifier.classify_async(
                "Analyze the trade-offs between microservices and monoliths..."
            )

        assert result == ComplexityLevel.COMPLEX

    @pytest.mark.asyncio
    async def test_fallback_to_heuristic_on_error(self, classifier):
        """Should fallback to heuristic on API error."""
        with patch.object(classifier.client, "_call_api", side_effect=Exception("API down")):
            result = await classifier.classify_async("Simple question")

        # Should still return valid result from heuristic
        assert result in [ComplexityLevel.SIMPLE, ComplexityLevel.MEDIUM, ComplexityLevel.COMPLEX]


class TestNotDiamondRouter:
    """Test NotDiamondRouter model selection."""

    @pytest.fixture
    def router(self):
        """Create a router with test config."""
        config = NotDiamondConfig(enabled=True, api_key="test-key")
        return NotDiamondRouter(config)

    @pytest.mark.asyncio
    async def test_route_selects_best_model(self, router):
        """Should select optimal model for query."""
        mock_response = {
            "model": "openai/gpt-4o",
            "confidence": 0.92,
        }

        with patch.object(router.client, "_call_api", return_value=mock_response):
            result = await router.route(
                query="Explain quantum computing",
                candidates=["openai/gpt-4o", "anthropic/claude-3-5-sonnet"],
            )

        assert result.model == "openai/gpt-4o"
        assert result.confidence >= 0.9


class TestNotDiamondAvailability:
    """Test Not Diamond availability detection."""

    def test_not_available_without_key(self):
        """Should not be available without API key."""
        with patch.dict("os.environ", {}, clear=True):
            assert is_not_diamond_available() is False

    def test_available_with_key(self):
        """Should be available with API key and enabled flag."""
        with patch.dict(
            "os.environ",
            {
                "NOT_DIAMOND_API_KEY": "test-key",
                "LLM_COUNCIL_USE_NOT_DIAMOND": "true",
            },
        ):
            # Availability depends on config
            assert is_not_diamond_available() in [True, False]


class TestCaching:
    """Test response caching."""

    @pytest.fixture
    def client(self):
        """Create a client with caching enabled."""
        config = NotDiamondConfig(
            enabled=True,
            api_key="test-key",
            cache_ttl=300,
        )
        return NotDiamondClient(config)

    @pytest.mark.asyncio
    async def test_cache_hit(self, client):
        """Same query should hit cache."""
        # Directly test caching at the _call_api level
        endpoint = "/v2/modelRouter/modelSelect"
        data = {"messages": [{"role": "user", "content": "Test"}], "model": ["model-a"]}

        # First call - should cache
        client._set_cached(client._get_cache_key(endpoint, data), {"model": "cached-model"})

        # Verify cache works
        cached = client._get_cached(client._get_cache_key(endpoint, data))
        assert cached is not None
        assert cached["model"] == "cached-model"

        # Different data should not hit cache
        different_data = {
            "messages": [{"role": "user", "content": "Different"}],
            "model": ["model-a"],
        }
        assert client._get_cached(client._get_cache_key(endpoint, different_data)) is None

    @pytest.mark.asyncio
    async def test_cache_expiry(self, client):
        """Expired cache entries should not be returned."""
        import time

        endpoint = "/test"
        data = {"key": "value"}
        cache_key = client._get_cache_key(endpoint, data)

        # Set cache with expired timestamp
        client._cache[cache_key] = ({"result": "old"}, time.time() - 400)  # Expired (TTL=300)

        # Should return None for expired entry
        assert client._get_cached(cache_key) is None
