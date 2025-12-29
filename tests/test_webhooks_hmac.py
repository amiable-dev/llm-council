"""Tests for webhook HMAC authentication (ADR-025).

TDD: Write these tests first, then implement HMAC auth.
"""

import pytest
import time
from datetime import datetime


class TestHMACSignatureGeneration:
    """Test HMAC signature generation."""

    def test_generate_signature(self):
        """Should generate HMAC-SHA256 signature."""
        from llm_council.webhooks.hmac_auth import generate_signature

        payload = '{"event": "council.complete"}'
        secret = "test-secret"

        signature = generate_signature(payload, secret)

        # Should be hex digest
        assert isinstance(signature, str)
        assert len(signature) == 64  # SHA256 produces 64 hex chars

    def test_generate_signature_deterministic(self):
        """Same payload and secret should produce same signature."""
        from llm_council.webhooks.hmac_auth import generate_signature

        payload = '{"event": "council.complete"}'
        secret = "test-secret"

        sig1 = generate_signature(payload, secret)
        sig2 = generate_signature(payload, secret)

        assert sig1 == sig2

    def test_generate_signature_different_secrets(self):
        """Different secrets should produce different signatures."""
        from llm_council.webhooks.hmac_auth import generate_signature

        payload = '{"event": "council.complete"}'

        sig1 = generate_signature(payload, "secret-1")
        sig2 = generate_signature(payload, "secret-2")

        assert sig1 != sig2

    def test_generate_signature_different_payloads(self):
        """Different payloads should produce different signatures."""
        from llm_council.webhooks.hmac_auth import generate_signature

        secret = "test-secret"

        sig1 = generate_signature('{"event": "council.complete"}', secret)
        sig2 = generate_signature('{"event": "council.error"}', secret)

        assert sig1 != sig2


class TestHMACSignatureVerification:
    """Test HMAC signature verification."""

    def test_verify_signature_valid(self):
        """Should verify valid signature."""
        from llm_council.webhooks.hmac_auth import generate_signature, verify_signature

        payload = '{"event": "council.complete"}'
        secret = "test-secret"
        signature = generate_signature(payload, secret)

        assert verify_signature(payload, signature, secret) is True

    def test_verify_signature_invalid(self):
        """Should reject invalid signature."""
        from llm_council.webhooks.hmac_auth import verify_signature

        payload = '{"event": "council.complete"}'
        secret = "test-secret"
        invalid_signature = "0" * 64

        assert verify_signature(payload, invalid_signature, secret) is False

    def test_verify_signature_tampered_payload(self):
        """Should reject if payload was tampered."""
        from llm_council.webhooks.hmac_auth import generate_signature, verify_signature

        original_payload = '{"event": "council.complete"}'
        tampered_payload = '{"event": "council.error"}'
        secret = "test-secret"
        signature = generate_signature(original_payload, secret)

        assert verify_signature(tampered_payload, signature, secret) is False

    def test_verify_signature_wrong_secret(self):
        """Should reject if wrong secret used for verification."""
        from llm_council.webhooks.hmac_auth import generate_signature, verify_signature

        payload = '{"event": "council.complete"}'
        signature = generate_signature(payload, "secret-1")

        assert verify_signature(payload, signature, "secret-2") is False


class TestWebhookHeaders:
    """Test webhook header generation (n8n compatible)."""

    def test_generate_headers(self):
        """Should generate webhook headers."""
        from llm_council.webhooks.hmac_auth import generate_webhook_headers

        payload = '{"event": "council.complete"}'
        secret = "test-secret"

        headers = generate_webhook_headers(payload, secret)

        assert "X-Council-Signature" in headers
        assert "X-Council-Timestamp" in headers
        assert "X-Council-Version" in headers

    def test_signature_header_format(self):
        """Signature header should have sha256= prefix."""
        from llm_council.webhooks.hmac_auth import generate_webhook_headers

        payload = '{"event": "council.complete"}'
        secret = "test-secret"

        headers = generate_webhook_headers(payload, secret)

        assert headers["X-Council-Signature"].startswith("sha256=")

    def test_timestamp_header_is_unix(self):
        """Timestamp header should be unix timestamp."""
        from llm_council.webhooks.hmac_auth import generate_webhook_headers

        payload = '{"event": "council.complete"}'
        secret = "test-secret"

        before = int(time.time())
        headers = generate_webhook_headers(payload, secret)
        after = int(time.time())

        timestamp = int(headers["X-Council-Timestamp"])
        assert before <= timestamp <= after

    def test_version_header(self):
        """Version header should be 1.0."""
        from llm_council.webhooks.hmac_auth import generate_webhook_headers

        payload = '{"event": "council.complete"}'
        secret = "test-secret"

        headers = generate_webhook_headers(payload, secret)

        assert headers["X-Council-Version"] == "1.0"

    def test_headers_without_secret(self):
        """Should generate headers without signature when no secret."""
        from llm_council.webhooks.hmac_auth import generate_webhook_headers

        payload = '{"event": "council.complete"}'

        headers = generate_webhook_headers(payload, secret=None)

        assert "X-Council-Signature" not in headers
        assert "X-Council-Timestamp" in headers
        assert "X-Council-Version" in headers


class TestTimestampValidation:
    """Test timestamp validation to prevent replay attacks."""

    def test_validate_timestamp_valid(self):
        """Should accept recent timestamp."""
        from llm_council.webhooks.hmac_auth import validate_timestamp

        current_timestamp = str(int(time.time()))

        assert validate_timestamp(current_timestamp) is True

    def test_validate_timestamp_expired(self):
        """Should reject old timestamp (>5 min)."""
        from llm_council.webhooks.hmac_auth import validate_timestamp

        old_timestamp = str(int(time.time()) - 600)  # 10 minutes ago

        assert validate_timestamp(old_timestamp) is False

    def test_validate_timestamp_future(self):
        """Should reject future timestamp (>1 min)."""
        from llm_council.webhooks.hmac_auth import validate_timestamp

        future_timestamp = str(int(time.time()) + 120)  # 2 minutes in future

        assert validate_timestamp(future_timestamp) is False

    def test_validate_timestamp_custom_tolerance(self):
        """Should accept custom tolerance window."""
        from llm_council.webhooks.hmac_auth import validate_timestamp

        old_timestamp = str(int(time.time()) - 600)

        # With 15 minute tolerance, should pass
        assert validate_timestamp(old_timestamp, tolerance_seconds=900) is True


class TestVerifyWebhookRequest:
    """Test full webhook request verification."""

    def test_verify_request_valid(self):
        """Should verify valid request with all headers."""
        from llm_council.webhooks.hmac_auth import generate_webhook_headers, verify_webhook_request

        payload = '{"event": "council.complete"}'
        secret = "test-secret"
        headers = generate_webhook_headers(payload, secret)

        assert verify_webhook_request(payload, headers, secret) is True

    def test_verify_request_invalid_signature(self):
        """Should reject invalid signature."""
        from llm_council.webhooks.hmac_auth import verify_webhook_request
        import time

        payload = '{"event": "council.complete"}'
        headers = {
            "X-Council-Signature": "sha256=" + "0" * 64,
            "X-Council-Timestamp": str(int(time.time())),
            "X-Council-Version": "1.0",
        }
        secret = "test-secret"

        assert verify_webhook_request(payload, headers, secret) is False

    def test_verify_request_expired_timestamp(self):
        """Should reject expired timestamp."""
        from llm_council.webhooks.hmac_auth import generate_signature, verify_webhook_request

        payload = '{"event": "council.complete"}'
        secret = "test-secret"
        old_timestamp = str(int(time.time()) - 600)
        headers = {
            "X-Council-Signature": "sha256=" + generate_signature(payload, secret),
            "X-Council-Timestamp": old_timestamp,
            "X-Council-Version": "1.0",
        }

        assert verify_webhook_request(payload, headers, secret) is False

    def test_verify_request_missing_signature(self):
        """Should reject missing signature header."""
        from llm_council.webhooks.hmac_auth import verify_webhook_request
        import time

        payload = '{"event": "council.complete"}'
        headers = {"X-Council-Timestamp": str(int(time.time())), "X-Council-Version": "1.0"}
        secret = "test-secret"

        assert verify_webhook_request(payload, headers, secret) is False

    def test_verify_request_no_secret_skips_signature(self):
        """Should skip signature check when no secret provided."""
        from llm_council.webhooks.hmac_auth import verify_webhook_request
        import time

        payload = '{"event": "council.complete"}'
        headers = {"X-Council-Timestamp": str(int(time.time())), "X-Council-Version": "1.0"}

        # No secret = no signature verification
        assert verify_webhook_request(payload, headers, secret=None) is True
