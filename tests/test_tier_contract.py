"""Tests for TierContract dataclass (ADR-022).

TDD: Write these tests first, then implement the TierContract.
"""

import pytest
from typing import Dict, List


class TestTierContractStructure:
    """Test TierContract dataclass fields."""

    def test_tier_contract_has_required_fields(self):
        """TierContract must have all ADR-022 council-recommended fields."""
        from llm_council.tier_contract import TierContract

        contract = TierContract(
            tier="high",
            deadline_ms=180000,
            per_model_timeout_ms=90000,
            token_budget=4096,
            max_attempts=3,
            requires_peer_review=True,
            requires_verifier=False,
            allowed_models=["openai/gpt-4o", "anthropic/claude-opus-4-5-20250514"],
            aggregator_model="openai/gpt-4o",
            override_policy={"can_escalate": True, "can_deescalate": False},
        )

        assert contract.tier == "high"
        assert contract.deadline_ms == 180000
        assert contract.token_budget == 4096
        assert contract.max_attempts == 3
        assert contract.requires_peer_review is True
        assert contract.requires_verifier is False
        assert len(contract.allowed_models) == 2
        assert contract.aggregator_model == "openai/gpt-4o"
        assert contract.override_policy["can_escalate"] is True

    def test_tier_contract_is_immutable(self):
        """TierContract should be a frozen dataclass for safety."""
        from llm_council.tier_contract import TierContract

        contract = TierContract(
            tier="quick",
            deadline_ms=30000,
            per_model_timeout_ms=20000,
            token_budget=2048,
            max_attempts=1,
            requires_peer_review=False,
            requires_verifier=False,
            allowed_models=["openai/gpt-4o-mini"],
            aggregator_model="openai/gpt-4o-mini",
            override_policy={"can_escalate": True, "can_deescalate": False},
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            contract.tier = "high"


class TestCreateTierContract:
    """Test create_tier_contract() factory function."""

    def test_create_tier_contract_quick(self):
        """Quick tier contract has correct defaults."""
        from llm_council.tier_contract import create_tier_contract

        contract = create_tier_contract("quick")

        assert contract.tier == "quick"
        assert contract.deadline_ms == 30000  # 30s
        assert contract.requires_peer_review is False  # Quick skips full peer review
        assert contract.requires_verifier is True  # Quick uses lightweight verifier
        assert contract.max_attempts == 1
        assert contract.override_policy["can_escalate"] is True

    def test_create_tier_contract_balanced(self):
        """Balanced tier contract has correct defaults."""
        from llm_council.tier_contract import create_tier_contract

        contract = create_tier_contract("balanced")

        assert contract.tier == "balanced"
        assert contract.deadline_ms == 90000  # 90s
        assert contract.requires_peer_review is True
        assert contract.requires_verifier is False
        assert contract.max_attempts == 2

    def test_create_tier_contract_high(self):
        """High tier contract has correct defaults."""
        from llm_council.tier_contract import create_tier_contract

        contract = create_tier_contract("high")

        assert contract.tier == "high"
        assert contract.deadline_ms == 180000  # 180s
        assert contract.requires_peer_review is True
        assert contract.requires_verifier is False
        assert contract.max_attempts == 3

    def test_create_tier_contract_reasoning(self):
        """Reasoning tier contract has correct defaults."""
        from llm_council.tier_contract import create_tier_contract

        contract = create_tier_contract("reasoning")

        assert contract.tier == "reasoning"
        assert contract.deadline_ms == 600000  # 600s
        assert contract.requires_peer_review is True
        assert contract.requires_verifier is False
        assert contract.max_attempts == 2

    def test_create_tier_contract_uses_tier_model_pools(self):
        """Factory function should use TIER_MODEL_POOLS for allowed_models."""
        from llm_council.tier_contract import create_tier_contract
        from llm_council.config import TIER_MODEL_POOLS

        contract = create_tier_contract("quick")
        assert contract.allowed_models == TIER_MODEL_POOLS["quick"]

        contract = create_tier_contract("high")
        assert contract.allowed_models == TIER_MODEL_POOLS["high"]

    def test_create_tier_contract_invalid_tier_raises(self):
        """Invalid tier should raise ValueError."""
        from llm_council.tier_contract import create_tier_contract

        with pytest.raises(ValueError, match="Unknown tier"):
            create_tier_contract("invalid_tier")


class TestTierAggregators:
    """Test tier-appropriate aggregator models (ADR-022 council recommendation)."""

    def test_tier_aggregators_mapping_exists(self):
        """TIER_AGGREGATORS mapping should exist."""
        from llm_council.tier_contract import TIER_AGGREGATORS

        assert isinstance(TIER_AGGREGATORS, dict)
        assert "quick" in TIER_AGGREGATORS
        assert "balanced" in TIER_AGGREGATORS
        assert "high" in TIER_AGGREGATORS
        assert "reasoning" in TIER_AGGREGATORS

    def test_quick_tier_uses_fast_aggregator(self):
        """Quick tier should use a fast model for aggregation."""
        from llm_council.tier_contract import TIER_AGGREGATORS

        aggregator = TIER_AGGREGATORS["quick"]
        # Should be a mini/flash model
        assert any(fast in aggregator.lower() for fast in ["mini", "flash", "haiku"])

    def test_balanced_tier_uses_mid_aggregator(self):
        """Balanced tier should use a mid-tier model for aggregation."""
        from llm_council.tier_contract import TIER_AGGREGATORS

        aggregator = TIER_AGGREGATORS["balanced"]
        # Should be a capable but not premium model
        assert "gpt-4o" in aggregator or "sonnet" in aggregator.lower()

    def test_reasoning_tier_uses_capable_aggregator(self):
        """Reasoning tier needs aggregator that understands o1 outputs."""
        from llm_council.tier_contract import TIER_AGGREGATORS

        aggregator = TIER_AGGREGATORS["reasoning"]
        # Should be Claude Opus or similar (can understand chain-of-thought)
        assert "opus" in aggregator.lower() or "gpt-4o" in aggregator

    def test_create_tier_contract_uses_tier_aggregators(self):
        """Factory function should use TIER_AGGREGATORS for aggregator_model."""
        from llm_council.tier_contract import create_tier_contract, TIER_AGGREGATORS

        for tier in ["quick", "balanced", "high", "reasoning"]:
            contract = create_tier_contract(tier)
            assert contract.aggregator_model == TIER_AGGREGATORS[tier]


class TestTierContractDefaults:
    """Test DEFAULT_TIER_CONTRACTS configuration."""

    def test_default_tier_contracts_exists(self):
        """DEFAULT_TIER_CONTRACTS should be available for reference."""
        from llm_council.tier_contract import DEFAULT_TIER_CONTRACTS

        assert isinstance(DEFAULT_TIER_CONTRACTS, dict)
        assert "quick" in DEFAULT_TIER_CONTRACTS
        assert "balanced" in DEFAULT_TIER_CONTRACTS
        assert "high" in DEFAULT_TIER_CONTRACTS
        assert "reasoning" in DEFAULT_TIER_CONTRACTS

    def test_all_tier_contracts_are_tier_contract_instances(self):
        """All default contracts should be TierContract instances."""
        from llm_council.tier_contract import DEFAULT_TIER_CONTRACTS, TierContract

        for tier, contract in DEFAULT_TIER_CONTRACTS.items():
            assert isinstance(contract, TierContract), f"{tier} should be TierContract"


class TestTierContractTimeoutAlignment:
    """Test that TierContract timeouts align with ADR-012 tier timeouts."""

    def test_quick_timeout_matches_adr012(self):
        """Quick tier deadline should match ADR-012 (30s)."""
        from llm_council.tier_contract import create_tier_contract
        from llm_council.config import get_tier_timeout

        contract = create_tier_contract("quick")
        tier_timeout = get_tier_timeout("quick")

        assert contract.deadline_ms == tier_timeout["total"] * 1000

    def test_balanced_timeout_matches_adr012(self):
        """Balanced tier deadline should match ADR-012 (90s)."""
        from llm_council.tier_contract import create_tier_contract
        from llm_council.config import get_tier_timeout

        contract = create_tier_contract("balanced")
        tier_timeout = get_tier_timeout("balanced")

        assert contract.deadline_ms == tier_timeout["total"] * 1000

    def test_high_timeout_matches_adr012(self):
        """High tier deadline should match ADR-012 (180s)."""
        from llm_council.tier_contract import create_tier_contract
        from llm_council.config import get_tier_timeout

        contract = create_tier_contract("high")
        tier_timeout = get_tier_timeout("high")

        assert contract.deadline_ms == tier_timeout["total"] * 1000

    def test_reasoning_timeout_matches_adr012(self):
        """Reasoning tier deadline should match ADR-012 (600s)."""
        from llm_council.tier_contract import create_tier_contract
        from llm_council.config import get_tier_timeout

        contract = create_tier_contract("reasoning")
        tier_timeout = get_tier_timeout("reasoning")

        assert contract.deadline_ms == tier_timeout["total"] * 1000


class TestTierContractPerModelTimeout:
    """Test per_model_timeout_ms field for ADR-012 compliance."""

    def test_tier_contract_has_per_model_timeout(self):
        """TierContract should have per_model_timeout_ms field."""
        from llm_council.tier_contract import create_tier_contract

        contract = create_tier_contract("high")
        assert hasattr(contract, "per_model_timeout_ms")
        assert isinstance(contract.per_model_timeout_ms, int)

    def test_per_model_timeout_matches_adr012(self):
        """per_model_timeout_ms should align with ADR-012 tier timeouts."""
        from llm_council.tier_contract import create_tier_contract
        from llm_council.config import get_tier_timeout

        for tier in ["quick", "balanced", "high", "reasoning"]:
            contract = create_tier_contract(tier)
            tier_timeout = get_tier_timeout(tier)

            assert contract.per_model_timeout_ms == tier_timeout["per_model"] * 1000
