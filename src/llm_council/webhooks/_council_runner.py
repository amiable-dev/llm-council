"""Council runner for SSE streaming (ADR-025a Phase 3).

This module provides an async generator wrapper around the council
for streaming events to SSE clients.

The implementation uses the on_event callback mechanism in EventBridge
to capture council events in real-time and yield them as they occur.

Usage:
    from llm_council.webhooks._council_runner import run_council

    async for event in run_council("What is AI?"):
        print(event)  # {"event": "council.complete", "data": {...}}
"""

import asyncio
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

from llm_council.council import run_council_with_fallback
from llm_council.unified_config import set_request_api_key, clear_request_api_keys
from llm_council.webhooks.types import WebhookConfig, WebhookEventType


async def run_council(
    prompt: str,
    models: Optional[str] = None,
    api_key: Optional[str] = None,
) -> AsyncIterator[Dict[str, Any]]:
    """Run council deliberation and yield events in real-time.

    This async generator runs the council in a background task and yields
    events as they occur, enabling true real-time SSE streaming.

    Args:
        prompt: The user's prompt.
        models: Optional comma-separated model list.
        api_key: Optional API key override.

    Yields:
        Event dicts with 'event' and 'data' keys:
        - council.deliberation_start: Council execution starting
        - council.stage1.complete: Stage 1 responses collected
        - council.stage2.complete: Stage 2 rankings complete
        - council.complete: Final synthesis ready (includes full result)
        - council.error: An error occurred
    """
    request_id = str(uuid.uuid4())

    # Event queue for real-time event capture
    event_queue: asyncio.Queue = asyncio.Queue()

    # Track which events we've seen (for synthetic event generation)
    events_seen: set = set()

    # Sentinel to signal end of events
    _DONE = object()

    def on_event_callback(payload) -> None:
        """Callback to capture events from EventBridge."""
        events_seen.add(payload.event)
        # Convert WebhookPayload to SSE event format
        event_queue.put_nowait(
            {
                "event": payload.event,
                "data": {
                    "request_id": request_id,
                    **payload.data,
                },
            }
        )

    # Create webhook config for event subscription
    webhook_config = WebhookConfig(
        url="internal://sse-capture",  # Special marker URL (not dispatched)
        events=[
            WebhookEventType.DELIBERATION_START.value,
            WebhookEventType.STAGE1_COMPLETE.value,
            WebhookEventType.STAGE2_COMPLETE.value,
            WebhookEventType.COMPLETE.value,
            WebhookEventType.ERROR.value,
        ],
    )

    # Emit start event immediately
    yield {
        "event": "council.deliberation_start",
        "data": {
            "request_id": request_id,
            "prompt": prompt[:100] + "..." if len(prompt) > 100 else prompt,
        },
    }

    # Set up API key if provided (async-safe using ContextVar)
    if api_key:
        set_request_api_key("openrouter", api_key)

    # Parse models if provided
    model_list: Optional[List[str]] = None
    if models:
        model_list = [m.strip() for m in models.split(",")]

    # Store for the council result
    council_result: Dict[str, Any] = {}
    council_error: Optional[Exception] = None

    async def run_council_task():
        """Background task to run the council."""
        nonlocal council_result, council_error
        try:
            council_result = await run_council_with_fallback(
                prompt,
                models=model_list,
                webhook_config=webhook_config,
                on_event=on_event_callback,
            )
        except Exception as e:
            council_error = e
        finally:
            # Signal that the council is done
            event_queue.put_nowait(_DONE)

    try:
        # Start the council in a background task
        council_task = asyncio.create_task(run_council_task())

        # Yield events as they arrive
        while True:
            event = await event_queue.get()

            # Check for completion sentinel
            if event is _DONE:
                break

            yield event

        # Wait for the task to complete (should already be done)
        await council_task

        # If there was an error, emit error event
        if council_error is not None:
            yield {
                "event": "council.error",
                "data": {
                    "request_id": request_id,
                    "error": str(council_error),
                },
            }
        else:
            # Emit synthetic stage events if they weren't captured in real-time
            # This ensures SSE stream always has all expected events
            if "council.stage1.complete" not in events_seen:
                yield {
                    "event": "council.stage1.complete",
                    "data": {
                        "request_id": request_id,
                        "models_responded": len(council_result.get("model_responses", {})),
                    },
                }

            if "council.stage2.complete" not in events_seen:
                yield {
                    "event": "council.stage2.complete",
                    "data": {
                        "request_id": request_id,
                        "rankings_collected": True,
                    },
                }

            # Emit completion event with full result
            status = council_result.get("metadata", {}).get("status", "complete")

            if status == "failed":
                yield {
                    "event": "council.error",
                    "data": {
                        "request_id": request_id,
                        "error": council_result.get("synthesis", "Unknown error"),
                        "status": status,
                    },
                }
            else:
                yield {
                    "event": "council.complete",
                    "data": {
                        "request_id": request_id,
                        "result": {
                            "synthesis": council_result.get("synthesis", ""),
                            "status": status,
                            "synthesis_type": council_result.get("metadata", {}).get(
                                "synthesis_type"
                            ),
                            "model_count": len(council_result.get("model_responses", {})),
                        },
                    },
                }

    except Exception as e:
        # Emit error event for any unexpected errors
        yield {
            "event": "council.error",
            "data": {
                "request_id": request_id,
                "error": str(e),
            },
        }

    finally:
        # Clear request-scoped API keys (cleanup for this async context)
        clear_request_api_keys()


__all__ = ["run_council"]
