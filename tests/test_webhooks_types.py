"""Tests for webhook types (ADR-025).

TDD: Write these tests first, then implement webhook types.
"""

import pytest
from datetime import datetime


class TestWebhookEventType:
    """Test WebhookEventType enum."""

    def test_event_types_exist(self):
        """All required event types should be defined."""
        from llm_council.webhooks.types import WebhookEventType

        # Required events per ADR-025
        assert WebhookEventType.DELIBERATION_START.value == "council.deliberation_start"
        assert WebhookEventType.STAGE1_COMPLETE.value == "council.stage1.complete"
        assert WebhookEventType.MODEL_VOTE_CAST.value == "model.vote_cast"
        assert WebhookEventType.STAGE2_COMPLETE.value == "council.stage2.complete"
        assert WebhookEventType.CONSENSUS_REACHED.value == "consensus.reached"
        assert WebhookEventType.COMPLETE.value == "council.complete"
        assert WebhookEventType.ERROR.value == "council.error"

    def test_event_type_is_string_enum(self):
        """Event types should be string enums."""
        from llm_council.webhooks.types import WebhookEventType

        assert isinstance(WebhookEventType.COMPLETE.value, str)
        assert str(WebhookEventType.COMPLETE) == "WebhookEventType.COMPLETE"


class TestWebhookConfig:
    """Test WebhookConfig model."""

    def test_webhook_config_creation(self):
        """Should create WebhookConfig with url and events."""
        from llm_council.webhooks.types import WebhookConfig

        config = WebhookConfig(
            url="https://example.com/webhook", events=["council.complete", "council.error"]
        )

        assert config.url == "https://example.com/webhook"
        assert config.events == ["council.complete", "council.error"]

    def test_webhook_config_default_events(self):
        """Should have default events if not specified."""
        from llm_council.webhooks.types import WebhookConfig

        config = WebhookConfig(url="https://example.com/webhook")

        assert config.events == ["council.complete", "council.error"]

    def test_webhook_config_with_secret(self):
        """Should accept optional HMAC secret."""
        from llm_council.webhooks.types import WebhookConfig

        config = WebhookConfig(url="https://example.com/webhook", secret="my-hmac-secret")

        assert config.secret == "my-hmac-secret"

    def test_webhook_config_secret_optional(self):
        """Secret should be optional (None by default)."""
        from llm_council.webhooks.types import WebhookConfig

        config = WebhookConfig(url="https://example.com/webhook")

        assert config.secret is None

    def test_webhook_config_url_required(self):
        """URL should be required."""
        from llm_council.webhooks.types import WebhookConfig
        from pydantic import ValidationError

        with pytest.raises((ValidationError, TypeError)):
            WebhookConfig()


class TestWebhookPayload:
    """Test WebhookPayload model."""

    def test_webhook_payload_creation(self):
        """Should create WebhookPayload with required fields."""
        from llm_council.webhooks.types import WebhookPayload

        now = datetime.now()
        payload = WebhookPayload(
            event="council.complete",
            request_id="req-123",
            timestamp=now,
            data={"result": "success"},
        )

        assert payload.event == "council.complete"
        assert payload.request_id == "req-123"
        assert payload.timestamp == now
        assert payload.data == {"result": "success"}

    def test_webhook_payload_with_duration(self):
        """Should accept optional duration_ms."""
        from llm_council.webhooks.types import WebhookPayload

        payload = WebhookPayload(
            event="council.complete",
            request_id="req-123",
            timestamp=datetime.now(),
            data={},
            duration_ms=1234,
        )

        assert payload.duration_ms == 1234

    def test_webhook_payload_duration_optional(self):
        """Duration should be optional (None by default)."""
        from llm_council.webhooks.types import WebhookPayload

        payload = WebhookPayload(
            event="council.complete", request_id="req-123", timestamp=datetime.now(), data={}
        )

        assert payload.duration_ms is None

    def test_webhook_payload_to_dict(self):
        """Should serialize to dict for JSON."""
        from llm_council.webhooks.types import WebhookPayload

        now = datetime.now()
        payload = WebhookPayload(
            event="council.complete",
            request_id="req-123",
            timestamp=now,
            data={"result": "success"},
        )

        d = payload.model_dump()
        assert d["event"] == "council.complete"
        assert d["request_id"] == "req-123"
        assert d["data"] == {"result": "success"}

    def test_webhook_payload_serializes_datetime(self):
        """Timestamp should serialize to ISO format."""
        from llm_council.webhooks.types import WebhookPayload

        now = datetime.now()
        payload = WebhookPayload(
            event="council.complete", request_id="req-123", timestamp=now, data={}
        )

        json_str = payload.model_dump_json()
        assert "timestamp" in json_str


class TestWebhookDeliveryResult:
    """Test WebhookDeliveryResult model."""

    def test_delivery_result_success(self):
        """Should represent successful delivery."""
        from llm_council.webhooks.types import WebhookDeliveryResult

        result = WebhookDeliveryResult(success=True, status_code=200, attempt=1)

        assert result.success is True
        assert result.status_code == 200
        assert result.attempt == 1

    def test_delivery_result_failure(self):
        """Should represent failed delivery."""
        from llm_council.webhooks.types import WebhookDeliveryResult

        result = WebhookDeliveryResult(
            success=False, status_code=500, attempt=3, error="Internal server error"
        )

        assert result.success is False
        assert result.status_code == 500
        assert result.error == "Internal server error"

    def test_delivery_result_with_latency(self):
        """Should include latency_ms."""
        from llm_council.webhooks.types import WebhookDeliveryResult

        result = WebhookDeliveryResult(success=True, status_code=200, attempt=1, latency_ms=45)

        assert result.latency_ms == 45
