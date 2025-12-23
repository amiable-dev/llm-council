"""Webhook types for LLM Council (ADR-025).

This module defines the data types for webhook configuration,
payloads, and delivery results.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class WebhookEventType(str, Enum):
    """Webhook event types for council deliberation.

    Per ADR-025, these events are emitted at key stages of deliberation.
    """

    DELIBERATION_START = "council.deliberation_start"
    STAGE1_COMPLETE = "council.stage1.complete"
    MODEL_VOTE_CAST = "model.vote_cast"
    STAGE2_COMPLETE = "council.stage2.complete"
    CONSENSUS_REACHED = "consensus.reached"
    COMPLETE = "council.complete"
    ERROR = "council.error"


class WebhookConfig(BaseModel):
    """Configuration for a webhook endpoint.

    Attributes:
        url: The webhook endpoint URL.
        events: List of event types to subscribe to.
        secret: Optional HMAC secret for signature verification.
    """

    url: str
    events: List[str] = ["council.complete", "council.error"]
    secret: Optional[str] = None


class WebhookPayload(BaseModel):
    """Payload sent to webhook endpoints.

    Attributes:
        event: The event type (e.g., "council.complete").
        request_id: Unique identifier for the council request.
        timestamp: When the event occurred.
        data: Event-specific data.
        duration_ms: Optional duration in milliseconds.
    """

    event: str
    request_id: str
    timestamp: datetime
    data: Dict[str, Any]
    duration_ms: Optional[int] = None


class WebhookDeliveryResult(BaseModel):
    """Result of a webhook delivery attempt.

    Attributes:
        success: Whether the delivery was successful.
        status_code: HTTP status code received.
        attempt: Which attempt number this was (1-indexed).
        error: Error message if delivery failed.
        latency_ms: Time taken for the request.
    """

    success: bool
    status_code: int
    attempt: int
    error: Optional[str] = None
    latency_ms: Optional[int] = None
