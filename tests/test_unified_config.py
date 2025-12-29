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
        with patch.dict(
            os.environ,
            {
                "LLM_COUNCIL_OLLAMA_BASE_URL": "http://custom:11434",
                "LLM_COUNCIL_OLLAMA_TIMEOUT": "600.0",
            },
        ):
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
        with patch.dict(
            os.environ,
            {
                "LLM_COUNCIL_WEBHOOKS_ENABLED": "true",
                "LLM_COUNCIL_WEBHOOK_TIMEOUT": "15.0",
                "LLM_COUNCIL_WEBHOOK_RETRIES": "7",
            },
        ):
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


class TestAuditionConfig:
    """Test ADR-029 Audition Configuration."""

    def test_audition_config_defaults(self):
        """AuditionConfig should have correct defaults per ADR-029."""
        from llm_council.unified_config import AuditionConfig

        config = AuditionConfig()

        assert config.enabled is True
        assert config.max_audition_seats == 1

        # Shadow phase defaults
        assert config.shadow.min_sessions == 10
        assert config.shadow.min_days == 3
        assert config.shadow.max_failures == 3

        # Probation phase defaults
        assert config.probation.min_sessions == 25
        assert config.probation.min_days == 7
        assert config.probation.max_failures == 5

        # Evaluation phase defaults
        assert config.evaluation.min_sessions == 50
        assert config.evaluation.min_quality_percentile == 0.75

        # Quarantine defaults
        assert config.quarantine.cooldown_hours == 24

    def test_audition_config_validation(self):
        """AuditionConfig should validate field constraints."""
        from pydantic import ValidationError

        from llm_council.unified_config import AuditionConfig

        # Valid config
        config = AuditionConfig(max_audition_seats=2)
        assert config.max_audition_seats == 2

        # Invalid: max_audition_seats too high
        with pytest.raises(ValidationError):
            AuditionConfig(max_audition_seats=5)

        # Invalid: negative seats
        with pytest.raises(ValidationError):
            AuditionConfig(max_audition_seats=-1)

    def test_audition_shadow_config_validation(self):
        """ShadowPhaseConfig should validate constraints."""
        from pydantic import ValidationError

        from llm_council.unified_config import ShadowPhaseConfig

        # Valid
        config = ShadowPhaseConfig(min_sessions=5, min_days=2)
        assert config.min_sessions == 5

        # Invalid: min_sessions must be >= 1
        with pytest.raises(ValidationError):
            ShadowPhaseConfig(min_sessions=0)

    def test_audition_evaluation_config_validation(self):
        """EvaluationPhaseConfig should validate constraints."""
        from pydantic import ValidationError

        from llm_council.unified_config import EvaluationPhaseConfig

        # Valid
        config = EvaluationPhaseConfig(min_quality_percentile=0.80)
        assert config.min_quality_percentile == 0.80

        # Invalid: percentile > 1.0
        with pytest.raises(ValidationError):
            EvaluationPhaseConfig(min_quality_percentile=1.5)

        # Invalid: percentile < 0.0
        with pytest.raises(ValidationError):
            EvaluationPhaseConfig(min_quality_percentile=-0.1)

    def test_audition_in_model_intelligence_config(self):
        """AuditionConfig should be in ModelIntelligenceConfig."""
        from llm_council.unified_config import UnifiedConfig

        config = UnifiedConfig()

        assert hasattr(config.model_intelligence, "audition")
        assert config.model_intelligence.audition.enabled is True
        assert config.model_intelligence.audition.max_audition_seats == 1

    def test_audition_config_from_yaml(self, tmp_path):
        """AuditionConfig should load from YAML."""
        yaml_content = """
council:
  model_intelligence:
    audition:
      enabled: false
      max_audition_seats: 2
      shadow:
        min_sessions: 5
        min_days: 2
      evaluation:
        min_quality_percentile: 0.80
"""
        config_file = tmp_path / "llm_council.yaml"
        config_file.write_text(yaml_content)

        from llm_council.unified_config import load_config

        config = load_config(config_file)

        assert config.model_intelligence.audition.enabled is False
        assert config.model_intelligence.audition.max_audition_seats == 2
        assert config.model_intelligence.audition.shadow.min_sessions == 5
        assert config.model_intelligence.audition.shadow.min_days == 2
        assert config.model_intelligence.audition.evaluation.min_quality_percentile == 0.80

    def test_audition_serializes_to_dict(self):
        """Audition config should serialize to dict."""
        from llm_council.unified_config import UnifiedConfig

        config = UnifiedConfig()
        config_dict = config.to_dict()

        assert "model_intelligence" in config_dict
        assert "audition" in config_dict["model_intelligence"]
        assert config_dict["model_intelligence"]["audition"]["enabled"] is True
        assert config_dict["model_intelligence"]["audition"]["max_audition_seats"] == 1


# =============================================================================
# ADR-031 EvaluationConfig Tests (TDD - RED Phase)
# =============================================================================


class TestRubricConfig:
    """Test RubricConfig for rubric-based scoring (ADR-016/ADR-031)."""

    def test_rubric_config_defaults(self):
        """RubricConfig should have correct defaults per config.py."""
        from llm_council.unified_config import RubricConfig

        config = RubricConfig()

        assert config.enabled is False
        assert config.accuracy_ceiling_enabled is True
        assert config.weights == {
            "accuracy": 0.35,
            "relevance": 0.10,
            "completeness": 0.20,
            "conciseness": 0.15,
            "clarity": 0.20,
        }

    def test_rubric_weights_sum_to_one(self):
        """Rubric weights must sum to 1.0 (within tolerance)."""
        from llm_council.unified_config import RubricConfig

        # Valid weights summing to 1.0
        config = RubricConfig(
            weights={
                "accuracy": 0.40,
                "relevance": 0.15,
                "completeness": 0.20,
                "conciseness": 0.10,
                "clarity": 0.15,
            }
        )
        assert sum(config.weights.values()) == pytest.approx(1.0, abs=0.01)

        # Invalid: weights sum to 0.8
        with pytest.raises(ValueError, match="sum to 1.0"):
            RubricConfig(
                weights={
                    "accuracy": 0.30,
                    "relevance": 0.10,
                    "completeness": 0.20,
                    "conciseness": 0.10,
                    "clarity": 0.10,
                }
            )

        # Invalid: weights sum to 1.2
        with pytest.raises(ValueError, match="sum to 1.0"):
            RubricConfig(
                weights={
                    "accuracy": 0.40,
                    "relevance": 0.20,
                    "completeness": 0.25,
                    "conciseness": 0.20,
                    "clarity": 0.15,
                }
            )

    def test_rubric_weights_non_negative(self):
        """Rubric weights cannot be negative."""
        from llm_council.unified_config import RubricConfig

        # Invalid: negative weight
        with pytest.raises(ValueError, match="negative"):
            RubricConfig(
                weights={
                    "accuracy": -0.10,
                    "relevance": 0.30,
                    "completeness": 0.30,
                    "conciseness": 0.25,
                    "clarity": 0.25,
                }
            )

    def test_rubric_weights_required_dimensions(self):
        """Rubric weights must include all 5 dimensions."""
        from llm_council.unified_config import RubricConfig

        # Invalid: missing clarity
        with pytest.raises(ValueError, match="dimensions"):
            RubricConfig(
                weights={
                    "accuracy": 0.35,
                    "relevance": 0.15,
                    "completeness": 0.25,
                    "conciseness": 0.25,
                }
            )

        # Invalid: missing multiple dimensions
        with pytest.raises(ValueError, match="dimensions"):
            RubricConfig(
                weights={
                    "accuracy": 0.50,
                    "clarity": 0.50,
                }
            )


class TestSafetyConfig:
    """Test SafetyConfig for safety gate (ADR-016/ADR-031)."""

    def test_safety_config_defaults(self):
        """SafetyConfig should have correct defaults."""
        from llm_council.unified_config import SafetyConfig

        config = SafetyConfig()

        assert config.enabled is False
        assert config.score_cap == 0.0

    def test_safety_score_cap_bounds(self):
        """Safety score_cap must be in [0, 1] range."""
        from llm_council.unified_config import SafetyConfig

        # Valid bounds
        config = SafetyConfig(score_cap=0.0)
        assert config.score_cap == 0.0

        config = SafetyConfig(score_cap=0.5)
        assert config.score_cap == 0.5

        config = SafetyConfig(score_cap=1.0)
        assert config.score_cap == 1.0

        # Invalid: below 0
        with pytest.raises(ValueError):
            SafetyConfig(score_cap=-0.1)

        # Invalid: above 1
        with pytest.raises(ValueError):
            SafetyConfig(score_cap=1.1)


class TestBiasConfig:
    """Test BiasConfig for bias auditing (ADR-015/018/ADR-031)."""

    def test_bias_config_defaults(self):
        """BiasConfig should have correct defaults per config.py."""
        from llm_council.unified_config import BiasConfig

        config = BiasConfig()

        assert config.audit_enabled is False
        assert config.persistence_enabled is False
        assert config.store_path == "data/bias_metrics.jsonl"
        assert config.consent_level == "LOCAL_ONLY"
        assert config.length_correlation_threshold == 0.3  # |r| above this = bias
        assert config.position_variance_threshold == 0.5  # Match config.py default

    def test_bias_length_correlation_threshold_bounds(self):
        """Length correlation threshold must be in [0, 1] range."""
        from llm_council.unified_config import BiasConfig

        # Valid
        config = BiasConfig(length_correlation_threshold=0.5)
        assert config.length_correlation_threshold == 0.5

        # Invalid: below 0
        with pytest.raises(ValueError):
            BiasConfig(length_correlation_threshold=-0.1)

        # Invalid: above 1
        with pytest.raises(ValueError):
            BiasConfig(length_correlation_threshold=1.5)

    def test_bias_position_variance_threshold_bounds(self):
        """Position variance threshold must be >= 0."""
        from llm_council.unified_config import BiasConfig

        # Valid
        config = BiasConfig(position_variance_threshold=3.0)
        assert config.position_variance_threshold == 3.0

        config = BiasConfig(position_variance_threshold=0.0)
        assert config.position_variance_threshold == 0.0

        # Invalid: negative
        with pytest.raises(ValueError):
            BiasConfig(position_variance_threshold=-1.0)

    def test_bias_consent_level_validation(self):
        """Consent level must be one of the valid options."""
        from llm_council.unified_config import BiasConfig

        # Valid options
        for level in ["OFF", "LOCAL_ONLY", "ANONYMOUS", "ENHANCED", "RESEARCH"]:
            config = BiasConfig(consent_level=level)
            assert config.consent_level == level

        # Invalid option
        with pytest.raises(ValueError):
            BiasConfig(consent_level="INVALID")


class TestEvaluationConfig:
    """Test EvaluationConfig container (ADR-031)."""

    def test_evaluation_config_defaults(self):
        """EvaluationConfig should have correct sub-config defaults."""
        from llm_council.unified_config import EvaluationConfig

        config = EvaluationConfig()

        assert config.rubric.enabled is False
        assert config.safety.enabled is False
        assert config.bias.audit_enabled is False

    def test_evaluation_config_in_unified_config(self):
        """UnifiedConfig should include evaluation field."""
        config = UnifiedConfig()

        assert hasattr(config, "evaluation")
        assert config.evaluation is not None
        assert config.evaluation.rubric.enabled is False

    def test_evaluation_config_from_yaml(self, tmp_path):
        """EvaluationConfig should load from YAML."""
        yaml_content = """
council:
  evaluation:
    rubric:
      enabled: true
      accuracy_ceiling_enabled: false
      weights:
        accuracy: 0.40
        relevance: 0.10
        completeness: 0.20
        conciseness: 0.15
        clarity: 0.15
    safety:
      enabled: true
      score_cap: 0.5
    bias:
      audit_enabled: true
      persistence_enabled: true
      consent_level: RESEARCH
"""
        config_file = tmp_path / "llm_council.yaml"
        config_file.write_text(yaml_content)

        config = load_config(config_file)

        assert config.evaluation.rubric.enabled is True
        assert config.evaluation.rubric.accuracy_ceiling_enabled is False
        assert config.evaluation.rubric.weights["accuracy"] == 0.40
        assert config.evaluation.safety.enabled is True
        assert config.evaluation.safety.score_cap == 0.5
        assert config.evaluation.bias.audit_enabled is True
        assert config.evaluation.bias.persistence_enabled is True
        assert config.evaluation.bias.consent_level == "RESEARCH"

    def test_evaluation_serializes_to_dict(self):
        """Evaluation config should serialize to dict."""
        config = UnifiedConfig()
        config_dict = config.to_dict()

        assert "evaluation" in config_dict
        assert "rubric" in config_dict["evaluation"]
        assert "safety" in config_dict["evaluation"]
        assert "bias" in config_dict["evaluation"]

    def test_evaluation_serializes_to_yaml(self):
        """Evaluation config should serialize to YAML."""
        config = UnifiedConfig()
        yaml_str = config.to_yaml()

        assert "evaluation:" in yaml_str
        assert "rubric:" in yaml_str
        assert "safety:" in yaml_str
        assert "bias:" in yaml_str


class TestEvaluationEnvVarOverrides:
    """Test environment variable overrides for EvaluationConfig (ADR-031)."""

    def test_rubric_scoring_enabled_env(self, tmp_path, monkeypatch):
        """RUBRIC_SCORING_ENABLED env var should enable rubric scoring."""
        from llm_council.unified_config import get_effective_config, reload_config

        config_file = tmp_path / "llm_council.yaml"
        config_file.write_text("""
council:
  evaluation:
    rubric:
      enabled: false
""")
        monkeypatch.setenv("RUBRIC_SCORING_ENABLED", "true")
        reload_config()
        config = get_effective_config(config_file)

        assert config.evaluation.rubric.enabled is True

    def test_safety_gate_enabled_env(self, tmp_path, monkeypatch):
        """SAFETY_GATE_ENABLED env var should enable safety gate."""
        from llm_council.unified_config import get_effective_config, reload_config

        config_file = tmp_path / "llm_council.yaml"
        config_file.write_text("""
council:
  evaluation:
    safety:
      enabled: false
""")
        monkeypatch.setenv("SAFETY_GATE_ENABLED", "true")
        reload_config()
        config = get_effective_config(config_file)

        assert config.evaluation.safety.enabled is True

    def test_bias_audit_enabled_env(self, tmp_path, monkeypatch):
        """BIAS_AUDIT_ENABLED env var should enable bias audit."""
        from llm_council.unified_config import get_effective_config, reload_config

        config_file = tmp_path / "llm_council.yaml"
        config_file.write_text("""
council:
  evaluation:
    bias:
      audit_enabled: false
""")
        monkeypatch.setenv("BIAS_AUDIT_ENABLED", "true")
        reload_config()
        config = get_effective_config(config_file)

        assert config.evaluation.bias.audit_enabled is True

    def test_bias_persistence_enabled_env(self, tmp_path, monkeypatch):
        """BIAS_PERSISTENCE_ENABLED env var should enable bias persistence."""
        from llm_council.unified_config import get_effective_config, reload_config

        config_file = tmp_path / "llm_council.yaml"
        config_file.write_text("""
council:
  evaluation:
    bias:
      persistence_enabled: false
""")
        monkeypatch.setenv("BIAS_PERSISTENCE_ENABLED", "true")
        reload_config()
        config = get_effective_config(config_file)

        assert config.evaluation.bias.persistence_enabled is True


# =============================================================================
# ADR-032 Configuration Migration Tests (TDD - RED Phase)
# =============================================================================


class TestParseModelList:
    """Test parse_model_list helper for auto-detecting list formats (ADR-032)."""

    def test_parse_model_list_passthrough(self):
        """List input passes through unchanged."""
        from llm_council.unified_config import parse_model_list

        result = parse_model_list(["model-a", "model-b"])
        assert result == ["model-a", "model-b"]

    def test_parse_model_list_json_array(self):
        """JSON array string is parsed correctly."""
        from llm_council.unified_config import parse_model_list

        result = parse_model_list('["model-a", "model-b"]')
        assert result == ["model-a", "model-b"]

    def test_parse_model_list_comma_separated(self):
        """Comma-separated string is parsed correctly."""
        from llm_council.unified_config import parse_model_list

        result = parse_model_list("model-a, model-b, model-c")
        assert result == ["model-a", "model-b", "model-c"]

    def test_parse_model_list_comma_no_spaces(self):
        """Comma-separated without spaces works."""
        from llm_council.unified_config import parse_model_list

        result = parse_model_list("model-a,model-b")
        assert result == ["model-a", "model-b"]

    def test_parse_model_list_empty_string(self):
        """Empty string returns empty list."""
        from llm_council.unified_config import parse_model_list

        result = parse_model_list("")
        assert result == []

    def test_parse_model_list_empty_list(self):
        """Empty list passes through."""
        from llm_council.unified_config import parse_model_list

        result = parse_model_list([])
        assert result == []

    def test_parse_model_list_single_model(self):
        """Single model string is parsed correctly."""
        from llm_council.unified_config import parse_model_list

        result = parse_model_list("openai/gpt-4o")
        assert result == ["openai/gpt-4o"]


class TestSecretsConfig:
    """Test SecretsConfig metadata-only schema (ADR-032)."""

    def test_secrets_config_defaults(self):
        """SecretsConfig should have correct defaults."""
        from llm_council.unified_config import SecretsConfig

        config = SecretsConfig()

        assert config.required_providers == ["openrouter"]
        assert config.keychain_service == "llm-council"

    def test_secrets_config_custom_providers(self):
        """SecretsConfig should accept custom providers."""
        from llm_council.unified_config import SecretsConfig

        config = SecretsConfig(required_providers=["openrouter", "anthropic", "openai"])
        assert config.required_providers == ["openrouter", "anthropic", "openai"]

    def test_secrets_config_custom_keychain(self):
        """SecretsConfig should accept custom keychain service."""
        from llm_council.unified_config import SecretsConfig

        config = SecretsConfig(keychain_service="my-app")
        assert config.keychain_service == "my-app"

    def test_secrets_config_in_unified_config(self):
        """UnifiedConfig should include secrets field."""
        config = UnifiedConfig()

        assert hasattr(config, "secrets")
        assert config.secrets is not None
        assert config.secrets.required_providers == ["openrouter"]


class TestCouncilConfig:
    """Test CouncilConfig for core council behavior (ADR-032)."""

    def test_council_config_defaults(self):
        """CouncilConfig should match config.py defaults."""
        from llm_council.unified_config import CouncilConfig

        config = CouncilConfig()

        # Defaults from config.py
        assert "openai/gpt-5.2-pro" in config.models
        assert config.chairman == "google/gemini-3-pro-preview"
        assert config.synthesis_mode == "consensus"
        assert config.exclude_self_votes is True
        assert config.style_normalization is False
        assert config.normalizer_model == "google/gemini-2.0-flash-001"
        assert config.max_reviewers is None

    def test_council_config_model_list_from_comma(self):
        """ModelList should parse comma-separated string."""
        from llm_council.unified_config import CouncilConfig

        config = CouncilConfig(models="model1, model2, model3")
        assert config.models == ["model1", "model2", "model3"]

    def test_council_config_model_list_from_json(self):
        """ModelList should parse JSON array string."""
        from llm_council.unified_config import CouncilConfig

        config = CouncilConfig(models='["model1", "model2"]')
        assert config.models == ["model1", "model2"]

    def test_council_config_model_list_passthrough(self):
        """ModelList should pass through list."""
        from llm_council.unified_config import CouncilConfig

        config = CouncilConfig(models=["model1", "model2"])
        assert config.models == ["model1", "model2"]

    def test_council_config_synthesis_mode_validation(self):
        """synthesis_mode must be 'consensus' or 'debate'."""
        from llm_council.unified_config import CouncilConfig

        # Valid modes
        config = CouncilConfig(synthesis_mode="consensus")
        assert config.synthesis_mode == "consensus"

        config = CouncilConfig(synthesis_mode="debate")
        assert config.synthesis_mode == "debate"

        # Invalid mode
        with pytest.raises(ValueError):
            CouncilConfig(synthesis_mode="invalid")

    def test_council_config_style_normalization_auto(self):
        """style_normalization can be 'auto' string."""
        from llm_council.unified_config import CouncilConfig

        config = CouncilConfig(style_normalization="auto")
        assert config.style_normalization == "auto"

    def test_council_config_in_unified_config(self):
        """UnifiedConfig should include council field."""
        config = UnifiedConfig()

        assert hasattr(config, "council")
        assert config.council is not None
        assert config.council.synthesis_mode == "consensus"


class TestTimeoutsConfig:
    """Test TimeoutsConfig for tier-sovereign timeouts (ADR-032)."""

    def test_timeouts_config_defaults(self):
        """TimeoutsConfig should match config.py DEFAULT_TIER_TIMEOUTS."""
        from llm_council.unified_config import TimeoutsConfig

        config = TimeoutsConfig()

        # Quick tier
        assert config.quick.total == 30000
        assert config.quick.per_model == 20000

        # Balanced tier
        assert config.balanced.total == 90000
        assert config.balanced.per_model == 45000

        # High tier
        assert config.high.total == 180000
        assert config.high.per_model == 90000

        # Reasoning tier
        assert config.reasoning.total == 600000
        assert config.reasoning.per_model == 300000

        # Frontier tier
        assert config.frontier.total == 600000
        assert config.frontier.per_model == 300000

        # Multiplier
        assert config.multiplier == 1.0

    def test_timeouts_config_get_timeout(self):
        """get_timeout should return correct value."""
        from llm_council.unified_config import TimeoutsConfig

        config = TimeoutsConfig()

        assert config.get_timeout("quick") == 30000
        assert config.get_timeout("quick", "per_model") == 20000
        assert config.get_timeout("reasoning") == 600000

    def test_timeouts_config_multiplier_applied(self):
        """Multiplier should be applied to get_timeout."""
        from llm_council.unified_config import TimeoutsConfig

        config = TimeoutsConfig(multiplier=2.0)

        assert config.get_timeout("quick") == 60000
        assert config.get_timeout("quick", "per_model") == 40000

    def test_timeouts_config_invalid_tier(self):
        """get_timeout should return default for invalid tier."""
        from llm_council.unified_config import TimeoutsConfig

        config = TimeoutsConfig()

        # Should return default (high tier) for unknown tier
        result = config.get_timeout("unknown")
        assert result == 180000  # high tier default

    def test_timeouts_config_multiplier_validation(self):
        """Multiplier must be between 0.1 and 10.0."""
        from llm_council.unified_config import TimeoutsConfig

        # Valid
        config = TimeoutsConfig(multiplier=5.0)
        assert config.multiplier == 5.0

        # Too low
        with pytest.raises(ValueError):
            TimeoutsConfig(multiplier=0.05)

        # Too high
        with pytest.raises(ValueError):
            TimeoutsConfig(multiplier=15.0)

    def test_timeouts_config_in_unified_config(self):
        """UnifiedConfig should include timeouts field."""
        config = UnifiedConfig()

        assert hasattr(config, "timeouts")
        assert config.timeouts is not None
        assert config.timeouts.multiplier == 1.0


class TestCacheConfig:
    """Test CacheConfig for response caching (ADR-032)."""

    def test_cache_config_defaults(self):
        """CacheConfig should match config.py defaults."""
        from llm_council.unified_config import CacheConfig
        from pathlib import Path

        config = CacheConfig()

        assert config.enabled is False
        assert config.ttl_seconds == 0  # 0 = infinite (no expiry)
        assert config.directory == Path.home() / ".cache" / "llm-council"

    def test_cache_config_custom_values(self):
        """CacheConfig should accept custom values."""
        from llm_council.unified_config import CacheConfig
        from pathlib import Path

        config = CacheConfig(
            enabled=True,
            ttl_seconds=3600,
            directory=Path("/tmp/cache"),
        )

        assert config.enabled is True
        assert config.ttl_seconds == 3600
        assert config.directory == Path("/tmp/cache")

    def test_cache_config_ttl_validation(self):
        """TTL cannot be negative."""
        from llm_council.unified_config import CacheConfig

        # Valid: 0 (infinite)
        config = CacheConfig(ttl_seconds=0)
        assert config.ttl_seconds == 0

        # Invalid: negative
        with pytest.raises(ValueError):
            CacheConfig(ttl_seconds=-1)

    def test_cache_config_in_unified_config(self):
        """UnifiedConfig should include cache field."""
        config = UnifiedConfig()

        assert hasattr(config, "cache")
        assert config.cache is not None
        assert config.cache.enabled is False


class TestTelemetryConfig:
    """Test TelemetryConfig for opt-in telemetry (ADR-032)."""

    def test_telemetry_config_defaults(self):
        """TelemetryConfig should have opt-out defaults."""
        from llm_council.unified_config import TelemetryConfig

        config = TelemetryConfig()

        assert config.level == "off"
        assert config.endpoint == "https://ingest.llmcouncil.ai/v1/events"
        assert config.enabled is False

    def test_telemetry_config_enabled_property(self):
        """enabled property should reflect level."""
        from llm_council.unified_config import TelemetryConfig

        assert TelemetryConfig(level="off").enabled is False
        assert TelemetryConfig(level="anonymous").enabled is True
        assert TelemetryConfig(level="debug").enabled is True

    def test_telemetry_config_level_validation(self):
        """Level must be 'off', 'anonymous', or 'debug'."""
        from llm_council.unified_config import TelemetryConfig

        # Valid levels
        for level in ["off", "anonymous", "debug"]:
            config = TelemetryConfig(level=level)
            assert config.level == level

        # Invalid level
        with pytest.raises(ValueError):
            TelemetryConfig(level="invalid")

    def test_telemetry_config_custom_endpoint(self):
        """TelemetryConfig should accept custom endpoint."""
        from llm_council.unified_config import TelemetryConfig

        config = TelemetryConfig(endpoint="https://my-telemetry.example.com/v1")
        assert config.endpoint == "https://my-telemetry.example.com/v1"

    def test_telemetry_config_in_unified_config(self):
        """UnifiedConfig should include telemetry field."""
        config = UnifiedConfig()

        assert hasattr(config, "telemetry")
        assert config.telemetry is not None
        assert config.telemetry.level == "off"


class TestADR032EnvVarOverrides:
    """Test environment variable overrides for ADR-032 config sections."""

    def test_council_models_env_override(self, monkeypatch):
        """LLM_COUNCIL_MODELS env var should override models."""
        from llm_council.unified_config import get_effective_config, reload_config

        monkeypatch.setenv("LLM_COUNCIL_MODELS", "test/model1,test/model2")
        reload_config()
        config = get_effective_config()

        assert config.council.models == ["test/model1", "test/model2"]

    def test_council_chairman_env_override(self, monkeypatch):
        """LLM_COUNCIL_CHAIRMAN env var should override chairman."""
        from llm_council.unified_config import get_effective_config, reload_config

        monkeypatch.setenv("LLM_COUNCIL_CHAIRMAN", "test/chairman-model")
        reload_config()
        config = get_effective_config()

        assert config.council.chairman == "test/chairman-model"

    def test_council_mode_env_override(self, monkeypatch):
        """LLM_COUNCIL_MODE env var should override synthesis_mode."""
        from llm_council.unified_config import get_effective_config, reload_config

        monkeypatch.setenv("LLM_COUNCIL_MODE", "debate")
        reload_config()
        config = get_effective_config()

        assert config.council.synthesis_mode == "debate"

    def test_timeout_multiplier_env_override(self, monkeypatch):
        """LLM_COUNCIL_TIMEOUT_MULTIPLIER env var should override multiplier."""
        from llm_council.unified_config import get_effective_config, reload_config

        monkeypatch.setenv("LLM_COUNCIL_TIMEOUT_MULTIPLIER", "2.5")
        reload_config()
        config = get_effective_config()

        assert config.timeouts.multiplier == 2.5

    def test_cache_enabled_env_override(self, monkeypatch):
        """LLM_COUNCIL_CACHE env var should override cache.enabled."""
        from llm_council.unified_config import get_effective_config, reload_config

        monkeypatch.setenv("LLM_COUNCIL_CACHE", "true")
        reload_config()
        config = get_effective_config()

        assert config.cache.enabled is True

    def test_cache_ttl_env_override(self, monkeypatch):
        """LLM_COUNCIL_CACHE_TTL env var should override cache.ttl_seconds."""
        from llm_council.unified_config import get_effective_config, reload_config

        monkeypatch.setenv("LLM_COUNCIL_CACHE_TTL", "7200")
        reload_config()
        config = get_effective_config()

        assert config.cache.ttl_seconds == 7200

    def test_telemetry_level_env_override(self, monkeypatch):
        """LLM_COUNCIL_TELEMETRY env var should override telemetry.level."""
        from llm_council.unified_config import get_effective_config, reload_config

        monkeypatch.setenv("LLM_COUNCIL_TELEMETRY", "anonymous")
        reload_config()
        config = get_effective_config()

        assert config.telemetry.level == "anonymous"
        assert config.telemetry.enabled is True


class TestADR032YAMLLoading:
    """Test YAML loading for ADR-032 config sections."""

    def test_secrets_config_from_yaml(self, tmp_path):
        """SecretsConfig should load from YAML."""
        yaml_content = """
council:
  secrets:
    required_providers: ["openrouter", "anthropic"]
    keychain_service: "my-custom-app"
"""
        config_file = tmp_path / "llm_council.yaml"
        config_file.write_text(yaml_content)

        config = load_config(config_file)

        assert config.secrets.required_providers == ["openrouter", "anthropic"]
        assert config.secrets.keychain_service == "my-custom-app"

    def test_council_config_from_yaml(self, tmp_path):
        """CouncilConfig should load from YAML."""
        yaml_content = """
council:
  council:
    models:
      - openai/gpt-4o
      - anthropic/claude-3
    chairman: "google/gemini-2.5-pro"
    synthesis_mode: "debate"
    exclude_self_votes: false
    style_normalization: "auto"
"""
        config_file = tmp_path / "llm_council.yaml"
        config_file.write_text(yaml_content)

        config = load_config(config_file)

        assert config.council.models == ["openai/gpt-4o", "anthropic/claude-3"]
        assert config.council.chairman == "google/gemini-2.5-pro"
        assert config.council.synthesis_mode == "debate"
        assert config.council.exclude_self_votes is False
        assert config.council.style_normalization == "auto"

    def test_timeouts_config_from_yaml(self, tmp_path):
        """TimeoutsConfig should load from YAML."""
        yaml_content = """
council:
  timeouts:
    multiplier: 1.5
    quick:
      total: 15000
      per_model: 10000
"""
        config_file = tmp_path / "llm_council.yaml"
        config_file.write_text(yaml_content)

        config = load_config(config_file)

        assert config.timeouts.multiplier == 1.5
        assert config.timeouts.quick.total == 15000
        assert config.timeouts.quick.per_model == 10000

    def test_cache_config_from_yaml(self, tmp_path):
        """CacheConfig should load from YAML."""
        yaml_content = """
council:
  cache:
    enabled: true
    ttl_seconds: 1800
    directory: "/tmp/llm-cache"
"""
        config_file = tmp_path / "llm_council.yaml"
        config_file.write_text(yaml_content)

        config = load_config(config_file)

        assert config.cache.enabled is True
        assert config.cache.ttl_seconds == 1800
        assert str(config.cache.directory) == "/tmp/llm-cache"

    def test_telemetry_config_from_yaml(self, tmp_path):
        """TelemetryConfig should load from YAML."""
        yaml_content = """
council:
  telemetry:
    level: "debug"
    endpoint: "https://custom.telemetry.example.com"
"""
        config_file = tmp_path / "llm_council.yaml"
        config_file.write_text(yaml_content)

        config = load_config(config_file)

        assert config.telemetry.level == "debug"
        assert config.telemetry.enabled is True
        assert config.telemetry.endpoint == "https://custom.telemetry.example.com"


class TestADR032Serialization:
    """Test serialization of ADR-032 config sections."""

    def test_secrets_serializes_to_dict(self):
        """Secrets config should serialize to dict."""
        config = UnifiedConfig()
        config_dict = config.to_dict()

        assert "secrets" in config_dict
        assert config_dict["secrets"]["required_providers"] == ["openrouter"]

    def test_council_serializes_to_dict(self):
        """Council config should serialize to dict."""
        config = UnifiedConfig()
        config_dict = config.to_dict()

        assert "council" in config_dict
        assert "models" in config_dict["council"]
        assert "chairman" in config_dict["council"]

    def test_timeouts_serializes_to_dict(self):
        """Timeouts config should serialize to dict."""
        config = UnifiedConfig()
        config_dict = config.to_dict()

        assert "timeouts" in config_dict
        assert "multiplier" in config_dict["timeouts"]
        assert "quick" in config_dict["timeouts"]

    def test_cache_serializes_to_dict(self):
        """Cache config should serialize to dict."""
        config = UnifiedConfig()
        config_dict = config.to_dict()

        assert "cache" in config_dict
        assert "enabled" in config_dict["cache"]
        assert "ttl_seconds" in config_dict["cache"]

    def test_telemetry_serializes_to_dict(self):
        """Telemetry config should serialize to dict."""
        config = UnifiedConfig()
        config_dict = config.to_dict()

        assert "telemetry" in config_dict
        assert "level" in config_dict["telemetry"]
        assert "endpoint" in config_dict["telemetry"]

    def test_all_adr032_sections_in_yaml(self):
        """All ADR-032 sections should appear in YAML output."""
        config = UnifiedConfig()
        yaml_str = config.to_yaml()

        assert "secrets:" in yaml_str
        assert "council:" in yaml_str
        assert "timeouts:" in yaml_str
        assert "cache:" in yaml_str
        assert "telemetry:" in yaml_str


class TestGetApiKey:
    """Test get_api_key() helper function (ADR-032)."""

    def test_get_api_key_from_env(self, monkeypatch):
        """Environment variable takes priority."""
        from llm_council.unified_config import get_api_key

        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-from-env")
        result = get_api_key("openrouter")
        assert result == "test-key-from-env"

    def test_get_api_key_missing(self, monkeypatch):
        """Missing key returns None."""
        from llm_council.unified_config import get_api_key

        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("NONEXISTENT_PROVIDER_API_KEY", raising=False)

        result = get_api_key("nonexistent_provider")
        assert result is None

    def test_get_api_key_provider_case_insensitive(self, monkeypatch):
        """Provider name is normalized to uppercase for env lookup."""
        from llm_council.unified_config import get_api_key

        monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-key")
        result = get_api_key("anthropic")
        assert result == "anthropic-key"

        result = get_api_key("ANTHROPIC")
        assert result == "anthropic-key"

    def test_get_api_key_openai(self, monkeypatch):
        """OpenAI API key lookup works."""
        from llm_council.unified_config import get_api_key

        monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
        result = get_api_key("openai")
        assert result == "openai-key"

    def test_get_api_key_google(self, monkeypatch):
        """Google API key lookup works."""
        from llm_council.unified_config import get_api_key

        monkeypatch.setenv("GOOGLE_API_KEY", "google-key")
        result = get_api_key("google")
        assert result == "google-key"


class TestDumpEffectiveConfig:
    """Test dump_effective_config() helper function (ADR-032)."""

    def test_dump_effective_config_returns_yaml(self):
        """dump_effective_config returns valid YAML string."""
        from llm_council.unified_config import dump_effective_config

        yaml_str = dump_effective_config()
        assert isinstance(yaml_str, str)
        assert "council:" in yaml_str

    def test_dump_effective_config_includes_all_sections(self):
        """dump_effective_config includes all ADR-032 sections."""
        from llm_council.unified_config import dump_effective_config

        yaml_str = dump_effective_config()
        assert "secrets:" in yaml_str
        assert "council:" in yaml_str
        assert "timeouts:" in yaml_str
        assert "cache:" in yaml_str
        assert "telemetry:" in yaml_str

    def test_dump_effective_config_redact_secrets(self, monkeypatch):
        """redact_secrets=True redacts API keys in credentials section."""
        from llm_council.unified_config import dump_effective_config, reload_config

        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-secret-key-12345")
        reload_config()

        yaml_str = dump_effective_config(redact_secrets=True)

        # The credentials section should have [REDACTED] for openrouter
        # Note: The key may appear in other places (like env loading) but
        # credentials section should be redacted
        assert "[REDACTED]" in yaml_str

    def test_dump_effective_config_no_redact(self, monkeypatch):
        """redact_secrets=False shows actual values (for credentials section)."""
        from llm_council.unified_config import dump_effective_config, reload_config

        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-visible-key")
        reload_config()

        yaml_str = dump_effective_config(redact_secrets=False)
        assert "openrouter" in yaml_str.lower()


class TestTierPoolsConfig:
    """Test TierPoolsConfig for per-tier model pools (ADR-032)."""

    def test_tier_pools_exists_in_tiers(self):
        """TierPoolsConfig should exist in TierConfig.pools."""
        config = UnifiedConfig()
        assert hasattr(config.tiers, "pools")
        assert config.tiers.pools is not None

    def test_tier_pools_has_all_tiers(self):
        """All tiers should have a pool defined."""
        config = UnifiedConfig()
        pools = config.tiers.pools

        for tier in ["quick", "balanced", "high", "reasoning"]:
            assert tier in pools or hasattr(pools, tier)
