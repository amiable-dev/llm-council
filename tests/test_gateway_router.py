"""Tests for GatewayRouter implementation (ADR-023).

TDD: Write these tests first, then implement the GatewayRouter.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime


class TestGatewayRouterBasics:
    """Test GatewayRouter basic functionality."""

    def test_gateway_router_can_be_instantiated(self):
        """GatewayRouter should be instantiable."""
        from llm_council.gateway.router import GatewayRouter

        router = GatewayRouter()
        assert router is not None

    def test_gateway_router_has_default_gateway(self):
        """GatewayRouter should have OpenRouter as default gateway."""
        from llm_council.gateway.router import GatewayRouter
        from llm_council.gateway.openrouter import OpenRouterGateway

        router = GatewayRouter()

        # Should have at least the default OpenRouter gateway
        assert "openrouter" in router.gateways
        assert isinstance(router.gateways["openrouter"], OpenRouterGateway)

    def test_gateway_router_allows_custom_gateways(self):
        """GatewayRouter should accept custom gateway instances."""
        from llm_council.gateway.router import GatewayRouter
        from llm_council.gateway.openrouter import OpenRouterGateway

        custom_gateway = OpenRouterGateway(api_key="custom-key")
        router = GatewayRouter(gateways={"custom": custom_gateway})

        assert "custom" in router.gateways


class TestGatewayRouterModelRouting:
    """Test model-to-gateway routing."""

    def test_get_gateway_for_model_returns_default(self):
        """Should return default gateway for unknown models."""
        from llm_council.gateway.router import GatewayRouter

        router = GatewayRouter()

        gateway = router.get_gateway_for_model("openai/gpt-4o")
        assert gateway is not None

    def test_get_gateway_for_model_uses_routing_config(self):
        """Should use routing config to determine gateway."""
        from llm_council.gateway.router import GatewayRouter
        from llm_council.gateway.openrouter import OpenRouterGateway

        custom_gateway = OpenRouterGateway(api_key="custom-key")
        router = GatewayRouter(
            gateways={"openrouter": OpenRouterGateway(), "custom": custom_gateway},
            model_routing={"anthropic/*": "custom"},
        )

        # Claude models should route to custom gateway
        gateway = router.get_gateway_for_model("anthropic/claude-3-5-sonnet")
        assert gateway == router.gateways["custom"]


class TestGatewayRouterComplete:
    """Test GatewayRouter.complete() method."""

    @pytest.mark.asyncio
    async def test_complete_returns_response(self):
        """complete() should return GatewayResponse."""
        from llm_council.gateway.router import GatewayRouter
        from llm_council.gateway.types import (
            GatewayRequest,
            GatewayResponse,
            CanonicalMessage,
            ContentBlock,
        )

        router = GatewayRouter()
        request = GatewayRequest(
            model="openai/gpt-4o",
            messages=[
                CanonicalMessage(role="user", content=[ContentBlock(type="text", text="Hello")])
            ],
        )

        mock_response = GatewayResponse(
            content="Hi there!",
            model="openai/gpt-4o",
            status="ok",
            latency_ms=100,
        )

        with patch.object(
            router.gateways["openrouter"], "complete", new_callable=AsyncMock
        ) as mock_complete:
            mock_complete.return_value = mock_response
            response = await router.complete(request)

        assert isinstance(response, GatewayResponse)
        assert response.content == "Hi there!"

    @pytest.mark.asyncio
    async def test_complete_respects_circuit_breaker(self):
        """complete() should respect circuit breaker state."""
        from llm_council.gateway.router import GatewayRouter
        from llm_council.gateway.types import (
            GatewayRequest,
            GatewayResponse,
            CanonicalMessage,
            ContentBlock,
        )
        from llm_council.gateway.errors import CircuitOpenError

        router = GatewayRouter()
        request = GatewayRequest(
            model="openai/gpt-4o",
            messages=[
                CanonicalMessage(role="user", content=[ContentBlock(type="text", text="Hello")])
            ],
        )

        # Trip the circuit breaker
        cb = router._get_circuit_breaker("openrouter")
        for _ in range(cb.failure_threshold):
            cb.record_failure()

        # Should raise CircuitOpenError
        with pytest.raises(CircuitOpenError):
            await router.complete(request)


class TestGatewayRouterCircuitBreakers:
    """Test circuit breaker integration."""

    def test_router_has_per_gateway_circuit_breakers(self):
        """Router should maintain circuit breakers per gateway."""
        from llm_council.gateway.router import GatewayRouter

        router = GatewayRouter()

        cb1 = router._get_circuit_breaker("openrouter")
        cb2 = router._get_circuit_breaker("openrouter")

        # Should return same circuit breaker
        assert cb1 is cb2

    def test_router_creates_circuit_breakers_on_demand(self):
        """Router should create circuit breakers as needed."""
        from llm_council.gateway.router import GatewayRouter

        router = GatewayRouter()

        # Initially no circuit breakers
        cb = router._get_circuit_breaker("test-gateway")

        assert cb is not None
        assert cb.router_id == "test-gateway"


class TestGatewayRouterHealthCheck:
    """Test GatewayRouter health checking."""

    @pytest.mark.asyncio
    async def test_health_check_all_returns_statuses(self):
        """health_check_all() should return status for all gateways."""
        from llm_council.gateway.router import GatewayRouter
        from llm_council.gateway.base import RouterHealth, HealthStatus

        router = GatewayRouter()

        mock_health = RouterHealth(
            router_id="openrouter",
            status=HealthStatus.HEALTHY,
            latency_ms=50,
            last_check=datetime.now(),
        )

        with patch.object(
            router.gateways["openrouter"], "health_check", new_callable=AsyncMock
        ) as mock_hc:
            mock_hc.return_value = mock_health
            results = await router.health_check_all()

        assert "openrouter" in results
        assert results["openrouter"].status == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_get_healthy_gateways(self):
        """get_healthy_gateways() should filter by health status."""
        from llm_council.gateway.router import GatewayRouter
        from llm_council.gateway.base import RouterHealth, HealthStatus

        router = GatewayRouter()

        mock_health = RouterHealth(
            router_id="openrouter",
            status=HealthStatus.HEALTHY,
            latency_ms=50,
            last_check=datetime.now(),
        )

        with patch.object(
            router.gateways["openrouter"], "health_check", new_callable=AsyncMock
        ) as mock_hc:
            mock_hc.return_value = mock_health
            healthy = await router.get_healthy_gateways()

        assert "openrouter" in healthy


class TestGatewayRouterMetrics:
    """Test GatewayRouter metrics and observability."""

    def test_get_stats_returns_gateway_stats(self):
        """get_stats() should return stats for all gateways."""
        from llm_council.gateway.router import GatewayRouter

        router = GatewayRouter()
        stats = router.get_stats()

        assert "gateways" in stats
        assert "openrouter" in stats["gateways"]
        assert "circuit_breaker" in stats["gateways"]["openrouter"]


class TestGatewayRouterParallelQueries:
    """Test parallel query support."""

    @pytest.mark.asyncio
    async def test_complete_many_parallel(self):
        """complete_many() should execute requests in parallel."""
        from llm_council.gateway.router import GatewayRouter
        from llm_council.gateway.types import (
            GatewayRequest,
            GatewayResponse,
            CanonicalMessage,
            ContentBlock,
        )

        router = GatewayRouter()

        requests = [
            GatewayRequest(
                model=f"openai/gpt-4o-{i}",
                messages=[
                    CanonicalMessage(
                        role="user", content=[ContentBlock(type="text", text=f"Query {i}")]
                    )
                ],
            )
            for i in range(3)
        ]

        mock_responses = [
            GatewayResponse(
                content=f"Response {i}",
                model=f"openai/gpt-4o-{i}",
                status="ok",
                latency_ms=100,
            )
            for i in range(3)
        ]

        with patch.object(
            router.gateways["openrouter"], "complete", new_callable=AsyncMock
        ) as mock_complete:
            mock_complete.side_effect = mock_responses
            results = await router.complete_many(requests)

        assert len(results) == 3
        assert all(isinstance(r, GatewayResponse) for r in results)

    @pytest.mark.asyncio
    async def test_complete_many_returns_partial_on_failure(self):
        """complete_many() should return partial results on failures."""
        from llm_council.gateway.router import GatewayRouter
        from llm_council.gateway.types import (
            GatewayRequest,
            GatewayResponse,
            CanonicalMessage,
            ContentBlock,
        )

        router = GatewayRouter()

        requests = [
            GatewayRequest(
                model=f"openai/gpt-4o-{i}",
                messages=[
                    CanonicalMessage(
                        role="user", content=[ContentBlock(type="text", text=f"Query {i}")]
                    )
                ],
            )
            for i in range(2)
        ]

        # First succeeds, second fails
        async def side_effect(req):
            if "0" in req.model:
                return GatewayResponse(
                    content="Success",
                    model=req.model,
                    status="ok",
                    latency_ms=100,
                )
            else:
                return GatewayResponse(
                    content="",
                    model=req.model,
                    status="error",
                    error="Connection failed",
                    latency_ms=50,
                )

        with patch.object(
            router.gateways["openrouter"], "complete", new_callable=AsyncMock
        ) as mock_complete:
            mock_complete.side_effect = side_effect
            results = await router.complete_many(requests)

        assert len(results) == 2
        assert results[0].status == "ok"
        assert results[1].status == "error"
