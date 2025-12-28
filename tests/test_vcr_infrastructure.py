"""Tests for VCR infrastructure.

These tests ensure the VCR recording infrastructure is properly configured.
"""

from pathlib import Path

import pytest


def test_cassettes_directory_exists():
    """Verify tests/cassettes directory exists."""
    cassettes_dir = Path(__file__).parent / "cassettes"
    assert cassettes_dir.exists(), "tests/cassettes/ directory must exist"
    assert cassettes_dir.is_dir(), "tests/cassettes/ must be a directory"


def test_vcr_config_fixture_exists(vcr_config):
    """Verify vcr_config fixture is available and returns dict."""
    assert isinstance(vcr_config, dict), "vcr_config should return a dict"


def test_vcr_config_has_cassette_library(vcr_config):
    """Verify vcr_config specifies cassette library directory."""
    assert "cassette_library_dir" in vcr_config
    cassette_dir = vcr_config["cassette_library_dir"]
    assert "cassettes" in cassette_dir


def test_vcr_config_filters_secrets(vcr_config):
    """Verify vcr_config filters sensitive headers."""
    filter_headers = vcr_config.get("filter_headers", [])
    # Convert to lowercase strings for comparison
    header_names = [h.lower() if isinstance(h, str) else h[0].lower() for h in filter_headers]

    assert "authorization" in header_names, "Should filter authorization header"
    assert "x-api-key" in header_names, "Should filter x-api-key header"


def test_vcr_config_has_record_mode(vcr_config):
    """Verify vcr_config specifies record mode."""
    assert "record_mode" in vcr_config
    # Default should be 'none' to fail on missing cassettes in CI
    assert vcr_config["record_mode"] == "none"


def test_vcr_config_filters_query_params(vcr_config):
    """Verify vcr_config filters sensitive query parameters."""
    filter_params = vcr_config.get("filter_query_parameters", [])
    assert "api_key" in filter_params, "Should filter api_key query param"


def test_filter_request_body_filters_openrouter_key():
    """Verify request body filter removes OpenRouter API keys."""
    from conftest import _filter_request_body

    class MockRequest:
        body = '{"api_key": "sk-or-v1-abc123xyz"}'

    request = MockRequest()
    filtered = _filter_request_body(request)

    assert "sk-or-v1-abc123xyz" not in filtered.body
    assert "sk-or-v1-FILTERED" in filtered.body


def test_filter_request_body_filters_anthropic_key():
    """Verify request body filter removes Anthropic API keys."""
    from conftest import _filter_request_body

    class MockRequest:
        body = '{"api_key": "sk-ant-api03-abc123"}'

    request = MockRequest()
    filtered = _filter_request_body(request)

    assert "sk-ant-api03-abc123" not in filtered.body
    assert "sk-ant-FILTERED" in filtered.body


def test_slow_marker_registered():
    """Verify slow marker is registered."""
    # This test verifies that pytest_configure registered the markers
    # If the marker wasn't registered, pytest would warn about unknown markers
    pass


@pytest.mark.slow
def test_slow_marker_can_be_used():
    """Verify slow marker can be applied to tests."""
    # This test is just to verify the marker works
    pass


@pytest.mark.vcr
def test_vcr_marker_can_be_used():
    """Verify vcr marker can be applied to tests."""
    # This test is just to verify the marker works
    pass
