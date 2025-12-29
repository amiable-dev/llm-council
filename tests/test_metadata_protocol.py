"""TDD tests for ADR-026: MetadataProvider Protocol.

Tests the abstract protocol that all metadata sources must implement.
These tests are written FIRST per TDD methodology.
"""

import pytest
import inspect
from typing import Optional, Dict, List


class TestMetadataProviderProtocol:
    """Test MetadataProvider Protocol definition."""

    def test_protocol_has_get_model_info(self):
        """Protocol must define get_model_info method."""
        from llm_council.metadata.protocol import MetadataProvider

        assert hasattr(MetadataProvider, "get_model_info")
        sig = inspect.signature(MetadataProvider.get_model_info)
        assert "model_id" in sig.parameters

    def test_protocol_has_get_context_window(self):
        """Protocol must define get_context_window method."""
        from llm_council.metadata.protocol import MetadataProvider

        assert hasattr(MetadataProvider, "get_context_window")
        sig = inspect.signature(MetadataProvider.get_context_window)
        assert "model_id" in sig.parameters

    def test_protocol_has_get_pricing(self):
        """Protocol must define get_pricing method."""
        from llm_council.metadata.protocol import MetadataProvider

        assert hasattr(MetadataProvider, "get_pricing")
        sig = inspect.signature(MetadataProvider.get_pricing)
        assert "model_id" in sig.parameters

    def test_protocol_has_supports_reasoning(self):
        """Protocol must define supports_reasoning method."""
        from llm_council.metadata.protocol import MetadataProvider

        assert hasattr(MetadataProvider, "supports_reasoning")
        sig = inspect.signature(MetadataProvider.supports_reasoning)
        assert "model_id" in sig.parameters

    def test_protocol_has_list_available_models(self):
        """Protocol must define list_available_models method."""
        from llm_council.metadata.protocol import MetadataProvider

        assert hasattr(MetadataProvider, "list_available_models")

    def test_protocol_is_runtime_checkable(self):
        """Protocol should be runtime_checkable for isinstance()."""
        from llm_council.metadata.protocol import MetadataProvider
        from llm_council.metadata.types import ModelInfo

        # Create a mock that implements all methods
        class MockProvider:
            def get_model_info(self, model_id: str) -> Optional["ModelInfo"]:
                return None

            def get_context_window(self, model_id: str) -> int:
                return 4096

            def get_pricing(self, model_id: str) -> Dict[str, float]:
                return {}

            def supports_reasoning(self, model_id: str) -> bool:
                return False

            def list_available_models(self) -> List[str]:
                return []

        # Should be able to use isinstance() check
        provider = MockProvider()
        assert isinstance(provider, MetadataProvider)


class TestMockProviderCompliance:
    """Test that implementations can satisfy the protocol."""

    def test_mock_provider_satisfies_protocol(self):
        """A mock implementation should satisfy the protocol."""
        from llm_council.metadata.protocol import MetadataProvider
        from llm_council.metadata.types import ModelInfo

        class MockProvider:
            def get_model_info(self, model_id: str) -> Optional[ModelInfo]:
                return ModelInfo(id=model_id, context_window=4096)

            def get_context_window(self, model_id: str) -> int:
                return 4096

            def get_pricing(self, model_id: str) -> Dict[str, float]:
                return {}

            def supports_reasoning(self, model_id: str) -> bool:
                return False

            def list_available_models(self) -> List[str]:
                return []

        provider = MockProvider()
        assert isinstance(provider, MetadataProvider)

    def test_incomplete_implementation_not_protocol(self):
        """Incomplete implementation should not satisfy protocol."""
        from llm_council.metadata.protocol import MetadataProvider

        class IncompleteProvider:
            def get_model_info(self, model_id: str):
                return None

            # Missing other methods

        provider = IncompleteProvider()
        assert not isinstance(provider, MetadataProvider)

    def test_protocol_method_signatures(self):
        """Protocol methods should have expected return types."""
        from llm_council.metadata.protocol import MetadataProvider
        from llm_council.metadata.types import ModelInfo

        class TypedProvider:
            def get_model_info(self, model_id: str) -> Optional[ModelInfo]:
                return ModelInfo(id=model_id, context_window=4096)

            def get_context_window(self, model_id: str) -> int:
                return 4096

            def get_pricing(self, model_id: str) -> Dict[str, float]:
                return {"prompt": 0.01, "completion": 0.03}

            def supports_reasoning(self, model_id: str) -> bool:
                return model_id.startswith("openai/o")

            def list_available_models(self) -> List[str]:
                return ["openai/gpt-4o", "anthropic/claude-opus-4.5"]

        provider = TypedProvider()

        # Test return types
        info = provider.get_model_info("test")
        assert isinstance(info, ModelInfo)

        window = provider.get_context_window("test")
        assert isinstance(window, int)

        pricing = provider.get_pricing("test")
        assert isinstance(pricing, dict)

        reasoning = provider.supports_reasoning("openai/o1")
        assert isinstance(reasoning, bool)

        models = provider.list_available_models()
        assert isinstance(models, list)
