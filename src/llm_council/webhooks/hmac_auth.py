"""HMAC authentication for webhooks (ADR-025).

This module provides HMAC-SHA256 signature generation and verification
for secure webhook delivery. Compatible with n8n and other webhook systems.

Headers:
    X-Council-Signature: sha256=<hex-digest>
    X-Council-Timestamp: <unix-timestamp>
    X-Council-Version: 1.0
"""

import hmac
import hashlib
import time
from typing import Dict, Optional


def generate_signature(payload: str, secret: str) -> str:
    """Generate HMAC-SHA256 signature for a payload.

    Args:
        payload: The JSON payload string to sign.
        secret: The HMAC secret key.

    Returns:
        Hex-encoded signature string (64 characters).
    """
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_signature(payload: str, signature: str, secret: str) -> bool:
    """Verify HMAC-SHA256 signature for a payload.

    Uses constant-time comparison to prevent timing attacks.

    Args:
        payload: The JSON payload string that was signed.
        signature: The signature to verify (hex-encoded).
        secret: The HMAC secret key.

    Returns:
        True if signature is valid, False otherwise.
    """
    expected = generate_signature(payload, secret)
    return hmac.compare_digest(expected, signature)


def generate_webhook_headers(payload: str, secret: Optional[str] = None) -> Dict[str, str]:
    """Generate webhook headers including HMAC signature.

    Args:
        payload: The JSON payload string.
        secret: Optional HMAC secret. If None, signature is omitted.

    Returns:
        Dict of headers for webhook request.
    """
    headers = {
        "X-Council-Timestamp": str(int(time.time())),
        "X-Council-Version": "1.0",
    }

    if secret:
        signature = generate_signature(payload, secret)
        headers["X-Council-Signature"] = f"sha256={signature}"

    return headers


def validate_timestamp(timestamp: str, tolerance_seconds: int = 300) -> bool:
    """Validate timestamp to prevent replay attacks.

    Args:
        timestamp: Unix timestamp string.
        tolerance_seconds: Maximum age of timestamp (default 5 minutes).

    Returns:
        True if timestamp is within tolerance, False otherwise.
    """
    try:
        ts = int(timestamp)
    except (ValueError, TypeError):
        return False

    now = int(time.time())
    age = now - ts

    # Reject timestamps too old
    if age > tolerance_seconds:
        return False

    # Reject timestamps too far in future (max 60 seconds)
    if age < -60:
        return False

    return True


def verify_webhook_request(
    payload: str,
    headers: Dict[str, str],
    secret: Optional[str] = None,
    timestamp_tolerance: int = 300,
) -> bool:
    """Verify a complete webhook request.

    Performs signature verification and timestamp validation.

    Args:
        payload: The JSON payload string.
        headers: Request headers containing signature and timestamp.
        secret: HMAC secret. If None, signature check is skipped.
        timestamp_tolerance: Maximum age of timestamp in seconds.

    Returns:
        True if request is valid, False otherwise.
    """
    # Validate timestamp
    timestamp = headers.get("X-Council-Timestamp")
    if not timestamp or not validate_timestamp(timestamp, timestamp_tolerance):
        return False

    # Skip signature check if no secret
    if not secret:
        return True

    # Get signature from header
    signature_header = headers.get("X-Council-Signature")
    if not signature_header:
        return False

    # Parse signature (remove "sha256=" prefix)
    if not signature_header.startswith("sha256="):
        return False
    signature = signature_header[7:]  # len("sha256=") = 7

    return verify_signature(payload, signature, secret)
