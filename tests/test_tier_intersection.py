"""TDD tests for ADR-027: Tier Intersection Logic (Issue #119).

Tests for `resolve_tier_intersection()` function which handles models
belonging to multiple tiers (e.g., o1-preview is both reasoning and frontier).

These tests implement the RED phase of TDD - they should FAIL initially.
"""

import pytest


class TestModelInfoIsPreview:
    """Test is_preview field on ModelInfo dataclass."""

    def test_model_info_has_is_preview_field(self):
        """ModelInfo dataclass should have is_preview field."""
        from llm_council.metadata.types import ModelInfo

        info = ModelInfo(
            id="openai/o1-preview",
            context_window=128000,
            is_preview=True,
        )
        assert hasattr(info, "is_preview")
        assert info.is_preview is True

    def test_model_info_is_preview_defaults_to_false(self):
        """ModelInfo.is_preview should default to False."""
        from llm_council.metadata.types import ModelInfo

        info = ModelInfo(
            id="openai/gpt-4o",
            context_window=128000,
        )
        assert info.is_preview is False


class TestModelInfoSupportsReasoning:
    """Test supports_reasoning field on ModelInfo dataclass."""

    def test_model_info_has_supports_reasoning_field(self):
        """ModelInfo dataclass should have supports_reasoning field."""
        from llm_council.metadata.types import ModelInfo

        info = ModelInfo(
            id="openai/o1",
            context_window=200000,
            supports_reasoning=True,
        )
        assert hasattr(info, "supports_reasoning")
        assert info.supports_reasoning is True

    def test_model_info_supports_reasoning_defaults_to_false(self):
        """ModelInfo.supports_reasoning should default to False."""
        from llm_council.metadata.types import ModelInfo

        info = ModelInfo(
            id="openai/gpt-4o",
            context_window=128000,
        )
        assert info.supports_reasoning is False


class TestResolveTierIntersection:
    """Test resolve_tier_intersection() function."""

    def test_frontier_tier_includes_preview_models(self):
        """Frontier tier accepts all capable models including previews."""
        from llm_council.metadata.intersection import resolve_tier_intersection
        from llm_council.metadata.types import ModelInfo, QualityTier

        preview_model = ModelInfo(
            id="openai/gpt-5-preview",
            context_window=200000,
            quality_tier=QualityTier.FRONTIER,
            is_preview=True,
        )

        result = resolve_tier_intersection(
            requested_tier="frontier",
            model_info=preview_model,
        )
        assert result is True

    def test_frontier_tier_includes_non_preview_frontier_models(self):
        """Frontier tier includes stable frontier-quality models."""
        from llm_council.metadata.intersection import resolve_tier_intersection
        from llm_council.metadata.types import ModelInfo, QualityTier

        stable_frontier = ModelInfo(
            id="anthropic/claude-opus-4.5",
            context_window=200000,
            quality_tier=QualityTier.FRONTIER,
            is_preview=False,
        )

        result = resolve_tier_intersection(
            requested_tier="frontier",
            model_info=stable_frontier,
        )
        assert result is True

    def test_frontier_tier_excludes_non_frontier_quality(self):
        """Frontier tier excludes models without FRONTIER quality tier."""
        from llm_council.metadata.intersection import resolve_tier_intersection
        from llm_council.metadata.types import ModelInfo, QualityTier

        standard_model = ModelInfo(
            id="openai/gpt-4o-mini",
            context_window=128000,
            quality_tier=QualityTier.STANDARD,
            is_preview=False,
        )

        result = resolve_tier_intersection(
            requested_tier="frontier",
            model_info=standard_model,
        )
        assert result is False

    def test_reasoning_tier_excludes_preview_by_default(self):
        """Reasoning tier excludes preview models unless allow_preview=True."""
        from llm_council.metadata.intersection import resolve_tier_intersection
        from llm_council.metadata.types import ModelInfo, QualityTier

        reasoning_preview = ModelInfo(
            id="openai/o1-preview",
            context_window=200000,
            quality_tier=QualityTier.FRONTIER,
            is_preview=True,
            supports_reasoning=True,
        )

        # Default: exclude preview
        result = resolve_tier_intersection(
            requested_tier="reasoning",
            model_info=reasoning_preview,
            allow_preview=False,
        )
        assert result is False

    def test_reasoning_tier_includes_preview_when_allowed(self):
        """Reasoning tier includes preview models when allow_preview=True."""
        from llm_council.metadata.intersection import resolve_tier_intersection
        from llm_council.metadata.types import ModelInfo, QualityTier

        reasoning_preview = ModelInfo(
            id="openai/o1-preview",
            context_window=200000,
            quality_tier=QualityTier.FRONTIER,
            is_preview=True,
            supports_reasoning=True,
        )

        # Explicit allow: include preview
        result = resolve_tier_intersection(
            requested_tier="reasoning",
            model_info=reasoning_preview,
            allow_preview=True,
        )
        assert result is True

    def test_reasoning_tier_includes_stable_reasoning_models(self):
        """Reasoning tier includes stable models with reasoning support."""
        from llm_council.metadata.intersection import resolve_tier_intersection
        from llm_council.metadata.types import ModelInfo, QualityTier

        stable_reasoning = ModelInfo(
            id="openai/o1",
            context_window=200000,
            quality_tier=QualityTier.FRONTIER,
            is_preview=False,
            supports_reasoning=True,
        )

        result = resolve_tier_intersection(
            requested_tier="reasoning",
            model_info=stable_reasoning,
        )
        assert result is True

    def test_reasoning_tier_excludes_non_reasoning_models(self):
        """Reasoning tier excludes models without reasoning support."""
        from llm_council.metadata.intersection import resolve_tier_intersection
        from llm_council.metadata.types import ModelInfo, QualityTier

        non_reasoning = ModelInfo(
            id="openai/gpt-4o",
            context_window=128000,
            quality_tier=QualityTier.FRONTIER,
            is_preview=False,
            supports_reasoning=False,
        )

        result = resolve_tier_intersection(
            requested_tier="reasoning",
            model_info=non_reasoning,
        )
        assert result is False

    def test_high_tier_excludes_preview_models(self):
        """High tier excludes preview models (require proven stability)."""
        from llm_council.metadata.intersection import resolve_tier_intersection
        from llm_council.metadata.types import ModelInfo, QualityTier

        preview_model = ModelInfo(
            id="openai/gpt-5-preview",
            context_window=200000,
            quality_tier=QualityTier.FRONTIER,
            is_preview=True,
        )

        result = resolve_tier_intersection(
            requested_tier="high",
            model_info=preview_model,
        )
        assert result is False

    def test_high_tier_includes_stable_high_quality_models(self):
        """High tier includes stable frontier/standard quality models."""
        from llm_council.metadata.intersection import resolve_tier_intersection
        from llm_council.metadata.types import ModelInfo, QualityTier

        stable_model = ModelInfo(
            id="anthropic/claude-3.5-sonnet",
            context_window=200000,
            quality_tier=QualityTier.FRONTIER,
            is_preview=False,
        )

        result = resolve_tier_intersection(
            requested_tier="high",
            model_info=stable_model,
        )
        assert result is True

    def test_balanced_tier_includes_standard_models(self):
        """Balanced tier includes standard and above quality models."""
        from llm_council.metadata.intersection import resolve_tier_intersection
        from llm_council.metadata.types import ModelInfo, QualityTier

        standard_model = ModelInfo(
            id="openai/gpt-4o-mini",
            context_window=128000,
            quality_tier=QualityTier.STANDARD,
            is_preview=False,
        )

        result = resolve_tier_intersection(
            requested_tier="balanced",
            model_info=standard_model,
        )
        assert result is True

    def test_quick_tier_includes_economy_models(self):
        """Quick tier includes economy models for fast responses."""
        from llm_council.metadata.intersection import resolve_tier_intersection
        from llm_council.metadata.types import ModelInfo, QualityTier

        economy_model = ModelInfo(
            id="anthropic/claude-3-haiku",
            context_window=200000,
            quality_tier=QualityTier.ECONOMY,
            is_preview=False,
        )

        result = resolve_tier_intersection(
            requested_tier="quick",
            model_info=economy_model,
        )
        assert result is True


class TestTierIntersectionEdgeCases:
    """Edge case tests for tier intersection logic."""

    def test_unknown_tier_returns_false(self):
        """Unknown tier should return False (fail closed)."""
        from llm_council.metadata.intersection import resolve_tier_intersection
        from llm_council.metadata.types import ModelInfo, QualityTier

        model = ModelInfo(
            id="openai/gpt-4o",
            context_window=128000,
            quality_tier=QualityTier.FRONTIER,
        )

        result = resolve_tier_intersection(
            requested_tier="nonexistent_tier",
            model_info=model,
        )
        assert result is False

    def test_local_tier_includes_local_models(self):
        """Local tier includes locally-run models."""
        from llm_council.metadata.intersection import resolve_tier_intersection
        from llm_council.metadata.types import ModelInfo, QualityTier

        local_model = ModelInfo(
            id="ollama/llama3",
            context_window=8192,
            quality_tier=QualityTier.LOCAL,
            is_preview=False,
        )

        result = resolve_tier_intersection(
            requested_tier="local",
            model_info=local_model,
        )
        # Local tier should accept LOCAL quality tier models
        assert result is True
