import pytest
from unittest.mock import AsyncMock, patch
from llm_council.gateway.openrouter import OpenRouterGateway
from llm_council.gateway.types import GatewayRequest, CanonicalMessage, ContentBlock
from llm_council import model_constants as mc


@pytest.mark.anyio
async def test_openrouter_gateway_extracts_cost():
    # Mock the internal query_model_with_status method
    mock_response = {
        "status": "ok",
        "content": "Test response",
        "latency_ms": 100,
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
            "total_cost": 0.00015,
        },
    }

    with patch(
        "llm_council.gateway.openrouter.OpenRouterGateway._query_openrouter",
        return_value=mock_response,
    ):
        gateway = OpenRouterGateway(api_key="fake")
        msg = CanonicalMessage(role="user", content=[ContentBlock(type="text", text="test prompt")])
        request = GatewayRequest(messages=[msg], model=mc.OPENAI_LOW)

        response = await gateway.complete(request)

        assert getattr(response.usage, "total_cost", 0.0) == 0.00015
        assert response.usage.total_tokens == 30
