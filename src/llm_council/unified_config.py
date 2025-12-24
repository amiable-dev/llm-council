"""Unified YAML Configuration for LLM Council (ADR-024 Phase 2).

This module provides a unified configuration system that consolidates settings from:
- ADR-020: Query Triage & Model Selection (Layer 2)
- ADR-022: Tiered Model Selection (Layer 1)
- ADR-023: Multi-Router Gateway Support (Layer 4)

Configuration Priority: YAML > Environment Variables > Defaults

Example YAML configuration (llm_council.yaml):

    council:
      tiers:
        default: high
        pools:
          quick:
            models: [openai/gpt-4o-mini, anthropic/claude-3-5-haiku-20241022]
            timeout_seconds: 30
      triage:
        enabled: false
        wildcard:
          enabled: true
      gateways:
        default: openrouter
        fallback:
          enabled: true
          chain: [openrouter, requesty, direct]
"""

import fnmatch
import os
import re
from dataclasses import field
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from .tier_contract import TierContract, create_tier_contract


# =============================================================================
# Sub-configuration Models
# =============================================================================


class TierPoolConfig(BaseModel):
    """Configuration for a single tier's model pool."""

    models: List[str] = Field(default_factory=list)
    timeout_seconds: int = Field(default=90, ge=1, le=3600)
    per_model_timeout_seconds: Optional[int] = None
    peer_review: str = Field(default="standard")  # standard | lightweight

    @model_validator(mode="after")
    def set_per_model_timeout(self) -> "TierPoolConfig":
        """Set per_model timeout to half of total if not specified."""
        if self.per_model_timeout_seconds is None:
            self.per_model_timeout_seconds = self.timeout_seconds // 2
        return self


class EscalationConfig(BaseModel):
    """Configuration for tier escalation behavior."""

    enabled: bool = True
    notify_user: bool = True
    max_escalations: int = Field(default=2, ge=0, le=5)


class TierConfig(BaseModel):
    """Configuration for tier selection (ADR-022, Layer 1)."""

    default: str = Field(default="high")
    pools: Dict[str, TierPoolConfig] = Field(default_factory=dict)
    escalation: EscalationConfig = Field(default_factory=EscalationConfig)

    @field_validator("default")
    @classmethod
    def validate_tier_name(cls, v: str) -> str:
        valid_tiers = {"quick", "balanced", "high", "reasoning"}
        if v not in valid_tiers:
            raise ValueError(f"invalid tier '{v}', must be one of {valid_tiers}")
        return v

    @model_validator(mode="after")
    def ensure_default_pools(self) -> "TierConfig":
        """Ensure all standard tier pools exist with defaults."""
        default_pools = {
            "quick": TierPoolConfig(
                models=[
                    "openai/gpt-4o-mini",
                    "anthropic/claude-3-5-haiku-20241022",
                    "google/gemini-2.0-flash-001",
                ],
                timeout_seconds=30,
                peer_review="lightweight",
            ),
            "balanced": TierPoolConfig(
                models=[
                    "openai/gpt-4o",
                    "anthropic/claude-3-5-sonnet-20241022",
                    "google/gemini-1.5-pro",
                ],
                timeout_seconds=90,
            ),
            "high": TierPoolConfig(
                models=[
                    "openai/gpt-4o",
                    "anthropic/claude-opus-4-5-20250514",
                    "google/gemini-3-pro",
                    "x-ai/grok-4",
                ],
                timeout_seconds=180,
            ),
            "reasoning": TierPoolConfig(
                models=[
                    "openai/gpt-5.2-pro",
                    "anthropic/claude-opus-4-5-20250514",
                    "openai/o1-preview",
                    "deepseek/deepseek-r1",
                ],
                timeout_seconds=600,
            ),
        }
        for tier, pool in default_pools.items():
            if tier not in self.pools:
                self.pools[tier] = pool
        return self


class ComplexityClassificationConfig(BaseModel):
    """Configuration for complexity classification."""

    enabled: bool = True
    provider: str = "not_diamond"


class PromptOptimizationConfig(BaseModel):
    """Configuration for prompt optimization."""

    enabled: bool = True
    verify_semantic_equivalence: bool = True
    similarity_threshold: float = Field(default=0.93, ge=0.0, le=1.0)


class WildcardConfig(BaseModel):
    """Configuration for wildcard model selection."""

    enabled: bool = True
    pool: str = "domain_specialist"
    fallback_model: Optional[str] = None


class FastPathConfig(BaseModel):
    """Configuration for fast path (single model) routing."""

    enabled: bool = True
    confidence_threshold: float = Field(default=0.92, ge=0.0, le=1.0)
    escalate_on_low_confidence: bool = True


class TriageConfig(BaseModel):
    """Configuration for query triage (ADR-020, Layer 2)."""

    enabled: bool = False  # Opt-in; requires Not Diamond API key
    complexity_classification: ComplexityClassificationConfig = Field(
        default_factory=ComplexityClassificationConfig
    )
    prompt_optimization: PromptOptimizationConfig = Field(
        default_factory=PromptOptimizationConfig
    )
    wildcard: WildcardConfig = Field(default_factory=WildcardConfig)
    fast_path: FastPathConfig = Field(default_factory=FastPathConfig)


class GatewayProviderConfig(BaseModel):
    """Configuration for a single gateway provider."""

    enabled: bool = True
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    byok: Optional[Dict[str, str]] = None


class OllamaProviderConfig(BaseModel):
    """Configuration for Ollama provider (ADR-025a).

    Lives inside gateways.providers.ollama per council decision.
    Extends GatewayProviderConfig with Ollama-specific settings.
    """

    enabled: bool = True
    base_url: str = Field(default="http://localhost:11434")
    timeout_seconds: float = Field(default=120.0, ge=1.0, le=3600.0)
    hardware_profile: Optional[
        Literal["minimum", "recommended", "professional", "enterprise"]
    ] = None


class WebhookConfig(BaseModel):
    """Configuration for webhook notifications (ADR-025a).

    Top-level system service (like ObservabilityConfig).
    Note: url and secret are runtime-only, not stored in config.
    """

    enabled: bool = False  # Opt-in
    timeout_seconds: float = Field(default=5.0, ge=0.1, le=60.0)
    max_retries: int = Field(default=3, ge=0, le=10)
    https_only: bool = True
    default_events: List[str] = Field(
        default_factory=lambda: ["council.complete", "council.error"]
    )


class FallbackConfig(BaseModel):
    """Configuration for gateway fallback behavior."""

    enabled: bool = True
    chain: List[str] = Field(default_factory=lambda: ["openrouter", "requesty", "direct"])
    retry_on: List[str] = Field(
        default_factory=lambda: ["timeout", "rate_limit", "server_error"]
    )
    do_not_retry_on: List[str] = Field(
        default_factory=lambda: ["auth_error", "invalid_request", "content_filter"]
    )


class GatewayConfig(BaseModel):
    """Configuration for gateway routing (ADR-023, Layer 4)."""

    default: str = Field(default="openrouter")
    providers: Dict[str, Union[GatewayProviderConfig, OllamaProviderConfig]] = Field(
        default_factory=dict
    )
    model_routing: Dict[str, str] = Field(default_factory=dict)
    fallback: FallbackConfig = Field(default_factory=FallbackConfig)

    @field_validator("default")
    @classmethod
    def validate_gateway_name(cls, v: str) -> str:
        valid_gateways = {"openrouter", "requesty", "direct", "auto", "ollama"}
        if v not in valid_gateways:
            raise ValueError(f"invalid gateway '{v}', must be one of {valid_gateways}")
        return v

    @model_validator(mode="before")
    @classmethod
    def convert_ollama_provider(cls, data: Any) -> Any:
        """Convert ollama provider dict to OllamaProviderConfig."""
        if isinstance(data, dict) and "providers" in data:
            providers = data.get("providers", {})
            if isinstance(providers, dict) and "ollama" in providers:
                ollama_data = providers["ollama"]
                if isinstance(ollama_data, dict) and not isinstance(ollama_data, OllamaProviderConfig):
                    providers["ollama"] = OllamaProviderConfig(**ollama_data)
        return data

    @model_validator(mode="after")
    def ensure_default_providers(self) -> "GatewayConfig":
        """Ensure all standard gateway providers exist."""
        default_providers: Dict[str, Union[GatewayProviderConfig, OllamaProviderConfig]] = {
            "openrouter": GatewayProviderConfig(
                enabled=True,
                base_url="https://openrouter.ai/api/v1/chat/completions",
            ),
            "requesty": GatewayProviderConfig(
                enabled=True,
                base_url="https://router.requesty.ai/v1/chat/completions",
            ),
            "direct": GatewayProviderConfig(enabled=True),
            "ollama": OllamaProviderConfig(
                enabled=True,
                base_url="http://localhost:11434",
                timeout_seconds=120.0,
            ),
        }
        for name, provider in default_providers.items():
            if name not in self.providers:
                self.providers[name] = provider
        return self


class CredentialsConfig(BaseModel):
    """Configuration for API credentials."""

    not_diamond: Optional[str] = None
    openrouter: Optional[str] = None
    requesty: Optional[str] = None
    anthropic: Optional[str] = None
    openai: Optional[str] = None
    google: Optional[str] = None


# =============================================================================
# Model Intelligence Configuration (ADR-026)
# =============================================================================


class ModelIntelligenceRefreshConfig(BaseModel):
    """Configuration for model intelligence cache refresh."""

    registry_ttl: int = Field(default=3600, ge=60, le=86400)  # 1 hour default
    availability_ttl: int = Field(default=300, ge=30, le=3600)  # 5 min default


class ModelIntelligenceSelectionConfig(BaseModel):
    """Configuration for model selection algorithm."""

    min_providers: int = Field(default=2, ge=1, le=5)
    default_count: int = Field(default=4, ge=1, le=10)


class AntiHerdingConfig(BaseModel):
    """Configuration for anti-herding penalties."""

    enabled: bool = True
    traffic_threshold: float = Field(default=0.30, ge=0.0, le=1.0)
    max_penalty: float = Field(default=0.35, ge=0.0, le=1.0)


class ReasoningStageConfig(BaseModel):
    """Configuration for which council stages use reasoning parameters (ADR-026 Phase 2).

    Controls where reasoning effort/budget is applied in the 3-stage council process.
    """

    stage1: bool = True  # Primary model responses (default ON)
    stage2: bool = False  # Peer review evaluations (default OFF)
    stage3: bool = True  # Chairman synthesis (default ON)


class ReasoningEffortByTierConfig(BaseModel):
    """Configuration for reasoning effort levels by tier (ADR-026 Phase 2)."""

    quick: str = "minimal"
    balanced: str = "low"
    high: str = "medium"
    reasoning: str = "high"


class DomainOverridesConfig(BaseModel):
    """Configuration for domain-specific reasoning effort overrides (ADR-026 Phase 2)."""

    math: str = "high"
    coding: str = "medium"
    creative: str = "minimal"


class ReasoningOptimizationConfig(BaseModel):
    """Configuration for reasoning parameter optimization (ADR-026 Phase 2).

    Controls automatic injection of reasoning parameters for models that
    support reasoning (o1, o3, deepseek-r1, etc.).
    """

    enabled: bool = True  # Enabled by default when model intelligence is on
    effort_by_tier: ReasoningEffortByTierConfig = Field(
        default_factory=ReasoningEffortByTierConfig
    )
    domain_overrides: DomainOverridesConfig = Field(
        default_factory=DomainOverridesConfig
    )
    stages: ReasoningStageConfig = Field(default_factory=ReasoningStageConfig)
    max_budget_tokens: int = Field(default=32000, ge=1024, le=100000)
    min_budget_tokens: int = Field(default=1024, ge=256, le=32000)


class ModelIntelligenceConfig(BaseModel):
    """Configuration for Model Intelligence Layer (ADR-026).

    Controls dynamic model metadata fetching, caching, and selection.
    Disabled by default (opt-in via LLM_COUNCIL_MODEL_INTELLIGENCE=true).
    """

    enabled: bool = False  # Opt-in; requires API connectivity
    refresh: ModelIntelligenceRefreshConfig = Field(
        default_factory=ModelIntelligenceRefreshConfig
    )
    selection: ModelIntelligenceSelectionConfig = Field(
        default_factory=ModelIntelligenceSelectionConfig
    )
    anti_herding: AntiHerdingConfig = Field(default_factory=AntiHerdingConfig)
    reasoning: ReasoningOptimizationConfig = Field(
        default_factory=ReasoningOptimizationConfig
    )


class ObservabilityConfig(BaseModel):
    """Configuration for observability settings."""

    log_escalations: bool = True
    log_gateway_fallbacks: bool = True
    metrics_enabled: bool = True


# =============================================================================
# Main Unified Configuration
# =============================================================================


class UnifiedConfig(BaseModel):
    """Unified configuration for LLM Council (ADR-024).

    This consolidates settings from ADR-020, ADR-022, ADR-023, and ADR-026 into
    a single configuration object with YAML file support.
    """

    tiers: TierConfig = Field(default_factory=TierConfig)
    triage: TriageConfig = Field(default_factory=TriageConfig)
    gateways: GatewayConfig = Field(default_factory=GatewayConfig)
    credentials: CredentialsConfig = Field(default_factory=CredentialsConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    webhooks: WebhookConfig = Field(default_factory=WebhookConfig)
    model_intelligence: ModelIntelligenceConfig = Field(
        default_factory=ModelIntelligenceConfig
    )

    def get_tier_contract(self, tier: str) -> TierContract:
        """Get TierContract for a specific tier.

        Args:
            tier: One of quick, balanced, high, reasoning

        Returns:
            TierContract with tier-specific settings
        """
        # Use the existing create_tier_contract which pulls from config
        return create_tier_contract(tier)

    def get_gateway_for_model(self, model: str) -> str:
        """Get the gateway to use for a specific model.

        Args:
            model: Model identifier (e.g., "anthropic/claude-3-5-sonnet-20241022")

        Returns:
            Gateway name (openrouter, requesty, or direct)
        """
        # Check model routing patterns
        for pattern, gateway in self.gateways.model_routing.items():
            if fnmatch.fnmatch(model, pattern):
                return gateway
        # Fall back to default
        return self.gateways.default

    def get_fallback_chain(self) -> List[str]:
        """Get the gateway fallback chain.

        Returns:
            List of gateway names in fallback order
        """
        if self.gateways.fallback.enabled:
            return self.gateways.fallback.chain
        return [self.gateways.default]

    def to_yaml(self) -> str:
        """Serialize configuration to YAML string.

        Returns:
            YAML representation of the configuration
        """
        config_dict = {"council": self.to_dict()}
        return yaml.dump(config_dict, default_flow_style=False, sort_keys=False)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize configuration to dictionary.

        Returns:
            Dictionary representation of the configuration
        """
        return self.model_dump(exclude_none=True)


# =============================================================================
# Configuration Loading Functions
# =============================================================================


def _substitute_env_vars(value: Any) -> Any:
    """Recursively substitute environment variables in configuration values.

    Supports ${VAR_NAME} syntax.
    """
    if isinstance(value, str):
        # Find all ${VAR_NAME} patterns
        pattern = r"\$\{([^}]+)\}"
        matches = re.findall(pattern, value)
        for var_name in matches:
            env_value = os.getenv(var_name, "")
            value = value.replace(f"${{{var_name}}}", env_value)
        return value
    elif isinstance(value, dict):
        return {k: _substitute_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_substitute_env_vars(item) for item in value]
    return value


def _merge_dicts(base: Dict, override: Dict) -> Dict:
    """Deep merge two dictionaries, with override taking precedence."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _merge_dicts(result[key], value)
        else:
            result[key] = value
    return result


def load_config(
    config_path: Optional[Path] = None,
    strict: bool = False,
) -> UnifiedConfig:
    """Load configuration from YAML file.

    Args:
        config_path: Path to YAML configuration file. If None, uses defaults.
        strict: If True, raise ValueError on validation errors. If False,
                fall back to defaults on errors.

    Returns:
        UnifiedConfig object

    Raises:
        ValueError: If strict=True and configuration is invalid
    """
    if config_path is None or not config_path.exists():
        return UnifiedConfig()

    try:
        with open(config_path, "r") as f:
            raw_config = yaml.safe_load(f)

        if raw_config is None:
            return UnifiedConfig()

        # Substitute environment variables
        raw_config = _substitute_env_vars(raw_config)

        # Extract council section
        council_config = raw_config.get("council", {})

        # Build config from YAML
        return UnifiedConfig(**council_config)

    except yaml.YAMLError as e:
        if strict:
            raise ValueError(f"Invalid YAML: {e}")
        return UnifiedConfig()
    except Exception as e:
        if strict:
            raise ValueError(f"Configuration error: {e}")
        return UnifiedConfig()


def _find_config_file() -> Optional[Path]:
    """Find configuration file in standard locations.

    Search order:
    1. LLM_COUNCIL_CONFIG environment variable
    2. ./llm_council.yaml (current directory)
    3. ~/.config/llm-council/llm_council.yaml
    """
    # Check env var first
    env_path = os.getenv("LLM_COUNCIL_CONFIG")
    if env_path:
        path = Path(env_path)
        if path.exists():
            return path

    # Check current directory
    cwd_path = Path.cwd() / "llm_council.yaml"
    if cwd_path.exists():
        return cwd_path

    # Check home directory
    home_path = Path.home() / ".config" / "llm-council" / "llm_council.yaml"
    if home_path.exists():
        return home_path

    return None


def _apply_env_overrides(config: UnifiedConfig) -> UnifiedConfig:
    """Apply environment variable overrides to configuration.

    Environment variables take precedence over YAML configuration.
    """
    # Copy config data
    config_dict = config.to_dict()

    # Tier overrides
    tier_env = os.getenv("LLM_COUNCIL_DEFAULT_TIER")
    if tier_env:
        config_dict.setdefault("tiers", {})["default"] = tier_env

    # Per-tier model overrides
    for tier in ["quick", "balanced", "high", "reasoning"]:
        models_env = os.getenv(f"LLM_COUNCIL_MODELS_{tier.upper()}")
        if models_env:
            models = [m.strip() for m in models_env.split(",")]
            config_dict.setdefault("tiers", {}).setdefault("pools", {}).setdefault(tier, {})["models"] = models

    # Gateway overrides
    gateway_env = os.getenv("LLM_COUNCIL_DEFAULT_GATEWAY")
    if gateway_env:
        config_dict.setdefault("gateways", {})["default"] = gateway_env

    # Triage overrides
    triage_env = os.getenv("LLM_COUNCIL_TRIAGE_ENABLED")
    if triage_env:
        config_dict.setdefault("triage", {})["enabled"] = triage_env.lower() in ("true", "1", "yes")

    # Wildcard override
    wildcard_env = os.getenv("LLM_COUNCIL_WILDCARD_ENABLED")
    if wildcard_env:
        config_dict.setdefault("triage", {}).setdefault("wildcard", {})["enabled"] = wildcard_env.lower() in ("true", "1", "yes")

    # Prompt optimization override
    prompt_opt_env = os.getenv("LLM_COUNCIL_PROMPT_OPTIMIZATION_ENABLED")
    if prompt_opt_env:
        config_dict.setdefault("triage", {}).setdefault("prompt_optimization", {})["enabled"] = prompt_opt_env.lower() in ("true", "1", "yes")

    # Gateway fallback chain
    fallback_env = os.getenv("LLM_COUNCIL_GATEWAY_FALLBACK_CHAIN")
    if fallback_env:
        chain = [g.strip() for g in fallback_env.split(",")]
        config_dict.setdefault("gateways", {}).setdefault("fallback", {})["chain"] = chain

    # Credential overrides (always from env for security)
    for cred_name in ["openrouter", "requesty", "anthropic", "openai", "google"]:
        env_var = f"{cred_name.upper()}_API_KEY"
        if os.getenv(env_var):
            config_dict.setdefault("credentials", {})[cred_name] = os.getenv(env_var)

    not_diamond_key = os.getenv("NOT_DIAMOND_API_KEY")
    if not_diamond_key:
        config_dict.setdefault("credentials", {})["not_diamond"] = not_diamond_key

    # Ollama overrides (ADR-025a)
    ollama_base_url = os.getenv("LLM_COUNCIL_OLLAMA_BASE_URL")
    if ollama_base_url:
        config_dict.setdefault("gateways", {}).setdefault("providers", {}).setdefault("ollama", {})["base_url"] = ollama_base_url
    ollama_timeout = os.getenv("LLM_COUNCIL_OLLAMA_TIMEOUT")
    if ollama_timeout:
        config_dict.setdefault("gateways", {}).setdefault("providers", {}).setdefault("ollama", {})["timeout_seconds"] = float(ollama_timeout)

    # Webhook overrides (ADR-025a)
    webhooks_enabled = os.getenv("LLM_COUNCIL_WEBHOOKS_ENABLED")
    if webhooks_enabled:
        config_dict.setdefault("webhooks", {})["enabled"] = webhooks_enabled.lower() in ("true", "1", "yes")
    webhook_timeout = os.getenv("LLM_COUNCIL_WEBHOOK_TIMEOUT")
    if webhook_timeout:
        config_dict.setdefault("webhooks", {})["timeout_seconds"] = float(webhook_timeout)
    webhook_retries = os.getenv("LLM_COUNCIL_WEBHOOK_RETRIES")
    if webhook_retries:
        config_dict.setdefault("webhooks", {})["max_retries"] = int(webhook_retries)

    # Model Intelligence overrides (ADR-026)
    model_intelligence_enabled = os.getenv("LLM_COUNCIL_MODEL_INTELLIGENCE")
    if model_intelligence_enabled:
        config_dict.setdefault("model_intelligence", {})["enabled"] = model_intelligence_enabled.lower() in ("true", "1", "yes")

    # Reasoning optimization overrides (ADR-026 Phase 2)
    reasoning_enabled = os.getenv("LLM_COUNCIL_REASONING_ENABLED")
    if reasoning_enabled:
        config_dict.setdefault("model_intelligence", {}).setdefault("reasoning", {})["enabled"] = reasoning_enabled.lower() in ("true", "1", "yes")

    return UnifiedConfig(**config_dict)


def get_effective_config(config_path: Optional[Path] = None) -> UnifiedConfig:
    """Get the effective configuration with all overrides applied.

    Priority: Environment Variables > YAML > Defaults

    Args:
        config_path: Optional explicit path to configuration file.
                    If None, searches standard locations.

    Returns:
        UnifiedConfig with all overrides applied
    """
    # Find config file if not specified
    if config_path is None:
        config_path = _find_config_file()

    # Load from YAML
    config = load_config(config_path)

    # Apply environment variable overrides
    config = _apply_env_overrides(config)

    return config


# =============================================================================
# Global Configuration Instance
# =============================================================================

# Lazy-loaded global config instance
_global_config: Optional[UnifiedConfig] = None


def get_config() -> UnifiedConfig:
    """Get the global configuration instance.

    This function caches the configuration after first load.
    Use reload_config() to force a reload.

    Returns:
        UnifiedConfig instance
    """
    global _global_config
    if _global_config is None:
        _global_config = get_effective_config()
    return _global_config


def reload_config() -> UnifiedConfig:
    """Reload the global configuration from disk.

    Returns:
        Newly loaded UnifiedConfig instance
    """
    global _global_config
    _global_config = get_effective_config()
    return _global_config
