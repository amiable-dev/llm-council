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


@pytest.fixture(autouse=True)
def isolate_performance_store(tmp_path, monkeypatch):
    """#693: no test may append to the operator's real performance store.

    `~/.llm-council/performance_metrics.jsonl` on a developer machine had
    accumulated 1,868 `test/model-a` fixture records — about a quarter of the
    file. They carry `cost_usd: null`, so a reader totalling cost saw a third
    of rows missing one and concluded the capture pipeline was broken. It was
    not. The fixtures made working code look faulty.

    Autouse and unconditional, because the call sites that write are not the
    ones that look like they write: seven `run_verification` tests reached the
    real `persist_session_performance_data` through three layers without
    mentioning it. Opting in per test is how this happened.

    The singleton reset is load-bearing — `get_tracker()` memoises a tracker
    built from the path resolved at its first call, so a tracker constructed
    before this fixture would keep the old path for the rest of the session.

    `tests/test_issue693_store_isolation.py` fails if this fixture stops
    working, which is the difference between a convention and an invariant.
    """
    from llm_council.performance import integration

    monkeypatch.setenv(
        "LLM_COUNCIL_PERFORMANCE_STORE", str(tmp_path / "performance_metrics.jsonl")
    )
    # Pin the ENABLED inputs too, not just the path. A developer or CI shell
    # carrying LLM_COUNCIL_PERFORMANCE_TRACKING=false would otherwise silently
    # turn persistence off and fail the tests that assert a record was written
    # — flaky-by-environment (cf. #641), and the failure would look like a
    # capture bug rather than a harness one. Forced on, so tests that need it
    # off opt out explicitly.
    monkeypatch.setenv("LLM_COUNCIL_PERFORMANCE_TRACKING", "true")
    # Clear any leaked overrides so the env vars above are what resolve.
    monkeypatch.setattr(integration, "PERFORMANCE_STORE_PATH", None, raising=False)
    monkeypatch.setattr(integration, "PERFORMANCE_TRACKING_ENABLED", None, raising=False)
    integration._reset_tracker_singleton()
    yield
    integration._reset_tracker_singleton()


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
