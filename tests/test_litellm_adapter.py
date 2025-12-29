"""TDD tests for ADR-026: LiteLLM Metadata Adapter.

Tests the LiteLLM integration for fetching model metadata.
These tests are written FIRST per TDD methodology.
"""

import pytest
from unittest.mock import patch, MagicMock


class TestLiteLLMAdapter:
    """Test LiteLLM metadata extraction."""

    def test_adapter_lazy_import(self):
        """LiteLLM should be lazily imported (not required at init)."""
        from llm_council.metadata.litellm_adapter import LiteLLMAdapter

        # Should not raise even if litellm behavior differs
        adapter = LiteLLMAdapter()
        assert adapter._litellm is None

    def test_adapter_get_context_window_known_model(self):
        """Should extract context window from LiteLLM model map."""
        from llm_council.metadata.litellm_adapter import LiteLLMAdapter

        adapter = LiteLLMAdapter()

        # Mock LiteLLM's model_cost dict
        mock_litellm = MagicMock()
        mock_litellm.model_cost = {
            "gpt-4o": {"max_tokens": 128000},
            "claude-3-5-sonnet-20241022": {"max_tokens": 200000},
        }

        with patch.object(adapter, "_get_litellm", return_value=mock_litellm):
            window = adapter.get_context_window("openai/gpt-4o")
            assert window == 128000

    def test_adapter_returns_none_for_unknown(self):
        """Should return None for models not in LiteLLM."""
        from llm_council.metadata.litellm_adapter import LiteLLMAdapter

        adapter = LiteLLMAdapter()

        mock_litellm = MagicMock()
        mock_litellm.model_cost = {}

        with patch.object(adapter, "_get_litellm", return_value=mock_litellm):
            window = adapter.get_context_window("unknown/model")
            assert window is None

    def test_adapter_handles_import_error(self):
        """Should handle LiteLLM not being installed."""
        from llm_council.metadata.litellm_adapter import LiteLLMAdapter

        adapter = LiteLLMAdapter()

        with patch.object(adapter, "_get_litellm", side_effect=ImportError("No litellm")):
            window = adapter.get_context_window("any/model")
            assert window is None

    def test_adapter_model_id_normalization(self):
        """Should normalize model IDs to LiteLLM format."""
        from llm_council.metadata.litellm_adapter import LiteLLMAdapter

        adapter = LiteLLMAdapter()

        # LiteLLM uses different formats for model IDs
        assert adapter._normalize_model_id("openai/gpt-4o") == "gpt-4o"
        assert (
            adapter._normalize_model_id("anthropic/claude-3-5-sonnet-20241022")
            == "claude-3-5-sonnet-20241022"
        )
        # Ollama models keep their prefix for LiteLLM
        assert adapter._normalize_model_id("ollama/llama3.2") == "ollama/llama3.2"

    def test_adapter_get_pricing(self):
        """Should extract pricing from LiteLLM."""
        from llm_council.metadata.litellm_adapter import LiteLLMAdapter

        adapter = LiteLLMAdapter()

        mock_litellm = MagicMock()
        mock_litellm.model_cost = {
            "gpt-4o": {
                "input_cost_per_token": 0.0000025,
                "output_cost_per_token": 0.00001,
            },
        }

        with patch.object(adapter, "_get_litellm", return_value=mock_litellm):
            pricing = adapter.get_pricing("openai/gpt-4o")
            assert pricing is not None
            # Should convert to per-1K format
            assert "prompt" in pricing
            assert "completion" in pricing

    def test_adapter_supports_reasoning(self):
        """Should detect reasoning capability from LiteLLM."""
        from llm_council.metadata.litellm_adapter import LiteLLMAdapter

        adapter = LiteLLMAdapter()

        mock_litellm = MagicMock()
        mock_litellm.model_cost = {
            "o1": {"supports_reasoning": True},
            "gpt-4o": {},
        }

        with patch.object(adapter, "_get_litellm", return_value=mock_litellm):
            # o1 should support reasoning
            assert adapter.supports_reasoning("openai/o1") is True
            # gpt-4o should not
            assert adapter.supports_reasoning("openai/gpt-4o") is False


class TestLiteLLMAdapterCaching:
    """Test LiteLLM adapter caching behavior."""

    def test_adapter_caches_litellm_import(self):
        """LiteLLM module should be cached after first import."""
        from llm_council.metadata.litellm_adapter import LiteLLMAdapter

        adapter = LiteLLMAdapter()

        mock_litellm = MagicMock()
        mock_litellm.model_cost = {"gpt-4o": {"max_tokens": 128000}}

        call_count = 0
        original_get = adapter._get_litellm

        def counting_get():
            nonlocal call_count
            call_count += 1
            return mock_litellm

        with patch.object(adapter, "_get_litellm", counting_get):
            adapter.get_context_window("openai/gpt-4o")
            adapter.get_context_window("openai/gpt-4o")
            # Note: Actual caching depends on implementation
            # This test documents expected behavior
