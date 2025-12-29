"""Telemetry protocol for LLM Council.

This module defines the telemetry interface used by the council system.
By default, a no-op implementation is used that collects no data.

The protocol allows external implementations (such as Council Cloud) to
inject telemetry clients that transmit anonymized voting data for
leaderboard aggregation.

Privacy Notice:
- The default NoOpTelemetry sends no data anywhere
- Any telemetry implementation must respect user opt-out preferences
- Only anonymized, aggregate voting data should be transmitted
- No raw queries, responses, or personally identifiable information

Usage (default - no telemetry):
    from llm_council.telemetry import get_telemetry
    telemetry = get_telemetry()  # Returns NoOpTelemetry

Usage (with custom implementation):
    from llm_council.telemetry import set_telemetry

    class MyTelemetry:
        def is_enabled(self) -> bool: return True
        async def send_event(self, event): ...

    set_telemetry(MyTelemetry())
"""

from typing import Any, Dict, Protocol, runtime_checkable


@runtime_checkable
class TelemetryProtocol(Protocol):
    """Protocol defining the telemetry interface.

    Implementations must provide:
    - is_enabled(): Check if telemetry collection is active
    - send_event(): Asynchronously queue/send a telemetry event

    The protocol uses structural subtyping, so any class implementing
    these methods satisfies the protocol without explicit inheritance.
    """

    def is_enabled(self) -> bool:
        """Check if telemetry is enabled.

        Returns:
            True if telemetry events should be collected, False otherwise.
        """
        ...

    async def send_event(self, event: Dict[str, Any]) -> None:
        """Send a telemetry event.

        This method should be non-blocking and fire-and-forget.
        Implementations should handle batching and retries internally.

        Args:
            event: Telemetry event dictionary. Standard events include:
                - council_completed: Full council run completed
                - ranking_aggregated: Rankings calculated

        Event schema for 'council_completed':
            {
                "type": "council_completed",
                "timestamp": "ISO-8601 timestamp",
                "council_size": int,
                "responses_received": int,
                "synthesis_mode": "consensus" | "debate",
                "rankings": [
                    {
                        "model": "model/identifier",
                        "borda_score": float,
                        "vote_count": int
                    }
                ],
                "config": {
                    "exclude_self_votes": bool,
                    "style_normalization": bool
                }
            }
        """
        ...


class NoOpTelemetry:
    """Default no-op telemetry implementation.

    This implementation does nothing - no data is collected or transmitted.
    Used as the default when no external telemetry client is configured.
    """

    def is_enabled(self) -> bool:
        """Always returns False - telemetry is disabled."""
        return False

    async def send_event(self, event: Dict[str, Any]) -> None:
        """No-op - silently discards the event."""
        pass


# Global telemetry instance (default: no-op)
_telemetry: TelemetryProtocol = NoOpTelemetry()


def get_telemetry() -> TelemetryProtocol:
    """Get the current telemetry implementation.

    Returns:
        The configured telemetry client (NoOpTelemetry by default).
    """
    return _telemetry


def set_telemetry(impl: TelemetryProtocol) -> None:
    """Set a custom telemetry implementation.

    This allows external packages to inject their own telemetry
    clients that implement the TelemetryProtocol.

    Args:
        impl: A telemetry implementation satisfying TelemetryProtocol.

    Raises:
        TypeError: If impl doesn't satisfy TelemetryProtocol.

    Example:
        from llm_council.telemetry import set_telemetry
        from my_telemetry import MyTelemetryClient

        client = MyTelemetryClient(endpoint="https://...")
        set_telemetry(client)
    """
    global _telemetry

    if not isinstance(impl, TelemetryProtocol):
        raise TypeError(
            f"Telemetry implementation must satisfy TelemetryProtocol. "
            f"Got {type(impl).__name__} which is missing required methods."
        )

    _telemetry = impl


def reset_telemetry() -> None:
    """Reset telemetry to the default no-op implementation.

    Useful for testing or when disabling a previously configured client.
    """
    global _telemetry
    _telemetry = NoOpTelemetry()


def _auto_init_telemetry() -> None:
    """Auto-initialize telemetry based on configuration.

    Called during module import to set up telemetry if enabled in config.
    This is a no-op if telemetry is disabled (the default).
    """
    try:
        # ADR-032: Migrated to unified_config
        from llm_council.unified_config import get_config

        config = get_config()
        telemetry_config = config.telemetry

        if telemetry_config.enabled:
            from llm_council.telemetry_client import HttpTelemetry

            client = HttpTelemetry(
                endpoint=telemetry_config.endpoint,
                level=telemetry_config.level,
            )
            set_telemetry(client)
    except ImportError:
        # Config or client not available, use default NoOp
        pass
    except Exception:
        # Any other error, fail silently and use NoOp
        pass


# Auto-initialize on module load
_auto_init_telemetry()
