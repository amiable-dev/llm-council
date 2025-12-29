"""TDD tests for ADR-026: Offline Mode.

Tests that LLM_COUNCIL_OFFLINE=true disables all external metadata calls.
These tests are written FIRST per TDD methodology.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import os


class TestOfflineModeDetection:
    """Test offline mode detection from environment."""

    def test_offline_mode_from_env_true(self):
        """LLM_COUNCIL_OFFLINE=true should enable offline mode."""
        from llm_council.metadata.offline import is_offline_mode

        with patch.dict(os.environ, {"LLM_COUNCIL_OFFLINE": "true"}, clear=False):
            assert is_offline_mode() is True

    def test_offline_mode_from_env_1(self):
        """LLM_COUNCIL_OFFLINE=1 should enable offline mode."""
        from llm_council.metadata.offline import is_offline_mode

        with patch.dict(os.environ, {"LLM_COUNCIL_OFFLINE": "1"}, clear=False):
            assert is_offline_mode() is True

    def test_offline_mode_from_env_yes(self):
        """LLM_COUNCIL_OFFLINE=yes should enable offline mode."""
        from llm_council.metadata.offline import is_offline_mode

        with patch.dict(os.environ, {"LLM_COUNCIL_OFFLINE": "yes"}, clear=False):
            assert is_offline_mode() is True

    def test_offline_mode_default_false(self):
        """Offline mode should be disabled by default."""
        from llm_council.metadata.offline import is_offline_mode

        # Remove the env var if it exists
        env_copy = os.environ.copy()
        env_copy.pop("LLM_COUNCIL_OFFLINE", None)
        with patch.dict(os.environ, env_copy, clear=True):
            assert is_offline_mode() is False

    def test_offline_mode_from_env_false(self):
        """LLM_COUNCIL_OFFLINE=false should disable offline mode."""
        from llm_council.metadata.offline import is_offline_mode

        with patch.dict(os.environ, {"LLM_COUNCIL_OFFLINE": "false"}, clear=False):
            assert is_offline_mode() is False


class TestOfflineModeProvider:
    """Test that offline mode uses StaticRegistryProvider exclusively."""

    def test_get_provider_returns_static_in_offline_mode(self):
        """get_provider() should return StaticRegistryProvider in offline mode."""
        from llm_council.metadata import get_provider, reload_provider
        from llm_council.metadata.static_registry import StaticRegistryProvider

        with patch.dict(os.environ, {"LLM_COUNCIL_OFFLINE": "true"}, clear=False):
            reload_provider()  # Force reload with new env
            provider = get_provider()
            assert isinstance(provider, StaticRegistryProvider)

    def test_get_provider_returns_static_by_default(self):
        """get_provider() should return StaticRegistryProvider by default."""
        from llm_council.metadata import get_provider, reload_provider
        from llm_council.metadata.static_registry import StaticRegistryProvider

        # Even without offline mode, we use static provider
        # (Dynamic provider is future work)
        env_copy = os.environ.copy()
        env_copy.pop("LLM_COUNCIL_OFFLINE", None)
        with patch.dict(os.environ, env_copy, clear=True):
            reload_provider()
            provider = get_provider()
            assert isinstance(provider, StaticRegistryProvider)


class TestOfflineModeLogging:
    """Test offline mode logging."""

    def test_offline_mode_logs_info_on_startup(self, caplog):
        """Should log INFO about offline mode when enabled."""
        from llm_council.metadata.offline import check_offline_mode_startup
        import logging

        with patch.dict(os.environ, {"LLM_COUNCIL_OFFLINE": "true"}, clear=False):
            with caplog.at_level(logging.INFO):
                check_offline_mode_startup()
                # Check that something was logged about offline mode
                assert any("offline" in record.message.lower() for record in caplog.records)


class TestOfflineModeCoreOperations:
    """Test that core council operations work in offline mode."""

    def test_provider_models_available_offline(self):
        """Provider should return models without external calls."""
        from llm_council.metadata import get_provider, reload_provider

        with patch.dict(os.environ, {"LLM_COUNCIL_OFFLINE": "true"}, clear=False):
            reload_provider()
            provider = get_provider()

            # All tier models should be available
            models = provider.list_available_models()
            assert "openai/gpt-4o" in models
            assert "anthropic/claude-opus-4.5" in models
            assert len(models) >= 30

    def test_context_window_available_offline(self):
        """Context windows should be available without external calls."""
        from llm_council.metadata import get_provider, reload_provider

        with patch.dict(os.environ, {"LLM_COUNCIL_OFFLINE": "true"}, clear=False):
            reload_provider()
            provider = get_provider()

            # Context windows should be available
            window = provider.get_context_window("openai/gpt-4o")
            assert window >= 4096  # At least the safe default
            assert window == 128000  # Should be exact from registry


class TestOfflineModeGracefulDegradation:
    """Test graceful degradation messages in offline mode."""

    def test_unknown_model_uses_safe_defaults(self):
        """Unknown models should use safe defaults without errors."""
        from llm_council.metadata import get_provider, reload_provider

        with patch.dict(os.environ, {"LLM_COUNCIL_OFFLINE": "true"}, clear=False):
            reload_provider()
            provider = get_provider()

            # Unknown model should get safe defaults
            window = provider.get_context_window("brand-new/unknown-model")
            assert window == 4096  # Safe default

            # Should not raise
            info = provider.get_model_info("brand-new/unknown-model")
            assert info is None  # Unknown models return None

            reasoning = provider.supports_reasoning("brand-new/unknown-model")
            assert reasoning is False  # Safe default


class TestProviderFactory:
    """Test get_provider() and reload_provider() factory functions."""

    def test_get_provider_returns_singleton(self):
        """get_provider() should return cached instance."""
        from llm_council.metadata import get_provider, reload_provider

        reload_provider()  # Start fresh
        provider1 = get_provider()
        provider2 = get_provider()
        assert provider1 is provider2

    def test_reload_provider_creates_new_instance(self):
        """reload_provider() should create fresh instance."""
        from llm_council.metadata import get_provider, reload_provider

        provider1 = get_provider()
        reload_provider()
        provider2 = get_provider()
        assert provider1 is not provider2
