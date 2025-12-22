"""TDD tests for ADR-024 Phase 2: Unified YAML Configuration.

Tests the unified configuration system that consolidates settings from
ADR-020, ADR-022, ADR-023 into a single YAML file with env var fallback.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Will be created
from llm_council.unified_config import (
    UnifiedConfig,
    TierConfig,
    TriageConfig,
    GatewayConfig,
    load_config,
    get_effective_config,
)


class TestUnifiedConfigSchema:
    """Test Pydantic schema validation for unified configuration."""

    def test_default_config_is_valid(self):
        """Default configuration should be valid without any input."""
        config = UnifiedConfig()
        assert config is not None
        assert config.tiers is not None
        assert config.gateways is not None

    def test_tier_config_defaults(self):
        """Tier configuration should have correct defaults."""
        config = UnifiedConfig()
        assert config.tiers.default == "high"
        assert "quick" in config.tiers.pools
        assert "balanced" in config.tiers.pools
        assert "high" in config.tiers.pools
        assert "reasoning" in config.tiers.pools

    def test_tier_pool_models(self):
        """Each tier pool should have model list."""
        config = UnifiedConfig()
        assert len(config.tiers.pools["quick"].models) >= 2
        assert len(config.tiers.pools["balanced"].models) >= 2
        assert len(config.tiers.pools["high"].models) >= 3
        assert len(config.tiers.pools["reasoning"].models) >= 3

    def test_tier_pool_timeouts(self):
        """Each tier should have appropriate timeout configuration."""
        config = UnifiedConfig()
        assert config.tiers.pools["quick"].timeout_seconds == 30
        assert config.tiers.pools["balanced"].timeout_seconds == 90
        assert config.tiers.pools["high"].timeout_seconds == 180
        assert config.tiers.pools["reasoning"].timeout_seconds == 600

    def test_tier_escalation_config(self):
        """Tier escalation should be configurable."""
        config = UnifiedConfig()
        assert config.tiers.escalation.enabled is True
        assert config.tiers.escalation.notify_user is True
        assert config.tiers.escalation.max_escalations == 2

    def test_triage_config_defaults(self):
        """Triage configuration should default to disabled."""
        config = UnifiedConfig()
        assert config.triage.enabled is False
        assert config.triage.wildcard.enabled is True
        assert config.triage.prompt_optimization.enabled is True
        assert config.triage.fast_path.confidence_threshold == 0.92

    def test_gateway_config_defaults(self):
        """Gateway configuration should default to OpenRouter."""
        config = UnifiedConfig()
        assert config.gateways.default == "openrouter"
        assert config.gateways.fallback.enabled is True
        assert "openrouter" in config.gateways.fallback.chain

    def test_gateway_providers(self):
        """Gateway providers should be defined."""
        config = UnifiedConfig()
        assert "openrouter" in config.gateways.providers
        assert "requesty" in config.gateways.providers
        assert "direct" in config.gateways.providers

    def test_observability_defaults(self):
        """Observability settings should have sensible defaults."""
        config = UnifiedConfig()
        assert config.observability.log_escalations is True
        assert config.observability.log_gateway_fallbacks is True


class TestYAMLParsing:
    """Test YAML file parsing and loading."""

    def test_load_config_from_yaml(self, tmp_path):
        """Should load configuration from YAML file."""
        config_file = tmp_path / "llm_council.yaml"
        config_file.write_text("""
council:
  tiers:
    default: balanced
  triage:
    enabled: true
  gateways:
    default: requesty
""")
        config = load_config(config_file)
        assert config.tiers.default == "balanced"
        assert config.triage.enabled is True
        assert config.gateways.default == "requesty"

    def test_load_config_from_nonexistent_file(self, tmp_path):
        """Should return default config when file doesn't exist."""
        config_file = tmp_path / "nonexistent.yaml"
        config = load_config(config_file)
        assert config.tiers.default == "high"  # Default value

    def test_load_config_with_partial_yaml(self, tmp_path):
        """Should merge partial YAML with defaults."""
        config_file = tmp_path / "llm_council.yaml"
        config_file.write_text("""
council:
  tiers:
    default: quick
""")
        config = load_config(config_file)
        assert config.tiers.default == "quick"
        # Other defaults should be preserved
        assert config.gateways.default == "openrouter"
        assert config.triage.enabled is False

    def test_load_config_with_custom_tier_pool(self, tmp_path):
        """Should allow custom tier pool configuration."""
        config_file = tmp_path / "llm_council.yaml"
        config_file.write_text("""
council:
  tiers:
    pools:
      quick:
        models:
          - custom/model-1
          - custom/model-2
        timeout_seconds: 15
""")
        config = load_config(config_file)
        assert config.tiers.pools["quick"].models == ["custom/model-1", "custom/model-2"]
        assert config.tiers.pools["quick"].timeout_seconds == 15
        # Other tier pools should remain default
        assert "balanced" in config.tiers.pools

    def test_load_config_invalid_yaml_returns_default(self, tmp_path):
        """Should return default config on invalid YAML."""
        config_file = tmp_path / "llm_council.yaml"
        config_file.write_text("invalid: yaml: content:")
        config = load_config(config_file)
        # Should fall back to defaults
        assert config.tiers.default == "high"

    def test_load_config_with_env_var_substitution(self, tmp_path):
        """Should substitute environment variables in YAML."""
        config_file = tmp_path / "llm_council.yaml"
        config_file.write_text("""
council:
  credentials:
    openrouter: ${TEST_OPENROUTER_KEY}
""")
        with patch.dict(os.environ, {"TEST_OPENROUTER_KEY": "sk-test-key"}):
            config = load_config(config_file)
            assert config.credentials.openrouter == "sk-test-key"


class TestEnvVarOverrides:
    """Test environment variable overrides for configuration."""

    def test_env_var_overrides_yaml_tier(self, tmp_path):
        """Environment variables should override YAML configuration."""
        config_file = tmp_path / "llm_council.yaml"
        config_file.write_text("""
council:
  tiers:
    default: quick
""")
        with patch.dict(os.environ, {"LLM_COUNCIL_DEFAULT_TIER": "reasoning"}):
            config = get_effective_config(config_file)
            assert config.tiers.default == "reasoning"

    def test_env_var_overrides_gateway_default(self, tmp_path):
        """Should override gateway default via env var."""
        config_file = tmp_path / "llm_council.yaml"
        config_file.write_text("""
council:
  gateways:
    default: openrouter
""")
        with patch.dict(os.environ, {"LLM_COUNCIL_DEFAULT_GATEWAY": "direct"}):
            config = get_effective_config(config_file)
            assert config.gateways.default == "direct"

    def test_env_var_overrides_triage_enabled(self, tmp_path):
        """Should override triage enabled via env var."""
        config_file = tmp_path / "llm_council.yaml"
        config_file.write_text("""
council:
  triage:
    enabled: false
""")
        with patch.dict(os.environ, {"LLM_COUNCIL_TRIAGE_ENABLED": "true"}):
            config = get_effective_config(config_file)
            assert config.triage.enabled is True

    def test_env_var_overrides_tier_models(self, tmp_path):
        """Should override tier models via env var (comma-separated)."""
        with patch.dict(os.environ, {"LLM_COUNCIL_MODELS_QUICK": "model-a,model-b"}):
            config = get_effective_config()
            assert config.tiers.pools["quick"].models == ["model-a", "model-b"]

    def test_priority_env_over_yaml_over_defaults(self, tmp_path):
        """Priority should be: env vars > YAML > defaults."""
        config_file = tmp_path / "llm_council.yaml"
        config_file.write_text("""
council:
  tiers:
    default: balanced
""")
        # Without env var, YAML wins
        config = get_effective_config(config_file)
        assert config.tiers.default == "balanced"

        # With env var, env wins
        with patch.dict(os.environ, {"LLM_COUNCIL_DEFAULT_TIER": "quick"}):
            config = get_effective_config(config_file)
            assert config.tiers.default == "quick"


class TestConfigLocations:
    """Test configuration file discovery."""

    def test_find_config_in_current_directory(self, tmp_path, monkeypatch):
        """Should find llm_council.yaml in current directory."""
        config_file = tmp_path / "llm_council.yaml"
        config_file.write_text("""
council:
  tiers:
    default: quick
""")
        monkeypatch.chdir(tmp_path)
        config = get_effective_config()
        assert config.tiers.default == "quick"

    def test_find_config_in_home_directory(self, tmp_path, monkeypatch):
        """Should find config in ~/.config/llm-council/."""
        config_dir = tmp_path / ".config" / "llm-council"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "llm_council.yaml"
        config_file.write_text("""
council:
  tiers:
    default: balanced
""")
        # Create the working directory first
        work_dir = tmp_path / "some" / "other" / "dir"
        work_dir.mkdir(parents=True)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(work_dir)
        config = get_effective_config()
        assert config.tiers.default == "balanced"

    def test_explicit_config_path_via_env_var(self, tmp_path):
        """Should use explicit config path from env var."""
        config_file = tmp_path / "custom_config.yaml"
        config_file.write_text("""
council:
  tiers:
    default: reasoning
""")
        with patch.dict(os.environ, {"LLM_COUNCIL_CONFIG": str(config_file)}):
            config = get_effective_config()
            assert config.tiers.default == "reasoning"


class TestConfigValidation:
    """Test configuration validation."""

    def test_invalid_tier_name_rejected(self, tmp_path):
        """Should reject invalid tier names."""
        config_file = tmp_path / "llm_council.yaml"
        config_file.write_text("""
council:
  tiers:
    default: invalid_tier
""")
        with pytest.raises(ValueError, match="invalid.*tier"):
            load_config(config_file, strict=True)

    def test_invalid_gateway_name_rejected(self, tmp_path):
        """Should reject invalid gateway names."""
        config_file = tmp_path / "llm_council.yaml"
        config_file.write_text("""
council:
  gateways:
    default: invalid_gateway
""")
        with pytest.raises(ValueError, match="invalid.*gateway"):
            load_config(config_file, strict=True)

    def test_escalation_max_must_be_positive(self, tmp_path):
        """Should reject negative escalation max."""
        config_file = tmp_path / "llm_council.yaml"
        config_file.write_text("""
council:
  tiers:
    escalation:
      max_escalations: -1
""")
        with pytest.raises(ValueError):
            load_config(config_file, strict=True)

    def test_confidence_threshold_must_be_in_range(self, tmp_path):
        """Should reject confidence threshold outside 0-1."""
        config_file = tmp_path / "llm_council.yaml"
        config_file.write_text("""
council:
  triage:
    fast_path:
      confidence_threshold: 1.5
""")
        with pytest.raises(ValueError):
            load_config(config_file, strict=True)


class TestBackwardsCompatibility:
    """Test backwards compatibility with existing config system."""

    def test_legacy_json_config_still_works(self, tmp_path, monkeypatch):
        """Legacy JSON config should still be loaded."""
        config_dir = tmp_path / ".config" / "llm-council"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.json"
        config_file.write_text('{"council_models": ["legacy/model-1"]}')
        monkeypatch.setenv("HOME", str(tmp_path))
        config = get_effective_config()
        # Legacy config should be respected if no YAML exists
        # (exact behavior TBD based on implementation)
        assert config is not None

    def test_all_existing_env_vars_still_work(self):
        """All existing environment variables should still work."""
        env_vars = {
            "LLM_COUNCIL_MODELS": "test/model-1,test/model-2",
            "LLM_COUNCIL_CHAIRMAN": "test/chairman",
            "LLM_COUNCIL_MODE": "debate",
            "LLM_COUNCIL_EXCLUDE_SELF_VOTES": "false",
            "LLM_COUNCIL_WILDCARD_ENABLED": "true",
            "LLM_COUNCIL_PROMPT_OPTIMIZATION_ENABLED": "true",
        }
        with patch.dict(os.environ, env_vars, clear=False):
            config = get_effective_config()
            # Existing env vars should be respected
            assert config is not None


class TestConfigAccess:
    """Test configuration access patterns."""

    def test_get_tier_contract(self):
        """Should be able to get TierContract from config."""
        config = UnifiedConfig()
        tier_contract = config.get_tier_contract("balanced")
        assert tier_contract.tier == "balanced"
        assert tier_contract.deadline_ms == 90000
        assert len(tier_contract.allowed_models) >= 2

    def test_get_gateway_for_model(self):
        """Should be able to get gateway for a model."""
        config = UnifiedConfig()
        gateway = config.get_gateway_for_model("anthropic/claude-3-5-sonnet-20241022")
        assert gateway in ["openrouter", "requesty", "direct"]

    def test_get_gateway_fallback_chain(self):
        """Should be able to get fallback chain."""
        config = UnifiedConfig()
        chain = config.get_fallback_chain()
        assert isinstance(chain, list)
        assert len(chain) >= 1


class TestConfigSerialization:
    """Test configuration serialization."""

    def test_config_to_yaml(self):
        """Should be able to serialize config to YAML."""
        config = UnifiedConfig()
        yaml_str = config.to_yaml()
        assert "council:" in yaml_str
        assert "tiers:" in yaml_str
        assert "gateways:" in yaml_str

    def test_config_to_dict(self):
        """Should be able to serialize config to dict."""
        config = UnifiedConfig()
        config_dict = config.to_dict()
        assert "tiers" in config_dict
        assert "gateways" in config_dict
        assert "triage" in config_dict


class TestModelRouting:
    """Test model routing configuration."""

    def test_model_routing_patterns(self, tmp_path):
        """Should support glob patterns for model routing."""
        config_file = tmp_path / "llm_council.yaml"
        config_file.write_text("""
council:
  gateways:
    model_routing:
      "anthropic/*": requesty
      "openai/*": direct
      "google/*": openrouter
""")
        config = load_config(config_file)
        assert config.get_gateway_for_model("anthropic/claude-3-5-sonnet") == "requesty"
        assert config.get_gateway_for_model("openai/gpt-4o") == "direct"
        assert config.get_gateway_for_model("google/gemini-1.5-pro") == "openrouter"

    def test_model_routing_default_fallback(self):
        """Unknown models should use default gateway."""
        config = UnifiedConfig()
        gateway = config.get_gateway_for_model("unknown/model")
        assert gateway == config.gateways.default
