"""Tests for CLI entry point (ADR-009).

Tests verify that the CLI correctly dispatches between MCP and HTTP servers.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest


class TestCLIDispatch:
    """Tests for CLI argument dispatching."""

    def test_no_args_calls_mcp_server(self):
        """Running 'llm-council' with no args should start MCP server."""
        from llm_council import cli

        mock_mcp = MagicMock()
        with patch.object(sys, "argv", ["llm-council"]):
            with patch.dict("sys.modules", {"llm_council.mcp_server": MagicMock(mcp=mock_mcp)}):
                # Re-import to get fresh module with mocked dependencies
                import importlib

                importlib.reload(cli)
                cli.main()

        mock_mcp.run.assert_called_once()

    def test_serve_command_calls_http_server(self):
        """Running 'llm-council serve' should start HTTP server."""
        from llm_council import cli

        mock_uvicorn = MagicMock()
        mock_app = MagicMock()

        with patch.object(sys, "argv", ["llm-council", "serve"]):
            with patch.dict(
                "sys.modules",
                {
                    "uvicorn": mock_uvicorn,
                    "llm_council.http_server": MagicMock(app=mock_app),
                },
            ):
                import importlib

                importlib.reload(cli)
                cli.main()

        mock_uvicorn.run.assert_called_once()
        call_args = mock_uvicorn.run.call_args
        assert call_args[0][0] == mock_app  # First positional arg is app


class TestCLIGracefulDegradation:
    """Tests for graceful handling of missing dependencies."""

    def test_mcp_missing_shows_helpful_error(self, capsys):
        """Missing MCP deps should show installation instructions."""
        from llm_council import cli

        with patch.object(sys, "argv", ["llm-council"]):
            # Simulate ImportError for MCP
            with patch.object(cli, "serve_mcp", side_effect=SystemExit(1)):
                with pytest.raises(SystemExit) as exc_info:
                    cli.main()

                assert exc_info.value.code == 1

    def test_http_missing_shows_helpful_error(self, capsys):
        """Missing HTTP deps should show installation instructions."""
        from llm_council import cli

        with patch.object(sys, "argv", ["llm-council", "serve"]):
            # Simulate ImportError for HTTP
            with patch.object(cli, "serve_http", side_effect=SystemExit(1)):
                with pytest.raises(SystemExit) as exc_info:
                    cli.main()

                assert exc_info.value.code == 1


class TestCLIServeOptions:
    """Tests for HTTP serve command options."""

    def test_serve_default_host_and_port(self):
        """Default serve binds loopback only: 127.0.0.1:8000 (was 0.0.0.0)."""
        from llm_council import cli

        mock_uvicorn = MagicMock()
        mock_app = MagicMock()

        with patch.object(sys, "argv", ["llm-council", "serve"]):
            with patch.dict(
                "sys.modules",
                {
                    "uvicorn": mock_uvicorn,
                    "llm_council.http_server": MagicMock(app=mock_app),
                },
            ):
                import importlib

                importlib.reload(cli)
                cli.main()

        call_kwargs = mock_uvicorn.run.call_args[1]
        assert call_kwargs.get("host") == "127.0.0.1"
        assert call_kwargs.get("port") == 8000

    def test_serve_custom_port(self):
        """Serve should accept --port option."""
        from llm_council import cli

        mock_uvicorn = MagicMock()
        mock_app = MagicMock()

        with patch.object(sys, "argv", ["llm-council", "serve", "--port", "9000"]):
            with patch.dict(
                "sys.modules",
                {
                    "uvicorn": mock_uvicorn,
                    "llm_council.http_server": MagicMock(app=mock_app),
                },
            ):
                import importlib

                importlib.reload(cli)
                cli.main()

        call_kwargs = mock_uvicorn.run.call_args[1]
        assert call_kwargs.get("port") == 9000

    def test_serve_custom_host(self):
        """Serve should accept --host option."""
        from llm_council import cli

        mock_uvicorn = MagicMock()
        mock_app = MagicMock()

        with patch.object(sys, "argv", ["llm-council", "serve", "--host", "127.0.0.1"]):
            with patch.dict(
                "sys.modules",
                {
                    "uvicorn": mock_uvicorn,
                    "llm_council.http_server": MagicMock(app=mock_app),
                },
            ):
                import importlib

                importlib.reload(cli)
                cli.main()

        call_kwargs = mock_uvicorn.run.call_args[1]
        assert call_kwargs.get("host") == "127.0.0.1"


class TestServeExposureWarning:
    """Follow-up to GHSA-r7rh-j9cj-h9hh: exposing the server is a deliberate act.

    `serve` used to bind every interface by default with no authentication,
    which was the precondition for the advisory. It now binds loopback, and
    says so loudly when asked to bind wider without a token.
    """

    def _serve(self, host, monkeypatch, token=None):
        from llm_council import cli

        if token is None:
            monkeypatch.delenv("LLM_COUNCIL_API_TOKEN", raising=False)
        else:
            monkeypatch.setenv("LLM_COUNCIL_API_TOKEN", token)
        mock_uvicorn = MagicMock()
        with patch.dict(
            "sys.modules",
            {"uvicorn": mock_uvicorn, "llm_council.http_server": MagicMock(app=MagicMock())},
        ):
            cli.serve_http(host=host, port=8000)
        return mock_uvicorn

    def test_function_default_is_loopback(self):
        import inspect

        from llm_council import cli

        assert inspect.signature(cli.serve_http).parameters["host"].default == "127.0.0.1"

    @pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.20", "example.internal"])
    def test_warns_when_exposed_without_a_token(self, host, monkeypatch, capsys):
        uvicorn = self._serve(host, monkeypatch)
        err = capsys.readouterr().err
        assert "LLM_COUNCIL_API_TOKEN" in err
        assert "without authentication" in err
        uvicorn.run.assert_called_once()  # a warning, never a refusal

    @pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1", "127.0.0.2"])
    def test_silent_on_loopback(self, host, monkeypatch, capsys):
        self._serve(host, monkeypatch)
        assert capsys.readouterr().err == ""

    def test_silent_when_exposed_with_a_token(self, monkeypatch, capsys):
        self._serve("0.0.0.0", monkeypatch, token="s3cret")
        assert capsys.readouterr().err == ""

    def test_empty_token_counts_as_no_token(self, monkeypatch, capsys):
        self._serve("0.0.0.0", monkeypatch, token="")
        assert "LLM_COUNCIL_API_TOKEN" in capsys.readouterr().err
