"""Tests for MkDocs documentation configuration.

These tests ensure the documentation:
1. Has valid mkdocs.yml configuration
2. Has required documentation pages
3. Builds without errors (marked as slow)
"""

from pathlib import Path

import pytest
import yaml


@pytest.fixture
def mkdocs_config() -> dict:
    """Load and parse mkdocs.yml."""
    config_path = Path(__file__).parent.parent / "mkdocs.yml"
    assert config_path.exists(), "mkdocs.yml must exist"

    with open(config_path) as f:
        return yaml.safe_load(f)


def test_mkdocs_config_exists():
    """Verify mkdocs.yml exists."""
    config_path = Path(__file__).parent.parent / "mkdocs.yml"
    assert config_path.exists(), "mkdocs.yml must exist"


def test_mkdocs_config_valid_yaml():
    """Verify mkdocs.yml is valid YAML."""
    config_path = Path(__file__).parent.parent / "mkdocs.yml"
    with open(config_path) as f:
        try:
            yaml.safe_load(f)
        except yaml.YAMLError as e:
            pytest.fail(f"mkdocs.yml is not valid YAML: {e}")


def test_mkdocs_has_site_name(mkdocs_config: dict):
    """Verify mkdocs.yml has site_name."""
    assert mkdocs_config.get("site_name") == "llm-council"


def test_mkdocs_uses_material_theme(mkdocs_config: dict):
    """Verify mkdocs.yml uses Material theme."""
    theme = mkdocs_config.get("theme", {})
    assert theme.get("name") == "material", "Should use Material theme"


def test_mkdocs_has_navigation(mkdocs_config: dict):
    """Verify mkdocs.yml has navigation structure."""
    nav = mkdocs_config.get("nav", [])
    assert len(nav) > 0, "Should have navigation items"

    # Check for essential sections
    nav_str = str(nav)
    assert "Home" in nav_str, "Should have Home section"
    assert "Getting Started" in nav_str, "Should have Getting Started section"


def test_mkdocs_has_repo_url(mkdocs_config: dict):
    """Verify mkdocs.yml has repository URL."""
    repo_url = mkdocs_config.get("repo_url", "")
    assert "github.com" in repo_url, "Should have GitHub repo URL"
    assert "llm-council" in repo_url, "Should link to llm-council repo"


def test_docs_index_exists():
    """Verify docs/index.md exists."""
    index_path = Path(__file__).parent.parent / "docs" / "index.md"
    assert index_path.exists(), "docs/index.md must exist"


def test_docs_has_getting_started():
    """Verify getting-started docs exist."""
    docs_path = Path(__file__).parent.parent / "docs" / "getting-started"
    assert docs_path.exists(), "docs/getting-started/ must exist"

    required_files = ["installation.md", "quickstart.md", "configuration.md"]
    for filename in required_files:
        file_path = docs_path / filename
        assert file_path.exists(), f"docs/getting-started/{filename} must exist"


def test_docs_has_guides():
    """Verify guide docs exist."""
    docs_path = Path(__file__).parent.parent / "docs" / "guides"
    assert docs_path.exists(), "docs/guides/ must exist"


def test_docs_has_architecture():
    """Verify architecture docs exist."""
    docs_path = Path(__file__).parent.parent / "docs" / "architecture"
    assert docs_path.exists(), "docs/architecture/ must exist"


@pytest.mark.slow
def test_mkdocs_build_succeeds():
    """Verify mkdocs build completes without errors.

    Note: We don't use --strict mode because ADR files may contain
    internal links to files outside the docs/ folder (e.g., council
    reviews, source code) which generate warnings but are valid in
    the original ADR context.

    Requires: pip install "llm-council-core[docs]"
    """
    import subprocess
    import shutil

    # Skip if mkdocs is not installed (docs optional dependency)
    if shutil.which("mkdocs") is None:
        pytest.skip("mkdocs not installed (requires [docs] extra)")

    result = subprocess.run(
        ["mkdocs", "build"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )

    if result.returncode != 0:
        pytest.fail(f"mkdocs build failed:\n{result.stderr}")
