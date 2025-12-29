"""Webhook dispatcher for LLM Council (ADR-025).

This module provides async webhook delivery with retry logic,
HMAC authentication, and HTTPS enforcement.
"""

import asyncio
import time
from typing import List
from urllib.parse import urlparse

import httpx

# ADR-032: Migrated to unified_config
from llm_council.unified_config import get_config

from .types import WebhookConfig, WebhookPayload, WebhookDeliveryResult
from .hmac_auth import generate_webhook_headers


def _get_webhook_config():
    """Get webhook configuration from unified config."""
    try:
        config = get_config()
        if hasattr(config, "webhooks"):
            return config.webhooks
    except Exception:
        pass
    return None


# Default configuration (can be overridden via environment)
try:
    webhook_config = _get_webhook_config()
    if webhook_config:
        DEFAULT_TIMEOUT = getattr(webhook_config, "timeout", 5.0)
        DEFAULT_MAX_RETRIES = getattr(webhook_config, "max_retries", 3)
        DEFAULT_HTTPS_ONLY = getattr(webhook_config, "https_only", True)
    else:
        # Fallback if config not available
        DEFAULT_TIMEOUT = 5.0
        DEFAULT_MAX_RETRIES = 3
        DEFAULT_HTTPS_ONLY = True
except (ImportError, AttributeError):
    # Fallback if config not available
    DEFAULT_TIMEOUT = 5.0
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_HTTPS_ONLY = True


class WebhookDispatcher:
    """Async webhook dispatcher with retry and HMAC support.

    Features:
    - Automatic retry on 5xx and 429 errors
    - HMAC signature authentication
    - HTTPS enforcement (with localhost exception)
    - Exponential backoff on retries
    """

    def __init__(
        self,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        https_only: bool = DEFAULT_HTTPS_ONLY,
    ):
        """Initialize the dispatcher.

        Args:
            timeout: Request timeout in seconds.
            max_retries: Maximum retry attempts.
            https_only: Require HTTPS (except localhost).
        """
        self._timeout = timeout
        self._max_retries = max_retries
        self._https_only = https_only

    def _is_url_allowed(self, url: str) -> bool:
        """Check if URL is allowed based on HTTPS policy.

        Localhost URLs are always allowed for development.

        Args:
            url: The webhook URL to check.

        Returns:
            True if URL is allowed, False otherwise.
        """
        if not self._https_only:
            return True

        parsed = urlparse(url)

        # Allow HTTPS
        if parsed.scheme == "https":
            return True

        # Allow localhost/127.0.0.1 for development
        host = parsed.hostname or ""
        if host in ("localhost", "127.0.0.1", "::1"):
            return True

        return False

    def _should_retry(self, status_code: int) -> bool:
        """Determine if a request should be retried based on status code.

        Args:
            status_code: HTTP status code.

        Returns:
            True if request should be retried.
        """
        # Retry on 5xx server errors
        if 500 <= status_code < 600:
            return True

        # Retry on 429 rate limit
        if status_code == 429:
            return True

        return False

    def _should_dispatch(self, config: WebhookConfig, payload: WebhookPayload) -> bool:
        """Check if event should be dispatched based on subscription.

        Args:
            config: Webhook configuration with event subscriptions.
            payload: The webhook payload with event type.

        Returns:
            True if event matches subscription.
        """
        return payload.event in config.events

    async def dispatch(
        self,
        config: WebhookConfig,
        payload: WebhookPayload,
    ) -> WebhookDeliveryResult:
        """Dispatch a webhook to a single endpoint.

        Args:
            config: Webhook configuration.
            payload: The payload to send.

        Returns:
            WebhookDeliveryResult with delivery status.
        """
        # Check if event is subscribed
        if not self._should_dispatch(config, payload):
            return WebhookDeliveryResult(
                success=True,
                status_code=-1,  # Skipped indicator
                attempt=0,
                error=None,
            )

        # Check URL policy
        if not self._is_url_allowed(config.url):
            return WebhookDeliveryResult(
                success=False,
                status_code=0,
                attempt=1,
                error=f"HTTPS required. URL must use https:// (got: {config.url})",
            )

        # Serialize payload
        payload_json = payload.model_dump_json()

        # Generate headers
        headers = {
            "Content-Type": "application/json",
            **generate_webhook_headers(payload_json, config.secret),
        }

        # Attempt delivery with retries
        last_error = None
        last_status = 0

        for attempt in range(1, self._max_retries + 1):
            start_time = time.time()

            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.post(
                        config.url,
                        content=payload_json,
                        headers=headers,
                    )

                latency_ms = int((time.time() - start_time) * 1000)
                last_status = response.status_code

                # Success
                if 200 <= response.status_code < 300:
                    return WebhookDeliveryResult(
                        success=True,
                        status_code=response.status_code,
                        attempt=attempt,
                        latency_ms=latency_ms,
                    )

                # Check if we should retry
                if not self._should_retry(response.status_code):
                    return WebhookDeliveryResult(
                        success=False,
                        status_code=response.status_code,
                        attempt=attempt,
                        error=f"HTTP {response.status_code}",
                        latency_ms=latency_ms,
                    )

                last_error = f"HTTP {response.status_code}"

                # Wait before retry (exponential backoff)
                if attempt < self._max_retries:
                    # Check for Retry-After header on 429
                    retry_after = 1
                    if response.status_code == 429:
                        retry_after_header = response.headers.get("Retry-After", "1")
                        try:
                            retry_after = int(retry_after_header)
                        except ValueError:
                            retry_after = 1

                    await asyncio.sleep(min(retry_after, 2 ** (attempt - 1)))

            except httpx.TimeoutException as e:
                latency_ms = int((time.time() - start_time) * 1000)
                last_error = f"Timeout after {self._timeout}s"
                last_status = 0

                # Retry on timeout
                if attempt < self._max_retries:
                    await asyncio.sleep(2 ** (attempt - 1))

            except httpx.ConnectError as e:
                latency_ms = int((time.time() - start_time) * 1000)
                last_error = f"Connection error: {e}"
                last_status = 0

                # Retry on connection error
                if attempt < self._max_retries:
                    await asyncio.sleep(2 ** (attempt - 1))

            except Exception as e:
                latency_ms = int((time.time() - start_time) * 1000)
                last_error = str(e)
                last_status = 0
                break  # Don't retry on unexpected errors

        # All retries exhausted
        return WebhookDeliveryResult(
            success=False,
            status_code=last_status,
            attempt=self._max_retries,
            error=last_error,
        )

    async def dispatch_batch(
        self,
        configs: List[WebhookConfig],
        payload: WebhookPayload,
    ) -> List[WebhookDeliveryResult]:
        """Dispatch a webhook to multiple endpoints concurrently.

        Args:
            configs: List of webhook configurations.
            payload: The payload to send.

        Returns:
            List of WebhookDeliveryResults for each endpoint.
        """
        tasks = [self.dispatch(config, payload) for config in configs]
        return await asyncio.gather(*tasks)
