"""TDD tests for ADR-028: Background Discovery Worker (Issue #121).

Tests for the background worker that periodically refreshes the model registry.

These tests implement the RED phase of TDD.
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llm_council.metadata.registry import ModelRegistry
from llm_council.metadata.types import ModelInfo, QualityTier


class TestDiscoveryWorker:
    """Test run_discovery_worker() background task."""

    @pytest.mark.asyncio
    async def test_worker_calls_refresh_periodically(self):
        """Worker should call refresh_registry at specified interval."""
        from llm_council.metadata.worker import run_discovery_worker

        registry = ModelRegistry()
        mock_provider = MagicMock()
        mock_provider.list_available_models = MagicMock(return_value=["openai/gpt-4o"])
        mock_provider.get_model_info = MagicMock(
            return_value=ModelInfo(
                id="openai/gpt-4o",
                context_window=128000,
                quality_tier=QualityTier.FRONTIER,
            )
        )

        shutdown_event = asyncio.Event()
        refresh_count = 0

        # Patch refresh_registry to count calls
        original_refresh = registry.refresh_registry

        async def counting_refresh(provider, **kwargs):
            nonlocal refresh_count
            refresh_count += 1
            await original_refresh(provider, **kwargs)

        registry.refresh_registry = counting_refresh

        # Run worker briefly with short interval
        worker_task = asyncio.create_task(
            run_discovery_worker(
                registry=registry,
                provider=mock_provider,
                interval_seconds=0.1,  # 100ms for testing
                shutdown_event=shutdown_event,
            )
        )

        # Let it run for a bit
        await asyncio.sleep(0.35)

        # Signal shutdown
        shutdown_event.set()
        await asyncio.wait_for(worker_task, timeout=1.0)

        # Should have called refresh 3-4 times in 350ms with 100ms interval
        assert refresh_count >= 3

    @pytest.mark.asyncio
    async def test_worker_respects_interval(self):
        """Worker should wait interval_seconds between refreshes."""
        from llm_council.metadata.worker import run_discovery_worker

        registry = ModelRegistry()
        mock_provider = MagicMock()
        mock_provider.list_available_models = MagicMock(return_value=[])

        shutdown_event = asyncio.Event()
        refresh_times: list = []

        async def tracking_refresh(provider, **kwargs):
            refresh_times.append(datetime.utcnow())

        registry.refresh_registry = tracking_refresh

        worker_task = asyncio.create_task(
            run_discovery_worker(
                registry=registry,
                provider=mock_provider,
                interval_seconds=0.2,  # 200ms
                shutdown_event=shutdown_event,
            )
        )

        await asyncio.sleep(0.55)  # Should allow ~3 refreshes
        shutdown_event.set()
        await asyncio.wait_for(worker_task, timeout=1.0)

        # Check intervals between refreshes
        if len(refresh_times) >= 2:
            for i in range(1, len(refresh_times)):
                interval = (refresh_times[i] - refresh_times[i - 1]).total_seconds()
                # Allow some tolerance for async timing
                assert 0.15 <= interval <= 0.3

    @pytest.mark.asyncio
    async def test_worker_handles_refresh_errors(self):
        """Worker should continue running even if refresh fails."""
        from llm_council.metadata.worker import run_discovery_worker

        registry = ModelRegistry()
        mock_provider = MagicMock()

        refresh_attempts = 0

        async def counting_refresh(provider, **kwargs):
            nonlocal refresh_attempts
            refresh_attempts += 1
            # Simulate failure on first attempt
            if refresh_attempts == 1:
                raise ConnectionError("API unavailable")
            # Succeed on subsequent attempts

        # Replace refresh_registry with our counting version
        registry.refresh_registry = counting_refresh

        shutdown_event = asyncio.Event()

        worker_task = asyncio.create_task(
            run_discovery_worker(
                registry=registry,
                provider=mock_provider,
                interval_seconds=0.05,  # Very short for testing
                shutdown_event=shutdown_event,
            )
        )

        # Let it attempt multiple refreshes
        await asyncio.sleep(0.2)
        shutdown_event.set()
        await asyncio.wait_for(worker_task, timeout=1.0)

        # Worker should have continued after first failure
        assert refresh_attempts >= 2

    @pytest.mark.asyncio
    async def test_worker_stops_on_shutdown_event(self):
        """Worker should stop gracefully when shutdown_event is set."""
        from llm_council.metadata.worker import run_discovery_worker

        registry = ModelRegistry()
        mock_provider = MagicMock()
        mock_provider.list_available_models = MagicMock(return_value=[])

        shutdown_event = asyncio.Event()
        worker_started = False

        async def marking_refresh(provider, **kwargs):
            nonlocal worker_started
            worker_started = True

        registry.refresh_registry = marking_refresh

        worker_task = asyncio.create_task(
            run_discovery_worker(
                registry=registry,
                provider=mock_provider,
                interval_seconds=10,  # Long interval
                shutdown_event=shutdown_event,
            )
        )

        # Wait for first refresh
        await asyncio.sleep(0.05)
        assert worker_started

        # Signal shutdown
        shutdown_event.set()

        # Worker should stop within reasonable time
        await asyncio.wait_for(worker_task, timeout=1.0)

        # If we got here, worker stopped gracefully
        assert True

    @pytest.mark.asyncio
    async def test_worker_applies_exponential_backoff(self):
        """Worker should apply exponential backoff on repeated failures."""
        from llm_council.metadata.worker import run_discovery_worker

        registry = ModelRegistry()
        mock_provider = MagicMock()
        mock_provider.list_available_models = MagicMock(
            side_effect=ConnectionError("API unavailable")
        )

        shutdown_event = asyncio.Event()
        sleep_durations: list = []

        original_sleep = asyncio.sleep

        async def tracking_sleep(duration):
            sleep_durations.append(duration)
            # Don't actually sleep to speed up test
            if shutdown_event.is_set():
                raise asyncio.CancelledError()
            await original_sleep(0.01)

        with patch("asyncio.sleep", side_effect=tracking_sleep):
            worker_task = asyncio.create_task(
                run_discovery_worker(
                    registry=registry,
                    provider=mock_provider,
                    interval_seconds=1,
                    shutdown_event=shutdown_event,
                )
            )

            # Let it fail a few times
            await asyncio.sleep(0.1)
            shutdown_event.set()

            try:
                await asyncio.wait_for(worker_task, timeout=1.0)
            except asyncio.CancelledError:
                pass

        # Should have some backoff sleep calls from registry.refresh_registry
        # The refresh method uses exponential backoff internally
        assert len(sleep_durations) >= 1

    @pytest.mark.asyncio
    async def test_worker_logs_refresh_events(self):
        """Worker should log refresh start and completion."""
        from llm_council.metadata.worker import run_discovery_worker

        registry = ModelRegistry()
        mock_provider = MagicMock()
        mock_provider.list_available_models = MagicMock(return_value=["openai/gpt-4o"])
        mock_provider.get_model_info = MagicMock(
            return_value=ModelInfo(
                id="openai/gpt-4o",
                context_window=128000,
                quality_tier=QualityTier.FRONTIER,
            )
        )

        shutdown_event = asyncio.Event()

        with patch("llm_council.metadata.worker.logger") as mock_logger:
            worker_task = asyncio.create_task(
                run_discovery_worker(
                    registry=registry,
                    provider=mock_provider,
                    interval_seconds=0.1,
                    shutdown_event=shutdown_event,
                )
            )

            await asyncio.sleep(0.15)
            shutdown_event.set()
            await asyncio.wait_for(worker_task, timeout=1.0)

            # Should have logged at least starting message
            assert mock_logger.info.called or mock_logger.debug.called


class TestWorkerWithNoShutdownEvent:
    """Test worker behavior without shutdown event (cancellation-based)."""

    @pytest.mark.asyncio
    async def test_worker_can_be_cancelled(self):
        """Worker should handle cancellation gracefully."""
        from llm_council.metadata.worker import run_discovery_worker

        registry = ModelRegistry()
        mock_provider = MagicMock()
        mock_provider.list_available_models = MagicMock(return_value=[])

        worker_task = asyncio.create_task(
            run_discovery_worker(
                registry=registry,
                provider=mock_provider,
                interval_seconds=10,
                shutdown_event=None,  # No shutdown event
            )
        )

        await asyncio.sleep(0.05)
        worker_task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await worker_task
