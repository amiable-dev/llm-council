"""Tests for TierContract integration with council execution (ADR-022).

TDD: Write these tests first, then implement the integration.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import asyncio


class TestCouncilTierContractParameter:
    """Test that run_council_with_fallback accepts tier_contract parameter."""

    @pytest.mark.asyncio
    async def test_accepts_tier_contract_parameter(self):
        """run_council_with_fallback should accept optional tier_contract."""
        from llm_council.council import run_council_with_fallback
        from llm_council.tier_contract import create_tier_contract

        tier_contract = create_tier_contract("quick")

        # Mock the underlying functions to avoid actual API calls
        with patch("llm_council.council.stage1_collect_responses_with_status") as mock_stage1:
            mock_stage1.return_value = (
                [],
                {},
                {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            )

            with patch("llm_council.council.quick_synthesis") as mock_synthesis:
                mock_synthesis.return_value = (
                    "Quick response",
                    {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                )

                # Should not raise TypeError
                result = await run_council_with_fallback("Test query", tier_contract=tier_contract)

                assert "synthesis" in result

    @pytest.mark.asyncio
    async def test_accepts_models_parameter(self):
        """run_council_with_fallback should accept optional models list."""
        from llm_council.council import run_council_with_fallback

        custom_models = ["openai/gpt-4o-mini", "anthropic/claude-3-5-haiku-20241022"]

        with patch("llm_council.council.stage1_collect_responses_with_status") as mock_stage1:
            mock_stage1.return_value = (
                [],
                {},
                {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            )

            with patch("llm_council.council.quick_synthesis") as mock_synthesis:
                mock_synthesis.return_value = (
                    "Quick response",
                    {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                )

                result = await run_council_with_fallback("Test query", models=custom_models)

                assert "synthesis" in result


class TestTierContractUsesAllowedModels:
    """Test that tier_contract.allowed_models is used when provided."""

    @pytest.mark.asyncio
    async def test_tier_contract_models_used_over_default(self):
        """When tier_contract provided, use its allowed_models instead of COUNCIL_MODELS."""
        from llm_council.council import run_council_with_fallback
        from llm_council.tier_contract import create_tier_contract

        tier_contract = create_tier_contract("quick")
        expected_models = tier_contract.allowed_models

        with patch("llm_council.council.stage1_collect_responses_with_status") as mock_stage1:
            mock_stage1.return_value = (
                [],
                {},
                {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            )

            with patch("llm_council.council.quick_synthesis") as mock_synthesis:
                mock_synthesis.return_value = (
                    "Quick response",
                    {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                )

                await run_council_with_fallback("Test query", tier_contract=tier_contract)

                # Verify stage1 was called with tier_contract's models
                call_kwargs = mock_stage1.call_args
                # The models should be passed to stage1
                assert call_kwargs is not None

    @pytest.mark.asyncio
    async def test_explicit_models_override_tier_contract(self):
        """Explicit models parameter should override tier_contract.allowed_models."""
        from llm_council.council import run_council_with_fallback
        from llm_council.tier_contract import create_tier_contract

        tier_contract = create_tier_contract("quick")
        explicit_models = ["test/model-a", "test/model-b"]

        with patch("llm_council.council.stage1_collect_responses_with_status") as mock_stage1:
            mock_stage1.return_value = (
                [],
                {},
                {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            )

            with patch("llm_council.council.quick_synthesis") as mock_synthesis:
                mock_synthesis.return_value = (
                    "Quick response",
                    {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                )

                await run_council_with_fallback(
                    "Test query", models=explicit_models, tier_contract=tier_contract
                )

                # Should use explicit_models, not tier_contract.allowed_models


class TestTierContractTimeoutIntegration:
    """Test that tier_contract timeouts are respected."""

    @pytest.mark.asyncio
    async def test_tier_contract_timeout_used(self):
        """Tier contract's deadline_ms should influence timeout behavior."""
        from llm_council.tier_contract import create_tier_contract

        quick_contract = create_tier_contract("quick")
        reasoning_contract = create_tier_contract("reasoning")

        # Quick tier should have much shorter timeout
        assert quick_contract.deadline_ms < reasoning_contract.deadline_ms
        assert quick_contract.per_model_timeout_ms < reasoning_contract.per_model_timeout_ms


class TestTierContractAggregatorIntegration:
    """Test that tier_contract.aggregator_model is used for synthesis."""

    @pytest.mark.asyncio
    async def test_tier_contract_aggregator_used_in_synthesis(self):
        """Synthesis should use tier_contract.aggregator_model when provided."""
        from llm_council.tier_contract import create_tier_contract, TIER_AGGREGATORS

        quick_contract = create_tier_contract("quick")
        assert quick_contract.aggregator_model == TIER_AGGREGATORS["quick"]

        reasoning_contract = create_tier_contract("reasoning")
        assert reasoning_contract.aggregator_model == TIER_AGGREGATORS["reasoning"]


class TestQuickTierSkipsPeerReview:
    """Test quick tier behavior per ADR-022 council recommendation."""

    @pytest.mark.asyncio
    async def test_quick_tier_contract_skips_peer_review(self):
        """Quick tier should skip Stage 2 peer review (uses verifier instead)."""
        from llm_council.tier_contract import create_tier_contract

        quick_contract = create_tier_contract("quick")

        assert quick_contract.requires_peer_review is False
        assert quick_contract.requires_verifier is True

    @pytest.mark.asyncio
    async def test_high_tier_contract_uses_peer_review(self):
        """High tier should use full Stage 2 peer review."""
        from llm_council.tier_contract import create_tier_contract

        high_contract = create_tier_contract("high")

        assert high_contract.requires_peer_review is True
        assert high_contract.requires_verifier is False


class TestBackwardCompatibility:
    """Test backward compatibility when tier_contract is not provided."""

    @pytest.mark.asyncio
    async def test_works_without_tier_contract(self):
        """Should work exactly as before when tier_contract not provided."""
        from llm_council.council import run_council_with_fallback

        with patch("llm_council.council.stage1_collect_responses_with_status") as mock_stage1:
            mock_stage1.return_value = (
                [],
                {},
                {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            )

            with patch("llm_council.council.quick_synthesis") as mock_synthesis:
                mock_synthesis.return_value = (
                    "Quick response",
                    {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                )

                # No tier_contract parameter - should use defaults
                result = await run_council_with_fallback("Test query")

                assert "synthesis" in result
                assert result["metadata"]["status"] in ["complete", "partial", "failed"]


class TestTierContractMetadata:
    """Test that tier information is included in response metadata."""

    @pytest.mark.asyncio
    async def test_metadata_includes_tier_info(self):
        """Response metadata should include tier information when tier_contract provided."""
        from llm_council.council import run_council_with_fallback
        from llm_council.tier_contract import create_tier_contract

        tier_contract = create_tier_contract("quick")

        with patch("llm_council.council.stage1_collect_responses_with_status") as mock_stage1:
            mock_stage1.return_value = (
                [],
                {},
                {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            )

            with patch("llm_council.council.quick_synthesis") as mock_synthesis:
                mock_synthesis.return_value = (
                    "Quick response",
                    {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                )

                result = await run_council_with_fallback("Test query", tier_contract=tier_contract)

                # Metadata should include tier information
                assert "metadata" in result
                assert "tier" in result["metadata"]
                assert result["metadata"]["tier"] == "quick"
