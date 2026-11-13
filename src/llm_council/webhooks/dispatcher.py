"""Webhook dispatcher for LLM Council (ADR-025).

This module provides async webhook delivery with retry logic,
HMAC authentication, and destination enforcement (``url_guard``:
HTTPS, public-address-only, DNS-pinned — GHSA-r7rh-j9cj-h9hh).
"""

import asyncio
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx

# ADR-032: Migrated to unified_config
from llm_council.unified_config import get_config

from .types import WebhookConfig, WebhookPayload, WebhookDeliveryResult
from .hmac_auth import generate_webhook_headers
from .url_guard import WebhookTarget, WebhookTargetError, resolve_webhook_target


def _get_webhook_config():
    """Get webhook configuration from unified config."""
    try:
        config = get_config()
        if hasattr(config, "webhooks"):
            return config.webhooks
    except Exception:
        pass
    return None


# Fallbacks, used only when the unified config cannot be read.
DEFAULT_TIMEOUT = 5.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_HTTPS_ONLY = True


def webhook_settings() -> Tuple[float, int, bool]:
    """(timeout seconds, max attempts, https_only) from the unified config.

    Read at CALL time (#741). These used to be frozen into module constants at
    import, and the timeout was looked up under the wrong attribute name
    (``timeout`` for ``timeout_seconds``), so ``LLM_COUNCIL_WEBHOOK_TIMEOUT``
    and the YAML key never took effect.
    """
    config = _get_webhook_config()
    if config is None:
        return DEFAULT_TIMEOUT, DEFAULT_MAX_RETRIES, DEFAULT_HTTPS_ONLY
    return (
        float(getattr(config, "timeout_seconds", DEFAULT_TIMEOUT)),
        int(getattr(config, "max_retries", DEFAULT_MAX_RETRIES)),
        bool(getattr(config, "https_only", DEFAULT_HTTPS_ONLY)),
    )


class WebhookDispatcher:
    """Async webhook dispatcher with retry and HMAC support.

    Features:
    - Automatic retry on 5xx and 429 errors
    - HMAC signature authentication
    - Destination guard: HTTPS, public addresses only, DNS-pinned connect
      (operator allowlist: LLM_COUNCIL_WEBHOOK_ALLOWED_HOSTS)
    - Exponential backoff on retries
    """

    def __init__(
        self,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
        https_only: Optional[bool] = None,
    ):
        """Initialize the dispatcher.

        An argument left as None takes its value from the unified config
        (``webhook_settings``) at construction time.

        Args:
            timeout: Request timeout in seconds.
            max_retries: Maximum retry attempts.
            https_only: Require HTTPS (except operator-allowlisted hosts).
        """
        cfg_timeout, cfg_retries, cfg_https_only = webhook_settings()
        self._timeout = cfg_timeout if timeout is None else timeout
        self._max_retries = cfg_retries if max_retries is None else max_retries
        self._https_only = cfg_https_only if https_only is None else https_only

    @staticmethod
    def _request_parts(target: WebhookTarget) -> Tuple[Any, Dict[str, str], Dict[str, Any]]:
        """(url, extra headers, httpx extensions) that connect to the CHECKED address.

        For a DNS name the socket goes to ``pinned_ip`` — the address the guard
        approved — while ``Host`` and TLS (SNI + certificate verification, via
        httpx's ``sni_hostname``) still use the name. Resolving again here would
        let a second DNS answer differ from the one that was checked.
        """
        if target.allowlisted or target.pinned_ip is None or target.pinned_ip == target.host:
            return target.url, {}, {}
        original = httpx.URL(target.url)
        pinned = original.copy_with(host=target.pinned_ip)
        extensions: Dict[str, Any] = {}
        if target.scheme == "https":
            extensions["sni_hostname"] = target.host
        return pinned, {"Host": original.netloc.decode("ascii")}, extensions

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

        # Destination guard. Resolved ONCE, before the retry loop: a rejected
        # target makes no connection and no retries (nothing to time), and an
        # accepted one is pinned for every attempt. The error never echoes the
        # caller-controlled URL (it is logged).
        try:
            target = await resolve_webhook_target(config.url, https_only=self._https_only)
        except WebhookTargetError as e:
            return WebhookDeliveryResult(success=False, status_code=0, attempt=1, error=str(e))
        request_url, pin_headers, extensions = self._request_parts(target)

        # Serialize payload
        payload_json = payload.model_dump_json()

        # Generate headers
        headers = {
            "Content-Type": "application/json",
            **generate_webhook_headers(payload_json, config.secret),
            **pin_headers,
        }

        # Attempt delivery with retries
        last_error = None
        last_status = 0

        for attempt in range(1, self._max_retries + 1):
            start_time = time.time()

            try:
                # follow_redirects=False is load-bearing: a redirect would be
                # an unchecked second destination.
                async with httpx.AsyncClient(
                    timeout=self._timeout, follow_redirects=False
                ) as client:
                    response = await client.post(
                        request_url,
                        content=payload_json,
                        headers=headers,
                        extensions=extensions,
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
