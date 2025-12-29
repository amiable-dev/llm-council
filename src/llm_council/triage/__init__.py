"""Triage package for ADR-020 Layer 2 (Query Triage).

This package handles query classification, model selection, and prompt optimization
before council execution.

Features:
- Fast path: Confidence-gated routing for simple queries (Issue #57)
- Wildcard selection: Adds domain specialist to council (Issue #48)
- Prompt optimizer: Per-model prompt adaptation (Issue #49)
- Complexity classifier: Tier escalation detection (Issue #50)
"""

from typing import Optional

# ADR-032: Migrated to unified_config
from llm_council.unified_config import get_config
from llm_council.tier_contract import TierContract


def _get_council_models() -> list:
    """Get council models from unified config."""
    return get_config().council.models


from .types import (
    DEFAULT_SPECIALIST_POOLS,
    DomainCategory,
    TriageRequest,
    TriageResult,
    WildcardConfig,
)
from .wildcard import classify_query_domain, select_wildcard
from .prompt_optimizer import PromptOptimizer, get_model_provider
from .fast_path import (
    FastPathRouter,
    FastPathResult,
    FastPathConfig,
    ConfidenceExtractor,
    get_fast_path_router,
    is_fast_path_enabled,
)
from .shadow_sampling import (
    ShadowSampler,
    ShadowSamplingConfig,
    ShadowSampleResult,
    DisagreementDetector,
    ShadowMetricStore,
    get_shadow_sampler,
    get_shadow_store,
)
from .rollback_metrics import (
    RollbackMonitor,
    RollbackConfig,
    RollbackMetricStore,
    MetricType,
    RollbackEvent,
    get_rollback_monitor,
    should_disable_fast_path,
)
from .not_diamond import (
    NotDiamondConfig,
    NotDiamondClient,
    NotDiamondClassifier,
    NotDiamondRouter,
    RouteResult,
    is_not_diamond_available,
    get_not_diamond_config,
    get_not_diamond_client,
)

__all__ = [
    "run_triage",
    "TriageResult",
    "TriageRequest",
    "WildcardConfig",
    "DomainCategory",
    "DEFAULT_SPECIALIST_POOLS",
    "classify_query_domain",
    "select_wildcard",
    "PromptOptimizer",
    "get_model_provider",
    # Fast path (Issue #57)
    "FastPathRouter",
    "FastPathResult",
    "FastPathConfig",
    "ConfidenceExtractor",
    "get_fast_path_router",
    "is_fast_path_enabled",
    # Shadow sampling (Issue #58)
    "ShadowSampler",
    "ShadowSamplingConfig",
    "ShadowSampleResult",
    "DisagreementDetector",
    "ShadowMetricStore",
    "get_shadow_sampler",
    "get_shadow_store",
    # Rollback metrics (Issue #60)
    "RollbackMonitor",
    "RollbackConfig",
    "RollbackMetricStore",
    "MetricType",
    "RollbackEvent",
    "get_rollback_monitor",
    "should_disable_fast_path",
    # Not Diamond integration (Issue #59)
    "NotDiamondConfig",
    "NotDiamondClient",
    "NotDiamondClassifier",
    "NotDiamondRouter",
    "RouteResult",
    "is_not_diamond_available",
    "get_not_diamond_config",
    "get_not_diamond_client",
]


def run_triage(
    query: str,
    tier_contract: Optional[TierContract] = None,
    domain_hint: Optional[DomainCategory] = None,
    include_wildcard: bool = False,
    wildcard_config: Optional[WildcardConfig] = None,
    optimize_prompts: bool = False,
) -> TriageResult:
    """Run query triage to determine models and optimize prompts.

    Performs domain classification, optional wildcard selection,
    and optional per-model prompt optimization.

    Args:
        query: The user query to triage
        tier_contract: Optional tier contract constraining model selection
        domain_hint: Optional domain hint for specialist selection
        include_wildcard: Whether to add a wildcard specialist model
        wildcard_config: Optional custom wildcard configuration
        optimize_prompts: Whether to apply per-model prompt optimization

    Returns:
        TriageResult with resolved models and prompts
    """
    # Determine base models to use
    if tier_contract is not None:
        models = list(tier_contract.allowed_models)
    else:
        models = list(_get_council_models())

    metadata = {"mode": "passthrough"}

    # Optionally add wildcard specialist
    if include_wildcard:
        domain = classify_query_domain(query, domain_hint=domain_hint)
        wildcard = select_wildcard(
            domain,
            exclude_models=models,
            config=wildcard_config,
            tier_contract=tier_contract,
        )
        models = models + [wildcard]
        metadata = {
            "mode": "wildcard",
            "domain": domain.value,
            "wildcard": wildcard,
        }

    # Apply prompt optimization if enabled
    if optimize_prompts:
        optimizer = PromptOptimizer(enabled=True)
        optimized_prompts = optimizer.optimize(query, models)
        metadata["optimization_applied"] = True
    else:
        # Passthrough: use original query for all models
        optimized_prompts = {model: query for model in models}

    return TriageResult(
        resolved_models=models,
        optimized_prompts=optimized_prompts,
        fast_path=False,
        escalation_recommended=False,
        metadata=metadata,
    )
