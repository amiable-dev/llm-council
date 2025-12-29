"""Tests for llm_council configuration.

ADR-032: Migrated from config.py to unified_config.py.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch
import yaml
import pytest


def test_config_loads_api_key_from_env():
    """Test that API key is loaded from environment variable."""
    from llm_council import unified_config

    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
        # Reload config to pick up env var
        unified_config.reload_config()

        key = unified_config.get_api_key("openrouter")
        assert key == "test-key"

    # Cleanup
    unified_config.reload_config()


def test_council_models_from_env():
    """Test that council models can be set via environment variable."""
    from llm_council import unified_config

    test_models = "model1,model2,model3"
    with patch.dict(os.environ, {"LLM_COUNCIL_MODELS": test_models}):
        unified_config.reload_config()
        config = unified_config.get_config()

        assert config.council.models == ["model1", "model2", "model3"]

    # Cleanup
    unified_config.reload_config()


def test_council_models_from_env_json_format():
    """Test that council models can be set via JSON array env var."""
    from llm_council import unified_config

    test_models = '["model/a", "model/b", "model/c"]'
    with patch.dict(os.environ, {"LLM_COUNCIL_MODELS": test_models}):
        unified_config.reload_config()
        config = unified_config.get_config()

        assert config.council.models == ["model/a", "model/b", "model/c"]

    # Cleanup
    unified_config.reload_config()


def test_chairman_model_from_env():
    """Test that chairman model can be set via environment variable."""
    from llm_council import unified_config

    with patch.dict(os.environ, {"LLM_COUNCIL_CHAIRMAN": "test-chairman"}):
        unified_config.reload_config()
        config = unified_config.get_config()

        assert config.council.chairman == "test-chairman"

    # Cleanup
    unified_config.reload_config()


def test_yaml_config_file_loading():
    """Test that configuration can be loaded from YAML file."""
    from llm_council import unified_config

    with tempfile.TemporaryDirectory() as tmpdir:
        config_file = Path(tmpdir) / "llm_council.yaml"

        test_config = {
            "council": {
                "council": {"models": ["custom1", "custom2"], "chairman": "custom-chairman"}
            }
        }

        with open(config_file, "w") as f:
            yaml.dump(test_config, f)

        # Point env var to temp config file
        with patch.dict(os.environ, {"LLM_COUNCIL_CONFIG": str(config_file)}):
            unified_config.reload_config()
            config = unified_config.get_config()

            assert config.council.models == ["custom1", "custom2"]
            assert config.council.chairman == "custom-chairman"

    # Cleanup
    unified_config.reload_config()


def test_default_models_used():
    """Test that defaults are used when no config is provided."""
    from llm_council import unified_config

    with patch.dict(os.environ, {}, clear=True):
        # Point to non-existent config
        with patch("llm_council.unified_config._find_config_file", return_value=None):
            unified_config.reload_config()
            config = unified_config.get_config()

            # Should have default models
            assert len(config.council.models) >= 2
            assert len(config.council.chairman) > 0

    # Cleanup
    unified_config.reload_config()


def test_gateway_default_is_openrouter():
    """Test that default gateway is OpenRouter."""
    from llm_council import unified_config

    config = unified_config.get_config()

    assert config.gateways.default == "openrouter"


def test_openrouter_provider_configured():
    """Test that OpenRouter provider is configured."""
    from llm_council import unified_config

    config = unified_config.get_config()

    openrouter = config.gateways.providers.get("openrouter")
    assert openrouter is not None
    assert openrouter.enabled is True


def test_tier_pools_have_all_tiers():
    """Test that all expected tiers are configured."""
    from llm_council import unified_config

    config = unified_config.get_config()

    expected_tiers = {"quick", "balanced", "high", "reasoning", "frontier"}
    assert set(config.tiers.pools.keys()) == expected_tiers


def test_telemetry_default_off():
    """Test that telemetry is off by default."""
    from llm_council import unified_config

    config = unified_config.get_config()

    assert config.telemetry.level == "off"
    assert config.telemetry.enabled is False


def test_cache_default_disabled():
    """Test that cache is disabled by default."""
    from llm_council import unified_config

    config = unified_config.get_config()

    assert config.cache.enabled is False
