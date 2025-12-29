"""Tests for security configuration files.

ADR-035: DevSecOps Implementation
These tests validate security tool configurations exist and are properly structured.

TDD Approach:
- Tests are written FIRST (RED phase)
- Config files are created to make tests pass (GREEN phase)
- Config files are refined as needed (REFACTOR phase)
"""

from pathlib import Path

import pytest
import yaml

# Try to import tomli for TOML parsing (Python 3.11+ has tomllib built-in)
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def project_root() -> Path:
    """Get project root directory."""
    return Path(__file__).parent.parent


@pytest.fixture
def github_dir(project_root: Path) -> Path:
    """Get .github directory."""
    return project_root / ".github"


# =============================================================================
# Phase 1: Dependabot Configuration Tests
# Issues: #205
# =============================================================================


class TestDependabotConfig:
    """Tests for .github/dependabot.yml configuration."""

    @pytest.fixture
    def dependabot_path(self, github_dir: Path) -> Path:
        """Path to dependabot config."""
        return github_dir / "dependabot.yml"

    @pytest.fixture
    def dependabot_config(self, dependabot_path: Path) -> dict:
        """Load dependabot configuration."""
        if not dependabot_path.exists():
            pytest.skip("dependabot.yml not yet created")
        with open(dependabot_path) as f:
            return yaml.safe_load(f)

    def test_dependabot_config_exists(self, dependabot_path: Path):
        """Verify dependabot.yml exists."""
        assert dependabot_path.exists(), ".github/dependabot.yml must exist"
        assert dependabot_path.is_file()

    def test_dependabot_config_valid_yaml(self, dependabot_path: Path):
        """Verify dependabot.yml is valid YAML."""
        if not dependabot_path.exists():
            pytest.skip("dependabot.yml not yet created")
        with open(dependabot_path) as f:
            try:
                yaml.safe_load(f)
            except yaml.YAMLError as e:
                pytest.fail(f"dependabot.yml is not valid YAML: {e}")

    def test_dependabot_has_version_2(self, dependabot_config: dict):
        """Verify dependabot config uses version 2."""
        assert dependabot_config.get("version") == 2

    def test_dependabot_has_pip_ecosystem(self, dependabot_config: dict):
        """Verify Dependabot monitors pip dependencies."""
        updates = dependabot_config.get("updates", [])
        ecosystems = [u.get("package-ecosystem") for u in updates]
        assert "pip" in ecosystems, "Dependabot must monitor pip ecosystem"

    def test_dependabot_has_github_actions_ecosystem(self, dependabot_config: dict):
        """Verify Dependabot monitors GitHub Actions."""
        updates = dependabot_config.get("updates", [])
        ecosystems = [u.get("package-ecosystem") for u in updates]
        assert "github-actions" in ecosystems, "Dependabot must monitor github-actions"

    def test_dependabot_has_weekly_schedule(self, dependabot_config: dict):
        """Verify Dependabot runs at least weekly."""
        updates = dependabot_config.get("updates", [])
        for update in updates:
            schedule = update.get("schedule", {})
            interval = schedule.get("interval", "")
            assert interval in [
                "daily",
                "weekly",
            ], f"Schedule should be daily or weekly, got {interval}"

    def test_dependabot_has_labels(self, dependabot_config: dict):
        """Verify Dependabot PRs get labels."""
        pip_update = next(
            (
                u
                for u in dependabot_config.get("updates", [])
                if u.get("package-ecosystem") == "pip"
            ),
            None,
        )
        assert pip_update is not None
        labels = pip_update.get("labels", [])
        assert len(labels) > 0, "Dependabot should add labels to PRs"


# =============================================================================
# Phase 2: Gitleaks Configuration Tests
# Issues: #209
# =============================================================================


class TestGitleaksConfig:
    """Tests for .gitleaks.toml configuration."""

    @pytest.fixture
    def gitleaks_path(self, project_root: Path) -> Path:
        """Path to gitleaks config."""
        return project_root / ".gitleaks.toml"

    @pytest.fixture
    def gitleaks_content(self, gitleaks_path: Path) -> str:
        """Load gitleaks configuration as text."""
        if not gitleaks_path.exists():
            pytest.skip(".gitleaks.toml not yet created")
        return gitleaks_path.read_text()

    def test_gitleaks_config_exists(self, gitleaks_path: Path):
        """Verify .gitleaks.toml exists."""
        assert gitleaks_path.exists(), ".gitleaks.toml must exist"

    def test_gitleaks_config_valid_toml(self, gitleaks_path: Path):
        """Verify .gitleaks.toml is valid TOML."""
        if not gitleaks_path.exists():
            pytest.skip(".gitleaks.toml not yet created")
        if tomllib is None:
            pytest.skip("tomllib/tomli not available")
        with open(gitleaks_path, "rb") as f:
            try:
                tomllib.load(f)
            except Exception as e:
                pytest.fail(f".gitleaks.toml is not valid TOML: {e}")

    def test_gitleaks_extends_default(self, gitleaks_content: str):
        """Verify Gitleaks extends default ruleset."""
        assert "useDefault = true" in gitleaks_content

    def test_gitleaks_has_openrouter_pattern(self, gitleaks_content: str):
        """Verify custom rule for OpenRouter API keys."""
        assert "openrouter" in gitleaks_content.lower()
        assert "sk-or-v1-" in gitleaks_content

    def test_gitleaks_has_anthropic_pattern(self, gitleaks_content: str):
        """Verify custom rule for Anthropic API keys."""
        assert "anthropic" in gitleaks_content.lower()
        assert "sk-ant-" in gitleaks_content

    def test_gitleaks_has_allowlist(self, gitleaks_content: str):
        """Verify allowlist exists for example files."""
        assert "[allowlist]" in gitleaks_content or "allowlist" in gitleaks_content.lower()


# =============================================================================
# Phase 2: Pre-commit Configuration Tests
# Issues: #210
# =============================================================================


class TestPreCommitConfig:
    """Tests for .pre-commit-config.yaml."""

    @pytest.fixture
    def pre_commit_path(self, project_root: Path) -> Path:
        """Path to pre-commit config."""
        return project_root / ".pre-commit-config.yaml"

    @pytest.fixture
    def pre_commit_config(self, pre_commit_path: Path) -> dict:
        """Load pre-commit configuration."""
        if not pre_commit_path.exists():
            pytest.skip(".pre-commit-config.yaml not yet created")
        with open(pre_commit_path) as f:
            return yaml.safe_load(f)

    def test_pre_commit_config_exists(self, pre_commit_path: Path):
        """Verify .pre-commit-config.yaml exists."""
        assert pre_commit_path.exists(), ".pre-commit-config.yaml must exist"

    def test_pre_commit_has_repos(self, pre_commit_config: dict):
        """Verify pre-commit has repos configured."""
        assert "repos" in pre_commit_config
        assert len(pre_commit_config["repos"]) > 0

    def test_pre_commit_has_ruff_hook(self, pre_commit_config: dict):
        """Verify pre-commit has Ruff for linting."""
        repos = pre_commit_config.get("repos", [])
        repo_urls = [r.get("repo", "") for r in repos]
        assert any("ruff" in url for url in repo_urls), "Pre-commit must have Ruff hook"

    def test_pre_commit_has_gitleaks_hook(self, pre_commit_config: dict):
        """Verify pre-commit has Gitleaks for secret detection."""
        repos = pre_commit_config.get("repos", [])
        repo_urls = [r.get("repo", "") for r in repos]
        assert any("gitleaks" in url for url in repo_urls), "Pre-commit must have Gitleaks hook"

    def test_pre_commit_versions_are_pinned(self, pre_commit_config: dict):
        """Verify all pre-commit hook versions are pinned."""
        repos = pre_commit_config.get("repos", [])
        for repo in repos:
            rev = repo.get("rev", "")
            # Should start with 'v' (version tag) or be a SHA (40 chars)
            is_version_tag = rev.startswith("v")
            is_sha = len(rev) == 40 and rev.isalnum()
            assert is_version_tag or is_sha, f"Hook {repo.get('repo')} has unpinned version: {rev}"


# =============================================================================
# Phase 2: Semgrep Rules Tests
# Issues: #212
# =============================================================================


class TestSemgrepRules:
    """Tests for custom Semgrep rules."""

    @pytest.fixture
    def semgrep_dir(self, project_root: Path) -> Path:
        """Path to .semgrep directory."""
        return project_root / ".semgrep"

    @pytest.fixture
    def llm_rules_path(self, semgrep_dir: Path) -> Path:
        """Path to LLM security rules."""
        return semgrep_dir / "llm-security.yaml"

    def test_semgrep_directory_exists(self, semgrep_dir: Path):
        """Verify .semgrep/ directory exists for custom rules."""
        assert semgrep_dir.exists(), ".semgrep/ directory should exist"
        assert semgrep_dir.is_dir()

    def test_semgrep_llm_rules_exist(self, llm_rules_path: Path):
        """Verify LLM-specific security rules exist."""
        assert llm_rules_path.exists(), ".semgrep/llm-security.yaml should exist"

    def test_semgrep_rules_valid_yaml(self, semgrep_dir: Path):
        """Verify all Semgrep rule files are valid YAML."""
        if not semgrep_dir.exists():
            pytest.skip(".semgrep/ directory not yet created")
        for rule_file in semgrep_dir.glob("*.yaml"):
            with open(rule_file) as f:
                try:
                    yaml.safe_load(f)
                except yaml.YAMLError as e:
                    pytest.fail(f"{rule_file.name} is not valid YAML: {e}")

    def test_semgrep_rules_have_required_fields(self, semgrep_dir: Path):
        """Verify Semgrep rules have required structure."""
        if not semgrep_dir.exists():
            pytest.skip(".semgrep/ directory not yet created")
        for rule_file in semgrep_dir.glob("*.yaml"):
            with open(rule_file) as f:
                config = yaml.safe_load(f)
            assert "rules" in config, f"{rule_file.name} missing 'rules' key"
            for rule in config["rules"]:
                assert "id" in rule, f"Rule in {rule_file.name} missing 'id'"
                assert "message" in rule, f"Rule in {rule_file.name} missing 'message'"
                assert "severity" in rule, f"Rule in {rule_file.name} missing 'severity'"

    def test_semgrep_has_pickle_rule(self, llm_rules_path: Path):
        """Verify Semgrep has rule for unsafe pickle deserialization."""
        if not llm_rules_path.exists():
            pytest.skip("llm-security.yaml not yet created")
        with open(llm_rules_path) as f:
            config = yaml.safe_load(f)
        rule_ids = [r.get("id", "") for r in config.get("rules", [])]
        assert any(
            "pickle" in rid for rid in rule_ids
        ), "Should have a rule for unsafe pickle deserialization"

    def test_semgrep_has_exec_rule(self, llm_rules_path: Path):
        """Verify Semgrep has rule for unsafe exec/eval of LLM output."""
        if not llm_rules_path.exists():
            pytest.skip("llm-security.yaml not yet created")
        with open(llm_rules_path) as f:
            config = yaml.safe_load(f)
        rule_ids = [r.get("id", "") for r in config.get("rules", [])]
        assert any(
            "exec" in rid or "eval" in rid for rid in rule_ids
        ), "Should have a rule for unsafe exec/eval"


# =============================================================================
# Phase 3: SonarCloud Configuration Tests
# Issues: #215
# =============================================================================


class TestSonarConfig:
    """Tests for sonar-project.properties."""

    @pytest.fixture
    def sonar_path(self, project_root: Path) -> Path:
        """Path to SonarCloud config."""
        return project_root / "sonar-project.properties"

    @pytest.fixture
    def sonar_content(self, sonar_path: Path) -> str:
        """Load SonarCloud configuration as text."""
        if not sonar_path.exists():
            pytest.skip("sonar-project.properties not yet created")
        return sonar_path.read_text()

    def test_sonar_project_properties_exists(self, sonar_path: Path):
        """Verify sonar-project.properties exists."""
        assert sonar_path.exists(), "sonar-project.properties must exist"

    def test_sonar_has_project_key(self, sonar_content: str):
        """Verify SonarCloud project key is set."""
        assert "sonar.projectKey=" in sonar_content
        assert "amiable-dev_llm-council" in sonar_content

    def test_sonar_has_organization(self, sonar_content: str):
        """Verify SonarCloud organization is set."""
        assert "sonar.organization=" in sonar_content

    def test_sonar_sources_configured(self, sonar_content: str):
        """Verify source directories are configured."""
        assert "sonar.sources=" in sonar_content

    def test_sonar_tests_configured(self, sonar_content: str):
        """Verify test directories are configured."""
        assert "sonar.tests=" in sonar_content

    def test_sonar_python_version(self, sonar_content: str):
        """Verify Python version is specified."""
        assert "sonar.python.version=" in sonar_content


# =============================================================================
# Phase 4: Security Visibility Tests
# Issues: #218, #219
# =============================================================================


class TestSecurityVisibility:
    """Tests for security visibility in documentation."""

    @pytest.fixture
    def readme_content(self, project_root: Path) -> str:
        """Load README.md content."""
        readme_path = project_root / "README.md"
        return readme_path.read_text()

    @pytest.fixture
    def security_md_content(self, project_root: Path) -> str:
        """Load SECURITY.md content."""
        security_path = project_root / "SECURITY.md"
        return security_path.read_text()

    def test_readme_has_security_badges(self, readme_content: str):
        """Verify README has security badges."""
        # Check for at least one security-related badge
        security_badge_patterns = [
            "snyk.io",
            "securityscorecards.dev",
            "fossa.com",
            "workflows/security.yml/badge.svg",  # GitHub Actions security workflow
        ]
        has_badge = any(pattern in readme_content for pattern in security_badge_patterns)
        assert has_badge, "README should have at least one security badge"

    def test_security_md_has_automation_section(self, security_md_content: str):
        """Verify SECURITY.md documents automated scanning."""
        has_automation = "Automated" in security_md_content or "automated" in security_md_content
        assert has_automation, "SECURITY.md should have automated scanning section"
        assert "scanning" in security_md_content.lower()

    def test_security_md_mentions_tools(self, security_md_content: str):
        """Verify SECURITY.md mentions key security tools."""
        # Should mention at least some of the tools
        tools_mentioned = sum(
            1
            for tool in ["CodeQL", "Dependabot", "Gitleaks", "Semgrep"]
            if tool in security_md_content
        )
        assert tools_mentioned >= 2, "SECURITY.md should mention at least 2 security tools"

    def test_security_md_mentions_sbom(self, security_md_content: str):
        """Verify SECURITY.md mentions SBOM availability."""
        has_sbom = (
            "SBOM" in security_md_content or "Software Bill of Materials" in security_md_content
        )
        assert has_sbom, "SECURITY.md should mention SBOM"
