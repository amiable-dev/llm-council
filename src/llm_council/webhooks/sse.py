"""Server-Sent Events (SSE) support for LLM Council (ADR-025).

This module provides SSE event formatting and streaming for real-time
council deliberation updates.
"""

import json
from typing import Any, AsyncIterator, Dict, Optional

# SSE Content-Type header
SSE_CONTENT_TYPE = "text/event-stream"


def get_sse_headers() -> Dict[str, str]:
    """Get standard SSE response headers.

    Returns:
        Dict of headers for SSE response.
    """
    return {
        "Content-Type": SSE_CONTENT_TYPE,
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
    }


def format_sse_event(
    event: str,
    data: Any,
    event_id: Optional[str] = None,
    retry: Optional[int] = None,
) -> str:
    """Format data as an SSE event.

    Args:
        event: Event name/type.
        data: Event data (will be JSON encoded).
        event_id: Optional event ID for client reconnection.
        retry: Optional reconnection timeout in milliseconds.

    Returns:
        SSE-formatted event string.
    """
    lines = []

    # Add optional fields
    if event_id:
        lines.append(f"id: {event_id}")

    if retry is not None:
        lines.append(f"retry: {retry}")

    # Event type
    lines.append(f"event: {event}")

    # Data (JSON encoded)
    json_data = json.dumps(data)
    lines.append(f"data: {json_data}")

    # SSE events end with double newline
    return "\n".join(lines) + "\n\n"


def format_council_event(
    event_type: str,
    request_id: str,
    data: Dict[str, Any],
) -> str:
    """Format a council deliberation event as SSE.

    Args:
        event_type: Council event type (e.g., "council.complete").
        request_id: The request ID for this deliberation.
        data: Event-specific data.

    Returns:
        SSE-formatted event string.
    """
    payload = {
        "request_id": request_id,
        **data,
    }
    return format_sse_event(event_type, payload, event_id=request_id)


def format_keepalive() -> str:
    """Format an SSE keep-alive comment.

    Returns:
        SSE comment for keep-alive.
    """
    return ": keepalive\n\n"


async def council_event_generator(
    prompt: str,
    models: Optional[str],
    api_key: Optional[str],
    keepalive_interval: float = 15.0,
) -> AsyncIterator[str]:
    """Generate SSE events for council deliberation.

    This async generator yields SSE-formatted events as the council
    progresses through its deliberation stages.

    Args:
        prompt: The user's prompt.
        models: Optional comma-separated model list.
        api_key: Optional API key override.
        keepalive_interval: Seconds between keep-alive events.

    Yields:
        SSE-formatted event strings.
    """
    # Lazy import to avoid circular dependency
    from llm_council.webhooks._council_runner import run_council

    async for event in run_council(prompt, models, api_key):
        yield format_sse_event(
            event=event.get("event", "message"),
            data=event.get("data", {}),
        )
