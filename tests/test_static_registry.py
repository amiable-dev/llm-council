"""TDD tests for ADR-026: StaticRegistryProvider.

Tests the offline-safe provider using bundled YAML registry + LiteLLM fallback.
These tests are written FIRST per TDD methodology.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import tempfile


class TestStaticRegistryProviderBasic:
    """Test StaticRegistryProvider basic functionality."""

    def test_provider_implements_protocol(self):
        """StaticRegistryProvider must implement MetadataProvider protocol."""
        from llm_council.metadata.static_registry import StaticRegistryProvider
        from llm_council.metadata.protocol import MetadataProvider

        provider = StaticRegistryProvider()
        assert isinstance(provider, MetadataProvider)

    def test_provider_loads_bundled_registry(self):
        """Provider should load bundled registry.yaml on init."""
        from llm_council.metadata.static_registry import StaticRegistryProvider

        provider = StaticRegistryProvider()
        # Should have loaded the bundled models
        models = provider.list_available_models()
        assert len(models) >= 30  # ADR-026 requirement

    def test_provider_loads_custom_registry_path(self, tmp_path):
        """Provider should accept custom registry path."""
        from llm_council.metadata.static_registry import StaticRegistryProvider

        custom_registry = tmp_path / "custom_registry.yaml"
        custom_registry.write_text("""
version: "1.0"
models:
  - id: "custom/model-1"
    context_window: 8192
""")
        provider = StaticRegistryProvider(registry_path=custom_registry)
        models = provider.list_available_models()
        assert "custom/model-1" in models


class TestStaticRegistryGetModelInfo:
    """Test get_model_info() method."""

    def test_get_model_info_from_registry(self):
        """Should return ModelInfo for registered model."""
        from llm_council.metadata.static_registry import StaticRegistryProvider
        from llm_council.metadata.types import ModelInfo

        provider = StaticRegistryProvider()
        info = provider.get_model_info("openai/gpt-4o")

        assert info is not None
        assert isinstance(info, ModelInfo)
        assert info.id == "openai/gpt-4o"
        assert info.context_window == 128000

    def test_get_model_info_unknown_returns_none(self):
        """Should return None for unknown model."""
        from llm_council.metadata.static_registry import StaticRegistryProvider

        provider = StaticRegistryProvider()
        info = provider.get_model_info("nonexistent/model")

        assert info is None

    def test_get_model_info_includes_pricing(self):
        """ModelInfo should include pricing if available."""
        from llm_council.metadata.static_registry import StaticRegistryProvider

        provider = StaticRegistryProvider()
        info = provider.get_model_info("anthropic/claude-opus-4.5")

        assert info is not None
        assert info.pricing is not None
        assert "prompt" in info.pricing
        assert "completion" in info.pricing


class TestStaticRegistryContextWindow:
    """Test get_context_window() method with priority chain."""

    def test_context_window_from_local_registry(self):
        """Should return context window from local registry first."""
        from llm_council.metadata.static_registry import StaticRegistryProvider

        provider = StaticRegistryProvider()
        window = provider.get_context_window("openai/gpt-4o")

        assert window == 128000

    def test_context_window_default_4096(self):
        """Should return 4096 as safe default when model unknown."""
        from llm_council.metadata.static_registry import StaticRegistryProvider

        provider = StaticRegistryProvider()
        window = provider.get_context_window("completely/unknown")
        assert window == 4096  # ADR-026 safe default

    def test_context_window_priority_order(self):
        """Priority: local config > LiteLLM > default 4096."""
        from llm_council.metadata.static_registry import StaticRegistryProvider

        provider = StaticRegistryProvider()

        # Model in local registry should use local value
        window = provider.get_context_window("openai/gpt-4o")
        # Should use local registry value (128000)
        assert window == 128000


class TestStaticRegistrySupportsReasoning:
    """Test supports_reasoning() method."""

    def test_supports_reasoning_true_for_o1(self):
        """Should detect o1 as reasoning-capable."""
        from llm_council.metadata.static_registry import StaticRegistryProvider

        provider = StaticRegistryProvider()
        assert provider.supports_reasoning("openai/o1") is True

    def test_supports_reasoning_true_for_o1_preview(self):
        """Should detect o1-preview as reasoning-capable."""
        from llm_council.metadata.static_registry import StaticRegistryProvider

        provider = StaticRegistryProvider()
        assert provider.supports_reasoning("openai/o1-preview") is True

    def test_supports_reasoning_false_for_gpt4o_mini(self):
        """Should return False for non-reasoning models."""
        from llm_council.metadata.static_registry import StaticRegistryProvider

        provider = StaticRegistryProvider()
        assert provider.supports_reasoning("openai/gpt-4o-mini") is False

    def test_supports_reasoning_unknown_model(self):
        """Should return False for unknown models."""
        from llm_council.metadata.static_registry import StaticRegistryProvider

        provider = StaticRegistryProvider()
        assert provider.supports_reasoning("nonexistent/model") is False


class TestStaticRegistryGetPricing:
    """Test get_pricing() method."""

    def test_get_pricing_returns_dict(self):
        """Should return pricing dict for known model."""
        from llm_council.metadata.static_registry import StaticRegistryProvider

        provider = StaticRegistryProvider()
        pricing = provider.get_pricing("openai/gpt-4o")

        assert isinstance(pricing, dict)
        if pricing:  # If pricing is provided
            assert "prompt" in pricing or len(pricing) == 0

    def test_get_pricing_unknown_returns_empty(self):
        """Should return empty dict for unknown model."""
        from llm_council.metadata.static_registry import StaticRegistryProvider

        provider = StaticRegistryProvider()
        pricing = provider.get_pricing("nonexistent/model")

        assert pricing == {}


class TestStaticRegistryListModels:
    """Test list_available_models() method."""

    def test_list_returns_all_registered_models(self):
        """Should return list of all model IDs in registry."""
        from llm_council.metadata.static_registry import StaticRegistryProvider

        provider = StaticRegistryProvider()
        models = provider.list_available_models()

        assert isinstance(models, list)
        assert len(models) >= 30  # ADR-026 requirement
        assert "openai/gpt-4o" in models

    def test_list_includes_openai_models(self):
        """Should include OpenAI models."""
        from llm_council.metadata.static_registry import StaticRegistryProvider

        provider = StaticRegistryProvider()
        models = provider.list_available_models()

        openai_models = [m for m in models if m.startswith("openai/")]
        assert len(openai_models) >= 5

    def test_list_includes_anthropic_models(self):
        """Should include Anthropic models."""
        from llm_council.metadata.static_registry import StaticRegistryProvider

        provider = StaticRegistryProvider()
        models = provider.list_available_models()

        anthropic_models = [m for m in models if m.startswith("anthropic/")]
        assert len(anthropic_models) >= 4

    def test_list_includes_local_models(self):
        """Should include Ollama local models if registered."""
        from llm_council.metadata.static_registry import StaticRegistryProvider

        provider = StaticRegistryProvider()
        models = provider.list_available_models()

        ollama_models = [m for m in models if m.startswith("ollama/")]
        assert len(ollama_models) >= 2


class TestStaticRegistryYAMLSchema:
    """Test YAML registry schema validation."""

    def test_registry_yaml_valid_schema(self, tmp_path):
        """Registry YAML should validate against expected schema."""
        from llm_council.metadata.static_registry import StaticRegistryProvider

        valid_yaml = tmp_path / "valid.yaml"
        valid_yaml.write_text("""
version: "1.0"
updated: "2025-12-23"
models:
  - id: "test/model"
    context_window: 8192
    pricing:
      prompt: 0.001
      completion: 0.002
    supported_parameters: ["temperature", "top_p"]
    modalities: ["text"]
    quality_tier: "standard"
""")
        # Should not raise
        provider = StaticRegistryProvider(registry_path=valid_yaml)
        info = provider.get_model_info("test/model")
        assert info is not None
        assert info.context_window == 8192

    def test_registry_yaml_minimal_schema(self, tmp_path):
        """Registry should work with minimal required fields."""
        from llm_council.metadata.static_registry import StaticRegistryProvider

        minimal_yaml = tmp_path / "minimal.yaml"
        minimal_yaml.write_text("""
version: "1.0"
models:
  - id: "minimal/model"
    context_window: 4096
""")
        provider = StaticRegistryProvider(registry_path=minimal_yaml)
        info = provider.get_model_info("minimal/model")
        assert info is not None
        assert info.context_window == 4096

    def test_registry_yaml_empty_models_list(self, tmp_path):
        """Empty models list should result in empty provider."""
        from llm_council.metadata.static_registry import StaticRegistryProvider

        empty_yaml = tmp_path / "empty.yaml"
        empty_yaml.write_text("""
version: "1.0"
models: []
""")
        provider = StaticRegistryProvider(registry_path=empty_yaml)
        assert provider.list_available_models() == []
