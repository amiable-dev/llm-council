"""
Integration tests for council-verify skill (ADR-034 B3).

Tests skill discovery, progressive disclosure, and MCP integration.
"""

from pathlib import Path
from typing import Optional

import pytest

from llm_council.skills.loader import (
    SkillLoader,
    SkillMetadata,
    SkillFull,
    SkillNotFoundError,
)


# Path to the skills directory
SKILLS_DIR = Path(__file__).parent.parent.parent.parent / ".github" / "skills"


@pytest.fixture
def loader() -> SkillLoader:
    """Create a SkillLoader for the project's skills directory."""
    return SkillLoader(SKILLS_DIR)


class TestCouncilVerifySkillDiscovery:
    """Tests for skill discovery via SkillLoader."""

    def test_skills_directory_exists(self):
        """Skills directory should exist at .github/skills/."""
        assert SKILLS_DIR.exists(), f"Skills directory not found: {SKILLS_DIR}"

    def test_council_verify_skill_exists(self, loader: SkillLoader):
        """council-verify skill should be discoverable."""
        skills = loader.list_skills()
        assert "council-verify" in skills

    def test_council_verify_has_skill_md(self):
        """council-verify should have SKILL.md file."""
        skill_md = SKILLS_DIR / "council-verify" / "SKILL.md"
        assert skill_md.exists()

    def test_council_verify_has_references_dir(self):
        """council-verify should have references/ directory."""
        refs_dir = SKILLS_DIR / "council-verify" / "references"
        assert refs_dir.exists()
        assert refs_dir.is_dir()


class TestCouncilVerifyProgressiveDisclosure:
    """Tests for progressive disclosure levels."""

    def test_level1_metadata_loads(self, loader: SkillLoader):
        """Level 1: Should load metadata from YAML frontmatter."""
        metadata = loader.load_metadata("council-verify")

        assert metadata.name == "council-verify"
        assert metadata.description is not None
        assert len(metadata.description) > 0

    def test_level1_metadata_is_compact(self, loader: SkillLoader):
        """Level 1: Metadata should be token-efficient (~100-200 tokens)."""
        metadata = loader.load_metadata("council-verify")

        # Should be under 300 tokens for efficient discovery
        assert metadata.estimated_tokens < 300

    def test_level1_metadata_has_allowed_tools(self, loader: SkillLoader):
        """Level 1: Metadata should specify allowed tools."""
        metadata = loader.load_metadata("council-verify")

        # council-verify needs file reading and MCP access
        assert len(metadata.allowed_tools) > 0
        # Common tools for verification
        assert any(tool in metadata.allowed_tools for tool in ["Read", "Grep", "Glob"])

    def test_level1_metadata_has_category(self, loader: SkillLoader):
        """Level 1: Metadata should have category for filtering."""
        metadata = loader.load_metadata("council-verify")

        assert metadata.category is not None
        assert metadata.category in ["verification", "quality", "review"]

    def test_level2_full_loads(self, loader: SkillLoader):
        """Level 2: Should load full SKILL.md content."""
        full = loader.load_full("council-verify")

        assert full.metadata.name == "council-verify"
        assert len(full.body) > 0

    def test_level2_body_has_instructions(self, loader: SkillLoader):
        """Level 2: Body should contain usage instructions."""
        full = loader.load_full("council-verify")

        # Should have instruction sections
        assert "#" in full.body  # Has headers
        assert "verify" in full.body.lower() or "verification" in full.body.lower()

    def test_level2_body_larger_than_metadata(self, loader: SkillLoader):
        """Level 2: Full content should be larger than metadata alone."""
        metadata = loader.load_metadata("council-verify")
        full = loader.load_full("council-verify")

        assert full.estimated_tokens > metadata.estimated_tokens

    def test_level3_resources_available(self, loader: SkillLoader):
        """Level 3: Should have resources in references/ directory."""
        resources = loader.list_resources("council-verify")

        assert len(resources) > 0
        assert "rubrics.md" in resources

    def test_level3_rubrics_content(self, loader: SkillLoader):
        """Level 3: rubrics.md should contain scoring guidelines."""
        rubrics = loader.load_resource("council-verify", "rubrics.md")

        # Per ADR-016, rubrics should have these dimensions
        assert "Accuracy" in rubrics
        assert "Completeness" in rubrics
        assert "Clarity" in rubrics
        assert "Conciseness" in rubrics
        assert "Relevance" in rubrics

    def test_level3_rubrics_has_weights(self, loader: SkillLoader):
        """Level 3: rubrics.md should specify dimension weights."""
        rubrics = loader.load_resource("council-verify", "rubrics.md")

        # Per ADR-016, weights should be specified
        assert "30%" in rubrics  # Accuracy weight
        assert "25%" in rubrics  # Completeness weight

    def test_level3_rubrics_has_security_focus(self, loader: SkillLoader):
        """Level 3: rubrics.md should have security-specific criteria."""
        rubrics = loader.load_resource("council-verify", "rubrics.md")

        # Security domain-specific checks
        assert "Security" in rubrics
        # Common security concerns
        security_terms = ["injection", "authentication", "vulnerability", "OWASP"]
        assert any(term.lower() in rubrics.lower() for term in security_terms)


class TestCouncilVerifySkillFormat:
    """Tests for SKILL.md format compliance."""

    def test_skill_md_has_yaml_frontmatter(self):
        """SKILL.md should start with YAML frontmatter."""
        skill_md = SKILLS_DIR / "council-verify" / "SKILL.md"
        content = skill_md.read_text()

        assert content.startswith("---")
        # Find second delimiter
        second_delimiter = content.find("---", 3)
        assert second_delimiter > 0

    def test_skill_md_has_required_fields(self, loader: SkillLoader):
        """SKILL.md frontmatter should have required fields."""
        metadata = loader.load_metadata("council-verify")

        # Required per SKILL.md spec
        assert metadata.name is not None
        assert metadata.description is not None

    def test_skill_md_has_license(self, loader: SkillLoader):
        """SKILL.md should specify a license."""
        metadata = loader.load_metadata("council-verify")

        assert metadata.license is not None
        assert metadata.license in ["MIT", "Apache-2.0", "BSD-3-Clause", "GPL-3.0"]


class TestCouncilVerifyMCPIntegration:
    """Tests for MCP server integration."""

    def test_allowed_tools_includes_mcp(self, loader: SkillLoader):
        """Skill should allow MCP tool access."""
        metadata = loader.load_metadata("council-verify")

        # Check for MCP tool pattern
        mcp_tools = [t for t in metadata.allowed_tools if t.startswith("mcp:")]
        assert len(mcp_tools) > 0, "Should have at least one MCP tool"

    def test_mcp_tool_is_council_verify(self, loader: SkillLoader):
        """MCP tool should reference council verify endpoint."""
        metadata = loader.load_metadata("council-verify")

        mcp_tools = [t for t in metadata.allowed_tools if t.startswith("mcp:")]
        # Should reference llm-council MCP server
        assert any("llm-council" in t for t in mcp_tools)


class TestCouncilVerifyExitCodes:
    """Tests for verification exit code documentation."""

    def test_body_documents_exit_codes(self, loader: SkillLoader):
        """Skill body should document exit codes for CI/CD integration."""
        full = loader.load_full("council-verify")

        # Exit codes per ADR-034
        assert "exit" in full.body.lower() or "return" in full.body.lower()
        # Should mention the three outcomes
        assert "pass" in full.body.lower() or "success" in full.body.lower()
        assert "fail" in full.body.lower()

    def test_rubrics_documents_verdict_determination(self, loader: SkillLoader):
        """Rubrics should explain how verdicts are determined."""
        rubrics = loader.load_resource("council-verify", "rubrics.md")

        # Should have verdict section
        assert "verdict" in rubrics.lower() or "exit" in rubrics.lower()
        # Should mention threshold
        assert "threshold" in rubrics.lower()


class TestCouncilVerifyAccuracyCeiling:
    """Tests for ADR-016 accuracy ceiling rule."""

    def test_rubrics_documents_accuracy_ceiling(self, loader: SkillLoader):
        """Rubrics should document the accuracy ceiling rule."""
        rubrics = loader.load_resource("council-verify", "rubrics.md")

        # Per ADR-016, accuracy acts as ceiling
        assert "ceiling" in rubrics.lower()
        # Should mention the specific thresholds
        assert "4.0" in rubrics or "4" in rubrics  # Low accuracy cap
        assert "7.0" in rubrics or "7" in rubrics  # Medium accuracy cap


class TestProgressiveDisclosureTokenEfficiency:
    """Integration tests for token efficiency across levels."""

    def test_level1_under_200_tokens(self, loader: SkillLoader):
        """Level 1 should stay under 200 tokens for efficient discovery."""
        metadata = loader.load_metadata("council-verify")
        assert metadata.estimated_tokens < 200

    def test_level2_under_1000_tokens(self, loader: SkillLoader):
        """Level 2 should stay under 1000 tokens for reasonable context."""
        full = loader.load_full("council-verify")
        assert full.estimated_tokens < 1000

    def test_level3_adds_substantial_content(self, loader: SkillLoader):
        """Level 3 resources should add substantial content."""
        full = loader.load_full("council-verify")
        rubrics = loader.load_resource("council-verify", "rubrics.md")

        level3_tokens = full.estimated_tokens + len(rubrics) // 4
        assert level3_tokens > full.estimated_tokens * 1.5
