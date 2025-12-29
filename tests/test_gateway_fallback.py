import pytest
from unittest.mock import AsyncMock, patch
from llm_council.gateway.router import GatewayRouter, CircuitOpenError
from llm_council.gateway.types import (
    GatewayRequest,
    GatewayResponse,
    CanonicalMessage,
    ContentBlock,
)


@pytest.mark.asyncio
async def test_complete_uses_fallback_chain_on_failure():
    """ADR-023: If primary gateway fails, router should try fallback gateways."""

    # 1. Setup Mock Gateways
    primary_gateway = AsyncMock()
    primary_gateway.complete.side_effect = Exception("Primary failed")

    backup_gateway = AsyncMock()
    backup_gateway.complete.return_value = GatewayResponse(
        content="Success from backup", model="test-model", status="ok", latency_ms=100
    )

    # 2. Configure Router with Fallback Chain
    # We simulate a config where "primary" falls back to ["backup"]
    router = GatewayRouter(
        gateways={"primary": primary_gateway, "backup": backup_gateway},
        model_routing={"test-model": "primary"},
        fallback_chains={
            "primary": ["backup"]
        },  # This arg doesn't exist yet, so this line will eventually need implementation in Router
    )

    # 3. Create Request
    request = GatewayRequest(
        model="test-model",
        messages=[CanonicalMessage(role="user", content=[ContentBlock(type="text", text="Hello")])],
    )

    # 4. Patch internal helpers if needed, or just let it run.
    # The router uses _get_gateway_id internally.

    # 5. Execute
    response = await router.complete(request)

    # 6. Verify
    assert response.status == "ok"
    assert response.content == "Success from backup"

    # Verify primary was called
    assert primary_gateway.complete.called
    # Verify backup was called
    assert backup_gateway.complete.called


@pytest.mark.asyncio
async def test_complete_raises_if_all_fallbacks_fail():
    """ADR-023: If all gateways in chain fail, raise exception."""

    primary = AsyncMock()
    primary.complete.side_effect = Exception("Primary failed")

    backup = AsyncMock()
    backup.complete.side_effect = Exception("Backup failed")

    router = GatewayRouter(
        gateways={"primary": primary, "backup": backup},
        model_routing={"test-model": "primary"},
        fallback_chains={"primary": ["backup"]},
    )

    request = GatewayRequest(
        model="test-model",
        messages=[CanonicalMessage(role="user", content=[ContentBlock(type="text", text="Hello")])],
    )

    with pytest.raises(Exception) as exc:
        await router.complete(request)

    assert "Backup failed" in str(exc.value) or "Primary failed" in str(exc.value)
