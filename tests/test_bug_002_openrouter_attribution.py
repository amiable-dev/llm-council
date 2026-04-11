import pytest
import httpx
import uuid
from unittest.mock import MagicMock, patch
from llm_council.metadata.openrouter_client import OpenRouterClient
from llm_council.openrouter import query_model_with_status
from llm_council.council import run_full_council


@pytest.mark.asyncio
async def test_metadata_headers_sent():
    """Verify that identity headers are sent during metadata discovery."""
    client = OpenRouterClient(api_key="test-key")

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": []}
        mock_get.return_value = mock_response
        await client.fetch_models()

        # Check call args
        args, kwargs = mock_get.call_args
        headers = kwargs.get("headers", {})

        # Identity Headers
        assert headers.get("X-Title") == "LLM Council", "Missing X-Title in metadata call"
        assert headers.get("HTTP-Referer") == "https://github.com/mgammarino/llm-council", (
            "Missing Correct Referer in metadata call"
        )


@pytest.mark.asyncio
async def test_completion_headers_sent():
    """Verify that identity and tracing headers are sent during completion queries."""
    model = "openai/gpt-4o"
    messages = [{"role": "user", "content": "Hello"}]
    test_council_id = str(uuid.uuid4())

    with patch("httpx.AsyncClient.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hi"}}],
            "usage": {"total_tokens": 10},
        }
        mock_post.return_value = mock_response

        # Test direct query with council_id
        await query_model_with_status(model, messages, council_id=test_council_id)

        args, kwargs = mock_post.call_args
        headers = kwargs.get("headers", {})

        # Identity Headers
        assert headers.get("X-Title") == "LLM Council"
        assert headers.get("HTTP-Referer") == "https://github.com/mgammarino/llm-council"

        # Tracing Header
        assert headers.get("X-Council-ID") == test_council_id


@pytest.mark.asyncio
async def test_council_trace_propagation():
    """Verify that session_id from council.py propagates to X-Council-ID header."""
    # We'll use high-level run_full_council and intercept the Stage 1 HTTP calls
    # We don't need the whole thing to finish correctly, just to see the headers
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Something"}}],
            "usage": {"total_tokens": 10},
        }
        mock_post.return_value = mock_response

        # Run council and catch the orchestration exception if it fails later
        try:
            await run_full_council("Test query")
        except Exception:
            # We only care about the headers of the calls made before failure
            pass
        # All calls in the same council should share the same X-Council-ID
        all_calls = mock_post.call_args_list
        assert len(all_calls) > 0, "No calls made by council"

        ids = set()
        for i, call in enumerate(all_calls):
            _args, kwargs = call
            headers = kwargs.get("headers", {})
            print(f"Call {i} kwargs keys: {list(kwargs.keys())}")
            print(f"Call {i} headers: {list(headers.keys()) if headers else 'None'}")
            council_id = headers.get("X-Council-ID") if headers else None
            payload = kwargs.get("json", {})
            model = payload.get("model", "unknown")
            print(f"Call {i}: model={model}, X-Council-ID={council_id}")
            assert council_id is not None, (
                f"Call {i} ({model}) in the council pipeline missing X-Council-ID. Headers: {headers}"
            )
            ids.add(council_id)

        assert len(ids) == 1, f"Council session ID changed during deliberation: {ids}"
