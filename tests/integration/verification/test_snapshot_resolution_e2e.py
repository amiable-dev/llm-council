"""End-to-end tests: snapshot resolution failure surfaces via HTTP 422 and MCP error blob.

Issue #340 — verify must fail loudly when target_paths cannot be resolved
at the given snapshot_id, not silently produce a boilerplate-only prompt.
Parallels the existing BlockingEvidenceTooLarge handling (ADR-042 precedent).
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _route_paths(app):
    """All registered route paths, flattening Starlette 1.x nested routers.

    Starlette 1.x wraps ``include_router`` results in an ``_IncludedRouter``
    with no ``.path`` (its sub-routes carry the paths), so a flat
    ``[r.path for r in app.routes]`` raises ``AttributeError`` there. Walk the
    route tree recursively so this works on both Starlette 0.x and 1.x.
    """
    paths = []
    stack = list(app.routes)
    while stack:
        route = stack.pop()
        path = getattr(route, "path", None)
        if path is not None:
            paths.append(path)
        stack.extend(getattr(route, "routes", None) or [])
    return paths


class TestHTTPSnapshotResolution422:
    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from llm_council.http_server import app
        from llm_council.verification.api import router as verify_router

        router_paths = _route_paths(app)
        if "/v1/council/verify" not in router_paths:
            app.include_router(verify_router, prefix="/v1/council")
        return TestClient(app)

    def test_returns_422_with_structured_body_for_unresolvable_paths(self, client):
        """When target_paths is non-empty but expansion yields zero files,
        the endpoint must return HTTP 422 with detail.error =
        'snapshot_resolution_failed' rather than UNCLEAR with a soft verdict."""
        from llm_council.verification.api import SnapshotResolutionError

        with patch("llm_council.verification.api.run_verification") as mock_run:
            mock_run.side_effect = SnapshotResolutionError(
                snapshot_id="b50f2b3d",
                unresolved_paths=["tests/a.rs", "tests/b.rs"],
                expansion_warnings=[
                    "Path not found or invalid: tests/a.rs",
                    "Path not found or invalid: tests/b.rs",
                ],
            )

            response = client.post(
                "/v1/council/verify",
                json={
                    "snapshot_id": "b50f2b3d",
                    "target_paths": ["tests/a.rs", "tests/b.rs"],
                },
            )

            assert response.status_code == 422, response.text
            body = response.json()
            detail = body["detail"]
            assert detail["error"] == "snapshot_resolution_failed"
            assert detail["snapshot_id"] == "b50f2b3d"
            assert detail["unresolved_paths"] == ["tests/a.rs", "tests/b.rs"]
            assert detail["expansion_warnings"] == [
                "Path not found or invalid: tests/a.rs",
                "Path not found or invalid: tests/b.rs",
            ]


class TestMCPSnapshotResolutionErrorBlob:
    @pytest.mark.asyncio
    async def test_mcp_verify_returns_structured_error_blob(self):
        """MCP wrapper mirrors the HTTP 422 body shape for parity (same
        precedent as BlockingEvidenceTooLarge)."""
        from llm_council.mcp_server import verify
        from llm_council.verification.api import SnapshotResolutionError

        with (
            patch("llm_council.mcp_server.run_verification") as mock_run,
            patch("llm_council.mcp_server.create_transcript_store"),
        ):
            mock_run.side_effect = SnapshotResolutionError(
                snapshot_id="b50f2b3d",
                unresolved_paths=["a.rs"],
                expansion_warnings=["Path not found or invalid: a.rs"],
            )

            result = await verify(
                snapshot_id="b50f2b3d",
                target_paths=["a.rs"],
            )

            # Result is JSON string.
            payload = json.loads(result)
            assert payload["error"] == "snapshot_resolution_failed"
            assert payload["snapshot_id"] == "b50f2b3d"
            assert payload["unresolved_paths"] == ["a.rs"]
            assert payload["expansion_warnings"] == ["Path not found or invalid: a.rs"]
            # exit_code 2 (UNCLEAR) mirrors BlockingEvidenceTooLarge precedent —
            # caller knows verification did not run.
            assert payload["exit_code"] == 2
            assert payload["verdict"] == "unclear"
            assert payload["confidence"] == 0.0
