"""TDD tests for ADR-026 Phase 2: Reasoning Parameter Injection.

Tests for gateway-level injection of reasoning parameters into OpenRouter API calls.
Written BEFORE implementation per TDD workflow.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import os


class TestReasoningParamsDataclass:
    """Test ReasoningParams dataclass definition."""

    def test_reasoning_params_dataclass_exists(self):
        """ReasoningParams should be a dataclass."""
        from llm_council.gateway.types import ReasoningParams
        from dataclasses import is_dataclass

        params = ReasoningParams(
            effort="high",
            max_tokens=32000,
        )
        assert is_dataclass(params)

    def test_reasoning_params_has_required_fields(self):
        """ReasoningParams should have effort, max_tokens, exclude."""
        from llm_council.gateway.types import ReasoningParams

        params = ReasoningParams(
            effort="medium",
            max_tokens=16000,
        )
        assert params.effort == "medium"
        assert params.max_tokens == 16000
        assert params.exclude is False  # Default

    def test_reasoning_params_exclude_default_false(self):
        """ReasoningParams.exclude should default to False."""
        from llm_council.gateway.types import ReasoningParams

        params = ReasoningParams(effort="low", max_tokens=6400)
        assert params.exclude is False

    def test_reasoning_params_can_set_exclude(self):
        """ReasoningParams.exclude can be set to True."""
        from llm_council.gateway.types import ReasoningParams

        params = ReasoningParams(effort="high", max_tokens=32000, exclude=True)
        assert params.exclude is True


class TestReasoningParamsFromConfig:
    """Test creating ReasoningParams from ReasoningConfig."""

    def test_from_reasoning_config(self):
        """ReasoningParams.from_config() should create params from ReasoningConfig."""
        from llm_council.gateway.types import ReasoningParams
        from llm_council.reasoning import ReasoningConfig, ReasoningEffort

        config = ReasoningConfig(
            effort=ReasoningEffort.HIGH,
            budget_tokens=25600,
        )

        params = ReasoningParams.from_config(config)
        assert params.effort == "high"
        assert params.max_tokens == 25600
        assert params.exclude is False

    def test_from_reasoning_config_disabled(self):
        """from_config() should return None if config.enabled is False."""
        from llm_council.gateway.types import ReasoningParams
        from llm_council.reasoning import ReasoningConfig, ReasoningEffort

        config = ReasoningConfig(
            effort=ReasoningEffort.HIGH,
            budget_tokens=25600,
            enabled=False,
        )

        params = ReasoningParams.from_config(config)
        assert params is None


class TestGatewayReasoningInjection:
    """Test reasoning parameter injection in gateway layer."""

    def test_gateway_request_accepts_reasoning_params(self):
        """GatewayRequest should have optional reasoning_params field."""
        from llm_council.gateway.types import GatewayRequest, ReasoningParams

        params = ReasoningParams(effort="high", max_tokens=32000)
        request = GatewayRequest(
            model="openai/o1",
            messages=[{"role": "user", "content": "test"}],
            reasoning_params=params,
        )
        assert request.reasoning_params is not None
        assert request.reasoning_params.effort == "high"

    def test_gateway_request_reasoning_params_default_none(self):
        """GatewayRequest.reasoning_params should default to None."""
        from llm_council.gateway.types import GatewayRequest

        request = GatewayRequest(
            model="openai/gpt-4o",
            messages=[{"role": "user", "content": "test"}],
        )
        assert request.reasoning_params is None


class TestOpenRouterPayloadInjection:
    """Test reasoning injection into OpenRouter API payload."""

    @pytest.mark.asyncio
    async def test_injects_reasoning_for_o1_model(self):
        """Should inject reasoning params for openai/o1 model."""
        from llm_council.gateway.types import ReasoningParams
        from llm_council.gateway.openrouter import build_openrouter_payload

        params = ReasoningParams(effort="high", max_tokens=32000)
        payload = build_openrouter_payload(
            model="openai/o1",
            messages=[{"role": "user", "content": "test"}],
            reasoning_params=params,
        )

        assert "reasoning" in payload
        assert payload["reasoning"]["effort"] == "high"
        assert payload["reasoning"]["max_tokens"] == 32000

    @pytest.mark.asyncio
    async def test_injects_reasoning_for_o3_mini(self):
        """Should inject reasoning params for openai/o3-mini model."""
        from llm_council.gateway.types import ReasoningParams
        from llm_council.gateway.openrouter import build_openrouter_payload

        params = ReasoningParams(effort="medium", max_tokens=16000)
        payload = build_openrouter_payload(
            model="openai/o3-mini",
            messages=[{"role": "user", "content": "test"}],
            reasoning_params=params,
        )

        assert "reasoning" in payload
        assert payload["reasoning"]["effort"] == "medium"

    @pytest.mark.asyncio
    async def test_injects_reasoning_for_deepseek_r1(self):
        """Should inject reasoning params for deepseek/deepseek-r1 model."""
        from llm_council.gateway.types import ReasoningParams
        from llm_council.gateway.openrouter import build_openrouter_payload

        params = ReasoningParams(effort="high", max_tokens=25600)
        payload = build_openrouter_payload(
            model="deepseek/deepseek-r1",
            messages=[{"role": "user", "content": "test"}],
            reasoning_params=params,
        )

        assert "reasoning" in payload
        assert payload["reasoning"]["effort"] == "high"

    @pytest.mark.asyncio
    async def test_skips_injection_for_gpt4o(self):
        """Should NOT inject reasoning for non-reasoning models like gpt-4o."""
        from llm_council.gateway.types import ReasoningParams
        from llm_council.gateway.openrouter import build_openrouter_payload

        params = ReasoningParams(effort="high", max_tokens=32000)
        payload = build_openrouter_payload(
            model="openai/gpt-4o",
            messages=[{"role": "user", "content": "test"}],
            reasoning_params=params,
        )

        # Should not have reasoning block for non-reasoning model
        assert "reasoning" not in payload

    @pytest.mark.asyncio
    async def test_skips_injection_for_claude(self):
        """Should NOT inject reasoning for Anthropic Claude models."""
        from llm_council.gateway.types import ReasoningParams
        from llm_council.gateway.openrouter import build_openrouter_payload

        params = ReasoningParams(effort="high", max_tokens=32000)
        payload = build_openrouter_payload(
            model="anthropic/claude-opus-4.5",
            messages=[{"role": "user", "content": "test"}],
            reasoning_params=params,
        )

        # Should not have reasoning block for non-reasoning model
        assert "reasoning" not in payload

    @pytest.mark.asyncio
    async def test_skips_injection_when_params_none(self):
        """Should not inject reasoning when params is None."""
        from llm_council.gateway.openrouter import build_openrouter_payload

        payload = build_openrouter_payload(
            model="openai/o1",
            messages=[{"role": "user", "content": "test"}],
            reasoning_params=None,
        )

        assert "reasoning" not in payload


class TestPayloadFormat:
    """Test reasoning payload format matches OpenRouter API spec."""

    def test_payload_includes_reasoning_block(self):
        """Payload reasoning block should have correct structure."""
        from llm_council.gateway.types import ReasoningParams
        from llm_council.gateway.openrouter import build_openrouter_payload

        params = ReasoningParams(effort="high", max_tokens=32000, exclude=True)
        payload = build_openrouter_payload(
            model="openai/o1",
            messages=[{"role": "user", "content": "test"}],
            reasoning_params=params,
        )

        reasoning = payload["reasoning"]
        assert "effort" in reasoning
        assert "max_tokens" in reasoning
        assert "exclude" in reasoning

    def test_payload_reasoning_effort_matches_param(self):
        """Payload reasoning.effort should match ReasoningParams.effort."""
        from llm_council.gateway.types import ReasoningParams
        from llm_council.gateway.openrouter import build_openrouter_payload

        for effort in ["minimal", "low", "medium", "high", "xhigh"]:
            params = ReasoningParams(effort=effort, max_tokens=10000)
            payload = build_openrouter_payload(
                model="openai/o1",
                messages=[{"role": "user", "content": "test"}],
                reasoning_params=params,
            )
            assert payload["reasoning"]["effort"] == effort

    def test_payload_reasoning_max_tokens_matches_param(self):
        """Payload reasoning.max_tokens should match ReasoningParams.max_tokens."""
        from llm_council.gateway.types import ReasoningParams
        from llm_council.gateway.openrouter import build_openrouter_payload

        params = ReasoningParams(effort="high", max_tokens=25600)
        payload = build_openrouter_payload(
            model="openai/o1",
            messages=[{"role": "user", "content": "test"}],
            reasoning_params=params,
        )
        assert payload["reasoning"]["max_tokens"] == 25600


class TestDirectOpenRouterPath:
    """Test reasoning support in direct openrouter.py module."""

    def test_query_model_accepts_reasoning_params(self):
        """query_model() should accept optional reasoning_params parameter."""
        from llm_council.openrouter import query_model
        import inspect

        sig = inspect.signature(query_model)
        param_names = list(sig.parameters.keys())
        assert "reasoning_params" in param_names

    def test_query_models_parallel_accepts_reasoning_params(self):
        """query_models_parallel() should accept reasoning_params parameter."""
        from llm_council.openrouter import query_models_parallel
        import inspect

        sig = inspect.signature(query_models_parallel)
        param_names = list(sig.parameters.keys())
        assert "reasoning_params" in param_names
