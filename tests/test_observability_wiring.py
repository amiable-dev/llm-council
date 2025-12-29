import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from llm_council.gateway.router import GatewayRouter, CircuitOpenError
from llm_council.gateway.types import (
    GatewayRequest,
    GatewayResponse,
    CanonicalMessage,
    ContentBlock,
)
from llm_council.layer_contracts import LayerEventType, emit_layer_event


@pytest.mark.asyncio
async def test_gateway_emits_observability_events():
    """ADR-024: Gateway must emit L4 observability events."""

    # Mock helpers
    with (
        patch("llm_council.layer_contracts.emit_layer_event") as mock_emit,
        patch("llm_council.layer_contracts.cross_l3_to_l4") as mock_cross,
    ):
        # Setup
        router = GatewayRouter()

        # Mock successful gateway
        mock_gateway = AsyncMock()
        mock_gateway.complete.return_value = GatewayResponse(
            content="Success", model="test-model", status="ok", latency_ms=100
        )
        router.gateways["openrouter"] = mock_gateway

        request = GatewayRequest(
            model="openai/gpt-4o",
            messages=[
                CanonicalMessage(role="user", content=[ContentBlock(type="text", text="Hello")])
            ],
        )

        # Execute
        await router.complete(request)

        # Verify L3->L4 boundary crossing (Request event)
        mock_cross.assert_called_once()
        assert mock_cross.call_args[0][0] == request

        # Verify L4 Response event
        response_emits = [
            call
            for call in mock_emit.call_args_list
            if call[0][0] == LayerEventType.L4_GATEWAY_RESPONSE
        ]
        assert len(response_emits) == 1


@pytest.mark.asyncio
async def test_gateway_emits_fallback_events():
    """ADR-024: Gateway must emit fallback events."""

    with patch("llm_council.layer_contracts.emit_layer_event") as mock_emit:
        # Setup fallback chain
        primary = AsyncMock()
        primary.complete.side_effect = Exception("Primary failed")

        backup = AsyncMock()
        backup.complete.return_value = GatewayResponse(
            content="Backup", model="model", status="ok", latency_ms=100
        )

        router = GatewayRouter(
            gateways={"primary": primary, "backup": backup},
            model_routing={"model": "primary"},
            fallback_chains={"primary": ["backup"]},
        )

        request = GatewayRequest(
            model="model",
            messages=[
                CanonicalMessage(role="user", content=[ContentBlock(type="text", text="Hello")])
            ],
        )

        await router.complete(request)

        # Verify Fallback event
        fallback_emits = [
            call
            for call in mock_emit.call_args_list
            if call[0][0] == LayerEventType.L4_GATEWAY_FALLBACK
        ]
        assert len(fallback_emits) == 1
        assert fallback_emits[0][0][1]["from_gateway"] == "primary"
        assert fallback_emits[0][0][1]["to_gateway"] == "backup"


@pytest.mark.asyncio
async def test_council_emits_layer_events():
    """ADR-024: Council execution must emit L1/L2/L3 events."""
    from llm_council.council import run_council_with_fallback
    from llm_council.tier_contract import TierContract

    with (
        patch("llm_council.council.emit_layer_event") as mock_emit,
        patch("llm_council.council.cross_l1_to_l2") as mock_l1,
        patch("llm_council.council.cross_l2_to_l3") as mock_l2,
        patch("llm_council.council.query_models_with_progress") as mock_query,
        patch("llm_council.council.stage3_synthesize_final") as mock_synth,
        patch("llm_council.council.stage2_collect_rankings") as mock_stage2,
        patch("llm_council.council.run_triage") as mock_triage,
        patch("llm_council.council.stage1_5_normalize_styles") as mock_stage15_normalize_styles,
    ):
        # Setup mocks
        mock_query.return_value = {}
        mock_synth.return_value = ({"response": "Synthesis"}, {}, None)
        mock_stage2.return_value = ([], {}, {})
        mock_stage15_normalize_styles.return_value = ([], {})

        from llm_council.triage import TriageResult

        # ... (skipping lines) ...

        # Mock Tier Contract
        tier = TierContract(
            tier="quick",
            allowed_models=["test-model"],
            deadline_ms=1000,
            per_model_timeout_ms=500,
            token_budget=1000,
            max_attempts=1,
            requires_peer_review=False,
            requires_verifier=False,
            aggregator_model="aggregator",
            override_policy={},
        )

        # Use real TriageResult
        mock_triage.return_value = TriageResult(
            resolved_models=["test-model"],
            optimized_prompts={},
            fast_path=False,
            escalation_recommended=False,
            metadata={},
        )

        # Execute with triage enabled
        await run_council_with_fallback("test query", tier_contract=tier, use_wildcard=True)

        # Verify L1->L2 crossing
        mock_l1.assert_called_once()

        # Verify L2->L3 crossing
        mock_l2.assert_called_once()

        # Verify L3 Start event
        start_emits = [
            call
            for call in mock_emit.call_args_list
            if call[0][0] == LayerEventType.L3_COUNCIL_START
        ]
        assert len(start_emits) == 1
