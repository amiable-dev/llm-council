"""Gateway router for LLM Council multi-router orchestration (ADR-023).

The GatewayRouter orchestrates requests across multiple gateway backends,
with features like:
- Model-based routing (route Claude models to one gateway, GPT to another)
- Circuit breaker integration for fault tolerance
- Fallback chains for reliability
- Parallel execution for council queries
"""

import asyncio
import fnmatch
from typing import Any, Dict, List, Optional

from .base import BaseRouter, HealthStatus, RouterHealth
from .circuit_breaker import CircuitBreaker
from .errors import CircuitOpenError
from .openrouter import OpenRouterGateway
from .types import GatewayRequest, GatewayResponse


class GatewayRouter:
    """Orchestrates requests across multiple gateway backends.

    Provides model-based routing, circuit breaker protection, and
    parallel execution for multi-model council queries.

    Example:
        router = GatewayRouter()
        request = GatewayRequest(
            model="openai/gpt-4o",
            messages=[CanonicalMessage(role="user", content=[ContentBlock(type="text", text="Hello")])]
        )
        response = await router.complete(request)
    """

    def __init__(
        self,
        gateways: Optional[Dict[str, BaseRouter]] = None,
        model_routing: Optional[Dict[str, str]] = None,
        default_gateway: str = "openrouter",
        circuit_breaker_config: Optional[Dict[str, Any]] = None,
    ):
        """Initialize the gateway router.

        Args:
            gateways: Dict mapping gateway_id to gateway instance.
                     If None, creates default OpenRouterGateway.
            model_routing: Dict mapping model patterns to gateway_id.
                          Supports wildcards (e.g., "anthropic/*": "custom").
            default_gateway: Gateway to use when no routing rule matches.
            circuit_breaker_config: Config for circuit breakers.
        """
        # Initialize gateways
        if gateways is not None:
            self.gateways = gateways
        else:
            self.gateways = {"openrouter": OpenRouterGateway()}

        self._model_routing = model_routing or {}
        self._default_gateway = default_gateway
        self._circuit_breaker_config = circuit_breaker_config or {
            "failure_threshold": 5,
            "success_threshold": 1,
            "timeout_seconds": 60,
        }

        # Circuit breakers per gateway
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}

    def get_gateway_for_model(self, model: str) -> BaseRouter:
        """Get the appropriate gateway for a model.

        Args:
            model: Model identifier (e.g., "openai/gpt-4o").

        Returns:
            The gateway to use for this model.
        """
        # Check routing rules
        for pattern, gateway_id in self._model_routing.items():
            if fnmatch.fnmatch(model, pattern):
                if gateway_id in self.gateways:
                    return self.gateways[gateway_id]

        # Fall back to default gateway
        return self.gateways.get(
            self._default_gateway,
            next(iter(self.gateways.values()))
        )

    def _get_circuit_breaker(self, gateway_id: str) -> CircuitBreaker:
        """Get or create circuit breaker for a gateway.

        Args:
            gateway_id: Gateway identifier.

        Returns:
            CircuitBreaker for the gateway.
        """
        if gateway_id not in self._circuit_breakers:
            self._circuit_breakers[gateway_id] = CircuitBreaker(
                router_id=gateway_id,
                **self._circuit_breaker_config,
            )
        return self._circuit_breakers[gateway_id]

    def _get_gateway_id(self, gateway: BaseRouter) -> str:
        """Get the ID for a gateway instance."""
        for gateway_id, gw in self.gateways.items():
            if gw is gateway:
                return gateway_id
        return "unknown"

    async def complete(self, request: GatewayRequest) -> GatewayResponse:
        """Route and execute a completion request.

        Args:
            request: Gateway request with model and messages.

        Returns:
            GatewayResponse from the selected gateway.

        Raises:
            CircuitOpenError: If the circuit breaker is open.
        """
        gateway = self.get_gateway_for_model(request.model)
        gateway_id = self._get_gateway_id(gateway)
        cb = self._get_circuit_breaker(gateway_id)

        # Check circuit breaker
        if not cb.allow_request():
            raise CircuitOpenError(
                f"Circuit is open for gateway {gateway_id}",
                router_id=gateway_id,
            )

        try:
            response = await gateway.complete(request)

            # Record success/failure based on response status
            if response.status == "ok":
                cb.record_success()
            elif response.status in ("error", "timeout"):
                cb.record_failure()

            return response
        except Exception as e:
            cb.record_failure()
            raise

    async def complete_many(
        self,
        requests: List[GatewayRequest],
    ) -> List[GatewayResponse]:
        """Execute multiple requests in parallel.

        Args:
            requests: List of gateway requests.

        Returns:
            List of responses (same order as requests).
        """
        tasks = [self.complete(req) for req in requests]
        # Use gather with return_exceptions to get all results
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to error responses
        responses = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                responses.append(GatewayResponse(
                    content="",
                    model=requests[i].model,
                    status="error",
                    error=str(result),
                ))
            else:
                responses.append(result)

        return responses

    async def health_check_all(self) -> Dict[str, RouterHealth]:
        """Check health of all gateways.

        Returns:
            Dict mapping gateway_id to health status.
        """
        results = {}
        for gateway_id, gateway in self.gateways.items():
            try:
                health = await gateway.health_check()
                results[gateway_id] = health
            except Exception as e:
                results[gateway_id] = RouterHealth(
                    router_id=gateway_id,
                    status=HealthStatus.UNHEALTHY,
                    latency_ms=0,
                    last_check=None,  # type: ignore
                    error_message=str(e),
                )
        return results

    async def get_healthy_gateways(self) -> List[str]:
        """Get list of healthy gateway IDs.

        Returns:
            List of gateway IDs with healthy status.
        """
        health_results = await self.health_check_all()
        return [
            gateway_id
            for gateway_id, health in health_results.items()
            if health.status == HealthStatus.HEALTHY
        ]

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics for all gateways and circuit breakers.

        Returns:
            Dict with gateway stats.
        """
        stats = {"gateways": {}}

        for gateway_id in self.gateways:
            cb = self._get_circuit_breaker(gateway_id)
            stats["gateways"][gateway_id] = {
                "circuit_breaker": cb.get_stats(),
            }

        return stats
