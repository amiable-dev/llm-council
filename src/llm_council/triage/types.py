"""Triage package types for ADR-020 Layer 2.

This module defines the core types for query triage and wildcard selection.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

# Import TierContract for type hints
from llm_council.tier_contract import TierContract


from llm_council import model_constants as mc


class DomainCategory(Enum):
    """Domain categories for specialist model selection.

    Per ADR-020, wildcard seat should be domain-specialized.
    """

    CODE = "code"
    REASONING = "reasoning"
    CREATIVE = "creative"
    MULTILINGUAL = "multilingual"
    GENERAL = "general"


# Default specialist pools per ADR-020 council recommendation
DEFAULT_SPECIALIST_POOLS: Dict[DomainCategory, List[str]] = {
    DomainCategory.CODE: [
        mc.WILDCARD_CODE_QWEN,
        mc.WILDCARD_CODE_MISTRAL,
    ],
    DomainCategory.REASONING: [
        mc.WILDCARD_REASONING_O1,
        mc.WILDCARD_REASONING_QWQ,
    ],
    DomainCategory.CREATIVE: [
        mc.WILDCARD_CREATIVE_OPUS,
        mc.WILDCARD_CREATIVE_COHERE,
    ],
    DomainCategory.MULTILINGUAL: [
        mc.OPENAI_HIGH,
        mc.WILDCARD_CREATIVE_COHERE,
    ],
    DomainCategory.GENERAL: [
        mc.WILDCARD_FALLBACK_MODEL,
    ],
}


@dataclass
class WildcardConfig:
    """Configuration for wildcard specialist pool.

    Per ADR-020, the wildcard seat selects from domain-specialized models
    to add diversity to the council.
    """

    specialist_pools: Dict[DomainCategory, List[str]] = field(
        default_factory=lambda: DEFAULT_SPECIALIST_POOLS.copy()
    )
    fallback_model: str = mc.WILDCARD_FALLBACK_MODEL
    max_selection_latency_ms: int = 200  # ADR-020: max 200ms selection latency
    diversity_constraints: List[str] = field(
        default_factory=lambda: ["family", "training", "architecture"]
    )


@dataclass
class TriageResult:
    """Result of query triage.

    Contains resolved models and optimized prompts for council execution.
    Per ADR-024, this is the output of Layer 2 (Query Triage).
    """

    resolved_models: List[str]
    optimized_prompts: Dict[str, str]
    fast_path: bool = False
    escalation_recommended: bool = False
    escalation_reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TriageRequest:
    """Input request for query triage.

    Contains the query and optional constraints for triage decisions.
    """

    query: str
    tier_contract: Optional[TierContract] = None
    domain_hint: Optional[DomainCategory] = None
