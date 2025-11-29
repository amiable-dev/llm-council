"""Shared test configuration and fixtures."""
import pytest


@pytest.fixture(autouse=True)
def reset_env(monkeypatch):
    """Clear environment variables before each test."""
    # Clear any LLM Council related env vars
    monkeypatch.delenv("LLM_COUNCIL_MODELS", raising=False)
    monkeypatch.delenv("LLM_COUNCIL_CHAIRMAN", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
