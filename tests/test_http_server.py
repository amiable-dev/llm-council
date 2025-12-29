"""Tests for HTTP server (ADR-009).

These tests require the optional [http] dependencies.
Install with: pip install "llm-council[http]"
"""

import os
from unittest.mock import AsyncMock, patch

import pytest

# Skip all tests in this module if HTTP deps not installed
fastapi = pytest.importorskip(
    "fastapi",
    reason="HTTP dependencies not installed. Install with: pip install 'llm-council[http]'",
)
from fastapi.testclient import TestClient


class TestHealthEndpoint:
    """Tests for the /health endpoint."""

    def test_health_returns_ok(self):
        """Health endpoint should return status ok."""
        from llm_council.http_server import app

        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert response.json()["service"] == "llm-council-local"


class TestCouncilRunEndpoint:
    """Tests for the /v1/council/run endpoint."""

    def test_requires_api_key(self):
        """Should return 400 if no API key provided."""
        from llm_council.http_server import app

        # Ensure no env var is set
        with patch.dict(os.environ, {}, clear=True):
            client = TestClient(app)
            response = client.post("/v1/council/run", json={"prompt": "test question"})

            assert response.status_code == 400
            assert "API key required" in response.json()["detail"]

    def test_accepts_api_key_in_request(self):
        """Should accept API key in request body."""
        from llm_council.http_server import app

        mock_result = (
            [{"model": "test", "response": "response1"}],
            [{"model": "test", "ranking": "1. A", "parsed_ranking": {"ranking": ["A"]}}],
            {"final_answer": "synthesized answer"},
            {"aggregate_rankings": []},
        )

        with patch("llm_council.http_server.run_full_council", new_callable=AsyncMock) as mock:
            mock.return_value = mock_result
            client = TestClient(app)
            response = client.post(
                "/v1/council/run",
                json={"prompt": "test question", "api_key": "sk-test-key"},
            )

            assert response.status_code == 200
            assert "stage1" in response.json()
            assert "stage2" in response.json()
            assert "stage3" in response.json()
            assert "metadata" in response.json()

    def test_accepts_api_key_from_env(self):
        """Should accept API key from environment variable."""
        from llm_council.http_server import app

        mock_result = (
            [{"model": "test", "response": "response1"}],
            [{"model": "test", "ranking": "1. A", "parsed_ranking": {"ranking": ["A"]}}],
            {"final_answer": "synthesized answer"},
            {"aggregate_rankings": []},
        )

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-env-key"}):
            with patch("llm_council.http_server.run_full_council", new_callable=AsyncMock) as mock:
                mock.return_value = mock_result
                client = TestClient(app)
                response = client.post("/v1/council/run", json={"prompt": "test question"})

                assert response.status_code == 200

    def test_returns_council_result_structure(self):
        """Response should contain stage1, stage2, stage3, metadata."""
        from llm_council.http_server import app

        mock_stage1 = [{"model": "openai/gpt-4", "response": "Answer 1"}]
        mock_stage2 = [
            {
                "model": "anthropic/claude",
                "ranking": "FINAL RANKING:\n1. Response A",
                "parsed_ranking": {"ranking": ["Response A"], "scores": {}},
            }
        ]
        mock_stage3 = {"final_answer": "The synthesized answer", "model": "chairman"}
        mock_metadata = {
            "aggregate_rankings": [{"model": "openai/gpt-4", "rank": 1}],
            "label_to_model": {"Response A": "openai/gpt-4"},
        }

        with patch("llm_council.http_server.run_full_council", new_callable=AsyncMock) as mock:
            mock.return_value = (mock_stage1, mock_stage2, mock_stage3, mock_metadata)

            client = TestClient(app)
            response = client.post(
                "/v1/council/run",
                json={"prompt": "What is the best approach?", "api_key": "sk-test"},
            )

            data = response.json()
            assert data["stage1"] == mock_stage1
            assert data["stage2"] == mock_stage2
            assert data["stage3"] == mock_stage3
            assert data["metadata"] == mock_metadata

    def test_prompt_is_required(self):
        """Should return 422 if prompt is missing."""
        from llm_council.http_server import app

        client = TestClient(app)
        response = client.post("/v1/council/run", json={"api_key": "sk-test"})

        assert response.status_code == 422  # Validation error

    def test_optional_models_parameter(self):
        """Should accept optional models list."""
        from llm_council.http_server import app

        mock_result = ([], [], {}, {})

        with patch("llm_council.http_server.run_full_council", new_callable=AsyncMock) as mock:
            mock.return_value = mock_result
            client = TestClient(app)
            response = client.post(
                "/v1/council/run",
                json={
                    "prompt": "test",
                    "api_key": "sk-test",
                    "models": ["openai/gpt-4", "anthropic/claude-3-opus"],
                },
            )

            assert response.status_code == 200
            # Verify models were passed to run_full_council
            mock.assert_called_once()
            call_kwargs = mock.call_args
            assert call_kwargs[1].get("models") == ["openai/gpt-4", "anthropic/claude-3-opus"]


class TestOpenAPISpec:
    """Tests for OpenAPI specification."""

    def test_openapi_spec_available(self):
        """OpenAPI spec should be available at /openapi.json."""
        from llm_council.http_server import app

        client = TestClient(app)
        response = client.get("/openapi.json")

        assert response.status_code == 200
        spec = response.json()
        assert "openapi" in spec
        assert "paths" in spec
        assert "/v1/council/run" in spec["paths"]
        assert "/health" in spec["paths"]

    def test_docs_available(self):
        """Interactive docs should be available at /docs."""
        from llm_council.http_server import app

        client = TestClient(app)
        response = client.get("/docs")

        assert response.status_code == 200


class TestStatelessDesign:
    """Tests verifying stateless design per ADR-009."""

    def test_no_persistent_state_between_requests(self):
        """Each request should be independent (no state carried over)."""
        from llm_council.http_server import app

        mock_result = (
            [{"model": "test", "response": "response"}],
            [{"model": "test", "ranking": "1. A", "parsed_ranking": {"ranking": ["A"]}}],
            {"final_answer": "answer"},
            {},
        )

        with patch("llm_council.http_server.run_full_council", new_callable=AsyncMock) as mock:
            mock.return_value = mock_result
            client = TestClient(app)

            # Make two requests
            response1 = client.post(
                "/v1/council/run", json={"prompt": "question 1", "api_key": "sk-test"}
            )
            response2 = client.post(
                "/v1/council/run", json={"prompt": "question 2", "api_key": "sk-test"}
            )

            # Both should succeed independently
            assert response1.status_code == 200
            assert response2.status_code == 200

            # Each request should have called run_full_council
            assert mock.call_count == 2

    def test_no_session_or_cookies(self):
        """Server should not set any session cookies."""
        from llm_council.http_server import app

        client = TestClient(app)
        response = client.get("/health")

        # No session cookies should be set
        assert "set-cookie" not in response.headers


class TestWebhookIntegration:
    """Tests for webhook parameter support in HTTP API (Issue #76)."""

    def test_accepts_webhook_url_parameter(self):
        """CouncilRequest should accept webhook_url parameter."""
        from llm_council.http_server import app

        mock_result = ([], [], {}, {})

        with patch("llm_council.http_server.run_full_council", new_callable=AsyncMock) as mock:
            mock.return_value = mock_result
            client = TestClient(app)
            response = client.post(
                "/v1/council/run",
                json={
                    "prompt": "test",
                    "api_key": "sk-test",
                    "webhook_url": "https://example.com/webhook",
                },
            )

            assert response.status_code == 200

    def test_accepts_webhook_events_parameter(self):
        """CouncilRequest should accept webhook_events parameter."""
        from llm_council.http_server import app

        mock_result = ([], [], {}, {})

        with patch("llm_council.http_server.run_full_council", new_callable=AsyncMock) as mock:
            mock.return_value = mock_result
            client = TestClient(app)
            response = client.post(
                "/v1/council/run",
                json={
                    "prompt": "test",
                    "api_key": "sk-test",
                    "webhook_url": "https://example.com/webhook",
                    "webhook_events": ["council.complete", "council.error"],
                },
            )

            assert response.status_code == 200

    def test_accepts_webhook_secret_parameter(self):
        """CouncilRequest should accept webhook_secret parameter."""
        from llm_council.http_server import app

        mock_result = ([], [], {}, {})

        with patch("llm_council.http_server.run_full_council", new_callable=AsyncMock) as mock:
            mock.return_value = mock_result
            client = TestClient(app)
            response = client.post(
                "/v1/council/run",
                json={
                    "prompt": "test",
                    "api_key": "sk-test",
                    "webhook_url": "https://example.com/webhook",
                    "webhook_secret": "my-hmac-secret",
                },
            )

            assert response.status_code == 200

    def test_webhook_config_passed_to_council(self):
        """Webhook config should be passed to run_full_council."""
        from llm_council.http_server import app

        mock_result = ([], [], {}, {})

        with patch("llm_council.http_server.run_full_council", new_callable=AsyncMock) as mock:
            mock.return_value = mock_result
            client = TestClient(app)
            response = client.post(
                "/v1/council/run",
                json={
                    "prompt": "test",
                    "api_key": "sk-test",
                    "webhook_url": "https://example.com/webhook",
                    "webhook_events": ["council.complete"],
                    "webhook_secret": "secret123",
                },
            )

            assert response.status_code == 200

            # Verify webhook_config was passed
            mock.assert_called_once()
            call_kwargs = mock.call_args.kwargs
            assert "webhook_config" in call_kwargs
            webhook_config = call_kwargs["webhook_config"]
            assert webhook_config.url == "https://example.com/webhook"
            assert webhook_config.events == ["council.complete"]
            assert webhook_config.secret == "secret123"

    def test_webhook_url_without_events_uses_defaults(self):
        """If webhook_url provided without events, use default events."""
        from llm_council.http_server import app

        mock_result = ([], [], {}, {})

        with patch("llm_council.http_server.run_full_council", new_callable=AsyncMock) as mock:
            mock.return_value = mock_result
            client = TestClient(app)
            response = client.post(
                "/v1/council/run",
                json={
                    "prompt": "test",
                    "api_key": "sk-test",
                    "webhook_url": "https://example.com/webhook",
                },
            )

            assert response.status_code == 200

            # Verify default events were used
            call_kwargs = mock.call_args.kwargs
            webhook_config = call_kwargs.get("webhook_config")
            assert webhook_config is not None
            # Default events should include at least council.complete
            assert "council.complete" in webhook_config.events

    def test_no_webhook_config_when_url_not_provided(self):
        """If no webhook_url, webhook_config should be None."""
        from llm_council.http_server import app

        mock_result = ([], [], {}, {})

        with patch("llm_council.http_server.run_full_council", new_callable=AsyncMock) as mock:
            mock.return_value = mock_result
            client = TestClient(app)
            response = client.post(
                "/v1/council/run",
                json={
                    "prompt": "test",
                    "api_key": "sk-test",
                },
            )

            assert response.status_code == 200

            # webhook_config should be None or not passed
            call_kwargs = mock.call_args.kwargs
            webhook_config = call_kwargs.get("webhook_config")
            assert webhook_config is None
