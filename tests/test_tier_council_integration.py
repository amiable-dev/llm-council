"""Tests for TierContract integration with council execution (ADR-022)."""

import pytest
from unittest.mock import patch, AsyncMock
import asyncio


class TestCouncilTierContractParameter:
    """Test that run_council_with_fallback accepts tier_contract parameter."""

    @pytest.mark.asyncio
    async def test_accepts_tier_contract_parameter(self):
        """run_council_with_fallback should accept optional tier_contract."""
        from llm_council.council import run_council_with_fallback
        from llm_council.tier_contract import create_tier_contract

        tier_contract = create_tier_contract("quick")

        with patch(
            "llm_council.council.run_full_council", new_callable=AsyncMock
        ) as mock_full_council:
            mock_full_council.return_value = ([], [], {"response": "ok"}, {"label_to_model": {}})

            result = await run_council_with_fallback("Test query", tier_contract=tier_contract)
            assert "response" in result
            assert mock_full_council.called


class TestTierContractUsesAllowedModels:
    """Test that tier_contract.allowed_models is used when provided."""

    @pytest.mark.asyncio
    async def test_tier_contract_models_used_over_default(self):
        """When tier_contract provided, verify delegation via orchestrator."""
        from llm_council.council import run_council_with_fallback
        from llm_council.tier_contract import create_tier_contract

        tier_contract = create_tier_contract("quick")

        with patch(
            "llm_council.council.run_full_council", new_callable=AsyncMock
        ) as mock_full_council:
            mock_full_council.return_value = ([], [], {"response": "ok"}, {"label_to_model": {}})

            await run_council_with_fallback("Test query", tier_contract=tier_contract)

            # Verify orchestrator was called with tier_contract
            call_kwargs = mock_full_council.call_args[1]
            assert call_kwargs["tier_contract"] == tier_contract

    @pytest.mark.asyncio
    async def test_explicit_models_override_tier_contract(self):
        """Explicit models parameter should override tier_contract.allowed_models."""
        from llm_council.council import run_council_with_fallback
        from llm_council.tier_contract import create_tier_contract

        tier_contract = create_tier_contract("quick")
        explicit_models = ["test/model-a", "test/model-b"]

        with patch(
            "llm_council.council.run_full_council", new_callable=AsyncMock
        ) as mock_full_council:
            mock_full_council.return_value = ([], [], {"response": "ok"}, {"label_to_model": {}})

            await run_council_with_fallback(
                "Test query", models=explicit_models, tier_contract=tier_contract
            )

            # Verify models parameter was passed
            assert mock_full_council.call_args[1]["models"] == explicit_models
