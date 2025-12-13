"""Tests for llm_council OpenRouter client (ADR-012 reliability features)."""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import httpx


def test_status_constants():
    """Test that status constants are defined."""
    from llm_council.openrouter import (
        STATUS_OK,
        STATUS_TIMEOUT,
        STATUS_RATE_LIMITED,
        STATUS_AUTH_ERROR,
        STATUS_ERROR,
    )

    assert STATUS_OK == "ok"
    assert STATUS_TIMEOUT == "timeout"
    assert STATUS_RATE_LIMITED == "rate_limited"
    assert STATUS_AUTH_ERROR == "auth_error"
    assert STATUS_ERROR == "error"


@pytest.mark.asyncio
async def test_query_model_with_status_success():
    """Test query_model_with_status returns structured result on success."""
    from llm_council.openrouter import query_model_with_status, STATUS_OK

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "Test response"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    }
    mock_response.raise_for_status = MagicMock()

    with patch('llm_council.openrouter.OPENROUTER_API_KEY', 'test-key'), \
         patch('httpx.AsyncClient') as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

        result = await query_model_with_status(
            "test-model",
            [{"role": "user", "content": "test"}]
        )

        assert result["status"] == STATUS_OK
        assert result["content"] == "Test response"
        assert "latency_ms" in result
        assert result["usage"]["total_tokens"] == 30


@pytest.mark.asyncio
async def test_query_model_with_status_timeout():
    """Test query_model_with_status handles timeout correctly."""
    from llm_council.openrouter import query_model_with_status, STATUS_TIMEOUT

    with patch('llm_council.openrouter.OPENROUTER_API_KEY', 'test-key'), \
         patch('httpx.AsyncClient') as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            side_effect=httpx.TimeoutException("Connection timeout")
        )

        result = await query_model_with_status(
            "test-model",
            [{"role": "user", "content": "test"}],
            timeout=5.0
        )

        assert result["status"] == STATUS_TIMEOUT
        assert "timeout" in result["error"].lower()
        assert "latency_ms" in result


@pytest.mark.asyncio
async def test_query_model_with_status_rate_limited():
    """Test query_model_with_status handles rate limiting (429)."""
    from llm_council.openrouter import query_model_with_status, STATUS_RATE_LIMITED

    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_response.headers = {"Retry-After": "30"}

    with patch('llm_council.openrouter.OPENROUTER_API_KEY', 'test-key'), \
         patch('httpx.AsyncClient') as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

        result = await query_model_with_status(
            "test-model",
            [{"role": "user", "content": "test"}]
        )

        assert result["status"] == STATUS_RATE_LIMITED
        assert result["retry_after"] == 30
        assert "latency_ms" in result


@pytest.mark.asyncio
async def test_query_model_with_status_auth_error():
    """Test query_model_with_status handles auth errors (401/403)."""
    from llm_council.openrouter import query_model_with_status, STATUS_AUTH_ERROR

    mock_response = MagicMock()
    mock_response.status_code = 401

    with patch('llm_council.openrouter.OPENROUTER_API_KEY', 'test-key'), \
         patch('httpx.AsyncClient') as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

        result = await query_model_with_status(
            "test-model",
            [{"role": "user", "content": "test"}]
        )

        assert result["status"] == STATUS_AUTH_ERROR
        assert "authentication" in result["error"].lower()


@pytest.mark.asyncio
async def test_query_model_with_status_generic_error():
    """Test query_model_with_status handles generic errors."""
    from llm_council.openrouter import query_model_with_status, STATUS_ERROR

    with patch('llm_council.openrouter.OPENROUTER_API_KEY', 'test-key'), \
         patch('httpx.AsyncClient') as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            side_effect=Exception("Network error")
        )

        result = await query_model_with_status(
            "test-model",
            [{"role": "user", "content": "test"}]
        )

        assert result["status"] == STATUS_ERROR
        assert "Network error" in result["error"]
        assert "latency_ms" in result


@pytest.mark.asyncio
async def test_query_model_backwards_compatible():
    """Test that query_model still returns None on failure (backwards compatibility)."""
    from llm_council.openrouter import query_model

    with patch('llm_council.openrouter.OPENROUTER_API_KEY', 'test-key'), \
         patch('httpx.AsyncClient') as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            side_effect=httpx.TimeoutException("Connection timeout")
        )

        result = await query_model(
            "test-model",
            [{"role": "user", "content": "test"}]
        )

        assert result is None


@pytest.mark.asyncio
async def test_query_models_with_progress():
    """Test query_models_with_progress calls progress callback."""
    from llm_council.openrouter import query_models_with_progress, STATUS_OK

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "Test"}}],
        "usage": {},
    }
    mock_response.raise_for_status = MagicMock()

    progress_calls = []

    async def track_progress(completed, total, message):
        progress_calls.append((completed, total, message))

    with patch('llm_council.openrouter.OPENROUTER_API_KEY', 'test-key'), \
         patch('httpx.AsyncClient') as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

        results = await query_models_with_progress(
            ["model-a", "model-b"],
            [{"role": "user", "content": "test"}],
            on_progress=track_progress
        )

        # Should have initial progress + one per model
        assert len(progress_calls) >= 3  # 0/2, 1/2, 2/2
        assert results["model-a"]["status"] == STATUS_OK
        assert results["model-b"]["status"] == STATUS_OK


@pytest.mark.asyncio
async def test_query_models_with_progress_no_callback():
    """Test query_models_with_progress works without callback."""
    from llm_council.openrouter import query_models_with_progress, STATUS_OK

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "Test"}}],
        "usage": {},
    }
    mock_response.raise_for_status = MagicMock()

    with patch('llm_council.openrouter.OPENROUTER_API_KEY', 'test-key'), \
         patch('httpx.AsyncClient') as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

        results = await query_models_with_progress(
            ["model-a"],
            [{"role": "user", "content": "test"}],
            on_progress=None  # No callback
        )

        assert results["model-a"]["status"] == STATUS_OK
