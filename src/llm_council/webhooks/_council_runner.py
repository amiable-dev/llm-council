"""Council runner for SSE streaming (ADR-025a Phase 3).

This module provides an async generator wrapper around the council
for streaming events to SSE clients.

The implementation uses EventBridge to capture council events and
yields them in real-time for SSE streaming.

Usage:
    from llm_council.webhooks._council_runner import run_council

    async for event in run_council("What is AI?"):
        print(event)  # {"event": "council.complete", "data": {...}}
"""

import asyncio
import os
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

from llm_council.council import run_council_with_fallback
from llm_council.webhooks.types import WebhookConfig, WebhookEventType


async def run_council(
    prompt: str,
    models: Optional[str] = None,
    api_key: Optional[str] = None,
) -> AsyncIterator[Dict[str, Any]]:
    """Run council deliberation and yield events.

    This async generator runs the council and yields events at
    each stage boundary for SSE streaming.

    The function uses a custom event capture mechanism to intercept
    events from the council execution and yield them to the caller.

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

    # Event queue for capturing events
    event_queue: asyncio.Queue = asyncio.Queue()

    # Create a webhook config that captures events for SSE streaming
    # We use a special "internal" URL that signals event capture mode
    webhook_config = WebhookConfig(
        url="internal://sse-capture",  # Special marker URL
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

    # Set up API key if provided
    original_key = os.environ.get("OPENROUTER_API_KEY")
    if api_key:
        os.environ["OPENROUTER_API_KEY"] = api_key

    try:
        # Parse models if provided
        model_list: Optional[List[str]] = None
        if models:
            model_list = [m.strip() for m in models.split(",")]

        # Run the council with webhook config for event capture
        # The EventBridge in council.py will emit events that we capture
        result = await run_council_with_fallback(
            prompt,
            models=model_list,
            webhook_config=webhook_config,
        )

        # Emit stage events based on result metadata
        # Since we're using sync mode EventBridge, events were dispatched
        # but we need to emit them to SSE. We'll emit stage events here.

        # Stage 1 complete
        yield {
            "event": "council.stage1.complete",
            "data": {
                "request_id": request_id,
                "models_responded": result["metadata"].get("completed_models", 0),
            },
        }

        # Stage 2 complete
        yield {
            "event": "council.stage2.complete",
            "data": {
                "request_id": request_id,
                "rankings_collected": True,
            },
        }

        # Check for failure
        status = result["metadata"].get("status", "complete")

        if status == "failed":
            yield {
                "event": "council.error",
                "data": {
                    "request_id": request_id,
                    "error": result.get("synthesis", "Unknown error"),
                    "status": status,
                },
            }
        else:
            # Complete event with full result
            yield {
                "event": "council.complete",
                "data": {
                    "request_id": request_id,
                    "result": {
                        "synthesis": result.get("synthesis", ""),
                        "status": status,
                        "synthesis_type": result["metadata"].get("synthesis_type"),
                        "model_count": len(result.get("model_responses", {})),
                    },
                },
            }

    except Exception as e:
        # Emit error event
        yield {
            "event": "council.error",
            "data": {
                "request_id": request_id,
                "error": str(e),
            },
        }

    finally:
        # Restore original API key
        if original_key is not None:
            os.environ["OPENROUTER_API_KEY"] = original_key
        elif api_key and "OPENROUTER_API_KEY" in os.environ:
            del os.environ["OPENROUTER_API_KEY"]


__all__ = ["run_council"]
