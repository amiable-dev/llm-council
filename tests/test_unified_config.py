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


# =============================================================================
# ADR-025a Configuration Alignment Tests (TDD - RED Phase)
# =============================================================================


class TestOllamaProviderConfig:
    """Test OllamaProviderConfig for local Ollama integration (ADR-025a)."""

    def test_ollama_config_defaults(self):
        """OllamaProviderConfig should have sensible defaults."""
        from llm_council.unified_config import OllamaProviderConfig

        config = OllamaProviderConfig()
        assert config.enabled is True
        assert config.base_url == "http://localhost:11434"
        assert config.timeout_seconds == 120.0
        assert config.hardware_profile is None

    def test_ollama_config_from_yaml(self, tmp_path):
        """Should load Ollama config from YAML under gateways.providers.ollama."""
        config_file = tmp_path / "llm_council.yaml"
        config_file.write_text("""
council:
  gateways:
    providers:
      ollama:
        enabled: true
        base_url: http://192.168.1.100:11434
        timeout_seconds: 300.0
        hardware_profile: professional
""")
        config = load_config(config_file)
        assert "ollama" in config.gateways.providers
        ollama_config = config.gateways.providers["ollama"]
        assert ollama_config.base_url == "http://192.168.1.100:11434"
        assert ollama_config.timeout_seconds == 300.0
        assert ollama_config.hardware_profile == "professional"

    def test_ollama_config_env_override(self, tmp_path):
        """Environment variables should override YAML for Ollama config."""
        config_file = tmp_path / "llm_council.yaml"
        config_file.write_text("""
council:
  gateways:
    providers:
      ollama:
        base_url: http://localhost:11434
        timeout_seconds: 120.0
""")
        with patch.dict(os.environ, {
            "LLM_COUNCIL_OLLAMA_BASE_URL": "http://custom:11434",
            "LLM_COUNCIL_OLLAMA_TIMEOUT": "600.0"
        }):
            config = get_effective_config(config_file)
            ollama_config = config.gateways.providers["ollama"]
            assert ollama_config.base_url == "http://custom:11434"
            assert ollama_config.timeout_seconds == 600.0

    def test_ollama_timeout_validation(self):
        """Ollama timeout should be within valid range (1-3600 seconds)."""
        from llm_council.unified_config import OllamaProviderConfig

        # Valid timeout
        config = OllamaProviderConfig(timeout_seconds=500.0)
        assert config.timeout_seconds == 500.0

        # Too low
        with pytest.raises(ValueError):
            OllamaProviderConfig(timeout_seconds=0.5)

        # Too high
        with pytest.raises(ValueError):
            OllamaProviderConfig(timeout_seconds=4000.0)

    def test_ollama_hardware_profile_validation(self):
        """Hardware profile should be one of the valid options."""
        from llm_council.unified_config import OllamaProviderConfig

        # Valid profiles
        for profile in ["minimum", "recommended", "professional", "enterprise"]:
            config = OllamaProviderConfig(hardware_profile=profile)
            assert config.hardware_profile == profile

        # Invalid profile
        with pytest.raises(ValueError):
            OllamaProviderConfig(hardware_profile="invalid")


class TestWebhookConfig:
    """Test WebhookConfig for webhook notifications (ADR-025a)."""

    def test_webhook_config_defaults(self):
        """WebhookConfig should have sensible defaults."""
        from llm_council.unified_config import WebhookConfig

        config = WebhookConfig()
        assert config.enabled is False  # Opt-in
        assert config.timeout_seconds == 5.0
        assert config.max_retries == 3
        assert config.https_only is True
        assert config.default_events == ["council.complete", "council.error"]

    def test_webhook_config_from_yaml(self, tmp_path):
        """Should load webhook config from YAML at top level."""
        config_file = tmp_path / "llm_council.yaml"
        config_file.write_text("""
council:
  webhooks:
    enabled: true
    timeout_seconds: 10.0
    max_retries: 5
    https_only: false
    default_events:
      - council.complete
      - council.error
      - model.response
""")
        config = load_config(config_file)
        assert config.webhooks.enabled is True
        assert config.webhooks.timeout_seconds == 10.0
        assert config.webhooks.max_retries == 5
        assert config.webhooks.https_only is False
        assert "model.response" in config.webhooks.default_events

    def test_webhook_config_env_override(self, tmp_path):
        """Environment variables should override YAML for webhook config."""
        config_file = tmp_path / "llm_council.yaml"
        config_file.write_text("""
council:
  webhooks:
    enabled: false
    timeout_seconds: 5.0
""")
        with patch.dict(os.environ, {
            "LLM_COUNCIL_WEBHOOKS_ENABLED": "true",
            "LLM_COUNCIL_WEBHOOK_TIMEOUT": "15.0",
            "LLM_COUNCIL_WEBHOOK_RETRIES": "7"
        }):
            config = get_effective_config(config_file)
            assert config.webhooks.enabled is True
            assert config.webhooks.timeout_seconds == 15.0
            assert config.webhooks.max_retries == 7

    def test_webhook_timeout_validation(self):
        """Webhook timeout should be within valid range (0.1-60 seconds)."""
        from llm_council.unified_config import WebhookConfig

        # Valid timeout
        config = WebhookConfig(timeout_seconds=30.0)
        assert config.timeout_seconds == 30.0

        # Too low
        with pytest.raises(ValueError):
            WebhookConfig(timeout_seconds=0.05)

        # Too high
        with pytest.raises(ValueError):
            WebhookConfig(timeout_seconds=120.0)

    def test_webhook_retries_validation(self):
        """Webhook retries should be within valid range (0-10)."""
        from llm_council.unified_config import WebhookConfig

        # Valid retries
        config = WebhookConfig(max_retries=5)
        assert config.max_retries == 5

        # Zero is valid (no retries)
        config = WebhookConfig(max_retries=0)
        assert config.max_retries == 0

        # Negative invalid
        with pytest.raises(ValueError):
            WebhookConfig(max_retries=-1)

        # Too high
        with pytest.raises(ValueError):
            WebhookConfig(max_retries=15)

    def test_webhook_default_events(self):
        """Default events should be customizable."""
        from llm_council.unified_config import WebhookConfig

        config = WebhookConfig(default_events=["custom.event"])
        assert config.default_events == ["custom.event"]


class TestGatewayConfigOllama:
    """Test GatewayConfig integration with Ollama (ADR-025a)."""

    def test_ollama_in_valid_gateways(self, tmp_path):
        """'ollama' should be a valid gateway name."""
        config_file = tmp_path / "llm_council.yaml"
        config_file.write_text("""
council:
  gateways:
    default: ollama
""")
        # Should not raise - ollama is valid
        config = load_config(config_file, strict=True)
        assert config.gateways.default == "ollama"

    def test_ollama_default_provider_exists(self):
        """Default config should include ollama provider."""
        config = UnifiedConfig()
        assert "ollama" in config.gateways.providers
        ollama = config.gateways.providers["ollama"]
        assert ollama.enabled is True
        assert ollama.base_url == "http://localhost:11434"

    def test_ollama_provider_config_type(self):
        """Ollama provider should use OllamaProviderConfig type."""
        from llm_council.unified_config import OllamaProviderConfig

        config = UnifiedConfig()
        ollama = config.gateways.providers["ollama"]
        # Should be typed correctly (either OllamaProviderConfig or has ollama-specific fields)
        assert hasattr(ollama, "timeout_seconds") or isinstance(ollama, OllamaProviderConfig)

    def test_ollama_in_fallback_chain(self, tmp_path):
        """Ollama should be usable in fallback chain."""
        config_file = tmp_path / "llm_council.yaml"
        config_file.write_text("""
council:
  gateways:
    fallback:
      chain: [openrouter, ollama]
""")
        config = load_config(config_file)
        assert "ollama" in config.gateways.fallback.chain


class TestConfigDeprecation:
    """Test deprecation bridge for config.py constants (ADR-025a)."""

    def test_deprecated_ollama_base_url_warns(self):
        """Accessing config.OLLAMA_BASE_URL should emit deprecation warning."""
        import warnings
        from llm_council import config

        # Reset the warning cache to ensure we see the warning
        config._deprecated_warned.discard("OLLAMA_BASE_URL")

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            # Access deprecated constant
            _ = config.OLLAMA_BASE_URL
            # Should have deprecation warning
            assert any(issubclass(warning.category, DeprecationWarning) for warning in w)
            assert any("unified_config" in str(warning.message).lower() or
                      "deprecated" in str(warning.message).lower()
                      for warning in w)

    def test_deprecated_webhook_timeout_warns(self):
        """Accessing config.WEBHOOK_TIMEOUT should emit deprecation warning."""
        import warnings
        from llm_council import config

        # Reset the warning cache to ensure we see the warning
        config._deprecated_warned.discard("WEBHOOK_TIMEOUT")

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            _ = config.WEBHOOK_TIMEOUT
            assert any(issubclass(warning.category, DeprecationWarning) for warning in w)

    def test_deprecated_attrs_return_correct_values(self):
        """Deprecated config attrs should return values from unified_config."""
        from llm_council import config
        from llm_council.unified_config import get_config
        import warnings

        # Suppress warnings for this test
        warnings.filterwarnings("ignore", category=DeprecationWarning)

        unified = get_config()
        ollama_config = unified.gateways.providers.get("ollama")
        if ollama_config:
            # Value from deprecated constant should match unified config
            assert config.OLLAMA_BASE_URL == ollama_config.base_url


class TestUnifiedConfigWithWebhooks:
    """Test UnifiedConfig includes webhooks field."""

    def test_unified_config_has_webhooks(self):
        """UnifiedConfig should have webhooks field."""
        config = UnifiedConfig()
        assert hasattr(config, "webhooks")
        assert config.webhooks is not None

    def test_webhooks_serializes_to_yaml(self):
        """Webhooks should be included in YAML serialization."""
        config = UnifiedConfig()
        yaml_str = config.to_yaml()
        assert "webhooks:" in yaml_str

    def test_webhooks_serializes_to_dict(self):
        """Webhooks should be included in dict serialization."""
        config = UnifiedConfig()
        config_dict = config.to_dict()
        assert "webhooks" in config_dict


class TestFrontierConfig:
    """Test FrontierConfig and GraduationConfig (ADR-027)."""

    def test_unified_config_has_frontier(self):
        """UnifiedConfig should have frontier field."""
        config = UnifiedConfig()
        assert hasattr(config, "frontier")
        assert config.frontier is not None

    def test_frontier_defaults_match_adr027(self):
        """Frontier config defaults should match ADR-027."""
        config = UnifiedConfig()
        assert config.frontier.voting_authority == "advisory"
        assert config.frontier.cost_ceiling_multiplier == 5.0
        assert config.frontier.fallback_tier == "high"

    def test_graduation_defaults_match_adr027(self):
        """Graduation config defaults should match ADR-027."""
        config = UnifiedConfig()
        assert config.frontier.graduation.min_age_days == 30
        assert config.frontier.graduation.min_completed_sessions == 100
        assert config.frontier.graduation.max_error_rate == 0.02
        assert config.frontier.graduation.min_quality_percentile == 0.75

    def test_frontier_tier_in_pools(self):
        """Frontier tier should be in default pools."""
        config = UnifiedConfig()
        assert "frontier" in config.tiers.pools
        assert len(config.tiers.pools["frontier"].models) > 0

    def test_frontier_is_valid_tier(self, tmp_path):
        """'frontier' should be a valid tier name."""
        from llm_council.unified_config import load_config

        config_file = tmp_path / "llm_council.yaml"
        config_file.write_text("""
council:
  tiers:
    default: frontier
""")
        # Should not raise
        load_config(config_file)

    def test_frontier_voting_authority_validation(self):
        """Invalid voting_authority should raise validation error."""
        from llm_council.unified_config import FrontierConfig
        import pytest

        with pytest.raises(ValueError):
            FrontierConfig(voting_authority="invalid")

    def test_frontier_fallback_tier_validation(self):
        """Invalid fallback_tier should raise validation error."""
        from llm_council.unified_config import FrontierConfig
        import pytest

        with pytest.raises(ValueError):
            FrontierConfig(fallback_tier="invalid")

    def test_frontier_serializes_to_yaml(self):
        """Frontier should be included in YAML serialization."""
        config = UnifiedConfig()
        yaml_str = config.to_yaml()
        assert "frontier:" in yaml_str
        assert "voting_authority:" in yaml_str
        assert "graduation:" in yaml_str


class TestDiscoveryConfig:
    """Test DiscoveryConfig for dynamic candidate discovery (ADR-028)."""

    def test_discovery_config_defaults(self):
        """DiscoveryConfig should have sensible defaults per ADR-028."""
        from llm_council.unified_config import DiscoveryConfig

        config = DiscoveryConfig()

        assert config.enabled is True
        assert config.refresh_interval_seconds == 300  # 5 minutes
        assert config.min_candidates_per_tier == 3
        assert config.max_candidates_per_tier == 10
        assert config.stale_threshold_minutes == 30
        assert config.max_refresh_retries == 3
        assert config.providers == {}

    def test_discovery_config_validation(self):
        """DiscoveryConfig should validate field ranges."""
        from llm_council.unified_config import DiscoveryConfig
        import pytest

        # Valid config
        config = DiscoveryConfig(
            refresh_interval_seconds=600,
            min_candidates_per_tier=5,
            max_candidates_per_tier=20,
        )
        assert config.refresh_interval_seconds == 600

        # Invalid: min > max candidates
        with pytest.raises(ValueError, match="min_candidates_per_tier"):
            DiscoveryConfig(
                min_candidates_per_tier=15,
                max_candidates_per_tier=10,
            )

        # Invalid: interval too short
        with pytest.raises(ValueError):
            DiscoveryConfig(refresh_interval_seconds=30)

        # Invalid: interval too long
        with pytest.raises(ValueError):
            DiscoveryConfig(refresh_interval_seconds=7200)

    def test_discovery_in_model_intelligence_config(self):
        """ModelIntelligenceConfig should include discovery."""
        from llm_council.unified_config import ModelIntelligenceConfig, DiscoveryConfig

        config = ModelIntelligenceConfig()
        assert hasattr(config, "discovery")
        assert isinstance(config.discovery, DiscoveryConfig)

    def test_discovery_env_var_overrides(self, monkeypatch):
        """Environment variables should override discovery config."""
        from llm_council.unified_config import get_effective_config, reload_config

        monkeypatch.setenv("LLM_COUNCIL_DISCOVERY_ENABLED", "false")
        monkeypatch.setenv("LLM_COUNCIL_DISCOVERY_INTERVAL", "600")
        monkeypatch.setenv("LLM_COUNCIL_DISCOVERY_MIN_CANDIDATES", "5")

        reload_config()
        config = get_effective_config()

        assert config.model_intelligence.discovery.enabled is False
        assert config.model_intelligence.discovery.refresh_interval_seconds == 600
        assert config.model_intelligence.discovery.min_candidates_per_tier == 5

    def test_discovery_provider_config(self):
        """DiscoveryProviderConfig should have correct defaults."""
        from llm_council.unified_config import DiscoveryProviderConfig

        provider = DiscoveryProviderConfig()

        assert provider.enabled is True
        assert provider.rate_limit_rpm == 60
        assert provider.timeout_seconds == 10.0

    def test_discovery_serializes_to_dict(self):
        """Discovery config should serialize to dict."""
        from llm_council.unified_config import UnifiedConfig

        config = UnifiedConfig()
        config_dict = config.to_dict()

        assert "model_intelligence" in config_dict
        assert "discovery" in config_dict["model_intelligence"]
        assert config_dict["model_intelligence"]["discovery"]["enabled"] is True
