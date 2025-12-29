"""Shared test configuration and fixtures."""

from pathlib import Path

import pytest

# =============================================================================
# Environment Reset
# =============================================================================


@pytest.fixture(autouse=True)
def reset_env(monkeypatch):
    """Clear environment variables before each test."""
    # Clear any LLM Council related env vars
    monkeypatch.delenv("LLM_COUNCIL_MODELS", raising=False)
    monkeypatch.delenv("LLM_COUNCIL_CHAIRMAN", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)


# =============================================================================
# VCR Configuration (ADR-033)
# =============================================================================
# See: https://vcrpy.readthedocs.io/en/latest/configuration.html
#
# Usage:
#   @pytest.mark.vcr()
#   def test_api_call():
#       ...
#
# To record new cassettes:
#   pytest --record-mode=once tests/test_file.py
#
# To update existing cassettes:
#   pytest --record-mode=new_episodes tests/test_file.py


@pytest.fixture(scope="module")
def vcr_config():
    """VCR configuration for recording/replaying HTTP interactions.

    This fixture is automatically used by pytest-recording when tests
    are marked with @pytest.mark.vcr().
    """
    return {
        # Store cassettes in tests/cassettes/
        "cassette_library_dir": str(Path(__file__).parent / "cassettes"),
        # Don't record in CI - fail if cassette missing
        "record_mode": "none",
        # Filter sensitive headers
        "filter_headers": [
            "authorization",
            "x-api-key",
            "openrouter-api-key",
            "anthropic-api-key",
            "openai-api-key",
            ("user-agent", "test-agent"),
        ],
        # Filter sensitive query parameters
        "filter_query_parameters": [
            "api_key",
            "key",
            "token",
        ],
        # Filter request body for API keys
        "before_record_request": _filter_request_body,
        # Decode compressed responses for readability
        "decode_compressed_response": True,
        # Match on these criteria
        "match_on": ["method", "scheme", "host", "port", "path", "query"],
    }


def _filter_request_body(request):
    """Filter sensitive data from request bodies before recording."""
    # Don't modify the original request
    if request.body:
        body = request.body
        if isinstance(body, bytes):
            body = body.decode("utf-8", errors="ignore")

        # Replace API key patterns
        import re

        # Order matters: apply more specific patterns first
        patterns = [
            (r"sk-or-v1-[a-zA-Z0-9_-]+", "sk-or-v1-FILTERED"),
            (r"sk-ant-api[a-zA-Z0-9_-]+", "sk-ant-FILTERED"),
            (r"sk-ant-[a-zA-Z0-9_-]+", "sk-ant-FILTERED"),
            (r"sk-proj-[a-zA-Z0-9_-]+", "sk-proj-FILTERED"),  # OpenAI project keys
        ]
        for pattern, replacement in patterns:
            body = re.sub(pattern, replacement, body)

        request.body = body.encode("utf-8") if isinstance(request.body, bytes) else body

    return request


# =============================================================================
# Custom Pytest Markers
# =============================================================================


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "vcr: marks tests to use VCR cassette recording")
