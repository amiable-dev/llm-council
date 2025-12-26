"""Layer Interface Contracts for ADR-024 Unified Routing Architecture.

This module formalizes the layer boundaries and provides:
1. Re-exports of all layer interface types
2. Validation functions for boundary crossing
3. Observability hooks for logging and monitoring

Layer Architecture:
- L1 (ADR-022): Tier Selection → outputs TierContract
- L2 (ADR-020): Query Triage → outputs TriageResult
- L3 (Core): Council Execution → outputs responses
- L4 (ADR-023): Gateway Routing → uses GatewayRequest

Architectural Principles (ADR-024):
1. Layer Sovereignty: Each layer owns its decision; no layer overrides another
2. Explicit Escalation: All escalations are logged, user-visible, and auditable
3. Failure Isolation: Gateway failures don't cascade to tier changes
4. Constraint Propagation: Tier constraints flow down; lower layers cannot violate
5. Observability by Default: Every layer emits metrics, logs, and traces
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import logging

# Re-export layer interface types
from .tier_contract import TierContract, create_tier_contract
from .triage.types import TriageResult, TriageRequest, DomainCategory, WildcardConfig
from .gateway.types import (
    GatewayRequest,
    GatewayResponse,
    CanonicalMessage,
    ContentBlock,
    UsageInfo,
)

__all__ = [
    # L1 types (Tier Selection)
    "TierContract",
    "create_tier_contract",
    # L2 types (Query Triage)
    "TriageResult",
    "TriageRequest",
    "DomainCategory",
    "WildcardConfig",
    # L4 types (Gateway Routing)
    "GatewayRequest",
    "GatewayResponse",
    "CanonicalMessage",
    "ContentBlock",
    "UsageInfo",
    # Validation functions
    "validate_tier_contract",
    "validate_triage_result",
    "validate_gateway_request",
    "validate_l1_to_l2_boundary",
    "validate_l2_to_l3_boundary",
    "validate_l3_to_l4_boundary",
    # Observability
    "LayerEvent",
    "LayerEventType",
    "emit_layer_event",
    "get_layer_events",
    "clear_layer_events",
    # Boundary crossing helpers
    "cross_l1_to_l2",
    "cross_l2_to_l3",
    "cross_l3_to_l4",
]


# =============================================================================
# Layer Event Types for Observability
# =============================================================================


class LayerEventType(Enum):
    """Types of events that occur at layer boundaries.

    Per ADR-024: "Observability by Default - Every layer emits metrics, logs, and traces"
    """

    # L1 Events (Tier Selection)
    L1_TIER_SELECTED = "l1_tier_selected"
    L1_TIER_ESCALATION = "l1_tier_escalation"
    L1_TIER_DEESCALATION = "l1_tier_deescalation"

    # L2 Events (Query Triage)
    L2_TRIAGE_COMPLETE = "l2_triage_complete"
    L2_WILDCARD_SELECTED = "l2_wildcard_selected"
    L2_DELIBERATION_ESCALATION = "l2_deliberation_escalation"
    L2_FAST_PATH_TRIGGERED = "l2_fast_path_triggered"

    # L3 Events (Council Execution)
    L3_COUNCIL_START = "l3_council_start"
    L3_COUNCIL_COMPLETE = "l3_council_complete"
    L3_STAGE_COMPLETE = "l3_stage_complete"
    L3_MODEL_TIMEOUT = "l3_model_timeout"

    # L4 Events (Gateway Routing)
    L4_GATEWAY_REQUEST = "l4_gateway_request"
    L4_GATEWAY_RESPONSE = "l4_gateway_response"
    L4_GATEWAY_FALLBACK = "l4_gateway_fallback"
    L4_CIRCUIT_BREAKER_OPEN = "l4_circuit_breaker_open"
    L4_CIRCUIT_BREAKER_CLOSE = "l4_circuit_breaker_close"

    # Cross-layer Events
    BOUNDARY_CROSSING = "boundary_crossing"
    VALIDATION_WARNING = "validation_warning"

    # Frontier Tier Events (ADR-027)
    FRONTIER_MODEL_SELECTED = "frontier_model_selected"
    FRONTIER_SHADOW_VOTE = "frontier_shadow_vote"
    FRONTIER_FALLBACK_TRIGGERED = "frontier_fallback_triggered"
    FRONTIER_COST_CEILING_EXCEEDED = "frontier_cost_ceiling_exceeded"
    FRONTIER_GRADUATION_CANDIDATE = "frontier_graduation_candidate"
    FRONTIER_GRADUATION_PROMOTED = "frontier_graduation_promoted"

    # Discovery Events (ADR-028)
    DISCOVERY_REFRESH_STARTED = "discovery_refresh_started"
    DISCOVERY_REFRESH_COMPLETE = "discovery_refresh_complete"
    DISCOVERY_REFRESH_FAILED = "discovery_refresh_failed"
    DISCOVERY_FALLBACK_TRIGGERED = "discovery_fallback_triggered"
    DISCOVERY_STALE_SERVE = "discovery_stale_serve"

    # Audition Events (ADR-029)
    AUDITION_STATE_TRANSITION = "audition_state_transition"
    AUDITION_MODEL_SELECTED = "audition_model_selected"
    AUDITION_FAILURE_RECORDED = "audition_failure_recorded"
    AUDITION_QUARANTINE_TRIGGERED = "audition_quarantine_triggered"
    AUDITION_GRADUATION_COMPLETE = "audition_graduation_complete"


@dataclass
class LayerEvent:
    """An event emitted at a layer boundary.

    Used for observability, logging, and audit trails.
    """

    event_type: LayerEventType
    data: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    layer_from: Optional[str] = None
    layer_to: Optional[str] = None


# Global event store (in-memory for now, can be replaced with proper sink)
_layer_events: List[LayerEvent] = []

# Logger for layer events
logger = logging.getLogger("llm_council.layers")


def emit_layer_event(
    event_type: LayerEventType,
    data: Dict[str, Any],
    layer_from: Optional[str] = None,
    layer_to: Optional[str] = None,
) -> LayerEvent:
    """Emit a layer event for observability.

    Args:
        event_type: Type of event
        data: Event-specific data
        layer_from: Source layer (e.g., "L1", "L2")
        layer_to: Destination layer (e.g., "L2", "L3")

    Returns:
        The emitted LayerEvent
    """
    event = LayerEvent(
        event_type=event_type,
        data=data,
        layer_from=layer_from,
        layer_to=layer_to,
    )
    _layer_events.append(event)

    # Also log the event
    logger.info(
        "Layer event: %s from=%s to=%s data=%s",
        event_type.value,
        layer_from,
        layer_to,
        data,
    )

    # Notify subscribed metrics adapters (ADR-030)
    # Lazy import to avoid circular dependency
    try:
        from .observability.metrics_adapter import _notify_adapters

        _notify_adapters(event)
    except ImportError:
        pass  # Observability module not available

    return event


def get_layer_events() -> List[LayerEvent]:
    """Get all emitted layer events.

    Returns:
        List of LayerEvents in emission order
    """
    return list(_layer_events)


def clear_layer_events() -> None:
    """Clear all layer events.

    Typically called at the start of a new request.
    """
    _layer_events.clear()


# =============================================================================
# Validation Functions
# =============================================================================


def validate_tier_contract(contract: TierContract) -> bool:
    """Validate a TierContract (L1 output).

    Args:
        contract: TierContract to validate

    Returns:
        True if valid

    Raises:
        ValueError: If contract is invalid
    """
    if contract is None:
        raise ValueError("TierContract cannot be None")

    if not isinstance(contract, TierContract):
        raise ValueError(f"Expected TierContract, got {type(contract)}")

    if contract.tier not in ("quick", "balanced", "high", "reasoning"):
        raise ValueError(f"Invalid tier: {contract.tier}")

    if not contract.allowed_models or len(contract.allowed_models) == 0:
        raise ValueError("TierContract must have at least one allowed model")

    if contract.deadline_ms <= 0:
        raise ValueError("TierContract deadline_ms must be positive")

    if contract.per_model_timeout_ms <= 0:
        raise ValueError("TierContract per_model_timeout_ms must be positive")

    return True


def validate_triage_result(result: TriageResult) -> bool:
    """Validate a TriageResult (L2 output).

    Args:
        result: TriageResult to validate

    Returns:
        True if valid

    Raises:
        ValueError: If result is invalid
    """
    if result is None:
        raise ValueError("TriageResult cannot be None")

    if not isinstance(result, TriageResult):
        raise ValueError(f"Expected TriageResult, got {type(result)}")

    if not result.resolved_models or len(result.resolved_models) == 0:
        raise ValueError("TriageResult must have at least one resolved model")

    return True


def validate_gateway_request(request: GatewayRequest) -> bool:
    """Validate a GatewayRequest (L4 input).

    Args:
        request: GatewayRequest to validate

    Returns:
        True if valid

    Raises:
        ValueError: If request is invalid
    """
    if request is None:
        raise ValueError("GatewayRequest cannot be None")

    if not isinstance(request, GatewayRequest):
        raise ValueError(f"Expected GatewayRequest, got {type(request)}")

    if not request.model:
        raise ValueError("GatewayRequest must have a model")

    if not request.messages or len(request.messages) == 0:
        raise ValueError("GatewayRequest must have at least one message")

    return True


# =============================================================================
# Boundary Validation Functions
# =============================================================================


def validate_l1_to_l2_boundary(
    contract: TierContract,
    query: str,
) -> bool:
    """Validate the L1 → L2 boundary crossing.

    Args:
        contract: TierContract from L1
        query: Query string being processed

    Returns:
        True if valid

    Raises:
        ValueError: If boundary crossing is invalid
    """
    validate_tier_contract(contract)

    if not query or not query.strip():
        raise ValueError("Query cannot be empty at L1→L2 boundary")

    return True


def validate_l2_to_l3_boundary(
    result: TriageResult,
    tier_contract: Optional[TierContract] = None,
) -> bool:
    """Validate the L2 → L3 boundary crossing.

    Per ADR-024: "models MUST come from TierContract.allowed_models"
    This is a soft constraint (warning) not hard (error).

    Args:
        result: TriageResult from L2
        tier_contract: Optional TierContract to validate against

    Returns:
        True if valid (may emit warnings)
    """
    validate_triage_result(result)

    # Soft constraint: warn if models not in tier pool
    if tier_contract is not None:
        allowed = set(tier_contract.allowed_models)
        resolved = set(result.resolved_models)
        outside_tier = resolved - allowed

        if outside_tier:
            emit_layer_event(
                LayerEventType.VALIDATION_WARNING,
                {
                    "message": "TriageResult contains models outside TierContract.allowed_models",
                    "outside_models": list(outside_tier),
                    "tier": tier_contract.tier,
                },
                layer_from="L2",
                layer_to="L3",
            )

    return True


def validate_l3_to_l4_boundary(request: GatewayRequest) -> bool:
    """Validate the L3 → L4 boundary crossing.

    Args:
        request: GatewayRequest for L4

    Returns:
        True if valid

    Raises:
        ValueError: If boundary crossing is invalid
    """
    return validate_gateway_request(request)


# =============================================================================
# Boundary Crossing Helpers
# =============================================================================


def cross_l1_to_l2(
    contract: TierContract,
    query: str,
) -> bool:
    """Cross the L1 → L2 boundary with validation and event emission.

    Args:
        contract: TierContract from L1
        query: Query string being processed

    Returns:
        True if crossing succeeded
    """
    # Validate
    validate_l1_to_l2_boundary(contract, query)

    # Emit event
    emit_layer_event(
        LayerEventType.L1_TIER_SELECTED,
        {
            "tier": contract.tier,
            "deadline_ms": contract.deadline_ms,
            "model_count": len(contract.allowed_models),
            "query_length": len(query),
        },
        layer_from="L1",
        layer_to="L2",
    )

    return True


def cross_l2_to_l3(
    result: TriageResult,
    tier_contract: Optional[TierContract] = None,
) -> bool:
    """Cross the L2 → L3 boundary with validation and event emission.

    Args:
        result: TriageResult from L2
        tier_contract: Optional TierContract to validate against

    Returns:
        True if crossing succeeded
    """
    # Validate
    validate_l2_to_l3_boundary(result, tier_contract)

    # Emit event
    emit_layer_event(
        LayerEventType.L2_TRIAGE_COMPLETE,
        {
            "model_count": len(result.resolved_models),
            "fast_path": result.fast_path,
            "escalation_recommended": result.escalation_recommended,
            "has_optimized_prompts": len(result.optimized_prompts) > 0,
        },
        layer_from="L2",
        layer_to="L3",
    )

    # Emit escalation event if recommended
    if result.escalation_recommended:
        emit_layer_event(
            LayerEventType.L2_DELIBERATION_ESCALATION,
            {
                "reason": result.escalation_reason or "unspecified",
            },
            layer_from="L2",
            layer_to="L3",
        )

    return True


def cross_l3_to_l4(request: GatewayRequest) -> bool:
    """Cross the L3 → L4 boundary with validation and event emission.

    Args:
        request: GatewayRequest for L4

    Returns:
        True if crossing succeeded
    """
    # Validate
    validate_l3_to_l4_boundary(request)

    # Emit event
    emit_layer_event(
        LayerEventType.L4_GATEWAY_REQUEST,
        {
            "model": request.model,
            "message_count": len(request.messages),
            "timeout": request.timeout,
        },
        layer_from="L3",
        layer_to="L4",
    )

    return True
