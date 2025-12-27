"""Tests for telemetry configuration.

Tests the LLM_COUNCIL_TELEMETRY environment variable and auto-initialization.
"""

import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


class TestTelemetryConfig:
    """Test telemetry configuration parsing."""

    def test_telemetry_default_is_off(self):
        """Telemetry should be disabled by default."""
        # Clear any existing telemetry env var
        with patch.dict(os.environ, {}, clear=True):
            # Need to reload config to pick up env changes
            import importlib
            from llm_council import config
            importlib.reload(config)

            assert config.TELEMETRY_ENABLED is False
            assert config.TELEMETRY_LEVEL == "off"

    def test_telemetry_off_explicitly(self):
        """LLM_COUNCIL_TELEMETRY=off should disable telemetry."""
        with patch.dict(os.environ, {"LLM_COUNCIL_TELEMETRY": "off"}):
            import importlib
            from llm_council import config
            importlib.reload(config)

            assert config.TELEMETRY_ENABLED is False
            assert config.TELEMETRY_LEVEL == "off"

    def test_telemetry_anonymous_level(self):
        """LLM_COUNCIL_TELEMETRY=anonymous should enable basic telemetry."""
        with patch.dict(os.environ, {"LLM_COUNCIL_TELEMETRY": "anonymous"}):
            import importlib
            from llm_council import config
            importlib.reload(config)

            assert config.TELEMETRY_ENABLED is True
            assert config.TELEMETRY_LEVEL == "anonymous"

    def test_telemetry_debug_level(self):
        """LLM_COUNCIL_TELEMETRY=debug should enable debug telemetry."""
        with patch.dict(os.environ, {"LLM_COUNCIL_TELEMETRY": "debug"}):
            import importlib
            from llm_council import config
            importlib.reload(config)

            assert config.TELEMETRY_ENABLED is True
            assert config.TELEMETRY_LEVEL == "debug"

    def test_telemetry_case_insensitive(self):
        """Telemetry level should be case-insensitive."""
        with patch.dict(os.environ, {"LLM_COUNCIL_TELEMETRY": "ANONYMOUS"}):
            import importlib
            from llm_council import config
            importlib.reload(config)

            assert config.TELEMETRY_ENABLED is True
            assert config.TELEMETRY_LEVEL == "anonymous"

    def test_telemetry_endpoint_default(self):
        """Default telemetry endpoint should be set."""
        with patch.dict(os.environ, {"LLM_COUNCIL_TELEMETRY": "anonymous"}):
            import importlib
            from llm_council import config
            importlib.reload(config)

            assert config.TELEMETRY_ENDPOINT is not None
            assert "telemetry" in config.TELEMETRY_ENDPOINT.lower() or "ingest" in config.TELEMETRY_ENDPOINT.lower()

    def test_telemetry_endpoint_override(self):
        """LLM_COUNCIL_TELEMETRY_ENDPOINT should override default."""
        custom_endpoint = "https://custom.example.com/events"
        with patch.dict(os.environ, {
            "LLM_COUNCIL_TELEMETRY": "anonymous",
            "LLM_COUNCIL_TELEMETRY_ENDPOINT": custom_endpoint
        }):
            import importlib
            from llm_council import config
            importlib.reload(config)

            assert config.TELEMETRY_ENDPOINT == custom_endpoint


class TestHttpTelemetryClient:
    """Test the HTTP telemetry client implementation."""

    def test_client_implements_protocol(self):
        """HttpTelemetry should implement TelemetryProtocol."""
        from llm_council.telemetry import TelemetryProtocol
        from llm_council.telemetry_client import HttpTelemetry

        client = HttpTelemetry(endpoint="https://example.com/events", level="anonymous")

        assert isinstance(client, TelemetryProtocol)

    def test_client_disabled_when_level_off(self):
        """Client should report disabled when level is off."""
        from llm_council.telemetry_client import HttpTelemetry

        client = HttpTelemetry(endpoint="https://example.com/events", level="off")

        assert client.is_enabled() is False

    def test_client_enabled_when_level_anonymous(self):
        """Client should report enabled when level is anonymous."""
        from llm_council.telemetry_client import HttpTelemetry

        client = HttpTelemetry(endpoint="https://example.com/events", level="anonymous")

        assert client.is_enabled() is True

    @pytest.mark.asyncio
    async def test_send_event_does_nothing_when_disabled(self):
        """send_event should be a no-op when disabled."""
        from llm_council.telemetry_client import HttpTelemetry

        client = HttpTelemetry(endpoint="https://example.com/events", level="off")

        # Should not raise any errors
        await client.send_event({"type": "test"})

    @pytest.mark.asyncio
    async def test_send_event_posts_to_endpoint(self):
        """send_event should POST to the configured endpoint."""
        from llm_council.telemetry_client import HttpTelemetry

        client = HttpTelemetry(
            endpoint="https://example.com/events",
            level="anonymous",
            batch_size=1,  # Immediate send
        )

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock()

            await client.send_event({"type": "council_completed", "rankings": []})

            # Give async task time to complete
            import asyncio
            await asyncio.sleep(0.1)

            # Verify POST was called
            mock_client.post.assert_called()

    def test_filter_strips_query_text_at_anonymous_level(self):
        """Anonymous level should strip query_text and query_hash."""
        from llm_council.telemetry_client import HttpTelemetry

        client = HttpTelemetry(endpoint="https://example.com/events", level="anonymous")

        event = {
            "type": "council_completed",
            "query_text": "What is the meaning of life?",
            "query_hash": "abc123",
            "rankings": []
        }

        filtered = client._filter_event(event)

        assert "query_text" not in filtered
        assert "query_hash" not in filtered
        assert "rankings" in filtered

    def test_filter_keeps_query_hash_at_debug_level(self):
        """Debug level should keep query_hash but strip query_text."""
        from llm_council.telemetry_client import HttpTelemetry

        client = HttpTelemetry(endpoint="https://example.com/events", level="debug")

        event = {
            "type": "council_completed",
            "query_text": "What is the meaning of life?",
            "query_hash": "abc123",
            "rankings": []
        }

        filtered = client._filter_event(event)

        assert "query_text" not in filtered
        assert "query_hash" in filtered
        assert filtered["query_hash"] == "abc123"


class TestTelemetryAutoInit:
    """Test automatic telemetry initialization."""

    def test_telemetry_auto_initialized_when_enabled(self):
        """Telemetry should be auto-initialized when config enables it."""
        with patch.dict(os.environ, {"LLM_COUNCIL_TELEMETRY": "anonymous"}):
            import importlib
            from llm_council import unified_config
            # Must reload unified_config to pick up new env var
            unified_config.reload_config()

            # Reload telemetry to trigger auto-init with new config
            from llm_council import telemetry
            importlib.reload(telemetry)

            assert telemetry.get_telemetry().is_enabled() is True

    def test_telemetry_noop_when_disabled(self):
        """Telemetry should be NoOp when config disables it."""
        with patch.dict(os.environ, {"LLM_COUNCIL_TELEMETRY": "off"}):
            import importlib
            from llm_council import unified_config
            # Must reload unified_config to pick up new env var
            unified_config.reload_config()

            # Reload telemetry to trigger auto-init with new config
            from llm_council import telemetry
            importlib.reload(telemetry)

            assert telemetry.get_telemetry().is_enabled() is False
