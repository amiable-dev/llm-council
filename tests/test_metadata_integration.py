"""TDD tests for ADR-026: Metadata Integration.

End-to-end integration tests for the metadata system.
"""

import pytest
from unittest.mock import patch
import os


class TestMetadataProviderFactory:
    """Test get_provider() factory function."""

    def test_get_provider_returns_singleton(self):
        """get_provider() should return cached instance."""
        from llm_council.metadata import get_provider, reload_provider

        reload_provider()  # Start fresh
        provider1 = get_provider()
        provider2 = get_provider()
        assert provider1 is provider2

    def test_get_provider_can_be_reloaded(self):
        """reload_provider() should create fresh instance."""
        from llm_council.metadata import get_provider, reload_provider

        provider1 = get_provider()
        reload_provider()
        provider2 = get_provider()
        assert provider1 is not provider2


class TestMetadataWithTierConfig:
    """Test metadata integration with tier configuration."""

    def test_tier_models_have_metadata(self):
        """All tier models should have metadata available."""
        from llm_council.metadata import get_provider, reload_provider
        from llm_council.config import DEFAULT_TIER_MODEL_POOLS

        reload_provider()
        provider = get_provider()

        # Check that most tier models have metadata
        for tier, models in DEFAULT_TIER_MODEL_POOLS.items():
            for model_id in models:
                # Every configured model should have context window
                window = provider.get_context_window(model_id)
                assert window >= 4096, f"{model_id} should have context window"


class TestBundledRegistryContent:
    """Test the bundled registry has required models."""

    def test_registry_has_openai_models(self):
        """Registry should include OpenAI models."""
        from llm_council.metadata import get_provider, reload_provider

        reload_provider()
        provider = get_provider()
        models = provider.list_available_models()

        openai_models = [m for m in models if m.startswith("openai/")]
        assert len(openai_models) >= 5
        assert "openai/gpt-4o" in models
        assert "openai/gpt-4o-mini" in models

    def test_registry_has_anthropic_models(self):
        """Registry should include Anthropic models."""
        from llm_council.metadata import get_provider, reload_provider

        reload_provider()
        provider = get_provider()
        models = provider.list_available_models()

        anthropic_models = [m for m in models if m.startswith("anthropic/")]
        assert len(anthropic_models) >= 4
        assert "anthropic/claude-opus-4.5" in models

    def test_registry_has_google_models(self):
        """Registry should include Google models."""
        from llm_council.metadata import get_provider, reload_provider

        reload_provider()
        provider = get_provider()
        models = provider.list_available_models()

        google_models = [m for m in models if m.startswith("google/")]
        assert len(google_models) >= 3

    def test_registry_has_local_models(self):
        """Registry should include Ollama local models."""
        from llm_council.metadata import get_provider, reload_provider

        reload_provider()
        provider = get_provider()
        models = provider.list_available_models()

        ollama_models = [m for m in models if m.startswith("ollama/")]
        assert len(ollama_models) >= 2

    def test_registry_has_30_plus_models(self):
        """Registry should have at least 30 models per ADR-026."""
        from llm_council.metadata import get_provider, reload_provider

        reload_provider()
        provider = get_provider()
        models = provider.list_available_models()

        assert len(models) >= 30, f"Expected 30+ models, got {len(models)}"


class TestReasoningModelDetection:
    """Test reasoning model detection for parameter optimization."""

    def test_detects_openai_o1_as_reasoning(self):
        """Should detect OpenAI o1 as reasoning model."""
        from llm_council.metadata import get_provider, reload_provider

        reload_provider()
        provider = get_provider()

        assert provider.supports_reasoning("openai/o1") is True

    def test_detects_openai_o1_preview_as_reasoning(self):
        """Should detect OpenAI o1-preview as reasoning model."""
        from llm_council.metadata import get_provider, reload_provider

        reload_provider()
        provider = get_provider()

        assert provider.supports_reasoning("openai/o1-preview") is True

    def test_detects_openai_o1_mini_as_reasoning(self):
        """Should detect OpenAI o1-mini as reasoning model."""
        from llm_council.metadata import get_provider, reload_provider

        reload_provider()
        provider = get_provider()

        assert provider.supports_reasoning("openai/o1-mini") is True

    def test_detects_deepseek_r1_as_reasoning(self):
        """Should detect DeepSeek R1 as reasoning model."""
        from llm_council.metadata import get_provider, reload_provider

        reload_provider()
        provider = get_provider()

        assert provider.supports_reasoning("deepseek/deepseek-r1") is True

    def test_detects_non_reasoning_models(self):
        """Should correctly identify non-reasoning models."""
        from llm_council.metadata import get_provider, reload_provider

        reload_provider()
        provider = get_provider()

        assert provider.supports_reasoning("openai/gpt-4o-mini") is False
        assert provider.supports_reasoning("anthropic/claude-3-5-haiku-20241022") is False


class TestModelInfoContent:
    """Test ModelInfo content for registered models."""

    def test_gpt4o_has_correct_metadata(self):
        """GPT-4o should have correct metadata."""
        from llm_council.metadata import get_provider, reload_provider
        from llm_council.metadata.types import QualityTier

        reload_provider()
        provider = get_provider()
        info = provider.get_model_info("openai/gpt-4o")

        assert info is not None
        assert info.id == "openai/gpt-4o"
        assert info.context_window == 128000
        assert "vision" in info.modalities
        assert info.quality_tier == QualityTier.FRONTIER

    def test_claude_opus_has_correct_metadata(self):
        """Claude Opus 4.5 should have correct metadata."""
        from llm_council.metadata import get_provider, reload_provider
        from llm_council.metadata.types import QualityTier

        reload_provider()
        provider = get_provider()
        info = provider.get_model_info("anthropic/claude-opus-4.5")

        assert info is not None
        assert info.id == "anthropic/claude-opus-4.5"
        assert info.context_window == 200000
        assert "vision" in info.modalities
        assert info.quality_tier == QualityTier.FRONTIER

    def test_ollama_model_has_local_tier(self):
        """Ollama models should have LOCAL quality tier."""
        from llm_council.metadata import get_provider, reload_provider
        from llm_council.metadata.types import QualityTier

        reload_provider()
        provider = get_provider()
        info = provider.get_model_info("ollama/llama3.2")

        assert info is not None
        assert info.quality_tier == QualityTier.LOCAL
        # Local models should have zero pricing
        assert info.pricing.get("prompt", 0) == 0
        assert info.pricing.get("completion", 0) == 0
