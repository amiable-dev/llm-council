"""HTTP telemetry client for LLM Council.

This module provides an HTTP-based telemetry implementation that sends
anonymized voting data to the Council Cloud ingestion service.

Privacy Notice (ADR-001):
- OFF level: No data transmitted
- ANONYMOUS level: Only voting data (rankings, durations, model counts)
- DEBUG level: + query_hash for troubleshooting (no actual query text)

Usage:
    from llm_council.telemetry_client import HttpTelemetry
    from llm_council.telemetry import set_telemetry

    client = HttpTelemetry(
        endpoint="https://ingest.llmcouncil.ai/v1/events",
        level="anonymous"
    )
    set_telemetry(client)
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


# Fields to strip based on consent level
_SENSITIVE_FIELDS = {
    "off": set(),  # Nothing sent anyway
    "anonymous": {"query_text", "query_hash"},  # Strip both
    "debug": {"query_text"},  # Strip query_text, keep query_hash
}


class HttpTelemetry:
    """
    HTTP-based telemetry client for Council Cloud.

    Sends anonymized voting data to the ingestion service for aggregation
    into the LLM Leaderboard. Implements the TelemetryProtocol.

    Features:
    - Non-blocking, fire-and-forget event submission
    - Automatic batching for efficiency
    - Privacy-aware field filtering based on consent level
    - Graceful degradation on network errors
    """

    def __init__(
        self,
        endpoint: str,
        level: str = "anonymous",
        timeout: float = 5.0,
        max_retries: int = 2,
        batch_size: int = 5,
        flush_interval: float = 30.0,
    ):
        """
        Initialize the telemetry client.

        Args:
            endpoint: URL of the ingestion service
            level: Consent level (off, anonymous, debug)
            timeout: Request timeout in seconds
            max_retries: Number of retry attempts on failure
            batch_size: Number of events to batch before sending
            flush_interval: Max seconds to wait before flushing batch
        """
        self.endpoint = endpoint
        self.level = level.lower().strip()
        self.timeout = timeout
        self.max_retries = max_retries
        self.batch_size = batch_size
        self.flush_interval = flush_interval

        self._buffer: List[Dict[str, Any]] = []
        self._last_flush = datetime.utcnow()
        self._lock = asyncio.Lock()

    def is_enabled(self) -> bool:
        """Check if telemetry is enabled.

        Returns:
            True if level is not 'off', False otherwise.
        """
        return self.level != "off"

    def set_level(self, level: str) -> None:
        """Set the telemetry consent level.

        Args:
            level: New consent level to apply (off, anonymous, debug).
        """
        self.level = level.lower().strip()

    def disable(self) -> None:
        """Disable telemetry transmission (sets level to off)."""
        self.level = "off"

    def enable(self) -> None:
        """Enable telemetry transmission (sets level to anonymous if off)."""
        if self.level == "off":
            self.level = "anonymous"

    def _filter_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Filter event fields based on consent level.

        Strips sensitive fields according to the current level.

        Args:
            event: Raw event dictionary.

        Returns:
            Filtered event with sensitive fields removed.
        """
        fields_to_strip = _SENSITIVE_FIELDS.get(self.level, _SENSITIVE_FIELDS["anonymous"])
        if not fields_to_strip:
            return event

        return {k: v for k, v in event.items() if k not in fields_to_strip}

    async def send_event(self, event: Dict[str, Any]) -> None:
        """
        Queue an event for transmission.

        Events are batched and sent periodically or when batch_size is reached.
        This method is non-blocking and fire-and-forget.

        Sensitive fields are automatically stripped based on the consent level.

        Args:
            event: Telemetry event conforming to the schema
        """
        if not self.is_enabled():
            return

        # Filter event based on consent level
        filtered_event = self._filter_event(event)

        async with self._lock:
            self._buffer.append(filtered_event)

            # Check if we should flush
            should_flush = (
                len(self._buffer) >= self.batch_size
                or (datetime.utcnow() - self._last_flush).total_seconds() >= self.flush_interval
            )

            if should_flush:
                # Fire and forget - don't await
                asyncio.create_task(self._flush())

    async def _flush(self) -> None:
        """Flush buffered events to the ingestion service."""
        async with self._lock:
            if not self._buffer:
                return

            events = self._buffer.copy()
            self._buffer.clear()
            self._last_flush = datetime.utcnow()

        await self._send_batch(events)

    async def _send_batch(self, events: List[Dict[str, Any]]) -> None:
        """Send a batch of events to the ingestion service."""
        try:
            import httpx
        except ImportError:
            logger.warning("httpx not installed, telemetry disabled. Run: pip install httpx")
            return

        headers = {"Content-Type": "application/json"}
        payload = {"events": events}

        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        self.endpoint,
                        json=payload,
                        headers=headers,
                    )
                    response.raise_for_status()
                    logger.debug(f"Sent {len(events)} telemetry events")
                    return
            except Exception as e:
                logger.debug(
                    f"Telemetry send failed (attempt {attempt + 1}/{self.max_retries}): {e}"
                )
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(1)  # Brief backoff

        # Log at debug level to avoid cluttering user output
        logger.debug(
            f"Failed to send {len(events)} telemetry events after {self.max_retries} attempts"
        )

    async def close(self) -> None:
        """Flush remaining events and close the client."""
        await self._flush()


def create_telemetry_client(level: str = "off", endpoint: Optional[str] = None) -> HttpTelemetry:
    """
    Factory function to create a telemetry client based on config.

    Args:
        level: Telemetry level (off, anonymous, debug)
        endpoint: Optional custom endpoint URL

    Returns:
        Configured HttpTelemetry instance
    """
    # ADR-032: Migrated to unified_config
    from llm_council.unified_config import get_config

    config = get_config()

    return HttpTelemetry(
        endpoint=endpoint or config.telemetry.endpoint,
        level=level,
    )
