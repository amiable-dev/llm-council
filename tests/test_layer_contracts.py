"""TDD tests for ADR-024 Phase 3: Layer Interface Contracts.

Tests the formal layer boundaries and validation for the unified routing architecture.
"""

import pytest
from unittest.mock import MagicMock, patch

from llm_council.layer_contracts import (
    # Layer interface types (re-exported)
    TierContract,
    TriageResult,
    GatewayRequest,
    CanonicalMessage,
    ContentBlock,
    # Validation functions
    validate_tier_contract,
    validate_triage_result,
    validate_gateway_request,
    validate_l1_to_l2_boundary,
    validate_l2_to_l3_boundary,
    validate_l3_to_l4_boundary,
    # Observability hooks
    LayerEvent,
    LayerEventType,
    emit_layer_event,
    get_layer_events,
    clear_layer_events,
    # Boundary crossing helpers
    cross_l1_to_l2,
    cross_l2_to_l3,
    cross_l3_to_l4,
)
from llm_council.tier_contract import create_tier_contract
from llm_council.triage.types import DomainCategory


class TestLayerInterfaceExports:
    """Test that all layer interface types are properly exported."""

    def test_tier_contract_exported(self):
        """TierContract should be exported from layer_contracts."""
        assert TierContract is not None
        contract = create_tier_contract("balanced")
        assert isinstance(contract, TierContract)

    def test_triage_result_exported(self):
        """TriageResult should be exported from layer_contracts."""
        assert TriageResult is not None
        result = TriageResult(
            resolved_models=["model-a", "model-b"],
            optimized_prompts={"model-a": "prompt-a"},
        )
        assert result.resolved_models == ["model-a", "model-b"]

    def test_gateway_request_exported(self):
        """GatewayRequest should be exported from layer_contracts."""
        assert GatewayRequest is not None
        request = GatewayRequest(
            model="openai/gpt-4o",
            messages=[],
        )
        assert request.model == "openai/gpt-4o"

    def test_canonical_message_exported(self):
        """CanonicalMessage should be exported from layer_contracts."""
        assert CanonicalMessage is not None
        msg = CanonicalMessage(role="user", content=[])
        assert msg.role == "user"


class TestTierContractValidation:
    """Test validation of TierContract (L1 output)."""

    def test_valid_tier_contract(self):
        """Valid TierContract should pass validation."""
        contract = create_tier_contract("balanced")
        assert validate_tier_contract(contract) is True

    def test_invalid_tier_name(self):
        """Invalid tier name should fail validation."""
        # We can't create an invalid TierContract directly due to factory,
        # but we can test the validation function directly
        with pytest.raises(ValueError, match="(?i)tier|none"):
            validate_tier_contract(None)

    def test_tier_contract_has_allowed_models(self):
        """TierContract must have at least one allowed model."""
        contract = create_tier_contract("high")
        assert len(contract.allowed_models) >= 1

    def test_tier_contract_deadline_positive(self):
        """TierContract deadline must be positive."""
        contract = create_tier_contract("quick")
        assert contract.deadline_ms > 0


class TestTriageResultValidation:
    """Test validation of TriageResult (L2 output)."""

    def test_valid_triage_result(self):
        """Valid TriageResult should pass validation."""
        result = TriageResult(
            resolved_models=["openai/gpt-4o", "anthropic/claude-3-5-sonnet"],
            optimized_prompts={
                "openai/gpt-4o": "prompt",
                "anthropic/claude-3-5-sonnet": "prompt",
            },
        )
        assert validate_triage_result(result) is True

    def test_triage_result_must_have_models(self):
        """TriageResult must have at least one resolved model."""
        result = TriageResult(resolved_models=[], optimized_prompts={})
        with pytest.raises(ValueError, match="model"):
            validate_triage_result(result)

    def test_triage_result_prompts_match_models(self):
        """Optimized prompts should match resolved models."""
        result = TriageResult(
            resolved_models=["model-a", "model-b"],
            optimized_prompts={"model-a": "prompt-a"},  # Missing model-b
        )
        # Should still be valid - prompts are optional per model
        assert validate_triage_result(result) is True


class TestGatewayRequestValidation:
    """Test validation of GatewayRequest (L4 input)."""

    def test_valid_gateway_request(self):
        """Valid GatewayRequest should pass validation."""
        request = GatewayRequest(
            model="openai/gpt-4o",
            messages=[
                CanonicalMessage(
                    role="user",
                    content=[ContentBlock(type="text", text="Hello")],
                )
            ],
        )
        assert validate_gateway_request(request) is True

    def test_gateway_request_requires_model(self):
        """GatewayRequest must have a model."""
        request = GatewayRequest(model="", messages=[])
        with pytest.raises(ValueError, match="model"):
            validate_gateway_request(request)

    def test_gateway_request_requires_messages(self):
        """GatewayRequest must have at least one message."""
        request = GatewayRequest(model="openai/gpt-4o", messages=[])
        with pytest.raises(ValueError, match="message"):
            validate_gateway_request(request)


class TestBoundaryValidation:
    """Test validation at layer boundaries."""

    def test_l1_to_l2_boundary(self):
        """L1 to L2 boundary should validate TierContract."""
        contract = create_tier_contract("high")
        assert validate_l1_to_l2_boundary(contract, "test query") is True

    def test_l1_to_l2_boundary_requires_query(self):
        """L1 to L2 boundary requires a query string."""
        contract = create_tier_contract("balanced")
        with pytest.raises(ValueError, match="(?i)query|empty"):
            validate_l1_to_l2_boundary(contract, "")

    def test_l2_to_l3_boundary(self):
        """L2 to L3 boundary should validate TriageResult."""
        triage_result = TriageResult(
            resolved_models=["model-a"],
            optimized_prompts={"model-a": "prompt"},
        )
        assert validate_l2_to_l3_boundary(triage_result) is True

    def test_l2_to_l3_boundary_checks_models_in_tier(self):
        """L2 models must come from TierContract.allowed_models."""
        tier_contract = create_tier_contract("quick")
        triage_result = TriageResult(
            resolved_models=["unknown/model"],  # Not in quick tier
            optimized_prompts={},
        )
        # Should warn but not fail (soft constraint per ADR-024)
        assert validate_l2_to_l3_boundary(triage_result, tier_contract) is True

    def test_l3_to_l4_boundary(self):
        """L3 to L4 boundary should validate GatewayRequest."""
        request = GatewayRequest(
            model="openai/gpt-4o",
            messages=[
                CanonicalMessage(
                    role="user",
                    content=[ContentBlock(type="text", text="test")],
                )
            ],
        )
        assert validate_l3_to_l4_boundary(request) is True


class TestObservabilityHooks:
    """Test observability hooks at layer boundaries."""

    def setup_method(self):
        """Clear events before each test."""
        clear_layer_events()

    def test_emit_layer_event(self):
        """Should be able to emit layer events."""
        emit_layer_event(
            LayerEventType.L1_TIER_SELECTED,
            {"tier": "balanced", "deadline_ms": 90000},
        )
        events = get_layer_events()
        assert len(events) == 1
        assert events[0].event_type == LayerEventType.L1_TIER_SELECTED

    def test_layer_event_has_timestamp(self):
        """Layer events should have timestamps."""
        emit_layer_event(LayerEventType.L2_TRIAGE_COMPLETE, {})
        events = get_layer_events()
        assert events[0].timestamp is not None

    def test_layer_event_types(self):
        """All layer event types should be defined."""
        assert LayerEventType.L1_TIER_SELECTED is not None
        assert LayerEventType.L1_TIER_ESCALATION is not None
        assert LayerEventType.L2_TRIAGE_COMPLETE is not None
        assert LayerEventType.L2_DELIBERATION_ESCALATION is not None
        assert LayerEventType.L3_COUNCIL_START is not None
        assert LayerEventType.L3_COUNCIL_COMPLETE is not None
        assert LayerEventType.L4_GATEWAY_REQUEST is not None
        assert LayerEventType.L4_GATEWAY_FALLBACK is not None

    def test_clear_layer_events(self):
        """Should be able to clear all events."""
        emit_layer_event(LayerEventType.L1_TIER_SELECTED, {})
        emit_layer_event(LayerEventType.L2_TRIAGE_COMPLETE, {})
        clear_layer_events()
        events = get_layer_events()
        assert len(events) == 0


class TestBoundaryCrossingHelpers:
    """Test helper functions for crossing layer boundaries."""

    def setup_method(self):
        """Clear events before each test."""
        clear_layer_events()

    def test_cross_l1_to_l2(self):
        """cross_l1_to_l2 should validate and emit event."""
        contract = create_tier_contract("balanced")
        query = "What is the capital of France?"

        result = cross_l1_to_l2(contract, query)

        assert result is True
        events = get_layer_events()
        assert len(events) >= 1
        assert any(e.event_type == LayerEventType.L1_TIER_SELECTED for e in events)

    def test_cross_l2_to_l3(self):
        """cross_l2_to_l3 should validate and emit event."""
        triage_result = TriageResult(
            resolved_models=["model-a", "model-b"],
            optimized_prompts={"model-a": "prompt", "model-b": "prompt"},
        )

        result = cross_l2_to_l3(triage_result)

        assert result is True
        events = get_layer_events()
        assert len(events) >= 1
        assert any(e.event_type == LayerEventType.L2_TRIAGE_COMPLETE for e in events)

    def test_cross_l3_to_l4(self):
        """cross_l3_to_l4 should validate and emit event."""
        request = GatewayRequest(
            model="openai/gpt-4o",
            messages=[
                CanonicalMessage(
                    role="user",
                    content=[ContentBlock(type="text", text="test")],
                )
            ],
        )

        result = cross_l3_to_l4(request)

        assert result is True
        events = get_layer_events()
        assert len(events) >= 1
        assert any(e.event_type == LayerEventType.L4_GATEWAY_REQUEST for e in events)


class TestEscalationLogging:
    """Test that escalations are properly logged."""

    def setup_method(self):
        """Clear events before each test."""
        clear_layer_events()

    def test_tier_escalation_logged(self):
        """Tier escalation should emit L1_TIER_ESCALATION event."""
        emit_layer_event(
            LayerEventType.L1_TIER_ESCALATION,
            {"from_tier": "quick", "to_tier": "balanced", "reason": "low confidence"},
        )

        events = get_layer_events()
        assert len(events) == 1
        assert events[0].event_type == LayerEventType.L1_TIER_ESCALATION
        assert events[0].data["from_tier"] == "quick"
        assert events[0].data["to_tier"] == "balanced"

    def test_deliberation_escalation_logged(self):
        """Deliberation escalation should emit L2_DELIBERATION_ESCALATION event."""
        emit_layer_event(
            LayerEventType.L2_DELIBERATION_ESCALATION,
            {"confidence": 0.85, "threshold": 0.92},
        )

        events = get_layer_events()
        assert len(events) == 1
        assert events[0].event_type == LayerEventType.L2_DELIBERATION_ESCALATION

    def test_gateway_fallback_logged(self):
        """Gateway fallback should emit L4_GATEWAY_FALLBACK event."""
        emit_layer_event(
            LayerEventType.L4_GATEWAY_FALLBACK,
            {
                "from_gateway": "openrouter",
                "to_gateway": "requesty",
                "reason": "timeout",
            },
        )

        events = get_layer_events()
        assert len(events) == 1
        assert events[0].event_type == LayerEventType.L4_GATEWAY_FALLBACK
        assert events[0].data["from_gateway"] == "openrouter"


class TestLayerSovereignty:
    """Test that layer sovereignty principles are maintained."""

    def test_l2_cannot_violate_l1_constraints(self):
        """L2 should not be able to use models outside L1 allowed_models.

        Per ADR-024: "models MUST come from TierContract.allowed_models"
        This is a soft constraint (warning) not hard (error).
        """
        quick_contract = create_tier_contract("quick")

        # Try to use a model not in quick tier
        triage_result = TriageResult(
            resolved_models=["openai/gpt-5.2-pro"],  # Reasoning model
            optimized_prompts={},
        )

        # Validation should pass but emit a warning event
        result = validate_l2_to_l3_boundary(triage_result, quick_contract)
        assert result is True  # Soft constraint - warns but doesn't fail

    def test_escalation_requires_logging(self):
        """All escalations must be logged per ADR-024."""
        # This is verified by the emit_layer_event mechanism
        clear_layer_events()

        emit_layer_event(
            LayerEventType.L1_TIER_ESCALATION,
            {"from_tier": "balanced", "to_tier": "high", "reason": "complexity"},
        )

        events = get_layer_events()
        assert len(events) == 1
        # Verify event contains required audit information
        assert "from_tier" in events[0].data
        assert "to_tier" in events[0].data
        assert "reason" in events[0].data
