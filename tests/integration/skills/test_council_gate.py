"""
Integration tests for council-gate skill (ADR-034 B5).

Tests skill discovery, progressive disclosure, and CI/CD-specific features.
"""

from pathlib import Path

import pytest

from llm_council.skills.loader import (
    SkillLoader,
    SkillMetadata,
    SkillFull,
)


# Path to the skills directory
SKILLS_DIR = Path(__file__).parent.parent.parent.parent / ".github" / "skills"


@pytest.fixture
def loader() -> SkillLoader:
    """Create a SkillLoader for the project's skills directory."""
    return SkillLoader(SKILLS_DIR)


class TestCouncilGateSkillDiscovery:
    """Tests for skill discovery via SkillLoader."""

    def test_council_gate_skill_exists(self, loader: SkillLoader):
        """council-gate skill should be discoverable."""
        skills = loader.list_skills()
        assert "council-gate" in skills

    def test_council_gate_has_skill_md(self):
        """council-gate should have SKILL.md file."""
        skill_md = SKILLS_DIR / "council-gate" / "SKILL.md"
        assert skill_md.exists()

    def test_council_gate_has_references_dir(self):
        """council-gate should have references/ directory."""
        refs_dir = SKILLS_DIR / "council-gate" / "references"
        assert refs_dir.exists()
        assert refs_dir.is_dir()


class TestCouncilGateProgressiveDisclosure:
    """Tests for progressive disclosure levels."""

    def test_level1_metadata_loads(self, loader: SkillLoader):
        """Level 1: Should load metadata from YAML frontmatter."""
        metadata = loader.load_metadata("council-gate")

        assert metadata.name == "council-gate"
        assert metadata.description is not None
        assert len(metadata.description) > 0

    def test_level1_metadata_is_compact(self, loader: SkillLoader):
        """Level 1: Metadata should be token-efficient (~100-200 tokens)."""
        metadata = loader.load_metadata("council-gate")

        # Should be under 300 tokens for efficient discovery
        assert metadata.estimated_tokens < 300

    def test_level1_metadata_has_allowed_tools(self, loader: SkillLoader):
        """Level 1: Metadata should specify allowed tools."""
        metadata = loader.load_metadata("council-gate")

        # council-gate needs file reading and MCP access
        assert len(metadata.allowed_tools) > 0
        assert any(tool in metadata.allowed_tools for tool in ["Read", "Grep"])

    def test_level1_metadata_has_cicd_category(self, loader: SkillLoader):
        """Level 1: Metadata should have ci-cd category."""
        metadata = loader.load_metadata("council-gate")

        assert metadata.category is not None
        assert metadata.category == "ci-cd"

    def test_level1_metadata_has_devops_domain(self, loader: SkillLoader):
        """Level 1: Metadata should have devops domain."""
        metadata = loader.load_metadata("council-gate")

        assert metadata.domain is not None
        assert metadata.domain == "devops"

    def test_level2_full_loads(self, loader: SkillLoader):
        """Level 2: Should load full SKILL.md content."""
        full = loader.load_full("council-gate")

        assert full.metadata.name == "council-gate"
        assert len(full.body) > 0

    def test_level2_body_has_exit_codes(self, loader: SkillLoader):
        """Level 2: Body should document exit codes."""
        full = loader.load_full("council-gate")

        # Should document all three exit codes
        assert "exit" in full.body.lower() or "Exit" in full.body
        assert "0" in full.body  # PASS
        assert "1" in full.body  # FAIL
        assert "2" in full.body  # UNCLEAR

    def test_level2_body_has_github_actions(self, loader: SkillLoader):
        """Level 2: Body should include GitHub Actions example."""
        full = loader.load_full("council-gate")

        assert "github" in full.body.lower() or "GitHub" in full.body
        assert "actions" in full.body.lower() or "Actions" in full.body

    def test_level2_body_has_transcript_location(self, loader: SkillLoader):
        """Level 2: Body should document transcript location."""
        full = loader.load_full("council-gate")

        assert ".council" in full.body or "council/logs" in full.body

    def test_level2_body_larger_than_metadata(self, loader: SkillLoader):
        """Level 2: Full content should be larger than metadata alone."""
        metadata = loader.load_metadata("council-gate")
        full = loader.load_full("council-gate")

        assert full.estimated_tokens > metadata.estimated_tokens

    def test_level3_resources_available(self, loader: SkillLoader):
        """Level 3: Should have resources in references/ directory."""
        resources = loader.list_resources("council-gate")

        assert len(resources) > 0
        assert "ci-cd-rubric.md" in resources

    def test_level3_rubric_content(self, loader: SkillLoader):
        """Level 3: ci-cd-rubric.md should contain scoring guidelines."""
        rubric = loader.load_resource("council-gate", "ci-cd-rubric.md")

        # Per ADR-016, rubrics should have these dimensions
        assert "Accuracy" in rubric
        assert "Completeness" in rubric
        assert "Clarity" in rubric
        assert "Conciseness" in rubric
        assert "Relevance" in rubric


class TestCICDRubricContent:
    """Tests for CI/CD-specific rubric content."""

    def test_rubric_has_exit_code_documentation(self, loader: SkillLoader):
        """Rubric should document exit code meanings."""
        rubric = loader.load_resource("council-gate", "ci-cd-rubric.md")

        # Must document all three exit codes
        assert "Exit Code 0" in rubric or "exit_code" in rubric
        assert "PASS" in rubric
        assert "FAIL" in rubric
        assert "UNCLEAR" in rubric

    def test_rubric_has_accuracy_ceiling(self, loader: SkillLoader):
        """Rubric should document accuracy ceiling rule."""
        rubric = loader.load_resource("council-gate", "ci-cd-rubric.md")

        assert "ceiling" in rubric.lower()
        assert "4.0" in rubric or "4" in rubric
        assert "7.0" in rubric or "7" in rubric

    def test_rubric_has_cicd_accuracy_checks(self, loader: SkillLoader):
        """Rubric should have CI/CD-specific accuracy checks."""
        rubric = loader.load_resource("council-gate", "ci-cd-rubric.md")

        # CI/CD-specific concerns
        cicd_checks = ["migration", "dependency", "configuration", "breaking"]
        matches = [check for check in cicd_checks if check.lower() in rubric.lower()]
        assert len(matches) >= 2, f"Expected 2+ CI/CD checks, found: {matches}"

    def test_rubric_has_security_focus(self, loader: SkillLoader):
        """Rubric should have security-specific criteria."""
        rubric = loader.load_resource("council-gate", "ci-cd-rubric.md")

        assert "Security" in rubric
        # Security concerns for CI/CD
        security_terms = ["secrets", "CVE", "vulnerability", "authentication"]
        matches = [term for term in security_terms if term.lower() in rubric.lower()]
        assert len(matches) >= 2, f"Expected 2+ security terms, found: {matches}"

    def test_rubric_has_performance_focus(self, loader: SkillLoader):
        """Rubric should have performance-specific criteria."""
        rubric = loader.load_resource("council-gate", "ci-cd-rubric.md")

        assert "Performance" in rubric
        # Performance concerns for CI/CD
        perf_terms = ["regression", "bundle", "response time", "memory"]
        matches = [term for term in perf_terms if term.lower() in rubric.lower()]
        assert len(matches) >= 2, f"Expected 2+ performance terms, found: {matches}"

    def test_rubric_has_compliance_focus(self, loader: SkillLoader):
        """Rubric should have compliance-specific criteria."""
        rubric = loader.load_resource("council-gate", "ci-cd-rubric.md")

        assert "Compliance" in rubric
        # Compliance concerns
        compliance_terms = ["GDPR", "HIPAA", "SOC2", "audit", "license"]
        matches = [term for term in compliance_terms if term.lower() in rubric.lower()]
        assert len(matches) >= 2, f"Expected 2+ compliance terms, found: {matches}"

    def test_rubric_has_blocking_issues(self, loader: SkillLoader):
        """Rubric should define blocking issue severity levels."""
        rubric = loader.load_resource("council-gate", "ci-cd-rubric.md")

        assert "Blocking" in rubric
        assert "Critical" in rubric
        assert "Major" in rubric

    def test_rubric_has_pipeline_patterns(self, loader: SkillLoader):
        """Rubric should include pipeline integration patterns."""
        rubric = loader.load_resource("council-gate", "ci-cd-rubric.md")

        # Should have at least GitHub Actions example
        assert "GitHub Actions" in rubric or "github-actions" in rubric.lower()


class TestCouncilGateExitCodes:
    """Tests for exit code documentation."""

    def test_skill_documents_pass_exit_code(self, loader: SkillLoader):
        """Skill should document exit code 0 = PASS."""
        full = loader.load_full("council-gate")

        # Check for PASS documentation
        assert "PASS" in full.body or "pass" in full.body.lower()
        assert "0" in full.body

    def test_skill_documents_fail_exit_code(self, loader: SkillLoader):
        """Skill should document exit code 1 = FAIL."""
        full = loader.load_full("council-gate")

        # Check for FAIL documentation
        assert "FAIL" in full.body or "fail" in full.body.lower()
        assert "1" in full.body

    def test_skill_documents_unclear_exit_code(self, loader: SkillLoader):
        """Skill should document exit code 2 = UNCLEAR."""
        full = loader.load_full("council-gate")

        # Check for UNCLEAR documentation
        assert "UNCLEAR" in full.body or "unclear" in full.body.lower()
        assert "2" in full.body

    def test_rubric_maps_confidence_to_exit_code(self, loader: SkillLoader):
        """Rubric should explain confidence to exit code mapping."""
        rubric = loader.load_resource("council-gate", "ci-cd-rubric.md")

        # Should explain confidence threshold
        assert "confidence" in rubric.lower()
        assert "threshold" in rubric.lower()


class TestCouncilGateSkillFormat:
    """Tests for SKILL.md format compliance."""

    def test_skill_md_has_yaml_frontmatter(self):
        """SKILL.md should start with YAML frontmatter."""
        skill_md = SKILLS_DIR / "council-gate" / "SKILL.md"
        content = skill_md.read_text()

        assert content.startswith("---")
        second_delimiter = content.find("---", 3)
        assert second_delimiter > 0

    def test_skill_md_has_required_fields(self, loader: SkillLoader):
        """SKILL.md frontmatter should have required fields."""
        metadata = loader.load_metadata("council-gate")

        assert metadata.name is not None
        assert metadata.description is not None

    def test_skill_md_has_license(self, loader: SkillLoader):
        """SKILL.md should specify a license."""
        metadata = loader.load_metadata("council-gate")

        assert metadata.license is not None
        assert metadata.license in ["MIT", "Apache-2.0", "BSD-3-Clause", "GPL-3.0"]


class TestCouncilGateMCPIntegration:
    """Tests for MCP server integration."""

    def test_allowed_tools_includes_mcp(self, loader: SkillLoader):
        """Skill should allow MCP tool access."""
        metadata = loader.load_metadata("council-gate")

        mcp_tools = [t for t in metadata.allowed_tools if t.startswith("mcp:")]
        assert len(mcp_tools) > 0, "Should have at least one MCP tool"

    def test_mcp_tool_references_llm_council(self, loader: SkillLoader):
        """MCP tool should reference llm-council server."""
        metadata = loader.load_metadata("council-gate")

        mcp_tools = [t for t in metadata.allowed_tools if t.startswith("mcp:")]
        assert any("llm-council" in t for t in mcp_tools)


class TestCouncilGateVsOtherSkills:
    """Tests comparing council-gate to other skills."""

    def test_different_categories_from_verify(self, loader: SkillLoader):
        """council-gate should have different category than verify."""
        gate_meta = loader.load_metadata("council-gate")
        verify_meta = loader.load_metadata("council-verify")

        assert gate_meta.category != verify_meta.category
        assert gate_meta.category == "ci-cd"

    def test_devops_domain(self, loader: SkillLoader):
        """council-gate should have devops domain."""
        gate_meta = loader.load_metadata("council-gate")

        assert gate_meta.domain == "devops"

    def test_gate_and_verify_use_progressive_disclosure(self, loader: SkillLoader):
        """Gate and verify skills should support progressive disclosure."""
        gate_resources = loader.list_resources("council-gate")
        verify_resources = loader.list_resources("council-verify")

        assert len(gate_resources) > 0
        assert len(verify_resources) > 0


class TestProgressiveDisclosureTokenEfficiency:
    """Integration tests for token efficiency across levels."""

    def test_level1_under_200_tokens(self, loader: SkillLoader):
        """Level 1 should stay under 200 tokens for efficient discovery."""
        metadata = loader.load_metadata("council-gate")
        assert metadata.estimated_tokens < 200

    def test_level2_under_1000_tokens(self, loader: SkillLoader):
        """Level 2 should stay under 1000 tokens for reasonable context."""
        full = loader.load_full("council-gate")
        assert full.estimated_tokens < 1000

    def test_level3_adds_substantial_content(self, loader: SkillLoader):
        """Level 3 resources should add substantial content."""
        full = loader.load_full("council-gate")
        rubric = loader.load_resource("council-gate", "ci-cd-rubric.md")

        level3_tokens = full.estimated_tokens + len(rubric) // 4
        assert level3_tokens > full.estimated_tokens * 1.5


class TestGateAndVerifyIntegration:
    """Integration tests verifying gate and verify skills work together."""

    def test_gate_and_verify_discoverable(self, loader: SkillLoader):
        """Gate and verify skills should be discoverable."""
        skills = loader.list_skills()

        assert "council-verify" in skills
        assert "council-gate" in skills

    def test_skills_have_distinct_categories(self, loader: SkillLoader):
        """Gate and verify should have distinct categories."""
        verify_meta = loader.load_metadata("council-verify")
        gate_meta = loader.load_metadata("council-gate")

        assert verify_meta.category != gate_meta.category

    def test_gate_and_verify_have_rubrics(self, loader: SkillLoader):
        """Gate and verify should have rubric resources."""
        verify_resources = loader.list_resources("council-verify")
        gate_resources = loader.list_resources("council-gate")

        assert any("rubric" in r.lower() for r in verify_resources)
        assert any("rubric" in r.lower() for r in gate_resources)
