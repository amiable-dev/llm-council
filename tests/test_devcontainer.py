"""Tests for devcontainer configuration.

These tests ensure the devcontainer:
1. Exists and is valid JSON
2. Uses correct Python image
3. Has uv feature for package management
4. Configures VS Code extensions
"""

import json
from pathlib import Path

import pytest


@pytest.fixture
def devcontainer_config() -> dict:
    """Load and parse devcontainer.json."""
    config_path = Path(__file__).parent.parent / ".devcontainer" / "devcontainer.json"
    assert config_path.exists(), ".devcontainer/devcontainer.json must exist"

    with open(config_path) as f:
        return json.load(f)


def test_devcontainer_exists():
    """Verify devcontainer.json exists."""
    config_path = Path(__file__).parent.parent / ".devcontainer" / "devcontainer.json"
    assert config_path.exists(), ".devcontainer/devcontainer.json must exist"


def test_devcontainer_valid_json():
    """Verify devcontainer.json is valid JSON."""
    config_path = Path(__file__).parent.parent / ".devcontainer" / "devcontainer.json"
    with open(config_path) as f:
        try:
            json.load(f)
        except json.JSONDecodeError as e:
            pytest.fail(f"devcontainer.json is not valid JSON: {e}")


def test_devcontainer_has_name(devcontainer_config: dict):
    """Verify devcontainer has a name."""
    assert devcontainer_config.get("name") == "LLM Council Dev"


def test_devcontainer_uses_python_image(devcontainer_config: dict):
    """Verify devcontainer uses Python base image."""
    image = devcontainer_config.get("image", "")
    assert "python" in image.lower(), "Devcontainer should use a Python image"
    assert "3.12" in image or "3.11" in image, "Devcontainer should use Python 3.11+"


def test_devcontainer_has_uv(devcontainer_config: dict):
    """Verify devcontainer has uv feature installed."""
    features = devcontainer_config.get("features", {})
    uv_feature = str(features)
    assert "uv" in uv_feature.lower(), "Devcontainer should have uv feature"


def test_devcontainer_has_post_create_command(devcontainer_config: dict):
    """Verify devcontainer has postCreateCommand."""
    post_create = devcontainer_config.get("postCreateCommand", "")
    assert "uv sync" in post_create, "postCreateCommand should run uv sync"


def test_devcontainer_has_vscode_extensions(devcontainer_config: dict):
    """Verify devcontainer has VS Code extensions configured."""
    customizations = devcontainer_config.get("customizations", {})
    vscode = customizations.get("vscode", {})
    extensions = vscode.get("extensions", [])

    # Essential extensions
    assert any("ruff" in ext.lower() for ext in extensions), "Should have ruff extension"
    assert any("python" in ext.lower() for ext in extensions), "Should have python extension"


def test_devcontainer_forwards_port(devcontainer_config: dict):
    """Verify devcontainer forwards the API port."""
    forward_ports = devcontainer_config.get("forwardPorts", [])
    assert 8001 in forward_ports, "Devcontainer should forward port 8001"


def test_devcontainer_has_python_settings(devcontainer_config: dict):
    """Verify devcontainer has Python-related VS Code settings."""
    customizations = devcontainer_config.get("customizations", {})
    vscode = customizations.get("vscode", {})
    settings = vscode.get("settings", {})

    # Check for Python interpreter path
    assert (
        "python.defaultInterpreterPath" in settings or "[python]" in settings
    ), "Should have Python settings"
