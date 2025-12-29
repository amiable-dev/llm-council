"""Wildcard selection for ADR-020 Tier 3.

Provides domain classification and specialist model selection
to add diverse expertise to the council.
"""

import re
from typing import List, Optional

from llm_council.tier_contract import TierContract
from llm_council.layer_contracts import LayerEventType, emit_layer_event

from .types import DomainCategory, WildcardConfig, DEFAULT_SPECIALIST_POOLS

# Domain classification keywords
# Note: Using word boundaries where needed to avoid substring false positives
CODE_KEYWORDS = {
    "python",
    "javascript",
    "typescript",
    "java ",
    "code",
    "function",
    "class",
    "algorithm",
    "debug",
    "bug",
    "fix",
    "implement",
    " api ",
    "api ",
    "endpoint",
    "unit test",
    "refactor",
    "regex",
    "compile",
    "runtime",
    "error",
    "exception",
    "variable",
    "method",
    "interface",
    "sql",
    "query",
    "database",
    "git",
}

REASONING_KEYWORDS = {
    "prove",
    "proof",
    "theorem",
    "equation",
    "solve",
    "calculate",
    "probability",
    "derive",
    "analyze",
    "analysis",
    "logic",
    "logical",
    "conclude",
    "inference",
    "hypothesis",
    "deduce",
    "reason",
    "reasoning",
    "step by step",
    "why does",
    "mathematical",
    "math",
    "formula",
    "calculate",
    "puzzle",
}

CREATIVE_KEYWORDS = {
    "write a story",
    "write a poem",
    "compose",
    "haiku",
    "creative",
    "fiction",
    "imagine",
    "fantasy",
    "screenplay",
    "script",
    "novel",
    "character",
    "plot",
    "narrative",
    "song",
    "lyrics",
    "essay",
    "poem",
    "poetry",
    "draft",
    "short story",
    "story about",
    "a story",
}

MULTILINGUAL_KEYWORDS = {
    "translate",
    "translation",
    "in spanish",
    "in french",
    "in german",
    "in japanese",
    "in chinese",
    "in korean",
    "in arabic",
    "in portuguese",
    "in italian",
    "in russian",
    "en español",
    "en français",
    "auf deutsch",
    "multilingual",
    "language",
}


def classify_query_domain(
    query: str,
    domain_hint: Optional[DomainCategory] = None,
) -> DomainCategory:
    """Classify query into domain category for specialist selection.

    Uses keyword heuristics to determine the primary domain of a query.
    Can be overridden with explicit domain_hint.

    Args:
        query: The user query to classify
        domain_hint: Optional explicit domain override

    Returns:
        DomainCategory for the query
    """
    # Explicit hint takes precedence
    if domain_hint is not None:
        return domain_hint

    query_lower = query.lower()

    # Check each domain in priority order
    # Code first (most specific signals)
    if _matches_keywords(query_lower, CODE_KEYWORDS):
        return DomainCategory.CODE

    # Multilingual (language-specific)
    if _matches_keywords(query_lower, MULTILINGUAL_KEYWORDS):
        return DomainCategory.MULTILINGUAL

    # Reasoning (math/logic)
    if _matches_keywords(query_lower, REASONING_KEYWORDS):
        return DomainCategory.REASONING

    # Creative (writing)
    if _matches_keywords(query_lower, CREATIVE_KEYWORDS):
        return DomainCategory.CREATIVE

    # Default to general
    return DomainCategory.GENERAL


def _matches_keywords(text: str, keywords: set) -> bool:
    """Check if text contains any of the keywords."""
    for keyword in keywords:
        if keyword in text:
            return True
    return False


def select_wildcard(
    domain: DomainCategory,
    exclude_models: Optional[List[str]] = None,
    config: Optional[WildcardConfig] = None,
    tier_contract: Optional[TierContract] = None,
) -> str:
    """Select a wildcard specialist model for the domain.

    Selects from the specialist pool for the given domain,
    excluding models already in the base council.

    Args:
        domain: The classified domain category
        exclude_models: Models to exclude (e.g., base council)
        config: Optional custom wildcard configuration
        tier_contract: Optional tier contract (for future tier-specific pools)

    Returns:
        Model identifier string for the selected wildcard
    """
    if config is None:
        config = WildcardConfig()

    exclude_set = set(exclude_models) if exclude_models else set()
    exclude_list = list(exclude_set)

    # Get specialist pool for domain
    pool = config.specialist_pools.get(domain, [])

    # Filter out excluded models
    available = [m for m in pool if m not in exclude_set]

    # If pool is empty or all excluded, use fallback
    fallback_used = not available
    if fallback_used:
        selected_model = config.fallback_model
    else:
        # Select first available (could be randomized in future)
        selected_model = available[0]

    # ADR-024: Emit L2_WILDCARD_SELECTED event
    event_data = {
        "domain": domain.name,
        "selected_model": selected_model,
        "excluded_models": exclude_list,
        "fallback_used": fallback_used,
    }
    if tier_contract is not None:
        event_data["tier"] = tier_contract.tier

    emit_layer_event(
        LayerEventType.L2_WILDCARD_SELECTED,
        event_data,
        layer_from="L2",
        layer_to="L2",
    )

    return selected_model
