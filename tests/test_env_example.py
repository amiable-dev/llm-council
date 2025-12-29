"""Tests for .env.example template file.

These tests ensure the .env.example file:
1. Exists and is readable
2. Contains required environment variables
3. Does not contain real secrets
"""

import os
from pathlib import Path

import pytest


@pytest.fixture
def env_example_content() -> str:
    """Read the .env.example file content."""
    env_path = Path(__file__).parent.parent / ".env.example"
    assert env_path.exists(), ".env.example file must exist"
    return env_path.read_text()


def test_env_example_exists():
    """Verify .env.example file exists in project root."""
    env_path = Path(__file__).parent.parent / ".env.example"
    assert env_path.exists(), ".env.example file must exist"
    assert env_path.is_file(), ".env.example must be a file"


def test_env_example_has_required_vars(env_example_content: str):
    """Ensure .env.example includes essential variables."""
    required_vars = [
        "OPENROUTER_API_KEY",
        "LLM_COUNCIL_MODELS",
    ]
    for var in required_vars:
        assert var in env_example_content, f"Required variable {var} not in .env.example"


def test_env_example_has_gateway_options(env_example_content: str):
    """Ensure .env.example documents gateway options."""
    gateway_vars = [
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        "LLM_COUNCIL_DEFAULT_GATEWAY",
    ]
    for var in gateway_vars:
        assert var in env_example_content, f"Gateway variable {var} not in .env.example"


def test_env_example_has_no_real_secrets(env_example_content: str):
    """Ensure no actual API keys in template."""
    # OpenRouter API key patterns
    assert "sk-or-v1-" not in env_example_content, "Real OpenRouter key found"

    # Anthropic API key patterns
    assert "sk-ant-api" not in env_example_content, "Real Anthropic key found"

    # OpenAI API key patterns (but allow "sk-..." as placeholder)
    lines_with_sk = [
        line
        for line in env_example_content.split("\n")
        if "sk-" in line
        and not line.strip().startswith("#")
        and "=sk-..." not in line
        and "=sk-ant-..." not in line
    ]
    assert len(lines_with_sk) == 0, f"Potential real key found in lines: {lines_with_sk}"


def test_env_example_has_comments(env_example_content: str):
    """Ensure .env.example has helpful comments."""
    # Should have section headers
    assert "REQUIRED" in env_example_content, "Missing REQUIRED section header"
    assert "OPTIONAL" in env_example_content, "Missing OPTIONAL section header"

    # Should have instructions
    assert (
        "Copy this file" in env_example_content or "copy" in env_example_content.lower()
    ), "Missing copy instructions"


def test_env_example_warns_about_committing(env_example_content: str):
    """Ensure .env.example warns not to commit .env."""
    warning_phrases = ["NEVER commit", "never commit", "do not commit", "Don't commit"]
    has_warning = any(phrase in env_example_content for phrase in warning_phrases)
    assert has_warning, ".env.example should warn about not committing .env"


def test_env_example_documents_feature_flags(env_example_content: str):
    """Ensure .env.example documents key feature flags."""
    feature_flags = [
        "LLM_COUNCIL_RUBRIC_SCORING",
        "LLM_COUNCIL_BIAS_AUDIT",
        "LLM_COUNCIL_WILDCARD_ENABLED",
    ]
    for flag in feature_flags:
        assert flag in env_example_content, f"Feature flag {flag} not documented in .env.example"
