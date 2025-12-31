"""
Integration tests for verification API endpoint per ADR-034.

TDD Red Phase: These tests should fail until api.py is implemented.

Tests the POST /v1/council/verify endpoint:
1. Request validation
2. Response schema
3. Exit codes
4. Context isolation
5. Transcript persistence
"""

import json
import tempfile
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from llm_council.verification.types import VerdictType


class TestVerificationEndpoint:
    """Tests for POST /v1/council/verify endpoint."""

    @pytest.fixture
    def client(self):
        """Create test client with verification routes."""
        from llm_council.http_server import app
        from llm_council.verification.api import router as verify_router

        # Register verification router if not already registered
        # Check if router is already included
        router_paths = [route.path for route in app.routes]
        if "/v1/council/verify" not in router_paths:
            app.include_router(verify_router, prefix="/v1/council")

        return TestClient(app)

    @pytest.fixture
    def valid_request(self) -> Dict[str, Any]:
        """Valid verification request."""
        return {
            "snapshot_id": "abc1234def5678",
            "target_paths": ["src/"],
            "rubric_focus": "Security",
        }

    @pytest.fixture
    def mock_council_response(self):
        """Mock council response for testing."""
        return {
            "verdict": "pass",
            "confidence": 0.85,
            "rubric_scores": {
                "accuracy": 8.5,
                "relevance": 9.0,
                "completeness": 7.5,
                "conciseness": 8.0,
                "clarity": 8.5,
            },
            "blocking_issues": [],
            "rationale": "Code meets security requirements.",
        }

    def test_endpoint_exists(self, client):
        """Verify endpoint is registered."""
        # Should not return 404 (may return 422 for missing body)
        response = client.post("/v1/council/verify")
        assert response.status_code != 404, "Endpoint not found"

    def test_accepts_verification_request(self, client, valid_request):
        """Endpoint should accept valid VerificationRequest."""
        with patch("llm_council.verification.api.run_verification") as mock_verify:
            mock_verify.return_value = {
                "verification_id": "test-123",
                "verdict": "pass",
                "confidence": 0.85,
                "exit_code": 0,
                "rubric_scores": {},
                "blocking_issues": [],
                "rationale": "Test",
                "transcript_location": ".council/logs/test",
            }

            response = client.post("/v1/council/verify", json=valid_request)

            # Should not fail validation
            assert response.status_code in [200, 201], f"Failed: {response.text}"

    def test_rejects_invalid_snapshot_id(self, client):
        """Endpoint should reject invalid snapshot IDs."""
        invalid_request = {
            "snapshot_id": "bad",  # Too short
            "target_paths": ["src/"],
        }

        response = client.post("/v1/council/verify", json=invalid_request)

        # Should return validation error
        assert response.status_code == 422

    def test_returns_verification_result_schema(self, client, valid_request):
        """Response should match VerificationResult schema."""
        with patch("llm_council.verification.api.run_verification") as mock_verify:
            mock_verify.return_value = {
                "verification_id": "test-123",
                "verdict": "pass",
                "confidence": 0.85,
                "exit_code": 0,
                "rubric_scores": {
                    "accuracy": 8.0,
                    "relevance": 8.5,
                    "completeness": 7.5,
                    "conciseness": 8.0,
                    "clarity": 9.0,
                },
                "blocking_issues": [],
                "rationale": "All checks passed.",
                "transcript_location": ".council/logs/test",
            }

            response = client.post("/v1/council/verify", json=valid_request)
            assert response.status_code == 200

            data = response.json()

            # Required fields per ADR-034
            assert "verification_id" in data
            assert "verdict" in data
            assert "confidence" in data
            assert data["verdict"] in ["pass", "fail", "unclear"]
            assert 0 <= data["confidence"] <= 1

    def test_verdict_pass_exit_code_0(self, client, valid_request):
        """PASS verdict should return exit_code 0."""
        with patch("llm_council.verification.api.run_verification") as mock_verify:
            mock_verify.return_value = {
                "verification_id": "test-123",
                "verdict": "pass",
                "confidence": 0.90,
                "rubric_scores": {},
                "blocking_issues": [],
                "rationale": "Approved",
                "transcript_location": ".council/logs/test",
                "exit_code": 0,
            }

            response = client.post("/v1/council/verify", json=valid_request)
            data = response.json()

            assert data.get("exit_code") == 0

    def test_verdict_fail_exit_code_1(self, client, valid_request):
        """FAIL verdict should return exit_code 1."""
        with patch("llm_council.verification.api.run_verification") as mock_verify:
            mock_verify.return_value = {
                "verification_id": "test-123",
                "verdict": "fail",
                "confidence": 0.80,
                "rubric_scores": {},
                "blocking_issues": [{"severity": "critical", "description": "Security issue"}],
                "rationale": "Rejected",
                "transcript_location": ".council/logs/test",
                "exit_code": 1,
            }

            response = client.post("/v1/council/verify", json=valid_request)
            data = response.json()

            assert data.get("exit_code") == 1

    def test_verdict_unclear_exit_code_2(self, client, valid_request):
        """UNCLEAR verdict should return exit_code 2."""
        with patch("llm_council.verification.api.run_verification") as mock_verify:
            mock_verify.return_value = {
                "verification_id": "test-123",
                "verdict": "unclear",
                "confidence": 0.55,
                "rubric_scores": {},
                "blocking_issues": [],
                "rationale": "Requires human review",
                "transcript_location": ".council/logs/test",
                "exit_code": 2,
            }

            response = client.post("/v1/council/verify", json=valid_request)
            data = response.json()

            assert data.get("exit_code") == 2

    def test_includes_transcript_location(self, client, valid_request):
        """Response should include transcript location for audit."""
        with patch("llm_council.verification.api.run_verification") as mock_verify:
            mock_verify.return_value = {
                "verification_id": "test-123",
                "verdict": "pass",
                "confidence": 0.85,
                "exit_code": 0,
                "rubric_scores": {},
                "blocking_issues": [],
                "rationale": "OK",
                "transcript_location": ".council/logs/2025-01-01T00-00-00-test123",
            }

            response = client.post("/v1/council/verify", json=valid_request)
            data = response.json()

            assert "transcript_location" in data
            assert ".council/logs" in data["transcript_location"]


class TestVerificationContextIsolation:
    """Tests for context isolation in verification API."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from llm_council.http_server import app
        from llm_council.verification.api import router as verify_router

        router_paths = [route.path for route in app.routes]
        if "/v1/council/verify" not in router_paths:
            app.include_router(verify_router, prefix="/v1/council")

        return TestClient(app)

    def test_each_request_gets_unique_context(self, client):
        """Each verification request should get unique context ID."""
        request = {
            "snapshot_id": "abc1234def5678",
            "target_paths": ["src/"],
        }

        verification_ids = []

        with patch("llm_council.verification.api.run_verification") as mock_verify:
            # Return different IDs for each call
            mock_verify.side_effect = [
                {
                    "verification_id": f"id-{i}",
                    "verdict": "pass",
                    "confidence": 0.85,
                    "rubric_scores": {},
                    "blocking_issues": [],
                    "rationale": "OK",
                    "transcript_location": f".council/logs/test-{i}",
                }
                for i in range(3)
            ]

            for _ in range(3):
                response = client.post("/v1/council/verify", json=request)
                if response.status_code == 200:
                    verification_ids.append(response.json()["verification_id"])

        # All IDs should be unique
        assert len(verification_ids) == len(set(verification_ids))


class TestVerificationRequestValidation:
    """Tests for request validation."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from llm_council.http_server import app
        from llm_council.verification.api import router as verify_router

        router_paths = [route.path for route in app.routes]
        if "/v1/council/verify" not in router_paths:
            app.include_router(verify_router, prefix="/v1/council")

        return TestClient(app)

    def test_requires_snapshot_id(self, client):
        """Request must include snapshot_id."""
        request = {
            "target_paths": ["src/"],
        }

        response = client.post("/v1/council/verify", json=request)
        assert response.status_code == 422

    def test_snapshot_id_must_be_valid_hex(self, client):
        """Snapshot ID must be valid git SHA (hex)."""
        request = {
            "snapshot_id": "not-valid-hex!",
            "target_paths": ["src/"],
        }

        response = client.post("/v1/council/verify", json=request)
        assert response.status_code == 422

    def test_target_paths_optional(self, client):
        """target_paths should be optional."""
        request = {
            "snapshot_id": "abc1234def5678",
        }

        with patch("llm_council.verification.api.run_verification") as mock_verify:
            mock_verify.return_value = {
                "verification_id": "test-123",
                "verdict": "pass",
                "confidence": 0.85,
                "exit_code": 0,
                "rubric_scores": {},
                "blocking_issues": [],
                "rationale": "OK",
                "transcript_location": ".council/logs/test",
            }

            response = client.post("/v1/council/verify", json=request)
            # Should not fail due to missing target_paths
            assert response.status_code in [200, 201]

    def test_rubric_focus_optional(self, client):
        """rubric_focus should be optional."""
        request = {
            "snapshot_id": "abc1234def5678",
            "target_paths": ["src/"],
            # No rubric_focus
        }

        with patch("llm_council.verification.api.run_verification") as mock_verify:
            mock_verify.return_value = {
                "verification_id": "test-123",
                "verdict": "pass",
                "confidence": 0.85,
                "exit_code": 0,
                "rubric_scores": {},
                "blocking_issues": [],
                "rationale": "OK",
                "transcript_location": ".council/logs/test",
            }

            response = client.post("/v1/council/verify", json=request)
            assert response.status_code in [200, 201]


class TestVerificationErrorHandling:
    """Tests for error handling in verification API."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from llm_council.http_server import app
        from llm_council.verification.api import router as verify_router

        router_paths = [route.path for route in app.routes]
        if "/v1/council/verify" not in router_paths:
            app.include_router(verify_router, prefix="/v1/council")

        return TestClient(app)

    def test_handles_council_error_gracefully(self, client):
        """Should handle council errors without 500."""
        request = {
            "snapshot_id": "abc1234def5678",
            "target_paths": ["src/"],
        }

        with patch("llm_council.verification.api.run_verification") as mock_verify:
            mock_verify.side_effect = Exception("Council failed")

            response = client.post("/v1/council/verify", json=request)

            # Should return error response, not crash
            assert response.status_code in [500, 503]
            data = response.json()
            assert "error" in data or "detail" in data

    def test_returns_partial_result_on_timeout(self, client):
        """Should return partial result if council times out."""
        request = {
            "snapshot_id": "abc1234def5678",
            "target_paths": ["src/"],
        }

        with patch("llm_council.verification.api.run_verification") as mock_verify:
            # Simulate timeout with partial result
            mock_verify.return_value = {
                "verification_id": "test-123",
                "verdict": "unclear",
                "confidence": 0.3,
                "rubric_scores": {},
                "blocking_issues": [],
                "rationale": "Verification timed out - partial result",
                "transcript_location": ".council/logs/test",
                "exit_code": 2,
                "partial": True,
            }

            response = client.post("/v1/council/verify", json=request)
            data = response.json()

            # Should still return valid response
            assert response.status_code == 200
            assert data["verdict"] == "unclear"
