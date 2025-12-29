"""Tests for GitHub Actions security workflows.

ADR-035: DevSecOps Implementation
These tests validate security workflow configurations.

TDD Approach:
- Tests are written FIRST (RED phase)
- Workflow files are created to make tests pass (GREEN phase)
- Workflows are refined as needed (REFACTOR phase)
"""

from pathlib import Path

import pytest
import yaml


# =============================================================================
# Helpers
# =============================================================================


def normalize_yaml_on_key(config: dict) -> dict:
    """Normalize YAML config to handle 'on' being parsed as True.

    In YAML 1.1, 'on' is a reserved word that maps to boolean True.
    GitHub Actions workflows use 'on:' as a trigger key, which pyyaml
    parses as True. This function normalizes that back to 'on'.
    """
    if True in config and "on" not in config:
        config["on"] = config.pop(True)
    return config


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def project_root() -> Path:
    """Get project root directory."""
    return Path(__file__).parent.parent


@pytest.fixture
def workflows_dir(project_root: Path) -> Path:
    """Get .github/workflows directory."""
    return project_root / ".github" / "workflows"


# =============================================================================
# Security Workflow Tests (Layer 2 - Fork Compatible)
# Issues: #206, #207, #211, #209
# =============================================================================


class TestSecurityWorkflow:
    """Tests for .github/workflows/security.yml."""

    @pytest.fixture
    def workflow_path(self, workflows_dir: Path) -> Path:
        """Path to security workflow."""
        return workflows_dir / "security.yml"

    @pytest.fixture
    def workflow_config(self, workflow_path: Path) -> dict:
        """Load security workflow configuration."""
        if not workflow_path.exists():
            pytest.skip("security.yml not yet created")
        with open(workflow_path) as f:
            config = yaml.safe_load(f)
        return normalize_yaml_on_key(config)

    def test_security_workflow_exists(self, workflow_path: Path):
        """Verify security.yml workflow exists."""
        assert workflow_path.exists(), "security.yml must exist"

    def test_security_workflow_valid_yaml(self, workflow_path: Path):
        """Verify security.yml is valid YAML."""
        if not workflow_path.exists():
            pytest.skip("security.yml not yet created")
        with open(workflow_path) as f:
            try:
                yaml.safe_load(f)
            except yaml.YAMLError as e:
                pytest.fail(f"security.yml is not valid YAML: {e}")

    def test_security_workflow_has_name(self, workflow_config: dict):
        """Verify workflow has a name."""
        assert "name" in workflow_config

    def test_security_workflow_triggers_on_pr(self, workflow_config: dict):
        """Verify workflow runs on pull requests."""
        on = workflow_config.get("on", {})
        assert "pull_request" in on, "Workflow should trigger on pull_request"

    def test_security_workflow_triggers_on_push_master(self, workflow_config: dict):
        """Verify workflow runs on push to master."""
        on = workflow_config.get("on", {})
        push = on.get("push", {})
        branches = push.get("branches", [])
        assert "master" in branches, "Workflow should trigger on push to master"

    def test_security_workflow_has_codeql_job(self, workflow_config: dict):
        """Verify workflow includes CodeQL job."""
        jobs = workflow_config.get("jobs", {})
        assert "codeql" in jobs, "Workflow should have CodeQL job"

    def test_security_workflow_has_semgrep_job(self, workflow_config: dict):
        """Verify workflow includes Semgrep job."""
        jobs = workflow_config.get("jobs", {})
        assert "semgrep" in jobs, "Workflow should have Semgrep job"

    def test_security_workflow_has_gitleaks_job(self, workflow_config: dict):
        """Verify workflow includes Gitleaks job."""
        jobs = workflow_config.get("jobs", {})
        assert "gitleaks" in jobs, "Workflow should have Gitleaks job"

    def test_security_workflow_has_dependency_review_job(self, workflow_config: dict):
        """Verify workflow includes Dependency Review job."""
        jobs = workflow_config.get("jobs", {})
        assert "dependency-review" in jobs, "Workflow should have Dependency Review job"

    def test_security_workflow_fork_compatible_jobs_have_no_secrets(self, workflow_config: dict):
        """Verify fork-compatible jobs don't require secrets.

        Jobs in Layer 2 (PR checks) should work without repo secrets
        so that external contributors can run them from forks.
        """
        jobs = workflow_config.get("jobs", {})
        fork_compatible_jobs = ["codeql", "semgrep", "gitleaks", "dependency-review"]

        for job_name in fork_compatible_jobs:
            if job_name not in jobs:
                continue
            job = jobs[job_name]
            # Check for secrets.* references (except GITHUB_TOKEN which is always available)
            job_yaml = yaml.dump(job)
            # Find all secrets.XXX patterns
            import re

            secret_refs = re.findall(r"secrets\.(\w+)", job_yaml)
            non_github_secrets = [s for s in secret_refs if s != "GITHUB_TOKEN"]
            assert (
                len(non_github_secrets) == 0
            ), f"Fork-compatible job {job_name} references secrets: {non_github_secrets}"

    def test_security_workflow_actions_are_version_pinned(self, workflow_config: dict):
        """Verify all GitHub Actions are pinned to specific versions.

        Actions should use @vX.Y.Z or @SHA, not @master/@main.
        """
        jobs = workflow_config.get("jobs", {})
        for job_name, job in jobs.items():
            steps = job.get("steps", [])
            for step in steps:
                uses = step.get("uses", "")
                if uses and "@" in uses:
                    # Extract version after @
                    version = uses.split("@")[1]
                    assert version not in [
                        "master",
                        "main",
                        "latest",
                    ], f"Job {job_name} uses unpinned action: {uses}"


# =============================================================================
# Security Workflow Master-Only Jobs Tests (Layer 3)
# Issues: #215, #216, #217
# =============================================================================


class TestSecurityWorkflowMasterJobs:
    """Tests for master-only security jobs (require secrets)."""

    @pytest.fixture
    def workflow_path(self, workflows_dir: Path) -> Path:
        """Path to security workflow."""
        return workflows_dir / "security.yml"

    @pytest.fixture
    def workflow_config(self, workflow_path: Path) -> dict:
        """Load security workflow configuration."""
        if not workflow_path.exists():
            pytest.skip("security.yml not yet created")
        with open(workflow_path) as f:
            config = yaml.safe_load(f)
        return normalize_yaml_on_key(config)

    def test_security_workflow_has_sonarcloud_job(self, workflow_config: dict):
        """Verify workflow includes SonarCloud job."""
        jobs = workflow_config.get("jobs", {})
        assert "sonarcloud" in jobs, "Workflow should have SonarCloud job"

    def test_security_workflow_has_snyk_job(self, workflow_config: dict):
        """Verify workflow includes Snyk monitoring job."""
        jobs = workflow_config.get("jobs", {})
        assert "snyk-monitor" in jobs, "Workflow should have Snyk monitor job"

    def test_security_workflow_has_trivy_job(self, workflow_config: dict):
        """Verify workflow includes Trivy SCA job."""
        jobs = workflow_config.get("jobs", {})
        assert "trivy-sca" in jobs, "Workflow should have Trivy SCA job"

    def test_security_workflow_has_sbom_job(self, workflow_config: dict):
        """Verify workflow includes SBOM generation job."""
        jobs = workflow_config.get("jobs", {})
        assert "sbom-generate" in jobs, "Workflow should have SBOM generation job"

    def test_secret_requiring_jobs_are_master_only(self, workflow_config: dict):
        """Verify jobs requiring secrets only run on master push."""
        secret_jobs = ["sonarcloud", "snyk-monitor", "trivy-sca"]
        jobs = workflow_config.get("jobs", {})

        for job_name in secret_jobs:
            if job_name not in jobs:
                continue
            job = jobs[job_name]
            condition = job.get("if", "")
            # Must have condition limiting to push on master
            has_push_condition = "push" in condition
            has_master_condition = "refs/heads/master" in condition or "master" in condition
            assert (
                has_push_condition or has_master_condition
            ), f"Job {job_name} should only run on master push, got: {condition}"


# =============================================================================
# Release Security Workflow Tests (Layer 4)
# Issues: #213, #221
# =============================================================================


class TestReleaseSecurityWorkflow:
    """Tests for .github/workflows/release-security.yml."""

    @pytest.fixture
    def workflow_path(self, workflows_dir: Path) -> Path:
        """Path to release security workflow."""
        return workflows_dir / "release-security.yml"

    @pytest.fixture
    def workflow_config(self, workflow_path: Path) -> dict:
        """Load release security workflow configuration."""
        if not workflow_path.exists():
            pytest.skip("release-security.yml not yet created")
        with open(workflow_path) as f:
            config = yaml.safe_load(f)
        return normalize_yaml_on_key(config)

    def test_release_security_workflow_exists(self, workflow_path: Path):
        """Verify release-security.yml workflow exists."""
        assert workflow_path.exists(), "release-security.yml should exist for Layer 4"

    def test_release_security_triggers_on_release(self, workflow_config: dict):
        """Verify workflow runs on release publish."""
        on = workflow_config.get("on", {})
        assert "release" in on, "Workflow should trigger on release"

    def test_release_security_has_sbom_attachment(self, workflow_config: dict):
        """Verify workflow attaches SBOM to releases."""
        jobs = workflow_config.get("jobs", {})
        assert "sbom-attach" in jobs, "Workflow should have SBOM attachment job"

    def test_release_security_has_proper_permissions(self, workflow_config: dict):
        """Verify workflow has required permissions for release attachment."""
        permissions = workflow_config.get("permissions", {})
        # Need write access to attach files to releases
        assert (
            permissions.get("contents") == "write"
        ), "Workflow needs contents: write to attach files to releases"

    def test_release_security_has_provenance_job(self, workflow_config: dict):
        """Verify workflow has SLSA provenance generation job."""
        jobs = workflow_config.get("jobs", {})
        assert "provenance" in jobs, "Workflow should have provenance job for SLSA"

    def test_release_security_provenance_uses_attest_action(self, workflow_config: dict):
        """Verify provenance job uses GitHub's attest-build-provenance action."""
        jobs = workflow_config.get("jobs", {})
        provenance = jobs.get("provenance", {})
        steps = provenance.get("steps", [])

        attest_step = None
        for step in steps:
            uses = step.get("uses", "")
            if "attest-build-provenance" in uses:
                attest_step = step
                break

        assert attest_step is not None, "Should use actions/attest-build-provenance"

    def test_release_security_has_attestations_permission(self, workflow_config: dict):
        """Verify workflow has attestations: write for SLSA provenance."""
        permissions = workflow_config.get("permissions", {})
        assert (
            permissions.get("attestations") == "write"
        ), "Workflow needs attestations: write for SLSA provenance"

    def test_release_security_has_id_token_permission(self, workflow_config: dict):
        """Verify workflow has id-token: write for Sigstore signing."""
        permissions = workflow_config.get("permissions", {})
        assert (
            permissions.get("id-token") == "write"
        ), "Workflow needs id-token: write for Sigstore OIDC signing"

    def test_release_security_sbom_uses_correct_format_flag(self, workflow_config: dict):
        """Verify SBOM generation uses --output-format (not --format)."""
        jobs = workflow_config.get("jobs", {})
        sbom_job = jobs.get("sbom-attach", {})
        steps = sbom_job.get("steps", [])

        sbom_step = None
        for step in steps:
            if step.get("name", "").lower().startswith("generate sbom"):
                sbom_step = step
                break

        assert sbom_step is not None, "Should have SBOM generation step"
        run_cmd = sbom_step.get("run", "")
        assert "--output-format" in run_cmd, "Should use --output-format (not --format)"
        assert "--format json" not in run_cmd, "Should NOT use deprecated --format flag"


# =============================================================================
# CI Workflow Version Pinning Tests
# Issues: #214
# =============================================================================


class TestCIWorkflowVersionPinning:
    """Tests for version pinning in existing CI workflow."""

    @pytest.fixture
    def workflow_path(self, workflows_dir: Path) -> Path:
        """Path to CI workflow."""
        return workflows_dir / "ci.yml"

    @pytest.fixture
    def workflow_config(self, workflow_path: Path) -> dict:
        """Load CI workflow configuration."""
        if not workflow_path.exists():
            pytest.skip("ci.yml not found")
        with open(workflow_path) as f:
            config = yaml.safe_load(f)
        return normalize_yaml_on_key(config)

    def test_ci_workflow_actions_are_version_pinned(self, workflow_config: dict):
        """Verify all CI workflow actions are pinned to specific versions."""
        jobs = workflow_config.get("jobs", {})
        for job_name, job in jobs.items():
            steps = job.get("steps", [])
            for step in steps:
                uses = step.get("uses", "")
                if uses and "@" in uses:
                    version = uses.split("@")[1]
                    assert version not in [
                        "master",
                        "main",
                        "latest",
                    ], f"CI job {job_name} uses unpinned action: {uses}"


# =============================================================================
# Dependency Review License Blocking Tests
# Issues: #207
# =============================================================================


class TestDependencyReviewConfig:
    """Tests for Dependency Review license blocking configuration."""

    @pytest.fixture
    def config_path(self, project_root: Path) -> Path:
        """Path to dependency review config file."""
        return project_root / ".github" / "dependency-review-config.yml"

    @pytest.fixture
    def config(self, config_path: Path) -> dict:
        """Load dependency review configuration."""
        if not config_path.exists():
            pytest.skip("dependency-review-config.yml not yet created")
        with open(config_path) as f:
            return yaml.safe_load(f)

    @pytest.fixture
    def workflow_path(self, workflows_dir: Path) -> Path:
        """Path to security workflow."""
        return workflows_dir / "security.yml"

    @pytest.fixture
    def workflow_config(self, workflow_path: Path) -> dict:
        """Load security workflow configuration."""
        if not workflow_path.exists():
            pytest.skip("security.yml not yet created")
        with open(workflow_path) as f:
            config = yaml.safe_load(f)
        return normalize_yaml_on_key(config)

    def test_dependency_review_config_exists(self, config_path: Path):
        """Verify dependency-review-config.yml exists."""
        assert config_path.exists(), "dependency-review-config.yml must exist"

    def test_workflow_uses_config_file(self, workflow_config: dict):
        """Verify workflow references the config file."""
        jobs = workflow_config.get("jobs", {})
        dep_review = jobs.get("dependency-review", {})
        steps = dep_review.get("steps", [])

        # Find the Dependency Review action step
        dep_review_step = None
        for step in steps:
            uses = step.get("uses", "")
            if "dependency-review-action" in uses:
                dep_review_step = step
                break

        assert dep_review_step is not None, "Should have Dependency Review action"

        with_config = dep_review_step.get("with", {})
        config_file = with_config.get("config-file", "")
        assert (
            "dependency-review-config.yml" in config_file
        ), "Workflow should reference dependency-review-config.yml"

    def test_dependency_review_blocks_gpl(self, config: dict):
        """Verify Dependency Review blocks GPL licenses."""
        deny_licenses = config.get("deny-licenses", [])

        # Check for GPL licenses in deny list
        gpl_licenses = ["GPL-2.0", "GPL-3.0", "AGPL-3.0"]
        for license_id in gpl_licenses:
            assert license_id in deny_licenses, f"Dependency Review should block {license_id}"

    def test_dependency_review_fails_on_high_severity(self, config: dict):
        """Verify Dependency Review fails on high severity vulnerabilities."""
        fail_on = config.get("fail-on-severity", "")
        assert fail_on == "high", "Dependency Review should fail on high severity"

    def test_dependency_review_allows_sonarqube_action(self, config: dict):
        """Verify SonarQube action is allowed despite LGPL-3.0 license."""
        allow_list = config.get("allow-dependencies-licenses", [])
        sonar_allowed = any("sonarqube-scan-action" in pkg for pkg in allow_list)
        assert (
            sonar_allowed
        ), "SonarQube action should be allowed (build-time tool, not distributed)"


# =============================================================================
# OpenSSF Scorecard Workflow Tests (Phase 4 - Visibility)
# Issue: #220
# =============================================================================


class TestScorecardWorkflow:
    """Tests for .github/workflows/scorecard.yml."""

    @pytest.fixture
    def workflow_path(self, workflows_dir: Path) -> Path:
        """Path to scorecard workflow."""
        return workflows_dir / "scorecard.yml"

    @pytest.fixture
    def workflow_config(self, workflow_path: Path) -> dict:
        """Load scorecard workflow configuration."""
        if not workflow_path.exists():
            pytest.skip("scorecard.yml not yet created")
        with open(workflow_path) as f:
            config = yaml.safe_load(f)
        return normalize_yaml_on_key(config)

    def test_scorecard_workflow_exists(self, workflow_path: Path):
        """Verify scorecard.yml workflow exists."""
        assert workflow_path.exists(), "scorecard.yml must exist for OpenSSF Scorecard"

    def test_scorecard_workflow_valid_yaml(self, workflow_path: Path):
        """Verify scorecard.yml is valid YAML."""
        if not workflow_path.exists():
            pytest.skip("scorecard.yml not yet created")
        with open(workflow_path) as f:
            try:
                yaml.safe_load(f)
            except yaml.YAMLError as e:
                pytest.fail(f"scorecard.yml is not valid YAML: {e}")

    def test_scorecard_workflow_has_name(self, workflow_config: dict):
        """Verify workflow has a name."""
        assert "name" in workflow_config
        assert "Scorecard" in workflow_config["name"]

    def test_scorecard_workflow_triggers_on_push_master(self, workflow_config: dict):
        """Verify workflow runs on push to master."""
        on = workflow_config.get("on", {})
        push = on.get("push", {})
        branches = push.get("branches", [])
        assert "master" in branches, "Scorecard should trigger on push to master"

    def test_scorecard_workflow_has_schedule(self, workflow_config: dict):
        """Verify workflow runs on a schedule."""
        on = workflow_config.get("on", {})
        assert "schedule" in on, "Scorecard should have scheduled runs"

    def test_scorecard_workflow_has_analysis_job(self, workflow_config: dict):
        """Verify workflow has analysis job."""
        jobs = workflow_config.get("jobs", {})
        assert "analysis" in jobs, "Workflow should have analysis job"

    def test_scorecard_workflow_uses_scorecard_action(self, workflow_config: dict):
        """Verify workflow uses ossf/scorecard-action."""
        jobs = workflow_config.get("jobs", {})
        analysis = jobs.get("analysis", {})
        steps = analysis.get("steps", [])

        scorecard_step = None
        for step in steps:
            uses = step.get("uses", "")
            if "scorecard-action" in uses:
                scorecard_step = step
                break

        assert scorecard_step is not None, "Should use ossf/scorecard-action"

    def test_scorecard_workflow_publishes_results(self, workflow_config: dict):
        """Verify workflow publishes results for badge/API access."""
        jobs = workflow_config.get("jobs", {})
        analysis = jobs.get("analysis", {})
        steps = analysis.get("steps", [])

        scorecard_step = None
        for step in steps:
            uses = step.get("uses", "")
            if "scorecard-action" in uses:
                scorecard_step = step
                break

        assert scorecard_step is not None
        with_config = scorecard_step.get("with", {})
        assert with_config.get("publish_results") is True, "Scorecard should publish results"

    def test_scorecard_workflow_has_required_permissions(self, workflow_config: dict):
        """Verify workflow has required permissions for publishing."""
        jobs = workflow_config.get("jobs", {})
        analysis = jobs.get("analysis", {})
        permissions = analysis.get("permissions", {})

        # Required for publishing results
        assert (
            permissions.get("security-events") == "write"
        ), "Need security-events: write for SARIF upload"
        assert (
            permissions.get("id-token") == "write"
        ), "Need id-token: write for OIDC token (publish_results)"

    def test_scorecard_workflow_uploads_sarif(self, workflow_config: dict):
        """Verify workflow uploads SARIF to code-scanning."""
        jobs = workflow_config.get("jobs", {})
        analysis = jobs.get("analysis", {})
        steps = analysis.get("steps", [])

        sarif_upload_found = False
        for step in steps:
            uses = step.get("uses", "")
            if "upload-sarif" in uses:
                sarif_upload_found = True
                break

        assert sarif_upload_found, "Workflow should upload SARIF to code-scanning"

    def test_scorecard_workflow_actions_are_version_pinned(self, workflow_config: dict):
        """Verify all actions are pinned to specific versions."""
        jobs = workflow_config.get("jobs", {})
        for job_name, job in jobs.items():
            steps = job.get("steps", [])
            for step in steps:
                uses = step.get("uses", "")
                if uses and "@" in uses:
                    version = uses.split("@")[1]
                    assert version not in [
                        "master",
                        "main",
                        "latest",
                    ], f"Scorecard job uses unpinned action: {uses}"
