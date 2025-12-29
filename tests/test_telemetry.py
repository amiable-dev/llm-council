"""Tests for telemetry module."""

import pytest
from llm_council.telemetry import (
    TelemetryProtocol,
    NoOpTelemetry,
    get_telemetry,
    set_telemetry,
    reset_telemetry,
)


class TestNoOpTelemetry:
    """Tests for the default NoOpTelemetry implementation."""

    def test_is_enabled_returns_false(self):
        """NoOpTelemetry should always report as disabled."""
        telemetry = NoOpTelemetry()
        assert telemetry.is_enabled() is False

    @pytest.mark.asyncio
    async def test_send_event_does_nothing(self):
        """NoOpTelemetry.send_event should silently discard events."""
        telemetry = NoOpTelemetry()
        # Should not raise any exception
        await telemetry.send_event({"type": "test", "data": "ignored"})

    def test_satisfies_protocol(self):
        """NoOpTelemetry should satisfy TelemetryProtocol."""
        telemetry = NoOpTelemetry()
        assert isinstance(telemetry, TelemetryProtocol)


class TestTelemetryGlobals:
    """Tests for global telemetry management functions."""

    def setup_method(self):
        """Reset telemetry before each test."""
        reset_telemetry()

    def test_default_is_noop(self):
        """Default telemetry should be NoOpTelemetry."""
        telemetry = get_telemetry()
        assert isinstance(telemetry, NoOpTelemetry)
        assert telemetry.is_enabled() is False

    def test_set_telemetry_custom_implementation(self):
        """set_telemetry should allow custom implementations."""

        class CustomTelemetry:
            def __init__(self):
                self.events = []

            def is_enabled(self) -> bool:
                return True

            async def send_event(self, event):
                self.events.append(event)

        custom = CustomTelemetry()
        set_telemetry(custom)

        telemetry = get_telemetry()
        assert telemetry is custom
        assert telemetry.is_enabled() is True

    def test_reset_telemetry_restores_noop(self):
        """reset_telemetry should restore NoOpTelemetry."""

        class CustomTelemetry:
            def is_enabled(self) -> bool:
                return True

            async def send_event(self, event):
                pass

        set_telemetry(CustomTelemetry())
        assert get_telemetry().is_enabled() is True

        reset_telemetry()
        assert isinstance(get_telemetry(), NoOpTelemetry)
        assert get_telemetry().is_enabled() is False

    def test_set_telemetry_rejects_invalid_implementation(self):
        """set_telemetry should reject objects that don't satisfy protocol."""

        class InvalidTelemetry:
            # Missing is_enabled and send_event
            pass

        with pytest.raises(TypeError):
            set_telemetry(InvalidTelemetry())

    def test_set_telemetry_rejects_partial_implementation(self):
        """set_telemetry should reject partially implemented objects."""

        class PartialTelemetry:
            def is_enabled(self) -> bool:
                return True

            # Missing send_event

        with pytest.raises(TypeError):
            set_telemetry(PartialTelemetry())


class TestTelemetryProtocol:
    """Tests for TelemetryProtocol interface."""

    def test_protocol_is_runtime_checkable(self):
        """TelemetryProtocol should be usable with isinstance()."""

        class ValidImpl:
            def is_enabled(self) -> bool:
                return True

            async def send_event(self, event):
                pass

        assert isinstance(ValidImpl(), TelemetryProtocol)

    def test_noop_is_protocol_instance(self):
        """NoOpTelemetry should be recognized as TelemetryProtocol."""
        assert isinstance(NoOpTelemetry(), TelemetryProtocol)


@pytest.mark.asyncio
async def test_custom_telemetry_receives_events():
    """Custom telemetry should receive events sent through council."""
    reset_telemetry()

    received_events = []

    class TestTelemetry:
        def is_enabled(self) -> bool:
            return True

        async def send_event(self, event):
            received_events.append(event)

    set_telemetry(TestTelemetry())

    # Simulate sending an event
    telemetry = get_telemetry()
    await telemetry.send_event({"type": "council_completed", "council_size": 5, "rankings": []})

    assert len(received_events) == 1
    assert received_events[0]["type"] == "council_completed"
    assert received_events[0]["council_size"] == 5

    # Cleanup
    reset_telemetry()
