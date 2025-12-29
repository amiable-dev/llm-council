"""Tests for ADR-013: Secure API Key Handling.

ADR-032: Updated to use unified_config instead of config.py.
"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock
from io import StringIO


# =============================================================================
# Test 1: Key Resolution Priority Chain
# =============================================================================


class TestKeyResolutionPriority:
    """Test that key resolution follows ADR-013 priority chain:
    1. Environment variable
    2. System keychain
    3. .env file (via dotenv)
    4. Config file
    """

    def test_env_var_takes_priority_over_keychain(self):
        """Environment variable should override keychain."""
        from llm_council.unified_config import _get_api_key

        with (
            patch.dict(os.environ, {"OPENROUTER_API_KEY": "env-key"}),
            patch(
                "llm_council.unified_config._get_api_key_from_keychain", return_value="keychain-key"
            ),
        ):
            key = _get_api_key()
            assert key == "env-key"

    def test_keychain_used_when_no_env_var(self):
        """Keychain should be used when env var is not set."""
        from llm_council.unified_config import _get_api_key

        env_backup = os.environ.pop("OPENROUTER_API_KEY", None)
        try:
            with (
                patch(
                    "llm_council.unified_config._get_api_key_from_keychain",
                    return_value="keychain-key",
                ),
                patch("llm_council.unified_config._user_config", {}),
            ):
                key = _get_api_key()
                assert key == "keychain-key"
        finally:
            if env_backup:
                os.environ["OPENROUTER_API_KEY"] = env_backup

    def test_config_file_used_as_last_resort(self):
        """Config file should only be used when env var and keychain both fail."""
        from llm_council import unified_config

        env_backup = os.environ.pop("OPENROUTER_API_KEY", None)
        try:
            with (
                patch("llm_council.unified_config._get_api_key_from_keychain", return_value=None),
                patch.object(unified_config, "_user_config", {"openrouter_api_key": "config-key"}),
                patch.dict(os.environ, {"LLM_COUNCIL_SUPPRESS_WARNINGS": "1"}),
            ):
                key = unified_config._get_api_key()
                assert key == "config-key"
        finally:
            if env_backup:
                os.environ["OPENROUTER_API_KEY"] = env_backup

    def test_returns_none_when_no_key_found(self):
        """Should return None when no key is available anywhere."""
        from llm_council.unified_config import _get_api_key

        env_backup = os.environ.pop("OPENROUTER_API_KEY", None)
        try:
            with (
                patch("llm_council.unified_config._get_api_key_from_keychain", return_value=None),
                patch("llm_council.unified_config._user_config", {}),
            ):
                key = _get_api_key()
                assert key is None
        finally:
            if env_backup:
                os.environ["OPENROUTER_API_KEY"] = env_backup


# =============================================================================
# Test 2: Key Source Tracking
# =============================================================================


class TestKeySourceTracking:
    """Test that key source is tracked for diagnostics."""

    def test_key_source_tracked_for_env(self):
        """Key source should be 'environment' when from env var."""
        from llm_council.unified_config import _get_api_key, get_key_source

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "env-key"}):
            _get_api_key()
            assert get_key_source() == "environment"

    def test_key_source_tracked_for_keychain(self):
        """Key source should be 'keychain' when from keychain."""
        from llm_council.unified_config import _get_api_key, get_key_source

        env_backup = os.environ.pop("OPENROUTER_API_KEY", None)
        try:
            with (
                patch(
                    "llm_council.unified_config._get_api_key_from_keychain",
                    return_value="keychain-key",
                ),
                patch("llm_council.unified_config._user_config", {}),
            ):
                _get_api_key()
                assert get_key_source() == "keychain"
        finally:
            if env_backup:
                os.environ["OPENROUTER_API_KEY"] = env_backup

    def test_key_source_tracked_for_config(self):
        """Key source should be 'config_file' when from config."""
        from llm_council import unified_config

        env_backup = os.environ.pop("OPENROUTER_API_KEY", None)
        try:
            with (
                patch("llm_council.unified_config._get_api_key_from_keychain", return_value=None),
                patch.object(unified_config, "_user_config", {"openrouter_api_key": "config-key"}),
                patch.dict(os.environ, {"LLM_COUNCIL_SUPPRESS_WARNINGS": "1"}),
            ):
                unified_config._get_api_key()
                assert unified_config.get_key_source() == "config_file"
        finally:
            if env_backup:
                os.environ["OPENROUTER_API_KEY"] = env_backup


# =============================================================================
# Test 3: Keyring Optional Dependency
# =============================================================================


class TestKeyringOptional:
    """Test that keyring is an optional dependency that fails gracefully."""

    def test_keyring_import_error_handled(self):
        """Should handle ImportError when keyring not installed."""
        from llm_council import unified_config

        # Reset keyring state to force re-check
        original_keyring = unified_config.keyring
        unified_config.keyring = None

        try:
            # Patch import to fail
            with patch.dict(sys.modules, {"keyring": None}):
                # Force re-import check by resetting state
                unified_config.keyring = None
                result = unified_config._get_api_key_from_keychain()
                assert result is None
        finally:
            unified_config.keyring = original_keyring

    def test_keyring_fail_backend_returns_none(self):
        """Should return None when keyring has fail backend (headless)."""
        from llm_council import unified_config

        mock_keyring = MagicMock()
        original_keyring = unified_config.keyring
        unified_config.keyring = mock_keyring

        try:
            with patch("llm_council.unified_config._is_fail_backend", return_value=True):
                result = unified_config._get_api_key_from_keychain()
                assert result is None
        finally:
            unified_config.keyring = original_keyring

    def test_keyring_success_returns_key(self):
        """Should return key when keyring works."""
        from llm_council import unified_config

        mock_keyring = MagicMock()
        mock_keyring.get_password.return_value = "keychain-secret-key"
        original_keyring = unified_config.keyring
        unified_config.keyring = mock_keyring

        try:
            with patch("llm_council.unified_config._is_fail_backend", return_value=False):
                result = unified_config._get_api_key_from_keychain()
                assert result == "keychain-secret-key"
                mock_keyring.get_password.assert_called_once_with(
                    "llm-council", "openrouter_api_key"
                )
        finally:
            unified_config.keyring = original_keyring

    def test_keyring_exception_handled(self):
        """Should handle exceptions from keyring gracefully."""
        from llm_council import unified_config

        mock_keyring = MagicMock()
        mock_keyring.get_password.side_effect = Exception("Keychain locked")
        original_keyring = unified_config.keyring
        unified_config.keyring = mock_keyring

        try:
            with patch("llm_council.unified_config._is_fail_backend", return_value=False):
                result = unified_config._get_api_key_from_keychain()
                assert result is None
        finally:
            unified_config.keyring = original_keyring


# =============================================================================
# Test 4: Config File Warning
# =============================================================================


class TestConfigFileWarning:
    """Test that warnings are emitted when key is loaded from config file."""

    def test_warning_emitted_for_config_file_key(self, capsys):
        """Should emit warning to stderr when key from config file."""
        from llm_council import unified_config

        env_backup = os.environ.pop("OPENROUTER_API_KEY", None)
        warn_backup = os.environ.pop("LLM_COUNCIL_SUPPRESS_WARNINGS", None)
        try:
            with (
                patch("llm_council.unified_config._get_api_key_from_keychain", return_value=None),
                patch.object(unified_config, "_user_config", {"openrouter_api_key": "config-key"}),
            ):
                unified_config._get_api_key()
                captured = capsys.readouterr()
                assert "Warning" in captured.err or "insecure" in captured.err.lower()
        finally:
            if env_backup:
                os.environ["OPENROUTER_API_KEY"] = env_backup
            if warn_backup:
                os.environ["LLM_COUNCIL_SUPPRESS_WARNINGS"] = warn_backup

    def test_warning_suppressed_with_env_var(self, capsys):
        """Should suppress warning when LLM_COUNCIL_SUPPRESS_WARNINGS is set."""
        from llm_council import unified_config

        env_backup = os.environ.pop("OPENROUTER_API_KEY", None)
        try:
            with (
                patch("llm_council.unified_config._get_api_key_from_keychain", return_value=None),
                patch.object(unified_config, "_user_config", {"openrouter_api_key": "config-key"}),
                patch.dict(os.environ, {"LLM_COUNCIL_SUPPRESS_WARNINGS": "1"}),
            ):
                unified_config._get_api_key()
                captured = capsys.readouterr()
                assert "Warning" not in captured.err
        finally:
            if env_backup:
                os.environ["OPENROUTER_API_KEY"] = env_backup

    def test_no_warning_for_env_var_key(self, capsys):
        """Should not emit warning when key from env var."""
        from llm_council.unified_config import _get_api_key

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "env-key"}):
            _get_api_key()
            captured = capsys.readouterr()
            assert "Warning" not in captured.err

    def test_no_warning_for_keychain_key(self, capsys):
        """Should not emit warning when key from keychain."""
        from llm_council.unified_config import _get_api_key

        env_backup = os.environ.pop("OPENROUTER_API_KEY", None)
        try:
            with (
                patch(
                    "llm_council.unified_config._get_api_key_from_keychain",
                    return_value="keychain-key",
                ),
                patch("llm_council.unified_config._user_config", {}),
            ):
                _get_api_key()
                captured = capsys.readouterr()
                assert "Warning" not in captured.err
        finally:
            if env_backup:
                os.environ["OPENROUTER_API_KEY"] = env_backup


# =============================================================================
# Test 5: Setup Key CLI Command
# =============================================================================


class TestSetupKeyCommand:
    """Test the setup-key CLI command."""

    def test_setup_key_interactive_stores_key(self):
        """Interactive setup should prompt and store key."""
        from llm_council.cli import setup_key

        mock_keyring = MagicMock()

        with (
            patch("llm_council.cli.keyring", mock_keyring),
            patch("llm_council.cli._is_fail_backend", return_value=False),
            patch("getpass.getpass", return_value="sk-or-v1-test-key"),
        ):
            setup_key(from_stdin=False)
            mock_keyring.set_password.assert_called_once_with(
                "llm-council", "openrouter_api_key", "sk-or-v1-test-key"
            )

    def test_setup_key_stdin_reads_from_stdin(self):
        """Stdin mode should read key from stdin."""
        from llm_council.cli import setup_key

        mock_keyring = MagicMock()

        with (
            patch("llm_council.cli.keyring", mock_keyring),
            patch("llm_council.cli._is_fail_backend", return_value=False),
            patch("sys.stdin", StringIO("sk-or-v1-stdin-key\n")),
        ):
            setup_key(from_stdin=True)
            mock_keyring.set_password.assert_called_once_with(
                "llm-council", "openrouter_api_key", "sk-or-v1-stdin-key"
            )

    def test_setup_key_warns_invalid_format(self, capsys):
        """Should warn when key doesn't match expected format."""
        from llm_council.cli import setup_key

        mock_keyring = MagicMock()

        with (
            patch("llm_council.cli.keyring", mock_keyring),
            patch("llm_council.cli._is_fail_backend", return_value=False),
            patch("sys.stdin", StringIO("invalid-key-format\n")),
        ):
            # In stdin mode, it should still store but warn
            setup_key(from_stdin=True)
            captured = capsys.readouterr()
            assert "doesn't look like" in captured.out or "Warning" in captured.out

    def test_setup_key_fails_without_keyring(self, capsys):
        """Should fail gracefully when keyring not installed."""
        from llm_council.cli import setup_key

        with patch("llm_council.cli.keyring", None), patch.dict(sys.modules, {"keyring": None}):
            with pytest.raises(SystemExit) as exc_info:
                setup_key(from_stdin=False)
            assert exc_info.value.code == 1
            captured = capsys.readouterr()
            assert "keyring" in captured.err.lower()

    def test_setup_key_fails_with_fail_backend(self, capsys):
        """Should fail when keyring has fail backend (headless)."""
        from llm_council.cli import setup_key

        mock_keyring = MagicMock()

        with (
            patch("llm_council.cli.keyring", mock_keyring),
            patch("llm_council.cli._is_fail_backend", return_value=True),
        ):
            with pytest.raises(SystemExit) as exc_info:
                setup_key(from_stdin=False)
            assert exc_info.value.code == 1
            captured = capsys.readouterr()
            assert "backend" in captured.err.lower() or "headless" in captured.err.lower()


# =============================================================================
# Test 6: Health Check Includes Key Source
# =============================================================================

# Check if MCP is available for tests that need mcp_server
try:
    import mcp

    HAS_MCP = True
except ImportError:
    HAS_MCP = False


@pytest.mark.skipif(not HAS_MCP, reason="MCP package not installed (optional dependency)")
class TestHealthCheckKeySource:
    """Test that health check includes key source information."""

    @pytest.mark.asyncio
    async def test_health_check_shows_key_source(self):
        """Health check should include key source in output."""
        import json
        from llm_council.mcp_server import council_health_check

        with (
            patch("llm_council.mcp_server.OPENROUTER_API_KEY", "test-key"),
            patch("llm_council.mcp_server.get_key_source", return_value="environment"),
            patch("llm_council.mcp_server.query_model_with_status") as mock_query,
        ):
            mock_query.return_value = {"status": "ok", "content": "pong", "latency_ms": 100}

            result = await council_health_check()
            data = json.loads(result)

            assert "key_source" in data
            assert data["key_source"] == "environment"


# =============================================================================
# Test 7: Optional Dependency Declaration
# =============================================================================


def test_secure_extras_declared():
    """Test that [secure] extras are declared in pyproject.toml."""
    from pathlib import Path

    # Python 3.11+ has tomllib built-in; use tomli for 3.10
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib

    pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
    with open(pyproject_path, "rb") as f:
        pyproject = tomllib.load(f)

    optional_deps = pyproject.get("project", {}).get("optional-dependencies", {})
    assert "secure" in optional_deps, "Missing [secure] optional dependency"
    assert any("keyring" in dep for dep in optional_deps["secure"]), "keyring not in [secure] deps"
