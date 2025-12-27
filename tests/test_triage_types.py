"""Tests for triage package types (ADR-020 Layer 2).

TDD: Write these tests first, then implement the triage package.
"""

import pytest
from dataclasses import FrozenInstanceError


class TestTriageResult:
    """Test TriageResult dataclass."""

    def test_triage_result_has_required_fields(self):
        """TriageResult must have resolved_models and optimized_prompts."""
        from llm_council.triage.types import TriageResult

        result = TriageResult(
            resolved_models=["openai/gpt-4o", "anthropic/claude-3-5-sonnet-20241022"],
            optimized_prompts={"openai/gpt-4o": "Test prompt"},
        )

        assert result.resolved_models == ["openai/gpt-4o", "anthropic/claude-3-5-sonnet-20241022"]
        assert result.optimized_prompts["openai/gpt-4o"] == "Test prompt"

    def test_triage_result_default_fast_path_false(self):
        """TriageResult.fast_path should default to False."""
        from llm_council.triage.types import TriageResult

        result = TriageResult(
            resolved_models=["model-a"],
            optimized_prompts={},
        )

        assert result.fast_path is False

    def test_triage_result_default_escalation_false(self):
        """TriageResult.escalation_recommended should default to False."""
        from llm_council.triage.types import TriageResult

        result = TriageResult(
            resolved_models=["model-a"],
            optimized_prompts={},
        )

        assert result.escalation_recommended is False
        assert result.escalation_reason is None

    def test_triage_result_with_escalation(self):
        """TriageResult should support escalation with reason."""
        from llm_council.triage.types import TriageResult

        result = TriageResult(
            resolved_models=["model-a"],
            optimized_prompts={},
            escalation_recommended=True,
            escalation_reason="Query complexity exceeds tier capacity",
        )

        assert result.escalation_recommended is True
        assert result.escalation_reason == "Query complexity exceeds tier capacity"

    def test_triage_result_metadata_optional(self):
        """TriageResult should have optional metadata dict."""
        from llm_council.triage.types import TriageResult

        result = TriageResult(
            resolved_models=["model-a"],
            optimized_prompts={},
        )

        assert result.metadata == {}

    def test_triage_result_with_metadata(self):
        """TriageResult should store metadata."""
        from llm_council.triage.types import TriageResult

        result = TriageResult(
            resolved_models=["model-a"],
            optimized_prompts={},
            metadata={"domain": "code", "confidence": 0.95},
        )

        assert result.metadata["domain"] == "code"
        assert result.metadata["confidence"] == 0.95


class TestDomainCategory:
    """Test DomainCategory enum."""

    def test_domain_category_has_required_values(self):
        """DomainCategory should have CODE, REASONING, CREATIVE, MULTILINGUAL, GENERAL."""
        from llm_council.triage.types import DomainCategory

        assert DomainCategory.CODE.value == "code"
        assert DomainCategory.REASONING.value == "reasoning"
        assert DomainCategory.CREATIVE.value == "creative"
        assert DomainCategory.MULTILINGUAL.value == "multilingual"
        assert DomainCategory.GENERAL.value == "general"

    def test_domain_category_from_string(self):
        """DomainCategory should be constructible from string."""
        from llm_council.triage.types import DomainCategory

        assert DomainCategory("code") == DomainCategory.CODE
        assert DomainCategory("reasoning") == DomainCategory.REASONING


class TestWildcardConfig:
    """Test WildcardConfig dataclass."""

    def test_wildcard_config_has_specialist_pools(self):
        """WildcardConfig must have specialist_pools dict."""
        from llm_council.triage.types import WildcardConfig, DomainCategory

        config = WildcardConfig(
            specialist_pools={
                DomainCategory.CODE: ["deepseek/deepseek-chat", "codestral/codestral-latest"],
                DomainCategory.REASONING: ["openai/o1-preview", "deepseek/deepseek-r1"],
            }
        )

        assert DomainCategory.CODE in config.specialist_pools
        assert len(config.specialist_pools[DomainCategory.CODE]) == 2

    def test_wildcard_config_default_fallback_model(self):
        """WildcardConfig should have a default fallback model."""
        from llm_council.triage.types import WildcardConfig

        config = WildcardConfig(specialist_pools={})

        assert config.fallback_model is not None
        assert isinstance(config.fallback_model, str)

    def test_wildcard_config_custom_fallback(self):
        """WildcardConfig should allow custom fallback model."""
        from llm_council.triage.types import WildcardConfig

        config = WildcardConfig(
            specialist_pools={},
            fallback_model="meta-llama/llama-3.1-70b-instruct",
        )

        assert config.fallback_model == "meta-llama/llama-3.1-70b-instruct"

    def test_wildcard_config_selection_timeout(self):
        """WildcardConfig should have max selection timeout."""
        from llm_council.triage.types import WildcardConfig

        config = WildcardConfig(specialist_pools={})

        # ADR-020 specifies 200ms max selection latency
        assert config.max_selection_latency_ms == 200

    def test_wildcard_config_diversity_constraints(self):
        """WildcardConfig should have diversity constraint flags."""
        from llm_council.triage.types import WildcardConfig

        config = WildcardConfig(
            specialist_pools={},
            diversity_constraints=["family", "training", "architecture"],
        )

        assert "family" in config.diversity_constraints
        assert "architecture" in config.diversity_constraints


class TestDefaultWildcardPools:
    """Test default wildcard specialist pools from ADR-020."""

    def test_default_pools_exist(self):
        """Default specialist pools should be defined."""
        from llm_council.triage.types import DEFAULT_SPECIALIST_POOLS, DomainCategory

        assert DomainCategory.CODE in DEFAULT_SPECIALIST_POOLS
        assert DomainCategory.REASONING in DEFAULT_SPECIALIST_POOLS
        assert DomainCategory.CREATIVE in DEFAULT_SPECIALIST_POOLS
        assert DomainCategory.MULTILINGUAL in DEFAULT_SPECIALIST_POOLS

    def test_default_code_pool_has_specialists(self):
        """Code pool should have code-specialized models."""
        from llm_council.triage.types import DEFAULT_SPECIALIST_POOLS, DomainCategory

        code_pool = DEFAULT_SPECIALIST_POOLS[DomainCategory.CODE]
        assert len(code_pool) >= 1
        # Should include deepseek for code per ADR-020
        assert any("deepseek" in model.lower() for model in code_pool)

    def test_default_reasoning_pool_has_specialists(self):
        """Reasoning pool should have reasoning-specialized models."""
        from llm_council.triage.types import DEFAULT_SPECIALIST_POOLS, DomainCategory

        reasoning_pool = DEFAULT_SPECIALIST_POOLS[DomainCategory.REASONING]
        assert len(reasoning_pool) >= 1
        # Should include o1-preview or deepseek-r1 per ADR-020
        assert any("o1" in model.lower() or "r1" in model.lower() for model in reasoning_pool)


class TestTriageRequest:
    """Test TriageRequest dataclass for input to triage."""

    def test_triage_request_has_query(self):
        """TriageRequest must have query string."""
        from llm_council.triage.types import TriageRequest

        request = TriageRequest(query="What is the capital of France?")

        assert request.query == "What is the capital of France?"

    def test_triage_request_optional_tier_contract(self):
        """TriageRequest should optionally accept tier_contract."""
        from llm_council.triage.types import TriageRequest
        from llm_council.tier_contract import create_tier_contract

        tier_contract = create_tier_contract("balanced")
        request = TriageRequest(
            query="Test query",
            tier_contract=tier_contract,
        )

        assert request.tier_contract is not None
        assert request.tier_contract.tier == "balanced"

    def test_triage_request_default_tier_contract_none(self):
        """TriageRequest.tier_contract should default to None."""
        from llm_council.triage.types import TriageRequest

        request = TriageRequest(query="Test query")

        assert request.tier_contract is None

    def test_triage_request_optional_domain_hint(self):
        """TriageRequest should optionally accept domain_hint."""
        from llm_council.triage.types import TriageRequest, DomainCategory

        request = TriageRequest(
            query="Write a Python function",
            domain_hint=DomainCategory.CODE,
        )

        assert request.domain_hint == DomainCategory.CODE


class TestRunTriageStub:
    """Test run_triage() stub implementation."""

    def test_run_triage_exists(self):
        """run_triage function should exist."""
        from llm_council.triage import run_triage

        assert callable(run_triage)

    def test_run_triage_returns_triage_result(self):
        """run_triage should return TriageResult."""
        from llm_council.triage import run_triage
        from llm_council.triage.types import TriageResult

        result = run_triage("Test query")

        assert isinstance(result, TriageResult)

    def test_run_triage_passthrough_mode(self):
        """Stub run_triage should pass through query unchanged."""
        from llm_council.triage import run_triage
        from llm_council.unified_config import get_config

        COUNCIL_MODELS = get_config().council.models
        result = run_triage("What is 2 + 2?")

        # Passthrough should use default council models
        assert result.resolved_models == list(COUNCIL_MODELS)
        # Should have passthrough prompt for each model
        assert len(result.optimized_prompts) == len(COUNCIL_MODELS)

    def test_run_triage_preserves_original_query(self):
        """Stub run_triage should preserve original query in prompts."""
        from llm_council.triage import run_triage

        original_query = "Explain quantum computing"
        result = run_triage(original_query)

        # Each optimized prompt should contain original query
        for model, prompt in result.optimized_prompts.items():
            assert original_query in prompt

    def test_run_triage_with_tier_contract(self):
        """run_triage should use tier_contract's allowed_models when provided."""
        from llm_council.triage import run_triage
        from llm_council.tier_contract import create_tier_contract

        tier_contract = create_tier_contract("quick")
        result = run_triage("Test query", tier_contract=tier_contract)

        # Should use tier's allowed models
        assert result.resolved_models == tier_contract.allowed_models

    def test_run_triage_metadata_includes_stub_indicator(self):
        """Stub run_triage should indicate it's a passthrough in metadata."""
        from llm_council.triage import run_triage

        result = run_triage("Test query")

        assert "passthrough" in result.metadata or result.metadata.get("mode") == "passthrough"


class TestTriagePackageInit:
    """Test triage package __init__.py exports."""

    def test_triage_package_exports_types(self):
        """Triage package should export type classes."""
        from llm_council.triage import (
            TriageResult,
            TriageRequest,
            WildcardConfig,
            DomainCategory,
        )

        assert TriageResult is not None
        assert TriageRequest is not None
        assert WildcardConfig is not None
        assert DomainCategory is not None

    def test_triage_package_exports_run_triage(self):
        """Triage package should export run_triage function."""
        from llm_council.triage import run_triage

        assert callable(run_triage)

    def test_triage_package_exports_default_pools(self):
        """Triage package should export DEFAULT_SPECIALIST_POOLS."""
        from llm_council.triage import DEFAULT_SPECIALIST_POOLS

        assert isinstance(DEFAULT_SPECIALIST_POOLS, dict)
