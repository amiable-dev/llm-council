"""TDD tests for ADR-028: Application Startup Lifecycle (Issue #125).

Tests for start_discovery_worker() and stop_discovery_worker() functions.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestStartupLifecycle:
    """Test application startup/shutdown lifecycle hooks."""

    def setup_method(self):
        """Reset worker state before each test."""
        from llm_council.metadata.startup import _reset_worker_state

        _reset_worker_state()

    def teardown_method(self):
        """Reset worker state after each test."""
        from llm_council.metadata.startup import _reset_worker_state

        _reset_worker_state()

    @pytest.mark.asyncio
    async def test_startup_skipped_when_disabled(self, monkeypatch):
        """start_discovery_worker should skip when discovery disabled."""
        from llm_council.metadata.startup import (
            start_discovery_worker,
            get_worker_status,
        )
        from llm_council.unified_config import reload_config

        monkeypatch.setenv("LLM_COUNCIL_MODEL_INTELLIGENCE", "false")
        reload_config()

        await start_discovery_worker()

        status = get_worker_status()
        assert status["worker_running"] is False

    @pytest.mark.asyncio
    async def test_startup_starts_worker_when_enabled(self, monkeypatch):
        """start_discovery_worker should start worker when enabled."""
        from llm_council.metadata.startup import (
            start_discovery_worker,
            stop_discovery_worker,
            get_worker_status,
        )
        from llm_council.unified_config import reload_config

        monkeypatch.setenv("LLM_COUNCIL_MODEL_INTELLIGENCE", "true")
        monkeypatch.setenv("LLM_COUNCIL_DISCOVERY_ENABLED", "true")
        reload_config()

        # Mock the dynamic provider module
        with patch(
            "llm_council.metadata.dynamic_provider.DynamicMetadataProvider"
        ) as mock_provider_class:
            mock_provider = MagicMock()
            mock_provider.list_available_models = MagicMock(return_value=[])
            mock_provider_class.return_value = mock_provider

            await start_discovery_worker()

            status = get_worker_status()
            assert status["worker_running"] is True
            assert status["discovery_enabled"] is True

            # Cleanup
            await stop_discovery_worker()

    @pytest.mark.asyncio
    async def test_startup_refreshes_immediately(self, monkeypatch):
        """start_discovery_worker should refresh registry before starting worker."""
        from llm_council.metadata.startup import (
            start_discovery_worker,
            stop_discovery_worker,
        )
        from llm_council.metadata.registry import get_registry, _reset_registry
        from llm_council.unified_config import reload_config

        _reset_registry()
        monkeypatch.setenv("LLM_COUNCIL_MODEL_INTELLIGENCE", "true")
        monkeypatch.setenv("LLM_COUNCIL_DISCOVERY_ENABLED", "true")
        reload_config()

        with patch(
            "llm_council.metadata.dynamic_provider.DynamicMetadataProvider"
        ) as mock_provider_class:
            mock_provider = MagicMock()
            mock_provider.list_available_models = MagicMock(return_value=[])
            mock_provider_class.return_value = mock_provider

            with patch.object(
                get_registry(), "refresh_registry", new_callable=AsyncMock
            ) as mock_refresh:
                await start_discovery_worker()

                # refresh_registry should have been called for initial refresh
                assert mock_refresh.called

            await stop_discovery_worker()

        _reset_registry()

    @pytest.mark.asyncio
    async def test_shutdown_stops_worker_gracefully(self, monkeypatch):
        """stop_discovery_worker should stop worker gracefully."""
        from llm_council.metadata.startup import (
            start_discovery_worker,
            stop_discovery_worker,
            get_worker_status,
        )
        from llm_council.unified_config import reload_config

        monkeypatch.setenv("LLM_COUNCIL_MODEL_INTELLIGENCE", "true")
        monkeypatch.setenv("LLM_COUNCIL_DISCOVERY_ENABLED", "true")
        reload_config()

        with patch(
            "llm_council.metadata.dynamic_provider.DynamicMetadataProvider"
        ) as mock_provider_class:
            mock_provider = MagicMock()
            mock_provider.list_available_models = MagicMock(return_value=[])
            mock_provider_class.return_value = mock_provider

            await start_discovery_worker()
            assert get_worker_status()["worker_running"] is True

            await stop_discovery_worker()
            assert get_worker_status()["worker_running"] is False

    @pytest.mark.asyncio
    async def test_shutdown_idempotent(self):
        """stop_discovery_worker should be safe to call multiple times."""
        from llm_council.metadata.startup import stop_discovery_worker

        # Should not raise even if worker never started
        await stop_discovery_worker()
        await stop_discovery_worker()

    def test_get_worker_status_returns_dict(self):
        """get_worker_status should return status dictionary."""
        from llm_council.metadata.startup import get_worker_status

        status = get_worker_status()

        assert isinstance(status, dict)
        assert "worker_running" in status
        assert "discovery_enabled" in status
        assert "registry_status" in status

    def test_get_worker_status_includes_registry_health(self):
        """get_worker_status should include registry health check."""
        from llm_council.metadata.startup import get_worker_status

        status = get_worker_status()

        assert "registry_status" in status
        assert "registry_size" in status["registry_status"]
        assert "is_stale" in status["registry_status"]
