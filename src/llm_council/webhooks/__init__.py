"""Webhook support for LLM Council (ADR-025).

This package provides webhook delivery, SSE streaming, and event bridging
for real-time council deliberation updates.

Example usage:
    from llm_council.webhooks import (
        WebhookConfig,
        WebhookPayload,
        WebhookDispatcher,
        EventBridge,
        DispatchMode,
        format_sse_event,
    )

    # Configure webhook
    config = WebhookConfig(
        url="https://example.com/webhook",
        events=["council.complete", "council.error"],
        secret="my-hmac-secret"
    )

    # Dispatch webhook directly
    dispatcher = WebhookDispatcher()
    result = await dispatcher.dispatch(config, payload)

    # Or use EventBridge for automatic layer event → webhook mapping
    bridge = EventBridge(webhook_config=config, mode=DispatchMode.ASYNC)
    await bridge.start()
    await bridge.emit(layer_event)
    await bridge.shutdown()
"""

from .types import (
    WebhookEventType,
    WebhookConfig,
    WebhookPayload,
    WebhookDeliveryResult,
)
from .hmac_auth import (
    generate_signature,
    verify_signature,
    generate_webhook_headers,
    validate_timestamp,
    verify_webhook_request,
)
from .dispatcher import WebhookDispatcher
from .sse import (
    SSE_CONTENT_TYPE,
    get_sse_headers,
    format_sse_event,
    format_council_event,
    format_keepalive,
    council_event_generator,
)
from .event_bridge import (
    EventBridge,
    DispatchMode,
    transform_layer_event_to_webhook,
    LAYER_TO_WEBHOOK_MAPPING,
)

__all__ = [
    # Types
    "WebhookEventType",
    "WebhookConfig",
    "WebhookPayload",
    "WebhookDeliveryResult",
    # HMAC Auth
    "generate_signature",
    "verify_signature",
    "generate_webhook_headers",
    "validate_timestamp",
    "verify_webhook_request",
    # Dispatcher
    "WebhookDispatcher",
    # SSE
    "SSE_CONTENT_TYPE",
    "get_sse_headers",
    "format_sse_event",
    "format_council_event",
    "format_keepalive",
    "council_event_generator",
    # Event Bridge (ADR-025a)
    "EventBridge",
    "DispatchMode",
    "transform_layer_event_to_webhook",
    "LAYER_TO_WEBHOOK_MAPPING",
]
