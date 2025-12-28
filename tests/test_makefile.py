"""Tests for Makefile.

These tests ensure the Makefile:
1. Exists and is valid
2. Has a help target that lists all targets
3. Has expected development targets
"""

import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def makefile_content() -> str:
    """Read the Makefile content."""
    makefile_path = Path(__file__).parent.parent / "Makefile"
    assert makefile_path.exists(), "Makefile must exist"
    return makefile_path.read_text()


def test_makefile_exists():
    """Verify Makefile exists in project root."""
    makefile_path = Path(__file__).parent.parent / "Makefile"
    assert makefile_path.exists(), "Makefile must exist"
    assert makefile_path.is_file(), "Makefile must be a file"


def test_make_help_runs():
    """Verify make help command runs successfully."""
    result = subprocess.run(
        ["make", "help"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    assert result.returncode == 0, f"make help failed: {result.stderr}"


def test_make_help_shows_targets():
    """Verify make help shows expected targets."""
    result = subprocess.run(
        ["make", "help"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    output = result.stdout

    # Core targets that should be documented
    expected_targets = [
        "setup",
        "test",
        "lint",
        "format",
        "clean",
    ]

    for target in expected_targets:
        assert target in output, f"Target '{target}' not shown in make help"


def test_make_test_dry_run():
    """Verify make test would run pytest (dry run)."""
    result = subprocess.run(
        ["make", "--dry-run", "test"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    assert result.returncode == 0, f"make test dry-run failed: {result.stderr}"
    assert "pytest" in result.stdout, "make test should run pytest"


def test_make_lint_dry_run():
    """Verify make lint would run ruff (dry run)."""
    result = subprocess.run(
        ["make", "--dry-run", "lint"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    assert result.returncode == 0, f"make lint dry-run failed: {result.stderr}"
    assert "ruff" in result.stdout, "make lint should run ruff"


def test_make_format_dry_run():
    """Verify make format would run ruff format (dry run)."""
    result = subprocess.run(
        ["make", "--dry-run", "format"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    assert result.returncode == 0, f"make format dry-run failed: {result.stderr}"
    assert "ruff" in result.stdout, "make format should run ruff"


def test_makefile_has_phony_targets(makefile_content: str):
    """Verify Makefile declares .PHONY targets."""
    assert ".PHONY" in makefile_content, "Makefile should declare .PHONY targets"


def test_makefile_has_help_comments(makefile_content: str):
    """Verify targets have help comments (## syntax)."""
    # Count lines with ## comments
    help_comments = [line for line in makefile_content.split("\n") if "## " in line]
    assert len(help_comments) >= 10, "Makefile should have help comments for targets"


def test_makefile_has_docs_targets(makefile_content: str):
    """Verify Makefile has documentation targets."""
    assert "docs:" in makefile_content, "Makefile should have docs target"
    assert "docs-build:" in makefile_content, "Makefile should have docs-build target"


def test_makefile_has_coverage_target(makefile_content: str):
    """Verify Makefile has test coverage target."""
    assert "test-cov:" in makefile_content, "Makefile should have test-cov target"
    assert "--cov" in makefile_content, "test-cov should use pytest --cov"
