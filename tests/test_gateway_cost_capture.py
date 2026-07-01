"""Gateways populate UsageInfo cost fields via the CostResolver (ADR-011 #360).

OpenRouter returns an authoritative `usage.cost` on every response; the gateway
must capture it (it was previously discarded) and stamp cost_source="provider".
Ollama is local, so its calls resolve to cost 0 / "local_zero".
"""

from unittest.mock import AsyncMock, patch

from llm_council.gateway.openrouter import OpenRouterGateway
from llm_council.gateway.types import CanonicalMessage, ContentBlock, GatewayRequest


def _req(model="openai/gpt-4o"):
    return GatewayRequest(
        model=model,
        messages=[CanonicalMessage(role="user", content=[ContentBlock(type="text", text="hi")])],
    )


class TestOpenRouterCostCapture:
    async def test_captures_provider_cost_and_cached_tokens(self):
        gw = OpenRouterGateway()
        fake = {
            "status": "ok",
            "content": "hi",
            "latency_ms": 12,
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150,
                "cost": 0.0012,
                "cached_tokens": 20,
            },
        }
        with patch.object(gw, "_query_openrouter", new=AsyncMock(return_value=fake)):
            resp = await gw.complete(_req())

        assert resp.usage is not None
        assert resp.usage.cost_usd == 0.0012
        assert resp.usage.cost_source == "provider"
        assert resp.usage.cached_tokens == 20

    async def test_no_provider_cost_leaves_cost_unknown(self):
        # If OpenRouter omits cost, there's no ground truth and (without a
        # pricing lookup wired at this layer) cost stays unresolved.
        gw = OpenRouterGateway()
        fake = {
            "status": "ok",
            "content": "hi",
            "latency_ms": 12,
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        }
        with patch.object(gw, "_query_openrouter", new=AsyncMock(return_value=fake)):
            resp = await gw.complete(_req())

        assert resp.usage is not None
        assert resp.usage.cost_usd is None
        assert resp.usage.cost_source is None
        assert resp.usage.cached_tokens == 0


class TestDirectCostCapture:
    async def test_direct_uses_registry_estimate(self, monkeypatch):
        from llm_council.gateway import direct as direct_mod
        from llm_council.gateway.cost_resolver import CostResolver
        from llm_council.gateway.direct import DirectGateway

        # Inject a key so complete() doesn't short-circuit with auth_error.
        gw = DirectGateway(provider_keys={"openai": "test-key"})
        # Deterministic pricing so the estimate is exact.
        monkeypatch.setattr(
            direct_mod,
            "_COST_RESOLVER",
            CostResolver(pricing_lookup=lambda m: {"prompt": 0.0025, "completion": 0.01}),
        )
        fake = {
            "status": "ok",
            "content": "hi",
            "latency_ms": 5,
            "usage": {"prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500},
        }
        with patch.object(gw, "_query_provider", new=AsyncMock(return_value=fake)):
            resp = await gw.complete(_req())

        assert resp.usage.cost_usd == 0.0075
        assert resp.usage.cost_source == "registry_estimate"


class TestOllamaCostCapture:
    async def test_ollama_is_local_zero(self):
        from llm_council.gateway.ollama import OllamaGateway

        gw = OllamaGateway()
        fake = {
            "status": "ok",
            "content": "hi",
            "latency_ms": 5,
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        }
        with patch.object(gw, "_query_ollama", new=AsyncMock(return_value=fake)):
            resp = await gw.complete(_req("ollama/llama3"))

        assert resp.usage.cost_usd == 0.0
        assert resp.usage.cost_source == "local_zero"


class TestRequestyCostCapture:
    async def test_requesty_prefers_provider_cost(self):
        from llm_council.gateway.requesty import RequestyGateway

        gw = RequestyGateway(api_key="test")
        fake = {
            "status": "ok",
            "content": "hi",
            "latency_ms": 5,
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150,
                "cost": 0.002,
                "cached_tokens": 0,
            },
        }
        with patch.object(gw, "_query_requesty", new=AsyncMock(return_value=fake)):
            resp = await gw.complete(_req())

        assert resp.usage.cost_usd == 0.002
        assert resp.usage.cost_source == "provider"
