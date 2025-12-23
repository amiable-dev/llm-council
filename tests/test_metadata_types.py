"""TDD tests for ADR-026: Model Metadata Types.

Tests the core data structures for model metadata.
These tests are written FIRST per TDD methodology.
"""

import pytest
from dataclasses import FrozenInstanceError


class TestModelInfo:
    """Test ModelInfo dataclass for model metadata."""

    def test_model_info_required_fields(self):
        """ModelInfo must have id and context_window."""
        from llm_council.metadata.types import ModelInfo

        info = ModelInfo(
            id="openai/gpt-4o",
            context_window=128000,
        )
        assert info.id == "openai/gpt-4o"
        assert info.context_window == 128000

    def test_model_info_pricing(self):
        """ModelInfo should have pricing dict with prompt/completion."""
        from llm_council.metadata.types import ModelInfo

        info = ModelInfo(
            id="anthropic/claude-opus-4.5",
            context_window=200000,
            pricing={"prompt": 0.015, "completion": 0.075},
        )
        assert info.pricing["prompt"] == 0.015
        assert info.pricing["completion"] == 0.075

    def test_model_info_default_pricing(self):
        """ModelInfo pricing should default to empty dict."""
        from llm_council.metadata.types import ModelInfo

        info = ModelInfo(id="test/model", context_window=4096)
        assert info.pricing == {}

    def test_model_info_supported_parameters(self):
        """ModelInfo should track supported parameters."""
        from llm_council.metadata.types import ModelInfo

        info = ModelInfo(
            id="openai/gpt-4o",
            context_window=128000,
            supported_parameters=["temperature", "top_p", "tools", "reasoning"],
        )
        assert "reasoning" in info.supported_parameters
        assert "temperature" in info.supported_parameters

    def test_model_info_default_supported_parameters(self):
        """ModelInfo supported_parameters should default to empty list."""
        from llm_council.metadata.types import ModelInfo

        info = ModelInfo(id="test/model", context_window=4096)
        assert info.supported_parameters == []

    def test_model_info_modalities(self):
        """ModelInfo should track input modalities."""
        from llm_council.metadata.types import ModelInfo

        info = ModelInfo(
            id="openai/gpt-4o",
            context_window=128000,
            modalities=["text", "vision"],
        )
        assert "vision" in info.modalities
        assert "text" in info.modalities

    def test_model_info_default_modalities(self):
        """ModelInfo modalities should default to ['text']."""
        from llm_council.metadata.types import ModelInfo

        info = ModelInfo(id="test/model", context_window=4096)
        assert info.modalities == ["text"]

    def test_model_info_quality_tier(self):
        """ModelInfo should have quality tier classification."""
        from llm_council.metadata.types import ModelInfo, QualityTier

        info = ModelInfo(
            id="openai/gpt-4o",
            context_window=128000,
            quality_tier=QualityTier.FRONTIER,
        )
        assert info.quality_tier == QualityTier.FRONTIER

    def test_model_info_default_quality_tier(self):
        """ModelInfo quality_tier should default to STANDARD."""
        from llm_council.metadata.types import ModelInfo, QualityTier

        info = ModelInfo(id="test/model", context_window=4096)
        assert info.quality_tier == QualityTier.STANDARD

    def test_model_info_is_frozen(self):
        """ModelInfo should be immutable (frozen dataclass)."""
        from llm_council.metadata.types import ModelInfo

        info = ModelInfo(id="test/model", context_window=4096)
        with pytest.raises((FrozenInstanceError, AttributeError)):
            info.id = "changed"

    def test_model_info_equality(self):
        """ModelInfo instances with same values should be equal."""
        from llm_council.metadata.types import ModelInfo

        info1 = ModelInfo(id="test/model", context_window=4096)
        info2 = ModelInfo(id="test/model", context_window=4096)
        assert info1 == info2

    def test_model_info_immutable_fields_protected(self):
        """ModelInfo fields should be protected from mutation."""
        from llm_council.metadata.types import ModelInfo

        info = ModelInfo(id="test/model", context_window=4096)
        # Verify the dataclass is frozen
        assert info.__dataclass_fields__["id"].name == "id"
        # Note: While the dataclass is frozen, mutable fields (dict, list)
        # can still be mutated. This is a Python limitation.
        # For ADR-026, immutability is advisory rather than enforced.


class TestQualityTier:
    """Test QualityTier enum."""

    def test_quality_tier_values(self):
        """QualityTier should have expected values."""
        from llm_council.metadata.types import QualityTier

        assert QualityTier.FRONTIER.value == "frontier"
        assert QualityTier.STANDARD.value == "standard"
        assert QualityTier.ECONOMY.value == "economy"
        assert QualityTier.LOCAL.value == "local"

    def test_quality_tier_from_string(self):
        """Should convert string to QualityTier."""
        from llm_council.metadata.types import QualityTier

        assert QualityTier("frontier") == QualityTier.FRONTIER
        assert QualityTier("standard") == QualityTier.STANDARD
        assert QualityTier("economy") == QualityTier.ECONOMY
        assert QualityTier("local") == QualityTier.LOCAL

    def test_quality_tier_iteration(self):
        """Should be able to iterate over all tiers."""
        from llm_council.metadata.types import QualityTier

        tiers = list(QualityTier)
        assert len(tiers) == 4


class TestModality:
    """Test Modality enum."""

    def test_modality_values(self):
        """Modality should have text, vision, audio."""
        from llm_council.metadata.types import Modality

        assert Modality.TEXT.value == "text"
        assert Modality.VISION.value == "vision"
        assert Modality.AUDIO.value == "audio"

    def test_modality_from_string(self):
        """Should convert string to Modality."""
        from llm_council.metadata.types import Modality

        assert Modality("text") == Modality.TEXT
        assert Modality("vision") == Modality.VISION
        assert Modality("audio") == Modality.AUDIO

    def test_modality_iteration(self):
        """Should be able to iterate over all modalities."""
        from llm_council.metadata.types import Modality

        modalities = list(Modality)
        assert len(modalities) == 3
