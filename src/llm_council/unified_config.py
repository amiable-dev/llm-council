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
import json
import os
import re
from dataclasses import field
from pathlib import Path
from typing import Annotated, Any, Dict, List, Literal, Optional, Union

import yaml
from pydantic import BaseModel, BeforeValidator, Field, field_validator, model_validator

from .tier_contract import TierContract, create_tier_contract


# =============================================================================
# ADR-032: Model List Auto-Detection Helper
# =============================================================================


def parse_model_list(value: Union[str, List[str]]) -> List[str]:
    """Parse model list from string or list (ADR-032 auto-detection).

    Supports:
    - List passthrough: ["model1", "model2"]
    - JSON array: '["model1", "model2"]'
    - Comma-separated: "model1, model2"

    Args:
        value: Either a list of strings or a string representation

    Returns:
        List of model identifiers
    """
    if isinstance(value, list):
        return value
    if not value:
        return []
    value = value.strip()
    if value.startswith("["):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            # Fall through to comma parsing
            pass
    return [item.strip() for item in value.split(",") if item.strip()]


# Type alias for model lists with auto-detection
ModelList = Annotated[List[str], BeforeValidator(parse_model_list)]


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
    # Note: frontier field is populated by model_validator after class definitions

    @field_validator("default")
    @classmethod
    def validate_tier_name(cls, v: str) -> str:
        valid_tiers = {"quick", "balanced", "high", "reasoning", "frontier"}
        if v not in valid_tiers:
            raise ValueError(f"invalid tier '{v}', must be one of {valid_tiers}")
        return v

    @model_validator(mode="after")
    def ensure_default_pools(self) -> "TierConfig":
        """Ensure all standard tier pools exist with defaults."""
        default_pools = {
            "quick": TierPoolConfig(
                models=[
                    "openai/gpt-5-mini",
                    "anthropic/claude-haiku-4.5",
                    "google/gemini-3-flash-preview",
                ],
                timeout_seconds=30,
                peer_review="lightweight",
            ),
            "balanced": TierPoolConfig(
                models=[
                    "openai/gpt-5-mini",
                    "anthropic/claude-sonnet-4.5",
                    "google/gemini-3-flash-preview",
                    "x-ai/grok-code-fast-1",
                ],
                timeout_seconds=90,
            ),
            "high": TierPoolConfig(
                models=[
                    "openai/gpt-5.2",
                    "anthropic/claude-opus-4.5",
                    "google/gemini-3-pro-preview",
                    "x-ai/grok-4.1-fast",
                ],
                timeout_seconds=180,
            ),
            "reasoning": TierPoolConfig(
                models=[
                    "openai/gpt-5.2-pro",
                    "anthropic/claude-opus-4.5",
                    "google/gemini-3-pro-preview",
                    "x-ai/grok-4.1-fast",
                ],
                timeout_seconds=600,
            ),
            # ADR-027: Frontier tier for cutting-edge/preview models
            "frontier": TierPoolConfig(
                models=[
                    "openai/gpt-5.2-pro",
                    "anthropic/claude-opus-4.5",
                    "google/gemini-3-pro-preview",
                    "x-ai/grok-4.1-fast",
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
    prompt_optimization: PromptOptimizationConfig = Field(default_factory=PromptOptimizationConfig)
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
    hardware_profile: Optional[Literal["minimum", "recommended", "professional", "enterprise"]] = (
        None
    )


class WebhookConfig(BaseModel):
    """Configuration for webhook notifications (ADR-025a).

    Top-level system service (like ObservabilityConfig).
    Note: url and secret are runtime-only, not stored in config.
    """

    enabled: bool = False  # Opt-in
    timeout_seconds: float = Field(default=5.0, ge=0.1, le=60.0)
    max_retries: int = Field(default=3, ge=0, le=10)
    https_only: bool = True
    default_events: List[str] = Field(default_factory=lambda: ["council.complete", "council.error"])


class FallbackConfig(BaseModel):
    """Configuration for gateway fallback behavior."""

    enabled: bool = True
    chain: List[str] = Field(default_factory=lambda: ["openrouter", "requesty", "direct"])
    retry_on: List[str] = Field(default_factory=lambda: ["timeout", "rate_limit", "server_error"])
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
                if isinstance(ollama_data, dict) and not isinstance(
                    ollama_data, OllamaProviderConfig
                ):
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


class ScoringConfig(BaseModel):
    """Configuration for cost scoring algorithms (ADR-030).

    Controls how model costs are normalized into scores for selection.
    Default is log_ratio which handles exponential price differences gracefully.
    """

    cost_scale: Literal["linear", "log_ratio", "exponential"] = "log_ratio"
    cost_reference_high: float = Field(default=0.015, ge=0.0001, le=1.0)


class CircuitBreakerConfig(BaseModel):
    """Configuration for per-model circuit breakers (ADR-030).

    Circuit breakers prevent cascade failures by temporarily excluding models
    that are failing frequently. Uses sliding window failure tracking.
    """

    enabled: bool = True
    failure_threshold: float = Field(
        default=0.25, ge=0.0, le=1.0, description="Failure rate (0-1) to trigger circuit open"
    )
    min_requests: int = Field(
        default=5, ge=1, description="Minimum requests before circuit can trip"
    )
    window_seconds: int = Field(
        default=600, ge=60, description="Sliding window for failure tracking (10 min default)"
    )
    cooldown_seconds: int = Field(
        default=1800, ge=60, description="Time before OPEN transitions to HALF_OPEN (30 min)"
    )
    half_open_max_requests: int = Field(
        default=3, ge=1, description="Max probe requests in HALF_OPEN state"
    )
    half_open_success_threshold: float = Field(
        default=0.67, ge=0.0, le=1.0, description="Success rate to close circuit"
    )


class DiscoveryProviderConfig(BaseModel):
    """Provider-specific discovery settings (ADR-028)."""

    enabled: bool = True
    rate_limit_rpm: int = Field(default=60, ge=1, le=1000)
    timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0)


class DiscoveryConfig(BaseModel):
    """Configuration for dynamic candidate discovery (ADR-028).

    Controls background model registry refresh and request-time discovery.
    """

    enabled: bool = True  # Discovery enabled by default when model_intelligence is on
    refresh_interval_seconds: int = Field(default=300, ge=60, le=3600)  # 5 minutes
    min_candidates_per_tier: int = Field(default=3, ge=1, le=10)
    max_candidates_per_tier: int = Field(default=10, ge=3, le=50)
    stale_threshold_minutes: int = Field(default=30, ge=5, le=120)
    max_refresh_retries: int = Field(default=3, ge=1, le=10)
    providers: Dict[str, DiscoveryProviderConfig] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_candidates_range(self) -> "DiscoveryConfig":
        """Ensure min_candidates <= max_candidates."""
        if self.min_candidates_per_tier > self.max_candidates_per_tier:
            raise ValueError(
                f"min_candidates_per_tier ({self.min_candidates_per_tier}) "
                f"must be <= max_candidates_per_tier ({self.max_candidates_per_tier})"
            )
        return self


class GraduationConfig(BaseModel):
    """Configuration for frontier model graduation criteria (ADR-027)."""

    min_age_days: int = Field(default=30, ge=1)
    min_completed_sessions: int = Field(default=100, ge=1)
    max_error_rate: float = Field(default=0.02, ge=0.0, le=1.0)
    min_quality_percentile: float = Field(default=0.75, ge=0.0, le=1.0)


class FrontierConfig(BaseModel):
    """Configuration for frontier tier (ADR-027).

    Controls Shadow Mode voting, cost ceiling, and hard fallback behavior.
    """

    voting_authority: str = Field(default="advisory")  # "full" or "advisory"
    cost_ceiling_multiplier: float = Field(default=5.0, ge=1.0)
    fallback_tier: str = Field(default="high")
    graduation: GraduationConfig = Field(default_factory=GraduationConfig)

    @field_validator("voting_authority")
    @classmethod
    def validate_voting_authority(cls, v: str) -> str:
        valid = {"full", "advisory", "excluded"}
        if v not in valid:
            raise ValueError(f"invalid voting_authority '{v}', must be one of {valid}")
        return v

    @field_validator("fallback_tier")
    @classmethod
    def validate_fallback_tier(cls, v: str) -> str:
        valid = {"quick", "balanced", "high", "reasoning"}
        if v not in valid:
            raise ValueError(f"invalid fallback_tier '{v}', must be one of {valid}")
        return v


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
    effort_by_tier: ReasoningEffortByTierConfig = Field(default_factory=ReasoningEffortByTierConfig)
    domain_overrides: DomainOverridesConfig = Field(default_factory=DomainOverridesConfig)
    stages: ReasoningStageConfig = Field(default_factory=ReasoningStageConfig)
    max_budget_tokens: int = Field(default=32000, ge=1024, le=100000)
    min_budget_tokens: int = Field(default=1024, ge=256, le=32000)


class PerformanceTrackerConfig(BaseModel):
    """Configuration for internal performance tracking (ADR-026 Phase 3).

    Controls tracking of model performance from actual council sessions,
    building an Internal Performance Index for model selection.
    """

    enabled: bool = True  # Enabled by default when model intelligence is on
    store_path: str = "${HOME}/.llm-council/performance_metrics.jsonl"
    decay_days: int = Field(default=30, ge=1, le=365)
    min_samples_preliminary: int = Field(default=10, ge=1)
    min_samples_moderate: int = Field(default=30, ge=1)
    min_samples_high: int = Field(default=100, ge=1)


# =============================================================================
# ADR-029: Model Audition Configuration
# =============================================================================


class ShadowPhaseConfig(BaseModel):
    """Configuration for SHADOW phase of model audition."""

    min_sessions: int = Field(default=10, ge=1)
    min_days: int = Field(default=3, ge=1)
    max_failures: int = Field(default=3, ge=0)


class ProbationPhaseConfig(BaseModel):
    """Configuration for PROBATION phase of model audition."""

    min_sessions: int = Field(default=25, ge=1)
    min_days: int = Field(default=7, ge=1)
    max_failures: int = Field(default=5, ge=0)


class EvaluationPhaseConfig(BaseModel):
    """Configuration for EVALUATION phase of model audition."""

    min_sessions: int = Field(default=50, ge=1)
    min_quality_percentile: float = Field(default=0.75, ge=0.0, le=1.0)


class QuarantinePhaseConfig(BaseModel):
    """Configuration for QUARANTINE phase of model audition."""

    cooldown_hours: int = Field(default=24, ge=1, le=168)


class AuditionConfig(BaseModel):
    """Configuration for Model Audition Mechanism (ADR-029).

    Controls the volume-based audition process for newly discovered models.
    New models progress through states: SHADOW → PROBATION → EVALUATION → FULL

    Attributes:
        enabled: Whether audition mechanism is active (default: True)
        max_audition_seats: Maximum audition models per council session (default: 1)
        shadow: SHADOW phase configuration
        probation: PROBATION phase configuration
        evaluation: EVALUATION phase configuration
        quarantine: QUARANTINE phase configuration
        store_path: Path to audition status JSONL file
    """

    enabled: bool = True
    max_audition_seats: int = Field(default=1, ge=0, le=4)
    shadow: ShadowPhaseConfig = Field(default_factory=ShadowPhaseConfig)
    probation: ProbationPhaseConfig = Field(default_factory=ProbationPhaseConfig)
    evaluation: EvaluationPhaseConfig = Field(default_factory=EvaluationPhaseConfig)
    quarantine: QuarantinePhaseConfig = Field(default_factory=QuarantinePhaseConfig)
    store_path: str = "${HOME}/.llm-council/audition_status.jsonl"


class ModelIntelligenceConfig(BaseModel):
    """Configuration for Model Intelligence Layer (ADR-026).

    Controls dynamic model metadata fetching, caching, and selection.
    Disabled by default (opt-in via LLM_COUNCIL_MODEL_INTELLIGENCE=true).
    """

    enabled: bool = False  # Opt-in; requires API connectivity
    refresh: ModelIntelligenceRefreshConfig = Field(default_factory=ModelIntelligenceRefreshConfig)
    selection: ModelIntelligenceSelectionConfig = Field(
        default_factory=ModelIntelligenceSelectionConfig
    )
    anti_herding: AntiHerdingConfig = Field(default_factory=AntiHerdingConfig)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)  # ADR-030
    circuit_breaker: CircuitBreakerConfig = Field(default_factory=CircuitBreakerConfig)  # ADR-030
    discovery: DiscoveryConfig = Field(default_factory=DiscoveryConfig)  # ADR-028
    reasoning: ReasoningOptimizationConfig = Field(default_factory=ReasoningOptimizationConfig)
    performance_tracker: PerformanceTrackerConfig = Field(default_factory=PerformanceTrackerConfig)
    audition: AuditionConfig = Field(default_factory=AuditionConfig)  # ADR-029


class MetricsConfig(BaseModel):
    """Configuration for external metrics export (ADR-030).

    Bridges internal LayerEvents to external metrics backends (StatsD, Prometheus)
    for observability dashboards. Disabled by default - opt-in via config or env var.
    """

    enabled: bool = False  # Opt-in; requires metrics backend
    backend: Literal["none", "statsd", "prometheus"] = "none"
    statsd_host: str = "localhost"
    statsd_port: int = Field(default=8125, ge=1, le=65535)
    statsd_prefix: str = "llm_council"
    prometheus_port: int = Field(default=9090, ge=1, le=65535)


class ObservabilityConfig(BaseModel):
    """Configuration for observability settings."""

    log_escalations: bool = True
    log_gateway_fallbacks: bool = True
    metrics_enabled: bool = True
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)  # ADR-030


# =============================================================================
# ADR-032: Complete Configuration Migration
# =============================================================================


class SecretsConfig(BaseModel):
    """Metadata about required secrets (ADR-032).

    Note: Does NOT contain actual secrets or resolution logic.
    Use get_api_key() helper for resolution.
    """

    required_providers: List[str] = Field(
        default_factory=lambda: ["openrouter"],
        description="Providers that require API keys",
    )
    keychain_service: str = Field(
        default="llm-council",
        description="macOS Keychain service name",
    )


class CouncilConfig(BaseModel):
    """Core council behavior configuration (ADR-032)."""

    model_config = {"populate_by_name": True}

    models: ModelList = Field(
        default_factory=lambda: [
            "openai/gpt-5.2-pro",
            "google/gemini-3-pro-preview",
            "anthropic/claude-opus-4.5",
            "x-ai/grok-4",
        ],
        alias="LLM_COUNCIL_MODELS",
    )
    chairman: str = Field(
        default="google/gemini-3-pro-preview",
        alias="LLM_COUNCIL_CHAIRMAN",
    )
    synthesis_mode: Literal["consensus", "debate"] = Field(
        default="consensus",
        alias="LLM_COUNCIL_MODE",
    )
    exclude_self_votes: bool = Field(
        default=True,
        alias="LLM_COUNCIL_EXCLUDE_SELF_VOTES",
    )
    style_normalization: Union[bool, Literal["auto"]] = Field(
        default=False,
        alias="LLM_COUNCIL_STYLE_NORMALIZATION",
    )
    normalizer_model: str = Field(
        default="google/gemini-2.0-flash-001",
        alias="LLM_COUNCIL_NORMALIZER_MODEL",
    )
    max_reviewers: Optional[int] = Field(
        default=None,
        alias="LLM_COUNCIL_MAX_REVIEWERS",
    )


class TierTimeoutConfig(BaseModel):
    """Timeout configuration for a single tier (ADR-032)."""

    total: int = Field(ge=1000, description="Total timeout in ms")
    per_model: int = Field(ge=500, description="Per-model timeout in ms")


class TimeoutsConfig(BaseModel):
    """Tier-sovereign timeout configuration (ADR-022/ADR-032).

    All timeout values are in milliseconds.
    """

    model_config = {"populate_by_name": True}

    quick: TierTimeoutConfig = Field(
        default_factory=lambda: TierTimeoutConfig(total=30000, per_model=20000)
    )
    balanced: TierTimeoutConfig = Field(
        default_factory=lambda: TierTimeoutConfig(total=90000, per_model=45000)
    )
    high: TierTimeoutConfig = Field(
        default_factory=lambda: TierTimeoutConfig(total=180000, per_model=90000)
    )
    reasoning: TierTimeoutConfig = Field(
        default_factory=lambda: TierTimeoutConfig(total=600000, per_model=300000)
    )
    frontier: TierTimeoutConfig = Field(
        default_factory=lambda: TierTimeoutConfig(total=600000, per_model=300000)
    )
    multiplier: float = Field(
        default=1.0,
        ge=0.1,
        le=10.0,
        alias="LLM_COUNCIL_TIMEOUT_MULTIPLIER",
    )

    def get_timeout(self, tier: str, timeout_type: str = "total") -> int:
        """Get timeout with multiplier applied.

        Args:
            tier: One of quick, balanced, high, reasoning, frontier
            timeout_type: Either "total" or "per_model"

        Returns:
            Timeout in milliseconds with multiplier applied
        """
        tier_config = getattr(self, tier, None)
        if tier_config is None:
            # Fall back to high tier for unknown tiers
            tier_config = self.high
        base = getattr(tier_config, timeout_type, tier_config.total)
        return int(base * self.multiplier)


class CacheConfig(BaseModel):
    """Response caching configuration (ADR-032)."""

    model_config = {"populate_by_name": True}

    enabled: bool = Field(
        default=False,
        alias="LLM_COUNCIL_CACHE",
    )
    ttl_seconds: int = Field(
        default=0,  # 0 = infinite (no expiry)
        ge=0,
        alias="LLM_COUNCIL_CACHE_TTL",
    )
    directory: Path = Field(default_factory=lambda: Path.home() / ".cache" / "llm-council")


class TelemetryConfig(BaseModel):
    """Opt-in telemetry configuration (ADR-032)."""

    model_config = {"populate_by_name": True}

    level: Literal["off", "anonymous", "debug"] = Field(
        default="off",
        alias="LLM_COUNCIL_TELEMETRY",
    )
    endpoint: str = Field(default="https://ingest.llmcouncil.ai/v1/events")

    @property
    def enabled(self) -> bool:
        """Convenience property for checking if telemetry is on."""
        return self.level != "off"


# =============================================================================
# ADR-031: EvaluationConfig (Rubric, Safety, Bias)
# =============================================================================


class RubricConfig(BaseModel):
    """Rubric-based multi-dimensional scoring (ADR-016/ADR-031).

    Controls structured rubric evaluation with weighted dimensions.
    Weights must sum to 1.0 and include all 5 dimensions.
    """

    model_config = {"populate_by_name": True}

    enabled: bool = Field(default=False, validation_alias="RUBRIC_SCORING_ENABLED")
    accuracy_ceiling_enabled: bool = Field(
        default=True, validation_alias="ACCURACY_CEILING_ENABLED"
    )
    weights: Dict[str, float] = Field(
        default_factory=lambda: {
            "accuracy": 0.35,
            "relevance": 0.10,
            "completeness": 0.20,
            "conciseness": 0.15,
            "clarity": 0.20,
        }
    )

    @field_validator("weights")
    @classmethod
    def validate_weights(cls, v: Dict[str, float]) -> Dict[str, float]:
        """Validate rubric weights: non-negative, sum to 1.0, all dimensions present."""
        if not v:
            return v

        # Check for negative weights
        if any(x < 0 for x in v.values()):
            raise ValueError("Weights cannot be negative")

        # Check sum equals 1.0 (within tolerance)
        weight_sum = sum(v.values())
        if abs(weight_sum - 1.0) > 0.01:
            raise ValueError(f"Weights must sum to 1.0, got {weight_sum}")

        # Check all required dimensions present
        required = {"accuracy", "relevance", "completeness", "conciseness", "clarity"}
        if not required.issubset(v.keys()):
            missing = required - set(v.keys())
            raise ValueError(f"Weights must include all dimensions: {required}. Missing: {missing}")

        return v


class SafetyConfig(BaseModel):
    """Safety gate for harmful content detection (ADR-016/ADR-031).

    When enabled, caps scores for responses that fail safety checks.
    """

    model_config = {"populate_by_name": True}

    enabled: bool = Field(default=False, validation_alias="SAFETY_GATE_ENABLED")
    score_cap: float = Field(default=0.0, ge=0.0, le=1.0)


class BiasConfig(BaseModel):
    """Per-session and cross-session bias auditing (ADR-015/018/ADR-031).

    Controls bias detection and persistence for evaluator calibration.
    """

    model_config = {"populate_by_name": True}

    audit_enabled: bool = Field(default=False, validation_alias="BIAS_AUDIT_ENABLED")
    persistence_enabled: bool = Field(default=False, validation_alias="BIAS_PERSISTENCE_ENABLED")
    store_path: str = Field(default="data/bias_metrics.jsonl")
    consent_level: Literal["OFF", "LOCAL_ONLY", "ANONYMOUS", "ENHANCED", "RESEARCH"] = "LOCAL_ONLY"
    length_correlation_threshold: float = Field(
        default=0.3, ge=0.0, le=1.0
    )  # |r| above this = bias
    position_variance_threshold: float = Field(
        default=0.5, ge=0.0
    )  # Match original config.py default


class EvaluationConfig(BaseModel):
    """Evaluation-time configuration for scoring, safety, and bias (ADR-031).

    Container for all evaluation-related settings migrated from config.py.
    """

    rubric: RubricConfig = Field(default_factory=RubricConfig)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    bias: BiasConfig = Field(default_factory=BiasConfig)


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
    model_intelligence: ModelIntelligenceConfig = Field(default_factory=ModelIntelligenceConfig)
    frontier: FrontierConfig = Field(default_factory=FrontierConfig)  # ADR-027
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)  # ADR-031
    # ADR-032: Complete Configuration Migration
    secrets: SecretsConfig = Field(default_factory=SecretsConfig)
    council: CouncilConfig = Field(default_factory=CouncilConfig)
    timeouts: TimeoutsConfig = Field(default_factory=TimeoutsConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    telemetry: TelemetryConfig = Field(default_factory=TelemetryConfig)

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
            config_dict.setdefault("tiers", {}).setdefault("pools", {}).setdefault(tier, {})[
                "models"
            ] = models

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
        config_dict.setdefault("triage", {}).setdefault("wildcard", {})["enabled"] = (
            wildcard_env.lower() in ("true", "1", "yes")
        )

    # Prompt optimization override
    prompt_opt_env = os.getenv("LLM_COUNCIL_PROMPT_OPTIMIZATION_ENABLED")
    if prompt_opt_env:
        config_dict.setdefault("triage", {}).setdefault("prompt_optimization", {})["enabled"] = (
            prompt_opt_env.lower() in ("true", "1", "yes")
        )

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
        config_dict.setdefault("gateways", {}).setdefault("providers", {}).setdefault("ollama", {})[
            "base_url"
        ] = ollama_base_url
    ollama_timeout = os.getenv("LLM_COUNCIL_OLLAMA_TIMEOUT")
    if ollama_timeout:
        config_dict.setdefault("gateways", {}).setdefault("providers", {}).setdefault("ollama", {})[
            "timeout_seconds"
        ] = float(ollama_timeout)

    # Webhook overrides (ADR-025a)
    webhooks_enabled = os.getenv("LLM_COUNCIL_WEBHOOKS_ENABLED")
    if webhooks_enabled:
        config_dict.setdefault("webhooks", {})["enabled"] = webhooks_enabled.lower() in (
            "true",
            "1",
            "yes",
        )
    webhook_timeout = os.getenv("LLM_COUNCIL_WEBHOOK_TIMEOUT")
    if webhook_timeout:
        config_dict.setdefault("webhooks", {})["timeout_seconds"] = float(webhook_timeout)
    webhook_retries = os.getenv("LLM_COUNCIL_WEBHOOK_RETRIES")
    if webhook_retries:
        config_dict.setdefault("webhooks", {})["max_retries"] = int(webhook_retries)

    # Model Intelligence overrides (ADR-026)
    model_intelligence_enabled = os.getenv("LLM_COUNCIL_MODEL_INTELLIGENCE")
    if model_intelligence_enabled:
        config_dict.setdefault("model_intelligence", {})["enabled"] = (
            model_intelligence_enabled.lower() in ("true", "1", "yes")
        )

    # Reasoning optimization overrides (ADR-026 Phase 2)
    reasoning_enabled = os.getenv("LLM_COUNCIL_REASONING_ENABLED")
    if reasoning_enabled:
        config_dict.setdefault("model_intelligence", {}).setdefault("reasoning", {})["enabled"] = (
            reasoning_enabled.lower() in ("true", "1", "yes")
        )

    # Scoring overrides (ADR-030)
    cost_scale = os.getenv("LLM_COUNCIL_COST_SCALE")
    if cost_scale and cost_scale.lower() in ("linear", "log_ratio", "exponential"):
        config_dict.setdefault("model_intelligence", {}).setdefault("scoring", {})["cost_scale"] = (
            cost_scale.lower()
        )

    # Circuit breaker overrides (ADR-030)
    circuit_breaker_enabled = os.getenv("LLM_COUNCIL_CIRCUIT_BREAKER")
    if circuit_breaker_enabled:
        config_dict.setdefault("model_intelligence", {}).setdefault("circuit_breaker", {})[
            "enabled"
        ] = circuit_breaker_enabled.lower() in ("true", "1", "yes")

    circuit_threshold = os.getenv("LLM_COUNCIL_CIRCUIT_THRESHOLD")
    if circuit_threshold:
        config_dict.setdefault("model_intelligence", {}).setdefault("circuit_breaker", {})[
            "failure_threshold"
        ] = float(circuit_threshold)

    circuit_min_requests = os.getenv("LLM_COUNCIL_CIRCUIT_MIN_REQUESTS")
    if circuit_min_requests:
        config_dict.setdefault("model_intelligence", {}).setdefault("circuit_breaker", {})[
            "min_requests"
        ] = int(circuit_min_requests)

    # Discovery overrides (ADR-028)
    discovery_enabled = os.getenv("LLM_COUNCIL_DISCOVERY_ENABLED")
    if discovery_enabled:
        config_dict.setdefault("model_intelligence", {}).setdefault("discovery", {})["enabled"] = (
            discovery_enabled.lower() in ("true", "1", "yes")
        )

    discovery_interval = os.getenv("LLM_COUNCIL_DISCOVERY_INTERVAL")
    if discovery_interval:
        config_dict.setdefault("model_intelligence", {}).setdefault("discovery", {})[
            "refresh_interval_seconds"
        ] = int(discovery_interval)

    discovery_min_candidates = os.getenv("LLM_COUNCIL_DISCOVERY_MIN_CANDIDATES")
    if discovery_min_candidates:
        config_dict.setdefault("model_intelligence", {}).setdefault("discovery", {})[
            "min_candidates_per_tier"
        ] = int(discovery_min_candidates)

    # Metrics overrides (ADR-030)
    metrics_enabled = os.getenv("LLM_COUNCIL_METRICS_ENABLED")
    if metrics_enabled:
        config_dict.setdefault("observability", {}).setdefault("metrics", {})["enabled"] = (
            metrics_enabled.lower() in ("true", "1", "yes")
        )

    metrics_backend = os.getenv("LLM_COUNCIL_METRICS_BACKEND")
    if metrics_backend and metrics_backend.lower() in ("none", "statsd", "prometheus"):
        config_dict.setdefault("observability", {}).setdefault("metrics", {})["backend"] = (
            metrics_backend.lower()
        )

    statsd_host = os.getenv("LLM_COUNCIL_STATSD_HOST")
    if statsd_host:
        config_dict.setdefault("observability", {}).setdefault("metrics", {})["statsd_host"] = (
            statsd_host
        )

    statsd_port = os.getenv("LLM_COUNCIL_STATSD_PORT")
    if statsd_port:
        config_dict.setdefault("observability", {}).setdefault("metrics", {})["statsd_port"] = int(
            statsd_port
        )

    # Audition overrides (ADR-029)
    audition_enabled = os.getenv("LLM_COUNCIL_AUDITION_ENABLED")
    if audition_enabled:
        config_dict.setdefault("model_intelligence", {}).setdefault("audition", {})["enabled"] = (
            audition_enabled.lower() in ("true", "1", "yes")
        )

    audition_max_seats = os.getenv("LLM_COUNCIL_AUDITION_MAX_SEATS")
    if audition_max_seats:
        config_dict.setdefault("model_intelligence", {}).setdefault("audition", {})[
            "max_audition_seats"
        ] = int(audition_max_seats)

    audition_shadow_sessions = os.getenv("LLM_COUNCIL_AUDITION_SHADOW_SESSIONS")
    if audition_shadow_sessions:
        config_dict.setdefault("model_intelligence", {}).setdefault("audition", {}).setdefault(
            "shadow", {}
        )["min_sessions"] = int(audition_shadow_sessions)

    audition_eval_sessions = os.getenv("LLM_COUNCIL_AUDITION_EVAL_SESSIONS")
    if audition_eval_sessions:
        config_dict.setdefault("model_intelligence", {}).setdefault("audition", {}).setdefault(
            "evaluation", {}
        )["min_sessions"] = int(audition_eval_sessions)

    # Evaluation overrides (ADR-031)
    rubric_enabled = os.getenv("RUBRIC_SCORING_ENABLED")
    if rubric_enabled:
        config_dict.setdefault("evaluation", {}).setdefault("rubric", {})["enabled"] = (
            rubric_enabled.lower() in ("true", "1", "yes")
        )

    accuracy_ceiling_enabled = os.getenv("ACCURACY_CEILING_ENABLED")
    if accuracy_ceiling_enabled:
        config_dict.setdefault("evaluation", {}).setdefault("rubric", {})[
            "accuracy_ceiling_enabled"
        ] = accuracy_ceiling_enabled.lower() in ("true", "1", "yes")

    safety_enabled = os.getenv("SAFETY_GATE_ENABLED")
    if safety_enabled:
        config_dict.setdefault("evaluation", {}).setdefault("safety", {})["enabled"] = (
            safety_enabled.lower() in ("true", "1", "yes")
        )

    bias_audit_enabled = os.getenv("BIAS_AUDIT_ENABLED")
    if bias_audit_enabled:
        config_dict.setdefault("evaluation", {}).setdefault("bias", {})["audit_enabled"] = (
            bias_audit_enabled.lower() in ("true", "1", "yes")
        )

    bias_persistence_enabled = os.getenv("BIAS_PERSISTENCE_ENABLED")
    if bias_persistence_enabled:
        config_dict.setdefault("evaluation", {}).setdefault("bias", {})["persistence_enabled"] = (
            bias_persistence_enabled.lower() in ("true", "1", "yes")
        )

    # ADR-032: Council configuration overrides
    council_models = os.getenv("LLM_COUNCIL_MODELS")
    if council_models:
        config_dict.setdefault("council", {})["models"] = parse_model_list(council_models)

    council_chairman = os.getenv("LLM_COUNCIL_CHAIRMAN")
    if council_chairman:
        config_dict.setdefault("council", {})["chairman"] = council_chairman

    council_mode = os.getenv("LLM_COUNCIL_MODE")
    if council_mode:
        config_dict.setdefault("council", {})["synthesis_mode"] = council_mode

    council_exclude_self = os.getenv("LLM_COUNCIL_EXCLUDE_SELF_VOTES")
    if council_exclude_self:
        config_dict.setdefault("council", {})["exclude_self_votes"] = (
            council_exclude_self.lower() in ("true", "1", "yes")
        )

    council_style_norm = os.getenv("LLM_COUNCIL_STYLE_NORMALIZATION")
    if council_style_norm:
        if council_style_norm.lower() == "auto":
            config_dict.setdefault("council", {})["style_normalization"] = "auto"
        else:
            config_dict.setdefault("council", {})["style_normalization"] = (
                council_style_norm.lower() in ("true", "1", "yes")
            )

    council_normalizer = os.getenv("LLM_COUNCIL_NORMALIZER_MODEL")
    if council_normalizer:
        config_dict.setdefault("council", {})["normalizer_model"] = council_normalizer

    council_max_reviewers = os.getenv("LLM_COUNCIL_MAX_REVIEWERS")
    if council_max_reviewers:
        config_dict.setdefault("council", {})["max_reviewers"] = int(council_max_reviewers)

    # ADR-032: Timeout configuration overrides
    timeout_multiplier = os.getenv("LLM_COUNCIL_TIMEOUT_MULTIPLIER")
    if timeout_multiplier:
        config_dict.setdefault("timeouts", {})["multiplier"] = float(timeout_multiplier)

    # ADR-032: Cache configuration overrides
    cache_enabled = os.getenv("LLM_COUNCIL_CACHE")
    if cache_enabled:
        config_dict.setdefault("cache", {})["enabled"] = cache_enabled.lower() in (
            "true",
            "1",
            "yes",
        )

    cache_ttl = os.getenv("LLM_COUNCIL_CACHE_TTL")
    if cache_ttl:
        config_dict.setdefault("cache", {})["ttl_seconds"] = int(cache_ttl)

    cache_dir = os.getenv("LLM_COUNCIL_CACHE_DIR")
    if cache_dir:
        config_dict.setdefault("cache", {})["directory"] = cache_dir

    # ADR-032: Telemetry configuration overrides
    telemetry_level = os.getenv("LLM_COUNCIL_TELEMETRY")
    if telemetry_level and telemetry_level.lower() in ("off", "anonymous", "debug"):
        config_dict.setdefault("telemetry", {})["level"] = telemetry_level.lower()

    telemetry_endpoint = os.getenv("LLM_COUNCIL_TELEMETRY_ENDPOINT")
    if telemetry_endpoint:
        config_dict.setdefault("telemetry", {})["endpoint"] = telemetry_endpoint

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


# =============================================================================
# ADR-032: Helper Functions
# =============================================================================

# ADR-013: Key source tracking for diagnostics
_key_source: str = "unknown"

# Lazy-loaded keyring module (None means not checked, False means not installed)
keyring: Any = None


def _is_fail_backend() -> bool:
    """Check if keyring is using the fail backend (headless environment).

    Returns:
        True if keyring is unavailable or using fail backend
    """
    global keyring
    if keyring is None:
        try:
            import keyring as kr

            keyring = kr
        except ImportError:
            keyring = False
            return True

    if keyring is False:
        return True

    try:
        from keyring.backends import fail

        return isinstance(keyring.get_keyring(), fail.Keyring)
    except ImportError:
        return False


def _get_api_key_from_keychain(provider: str = "openrouter_api_key") -> Optional[str]:
    """Get API key from system keychain (ADR-013).

    Args:
        provider: The key name to look up (default: openrouter_api_key)

    Returns:
        API key string or None if not found/unavailable
    """
    global keyring
    if keyring is None:
        try:
            import keyring as kr

            keyring = kr
        except ImportError:
            keyring = False
            return None

    if keyring is False:
        return None

    if _is_fail_backend():
        return None

    try:
        config = get_config()
        return keyring.get_password(config.secrets.keychain_service, provider)
    except Exception:
        return None


def get_key_source() -> str:
    """Get the source of the last API key resolution (ADR-013).

    Returns:
        One of: "environment", "keychain", "config_file", "unknown"
    """
    return _key_source


def _get_api_key(provider: str = "openrouter") -> Optional[str]:
    """Internal API key resolution with source tracking (ADR-013).

    This is the internal implementation that tracks key source.
    Use get_api_key() for the public API.

    Priority:
    1. Environment variable (e.g., OPENROUTER_API_KEY)
    2. macOS Keychain (via keyring library, if available)
    3. User config file (deprecated, emits warning)

    Args:
        provider: Provider name (e.g., "openrouter", "anthropic", "openai")

    Returns:
        API key string or None if not found
    """
    global _key_source

    # Normalize provider name to uppercase for env var lookup
    env_var = f"{provider.upper()}_API_KEY"

    # 1. Check environment variable (includes .env via dotenv)
    key = os.environ.get(env_var)
    if key:
        _key_source = "environment"
        return key

    # 2. Try keychain (if keyring is available)
    keychain_key = _get_api_key_from_keychain(f"{provider}_api_key")
    if keychain_key:
        _key_source = "keychain"
        return keychain_key

    # 3. Try user config (deprecated)
    if _user_config.get(f"{provider}_api_key"):
        _key_source = "config_file"
        # Emit warning unless suppressed
        if not os.environ.get("LLM_COUNCIL_SUPPRESS_WARNINGS"):
            import sys

            print(
                f"Warning: Loading API key from config file is insecure. "
                f"Use environment variables or keychain instead.",
                file=sys.stderr,
            )
        return _user_config[f"{provider}_api_key"]

    _key_source = "unknown"
    return None


# User config for backwards compatibility with config file keys
_user_config: Dict[str, Any] = {}


def get_api_key(provider: str) -> Optional[str]:
    """Resolve API key for provider (ADR-013 resolution chain).

    Priority:
    1. Environment variable (e.g., OPENROUTER_API_KEY)
    2. macOS Keychain (via keyring library, if available)
    3. None (caller handles missing key)

    Note: dotenv is loaded at module import, so .env vars
    are already in os.environ.

    Args:
        provider: Provider name (e.g., "openrouter", "anthropic", "openai")

    Returns:
        API key string or None if not found
    """
    return _get_api_key(provider)


def dump_effective_config(redact_secrets: bool = True) -> str:
    """Dump the effective configuration as a YAML string.

    Useful for debugging and logging the current configuration state.

    Args:
        redact_secrets: If True, redacts API keys and sensitive values

    Returns:
        YAML string representation of the effective configuration
    """
    config = get_config()
    config_dict = {"council": config.to_dict()}

    if redact_secrets:
        # Redact credentials section
        if "credentials" in config_dict["council"]:
            for key in config_dict["council"]["credentials"]:
                if config_dict["council"]["credentials"][key]:
                    config_dict["council"]["credentials"][key] = "[REDACTED]"

    return yaml.dump(config_dict, default_flow_style=False, sort_keys=False)
