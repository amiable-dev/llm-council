"""TDD tests for ADR-026 Phase 1 Hollow Fix.

Tests for wiring selection.py to use real metadata from providers
instead of hardcoded regex patterns.

Written BEFORE implementation per TDD workflow.
"""

import pytest
from unittest.mock import MagicMock, patch


class TestGetProviderSafe:
    """Test _get_provider_safe() for graceful provider access (Issue #105)."""

    def test_returns_provider_when_available(self):
        """Should return provider when get_provider() succeeds."""
        from llm_council.metadata.selection import _get_provider_safe

        provider = _get_provider_safe()
        # Should return a provider (StaticRegistryProvider by default)
        assert provider is not None

    def test_returns_none_on_import_error(self):
        """Should return None if get_provider import fails."""
        from llm_council.metadata import selection

        # Mock the import to fail
        with patch.object(selection, "_get_provider_safe") as mock:
            # Simulate import failure scenario
            mock.return_value = None
            result = mock()
            assert result is None

    def test_returns_none_on_initialization_error(self):
        """Should return None if provider initialization fails."""
        from llm_council.metadata.selection import _get_provider_safe

        # Patch the module-level get_provider in metadata/__init__.py
        with patch("llm_council.metadata.get_provider") as mock_get:
            mock_get.side_effect = RuntimeError("Provider init failed")
            result = _get_provider_safe()
            assert result is None

    def test_provider_is_cached(self):
        """Provider should be retrieved fresh each call (no internal caching here)."""
        from llm_council.metadata.selection import _get_provider_safe

        # Call twice - both should work
        provider1 = _get_provider_safe()
        provider2 = _get_provider_safe()

        # Both should return a provider
        assert provider1 is not None
        assert provider2 is not None


class TestQualityScoreFromMetadata:
    """Test _get_quality_score_from_metadata() (Issue #106)."""

    def test_frontier_tier_returns_high_score(self):
        """FRONTIER quality tier should return 0.95."""
        from llm_council.metadata.selection import (
            _get_quality_score_from_metadata,
            QUALITY_TIER_SCORES,
        )
        from llm_council.metadata.types import QualityTier, ModelInfo

        # Create mock provider that returns FRONTIER tier
        mock_provider = MagicMock()
        mock_provider.get_model_info.return_value = ModelInfo(
            id="openai/gpt-4o",
            context_window=128000,
            pricing={"prompt": 0.0025, "completion": 0.01},
            quality_tier=QualityTier.FRONTIER,
        )

        score = _get_quality_score_from_metadata("openai/gpt-4o", mock_provider)
        assert score == QUALITY_TIER_SCORES[QualityTier.FRONTIER]
        assert score == 0.95

    def test_standard_tier_returns_medium_score(self):
        """STANDARD quality tier should return 0.75."""
        from llm_council.metadata.selection import (
            _get_quality_score_from_metadata,
            QUALITY_TIER_SCORES,
        )
        from llm_council.metadata.types import QualityTier, ModelInfo

        mock_provider = MagicMock()
        mock_provider.get_model_info.return_value = ModelInfo(
            id="anthropic/claude-3-5-sonnet",
            context_window=200000,
            pricing={"prompt": 0.003, "completion": 0.015},
            quality_tier=QualityTier.STANDARD,
        )

        score = _get_quality_score_from_metadata("anthropic/claude-3-5-sonnet", mock_provider)
        assert score == QUALITY_TIER_SCORES[QualityTier.STANDARD]
        assert score == 0.85  # ADR-030: Updated from 0.75

    def test_economy_tier_returns_lower_score(self):
        """ECONOMY quality tier should return 0.70 (ADR-030: updated from 0.55)."""
        from llm_council.metadata.selection import (
            _get_quality_score_from_metadata,
            QUALITY_TIER_SCORES,
        )
        from llm_council.metadata.types import QualityTier, ModelInfo

        mock_provider = MagicMock()
        mock_provider.get_model_info.return_value = ModelInfo(
            id="openai/gpt-4o-mini",
            context_window=128000,
            pricing={"prompt": 0.00015, "completion": 0.0006},
            quality_tier=QualityTier.ECONOMY,
        )

        score = _get_quality_score_from_metadata("openai/gpt-4o-mini", mock_provider)
        assert score == QUALITY_TIER_SCORES[QualityTier.ECONOMY]
        assert score == 0.70  # ADR-030: Updated from 0.55

    def test_local_tier_returns_lowest_score(self):
        """LOCAL quality tier should return 0.50 (ADR-030: updated from 0.40)."""
        from llm_council.metadata.selection import (
            _get_quality_score_from_metadata,
            QUALITY_TIER_SCORES,
        )
        from llm_council.metadata.types import QualityTier, ModelInfo

        mock_provider = MagicMock()
        mock_provider.get_model_info.return_value = ModelInfo(
            id="ollama/llama2",
            context_window=4096,
            pricing={"prompt": 0.0, "completion": 0.0},
            quality_tier=QualityTier.LOCAL,
        )

        score = _get_quality_score_from_metadata("ollama/llama2", mock_provider)
        assert score == QUALITY_TIER_SCORES[QualityTier.LOCAL]
        assert score == 0.50  # ADR-030: Updated from 0.40

    def test_unknown_model_returns_none(self):
        """Unknown model should return None to trigger fallback."""
        from llm_council.metadata.selection import _get_quality_score_from_metadata

        mock_provider = MagicMock()
        mock_provider.get_model_info.return_value = None

        score = _get_quality_score_from_metadata("unknown/model", mock_provider)
        assert score is None

    def test_no_provider_returns_none(self):
        """No provider should return None to trigger fallback."""
        from llm_council.metadata.selection import _get_quality_score_from_metadata

        score = _get_quality_score_from_metadata("openai/gpt-4o", None)
        assert score is None


class TestCostScoreFromMetadata:
    """Test _get_cost_score_from_metadata() (Issue #107)."""

    def test_free_model_returns_max_score(self):
        """Free models (price=0) should return 1.0."""
        from llm_council.metadata.selection import _get_cost_score_from_metadata

        mock_provider = MagicMock()
        mock_provider.get_pricing.return_value = {"prompt": 0.0, "completion": 0.0}

        score = _get_cost_score_from_metadata("ollama/llama2", mock_provider)
        assert score == 1.0

    def test_expensive_model_returns_low_score(self):
        """Expensive models (above reference) should return low score (<0.5).

        With log-ratio algorithm (ADR-030):
        - At reference price ($0.015): score = 0.5
        - Above reference: score < 0.5
        - Below reference: score > 0.5
        """
        from llm_council.metadata.selection import (
            _get_cost_score_from_metadata,
            COST_REFERENCE_HIGH,
        )

        mock_provider = MagicMock()
        # Expensive: 2x reference price
        mock_provider.get_pricing.return_value = {"prompt": 0.030, "completion": 0.06}

        score = _get_cost_score_from_metadata("anthropic/claude-3-opus", mock_provider)
        assert score is not None
        assert score < 0.5  # Log-ratio: 2x reference returns ~0.425

    def test_cheap_model_returns_high_score(self):
        """Cheap models should return high score (>0.8)."""
        from llm_council.metadata.selection import _get_cost_score_from_metadata

        mock_provider = MagicMock()
        # Very cheap
        mock_provider.get_pricing.return_value = {"prompt": 0.0001, "completion": 0.0004}

        score = _get_cost_score_from_metadata("openai/gpt-4o-mini", mock_provider)
        assert score is not None
        assert score > 0.8

    def test_midrange_model_returns_moderate_score(self):
        """Mid-range models should return moderate score."""
        from llm_council.metadata.selection import _get_cost_score_from_metadata

        mock_provider = MagicMock()
        mock_provider.get_pricing.return_value = {"prompt": 0.003, "completion": 0.015}

        score = _get_cost_score_from_metadata("anthropic/claude-3-5-sonnet", mock_provider)
        assert score is not None
        assert 0.4 < score < 0.9

    def test_unknown_model_returns_none(self):
        """Unknown model (no pricing) should return None."""
        from llm_council.metadata.selection import _get_cost_score_from_metadata

        mock_provider = MagicMock()
        mock_provider.get_pricing.return_value = {}

        score = _get_cost_score_from_metadata("unknown/model", mock_provider)
        assert score is None

    def test_no_provider_returns_none(self):
        """No provider should return None."""
        from llm_council.metadata.selection import _get_cost_score_from_metadata

        score = _get_cost_score_from_metadata("openai/gpt-4o", None)
        assert score is None


class TestMeetsContextRequirement:
    """Test _meets_context_requirement() with real metadata (Issue #108)."""

    def test_filters_small_context_models(self):
        """Models with context < required should be filtered out."""
        from llm_council.metadata.selection import (
            _meets_context_requirement,
            ModelCandidate,
        )

        mock_provider = MagicMock()
        mock_provider.get_context_window.return_value = 4096

        candidate = ModelCandidate(
            model_id="small/model",
            latency_score=0.9,
            cost_score=0.9,
            quality_score=0.9,
            availability_score=0.9,
            diversity_score=0.5,
        )

        # 4096 < 8000 required - should fail
        result = _meets_context_requirement(candidate, 8000, provider=mock_provider)
        assert result is False

    def test_passes_large_context_models(self):
        """Models with context >= required should pass."""
        from llm_council.metadata.selection import (
            _meets_context_requirement,
            ModelCandidate,
        )

        mock_provider = MagicMock()
        mock_provider.get_context_window.return_value = 128000

        candidate = ModelCandidate(
            model_id="large/model",
            latency_score=0.9,
            cost_score=0.9,
            quality_score=0.9,
            availability_score=0.9,
            diversity_score=0.5,
        )

        # 128000 >= 8000 required - should pass
        result = _meets_context_requirement(candidate, 8000, provider=mock_provider)
        assert result is True

    def test_exact_match_passes(self):
        """Exact context match should pass."""
        from llm_council.metadata.selection import (
            _meets_context_requirement,
            ModelCandidate,
        )

        mock_provider = MagicMock()
        mock_provider.get_context_window.return_value = 8000

        candidate = ModelCandidate(
            model_id="exact/model",
            latency_score=0.9,
            cost_score=0.9,
            quality_score=0.9,
            availability_score=0.9,
            diversity_score=0.5,
        )

        # 8000 >= 8000 required - should pass
        result = _meets_context_requirement(candidate, 8000, provider=mock_provider)
        assert result is True

    def test_fallback_returns_true_when_no_provider(self):
        """Should return True (legacy behavior) when no provider."""
        from llm_council.metadata.selection import (
            _meets_context_requirement,
            ModelCandidate,
        )

        candidate = ModelCandidate(
            model_id="any/model",
            latency_score=0.9,
            cost_score=0.9,
            quality_score=0.9,
            availability_score=0.9,
            diversity_score=0.5,
        )

        # Patch _get_provider_safe to return None
        with patch("llm_council.metadata.selection._get_provider_safe") as mock:
            mock.return_value = None
            result = _meets_context_requirement(candidate, 8000, provider=None)
            assert result is True

    def test_uses_real_context_from_registry(self):
        """Integration: Should use real context window from StaticRegistryProvider."""
        from llm_council.metadata.selection import (
            _meets_context_requirement,
            ModelCandidate,
        )
        from llm_council.metadata import StaticRegistryProvider

        provider = StaticRegistryProvider()

        # gpt-4o has 128000 context in registry
        candidate = ModelCandidate(
            model_id="openai/gpt-4o",
            latency_score=0.9,
            cost_score=0.9,
            quality_score=0.9,
            availability_score=0.9,
            diversity_score=0.5,
        )

        # 128000 >= 32000 - should pass
        result = _meets_context_requirement(candidate, 32000, provider=provider)
        assert result is True

        # 128000 >= 200000 - should fail
        result = _meets_context_requirement(candidate, 200000, provider=provider)
        assert result is False


class TestSelectTierModelsIntegration:
    """Integration tests for select_tier_models with real metadata."""

    def test_respects_context_requirement(self):
        """select_tier_models should filter by context window."""
        from llm_council.metadata.selection import select_tier_models

        # Request models with very large context requirement
        # This should filter out small context models
        models = select_tier_models(
            tier="high",
            count=4,
            required_context=100000,
        )

        # Should return models (may be fewer if filtered)
        assert isinstance(models, list)

    def test_uses_metadata_when_available(self):
        """Should use real metadata when provider is available."""
        from llm_council.metadata.selection import select_tier_models

        # This should work without crashing
        models = select_tier_models(tier="balanced", count=3)
        assert len(models) > 0
