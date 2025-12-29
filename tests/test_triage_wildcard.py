"""Tests for wildcard selection (ADR-020 Tier 3).

TDD: Write these tests first, then implement wildcard.py.
"""

import pytest
from unittest.mock import patch


class TestClassifyQueryDomain:
    """Test classify_query_domain() heuristic."""

    def test_classify_code_query_python(self):
        """Should classify Python code queries as CODE."""
        from llm_council.triage.wildcard import classify_query_domain
        from llm_council.triage.types import DomainCategory

        result = classify_query_domain("Write a Python function to sort a list")

        assert result == DomainCategory.CODE

    def test_classify_code_query_debug(self):
        """Should classify debugging queries as CODE."""
        from llm_council.triage.wildcard import classify_query_domain
        from llm_council.triage.types import DomainCategory

        result = classify_query_domain("Debug this JavaScript error: undefined is not a function")

        assert result == DomainCategory.CODE

    def test_classify_code_query_api(self):
        """Should classify API/implementation queries as CODE."""
        from llm_council.triage.wildcard import classify_query_domain
        from llm_council.triage.types import DomainCategory

        result = classify_query_domain("Implement a REST API endpoint for user authentication")

        assert result == DomainCategory.CODE

    def test_classify_reasoning_query_math(self):
        """Should classify math queries as REASONING."""
        from llm_council.triage.wildcard import classify_query_domain
        from llm_council.triage.types import DomainCategory

        result = classify_query_domain("Solve this equation: 2x + 5 = 15")

        assert result == DomainCategory.REASONING

    def test_classify_reasoning_query_logic(self):
        """Should classify logic puzzles as REASONING."""
        from llm_council.triage.wildcard import classify_query_domain
        from llm_council.triage.types import DomainCategory

        result = classify_query_domain("If all A are B and all B are C, what can we conclude?")

        assert result == DomainCategory.REASONING

    def test_classify_reasoning_query_proof(self):
        """Should classify proof requests as REASONING."""
        from llm_council.triage.wildcard import classify_query_domain
        from llm_council.triage.types import DomainCategory

        result = classify_query_domain("Prove that the square root of 2 is irrational")

        assert result == DomainCategory.REASONING

    def test_classify_creative_query_story(self):
        """Should classify story writing as CREATIVE."""
        from llm_council.triage.wildcard import classify_query_domain
        from llm_council.triage.types import DomainCategory

        result = classify_query_domain("Write a short story about a dragon who learns to cook")

        assert result == DomainCategory.CREATIVE

    def test_classify_creative_query_poem(self):
        """Should classify poetry as CREATIVE."""
        from llm_council.triage.wildcard import classify_query_domain
        from llm_council.triage.types import DomainCategory

        result = classify_query_domain("Compose a haiku about the ocean")

        assert result == DomainCategory.CREATIVE

    def test_classify_multilingual_query(self):
        """Should classify translation as MULTILINGUAL."""
        from llm_council.triage.wildcard import classify_query_domain
        from llm_council.triage.types import DomainCategory

        result = classify_query_domain("Translate 'Hello, how are you?' to Japanese")

        assert result == DomainCategory.MULTILINGUAL

    def test_classify_multilingual_query_spanish(self):
        """Should classify Spanish language queries as MULTILINGUAL."""
        from llm_council.triage.wildcard import classify_query_domain
        from llm_council.triage.types import DomainCategory

        result = classify_query_domain("Explain quantum physics in French")

        assert result == DomainCategory.MULTILINGUAL

    def test_classify_general_query_default(self):
        """Should classify generic queries as GENERAL."""
        from llm_council.triage.wildcard import classify_query_domain
        from llm_council.triage.types import DomainCategory

        result = classify_query_domain("What is the capital of France?")

        assert result == DomainCategory.GENERAL

    def test_classify_respects_domain_hint(self):
        """Should respect explicit domain hint over heuristics."""
        from llm_council.triage.wildcard import classify_query_domain
        from llm_council.triage.types import DomainCategory

        # Even though this looks like CODE, hint overrides
        result = classify_query_domain(
            "Write a function",
            domain_hint=DomainCategory.CREATIVE,
        )

        assert result == DomainCategory.CREATIVE


class TestSelectWildcard:
    """Test select_wildcard() for specialist model selection."""

    def test_select_wildcard_returns_model_id(self):
        """select_wildcard should return a model identifier string."""
        from llm_council.triage.wildcard import select_wildcard
        from llm_council.triage.types import DomainCategory

        result = select_wildcard(DomainCategory.CODE)

        assert isinstance(result, str)
        assert "/" in result  # Model IDs have provider/model format

    def test_select_wildcard_code_domain(self):
        """Should select code specialist for CODE domain."""
        from llm_council.triage.wildcard import select_wildcard
        from llm_council.triage.types import DomainCategory, DEFAULT_SPECIALIST_POOLS

        result = select_wildcard(DomainCategory.CODE)

        # Should be from code specialist pool
        assert result in DEFAULT_SPECIALIST_POOLS[DomainCategory.CODE]

    def test_select_wildcard_reasoning_domain(self):
        """Should select reasoning specialist for REASONING domain."""
        from llm_council.triage.wildcard import select_wildcard
        from llm_council.triage.types import DomainCategory, DEFAULT_SPECIALIST_POOLS

        result = select_wildcard(DomainCategory.REASONING)

        assert result in DEFAULT_SPECIALIST_POOLS[DomainCategory.REASONING]

    def test_select_wildcard_creative_domain(self):
        """Should select creative specialist for CREATIVE domain."""
        from llm_council.triage.wildcard import select_wildcard
        from llm_council.triage.types import DomainCategory, DEFAULT_SPECIALIST_POOLS

        result = select_wildcard(DomainCategory.CREATIVE)

        assert result in DEFAULT_SPECIALIST_POOLS[DomainCategory.CREATIVE]

    def test_select_wildcard_respects_diversity_constraint(self):
        """Wildcard should differ from base council models."""
        from llm_council.triage.wildcard import select_wildcard
        from llm_council.triage.types import DomainCategory

        base_council = [
            "openai/gpt-4o",
            "anthropic/claude-3-5-sonnet-20241022",
            "google/gemini-1.5-pro",
        ]
        result = select_wildcard(DomainCategory.CODE, exclude_models=base_council)

        assert result not in base_council

    def test_select_wildcard_fallback_on_empty_pool(self):
        """Should fallback to general pool if specialist pool is empty."""
        from llm_council.triage.wildcard import select_wildcard
        from llm_council.triage.types import DomainCategory, WildcardConfig

        # Custom config with empty code pool
        config = WildcardConfig(
            specialist_pools={DomainCategory.CODE: []},
            fallback_model="meta-llama/llama-3.1-70b-instruct",
        )

        result = select_wildcard(DomainCategory.CODE, config=config)

        assert result == config.fallback_model

    def test_select_wildcard_fallback_when_all_excluded(self):
        """Should fallback when all specialists are in exclude list."""
        from llm_council.triage.wildcard import select_wildcard
        from llm_council.triage.types import DomainCategory, DEFAULT_SPECIALIST_POOLS

        # Exclude all code specialists
        exclude_all = DEFAULT_SPECIALIST_POOLS[DomainCategory.CODE].copy()
        result = select_wildcard(DomainCategory.CODE, exclude_models=exclude_all)

        # Should return fallback
        assert result == "meta-llama/llama-3.1-70b-instruct"

    def test_select_wildcard_with_tier_constraint(self):
        """Quick tier should still get a wildcard (from quick-appropriate pool)."""
        from llm_council.triage.wildcard import select_wildcard
        from llm_council.triage.types import DomainCategory
        from llm_council.tier_contract import create_tier_contract

        tier_contract = create_tier_contract("quick")
        result = select_wildcard(DomainCategory.CODE, tier_contract=tier_contract)

        # Should still return a model
        assert isinstance(result, str)


class TestWildcardConfiguration:
    """Test wildcard configuration options."""

    def test_custom_specialist_pools(self):
        """Should allow custom specialist pool configuration."""
        from llm_council.triage.wildcard import select_wildcard
        from llm_council.triage.types import DomainCategory, WildcardConfig

        custom_config = WildcardConfig(
            specialist_pools={
                DomainCategory.CODE: ["custom/code-model"],
            }
        )

        result = select_wildcard(DomainCategory.CODE, config=custom_config)

        assert result == "custom/code-model"

    def test_custom_fallback_model(self):
        """Should use custom fallback when specified."""
        from llm_council.triage.wildcard import select_wildcard
        from llm_council.triage.types import DomainCategory, WildcardConfig

        custom_config = WildcardConfig(
            specialist_pools={DomainCategory.CODE: []},
            fallback_model="custom/fallback",
        )

        result = select_wildcard(DomainCategory.CODE, config=custom_config)

        assert result == "custom/fallback"


class TestIntegrationWithTriage:
    """Test wildcard integration with run_triage."""

    def test_run_triage_includes_wildcard(self):
        """run_triage with wildcard=True should add specialist model."""
        from llm_council.triage import run_triage
        from llm_council.unified_config import get_config

        COUNCIL_MODELS = get_config().council.models
        result = run_triage("Write a Python sorting algorithm", include_wildcard=True)

        # Should have council models + 1 wildcard
        assert len(result.resolved_models) == len(COUNCIL_MODELS) + 1

    def test_run_triage_wildcard_metadata(self):
        """Wildcard selection should be recorded in metadata."""
        from llm_council.triage import run_triage

        result = run_triage("Write a Python sorting algorithm", include_wildcard=True)

        assert "wildcard" in result.metadata
        assert "domain" in result.metadata

    def test_run_triage_no_wildcard_by_default(self):
        """run_triage should not include wildcard by default (passthrough mode)."""
        from llm_council.triage import run_triage
        from llm_council.unified_config import get_config

        COUNCIL_MODELS = get_config().council.models
        result = run_triage("Write a Python sorting algorithm")

        # Passthrough mode should not add wildcard
        assert len(result.resolved_models) == len(COUNCIL_MODELS)
        assert result.metadata.get("wildcard") is None


class TestDomainKeywords:
    """Test domain classification keyword detection."""

    def test_code_keywords_comprehensive(self):
        """Verify comprehensive code keyword detection."""
        from llm_council.triage.wildcard import classify_query_domain
        from llm_council.triage.types import DomainCategory

        code_queries = [
            "Fix this bug in my code",
            "How do I refactor this class?",
            "Write a unit test for this function",
            "What does this regex do?",
            "Implement a binary search algorithm",
        ]

        for query in code_queries:
            assert classify_query_domain(query) == DomainCategory.CODE, f"Failed for: {query}"

    def test_reasoning_keywords_comprehensive(self):
        """Verify comprehensive reasoning keyword detection."""
        from llm_council.triage.wildcard import classify_query_domain
        from llm_council.triage.types import DomainCategory

        reasoning_queries = [
            "Analyze this argument",
            "Calculate the probability",
            "Why does this theorem hold?",
            "Derive the formula for compound interest",
            "Step by step, solve this puzzle",
        ]

        for query in reasoning_queries:
            assert classify_query_domain(query) == DomainCategory.REASONING, f"Failed for: {query}"

    def test_creative_keywords_comprehensive(self):
        """Verify comprehensive creative keyword detection."""
        from llm_council.triage.wildcard import classify_query_domain
        from llm_council.triage.types import DomainCategory

        creative_queries = [
            "Write a creative essay",
            "Compose a song about love",
            "Create a fictional character",
            "Imagine a world where...",
            "Draft a screenplay scene",
        ]

        for query in creative_queries:
            assert classify_query_domain(query) == DomainCategory.CREATIVE, f"Failed for: {query}"


class TestWildcardObservability:
    """Test L2_WILDCARD_SELECTED event emission (ADR-024 Issue #65)."""

    def test_select_wildcard_emits_event(self):
        """select_wildcard() should emit L2_WILDCARD_SELECTED event."""
        from llm_council.triage.wildcard import select_wildcard
        from llm_council.triage.types import DomainCategory
        from llm_council.layer_contracts import LayerEventType, get_layer_events, clear_layer_events

        clear_layer_events()

        result = select_wildcard(DomainCategory.CODE, exclude_models=["openai/gpt-4o"])

        assert result is not None

        # Check event was emitted
        events = get_layer_events()
        wildcard_events = [e for e in events if e.event_type == LayerEventType.L2_WILDCARD_SELECTED]
        assert len(wildcard_events) == 1

        event = wildcard_events[0]
        assert event.data["domain"] == "CODE"
        assert event.data["selected_model"] == result
        assert "openai/gpt-4o" in event.data["excluded_models"]

    def test_select_wildcard_event_includes_tier_info(self):
        """Event should include tier constraint info if provided."""
        from llm_council.triage.wildcard import select_wildcard
        from llm_council.triage.types import DomainCategory
        from llm_council.tier_contract import create_tier_contract
        from llm_council.layer_contracts import LayerEventType, get_layer_events, clear_layer_events

        clear_layer_events()

        tier_contract = create_tier_contract("quick")
        result = select_wildcard(DomainCategory.REASONING, tier_contract=tier_contract)

        events = get_layer_events()
        wildcard_events = [e for e in events if e.event_type == LayerEventType.L2_WILDCARD_SELECTED]
        assert len(wildcard_events) == 1

        event = wildcard_events[0]
        assert event.data["tier"] == "quick"

    def test_fallback_selection_emits_event_with_fallback_flag(self):
        """When fallback model is used, event should indicate this."""
        from llm_council.triage.wildcard import select_wildcard
        from llm_council.triage.types import DomainCategory, WildcardConfig
        from llm_council.layer_contracts import LayerEventType, get_layer_events, clear_layer_events

        clear_layer_events()

        # Create config with empty pools to force fallback
        config = WildcardConfig(
            specialist_pools={DomainCategory.CODE: []},  # Empty pool
            fallback_model="meta-llama/llama-3-70b-instruct",
        )

        result = select_wildcard(DomainCategory.CODE, config=config)

        assert result == "meta-llama/llama-3-70b-instruct"

        events = get_layer_events()
        wildcard_events = [e for e in events if e.event_type == LayerEventType.L2_WILDCARD_SELECTED]
        assert len(wildcard_events) == 1

        event = wildcard_events[0]
        assert event.data["fallback_used"] is True
