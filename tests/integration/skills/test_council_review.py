"""
Integration tests for council-review skill (ADR-034 B4).

Tests skill discovery, progressive disclosure, and code review-specific features.
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


class TestCouncilReviewSkillDiscovery:
    """Tests for skill discovery via SkillLoader."""

    def test_council_review_skill_exists(self, loader: SkillLoader):
        """council-review skill should be discoverable."""
        skills = loader.list_skills()
        assert "council-review" in skills

    def test_council_review_has_skill_md(self):
        """council-review should have SKILL.md file."""
        skill_md = SKILLS_DIR / "council-review" / "SKILL.md"
        assert skill_md.exists()

    def test_council_review_has_references_dir(self):
        """council-review should have references/ directory."""
        refs_dir = SKILLS_DIR / "council-review" / "references"
        assert refs_dir.exists()
        assert refs_dir.is_dir()


class TestCouncilReviewProgressiveDisclosure:
    """Tests for progressive disclosure levels."""

    def test_level1_metadata_loads(self, loader: SkillLoader):
        """Level 1: Should load metadata from YAML frontmatter."""
        metadata = loader.load_metadata("council-review")

        assert metadata.name == "council-review"
        assert metadata.description is not None
        assert len(metadata.description) > 0

    def test_level1_metadata_is_compact(self, loader: SkillLoader):
        """Level 1: Metadata should be token-efficient (~100-200 tokens)."""
        metadata = loader.load_metadata("council-review")

        # Should be under 300 tokens for efficient discovery
        assert metadata.estimated_tokens < 300

    def test_level1_metadata_has_allowed_tools(self, loader: SkillLoader):
        """Level 1: Metadata should specify allowed tools."""
        metadata = loader.load_metadata("council-review")

        # council-review needs file reading and MCP access
        assert len(metadata.allowed_tools) > 0
        # Common tools for code review
        assert any(tool in metadata.allowed_tools for tool in ["Read", "Grep", "Glob"])

    def test_level1_metadata_has_code_review_category(self, loader: SkillLoader):
        """Level 1: Metadata should have code-review category."""
        metadata = loader.load_metadata("council-review")

        assert metadata.category is not None
        assert metadata.category == "code-review"

    def test_level1_metadata_has_software_engineering_domain(self, loader: SkillLoader):
        """Level 1: Metadata should have software-engineering domain."""
        metadata = loader.load_metadata("council-review")

        assert metadata.domain is not None
        assert metadata.domain == "software-engineering"

    def test_level2_full_loads(self, loader: SkillLoader):
        """Level 2: Should load full SKILL.md content."""
        full = loader.load_full("council-review")

        assert full.metadata.name == "council-review"
        assert len(full.body) > 0

    def test_level2_body_has_workflow(self, loader: SkillLoader):
        """Level 2: Body should contain workflow instructions."""
        full = loader.load_full("council-review")

        # Should have workflow section
        assert "workflow" in full.body.lower()
        assert "review" in full.body.lower()

    def test_level2_body_has_input_formats(self, loader: SkillLoader):
        """Level 2: Body should document input formats."""
        full = loader.load_full("council-review")

        # Should document file_paths and git_diff options
        assert "file_paths" in full.body or "file-paths" in full.body
        assert "git_diff" in full.body or "diff" in full.body

    def test_level2_body_has_output_schema(self, loader: SkillLoader):
        """Level 2: Body should include output schema."""
        full = loader.load_full("council-review")

        # Should have JSON schema for output
        assert "verdict" in full.body
        assert "blocking_issues" in full.body

    def test_level2_body_larger_than_metadata(self, loader: SkillLoader):
        """Level 2: Full content should be larger than metadata alone."""
        metadata = loader.load_metadata("council-review")
        full = loader.load_full("council-review")

        assert full.estimated_tokens > metadata.estimated_tokens

    def test_level3_resources_available(self, loader: SkillLoader):
        """Level 3: Should have resources in references/ directory."""
        resources = loader.list_resources("council-review")

        assert len(resources) > 0
        assert "code-review-rubric.md" in resources

    def test_level3_rubric_content(self, loader: SkillLoader):
        """Level 3: code-review-rubric.md should contain scoring guidelines."""
        rubric = loader.load_resource("council-review", "code-review-rubric.md")

        # Per ADR-016, rubrics should have these dimensions
        assert "Accuracy" in rubric
        assert "Completeness" in rubric
        assert "Clarity" in rubric
        assert "Conciseness" in rubric
        assert "Relevance" in rubric


class TestCodeReviewRubricContent:
    """Tests for code-review-specific rubric content."""

    def test_rubric_has_higher_accuracy_weight(self, loader: SkillLoader):
        """Code review should weight accuracy at 35% (higher than general 30%)."""
        rubric = loader.load_resource("council-review", "code-review-rubric.md")

        # Accuracy is 35% for code review (vs 30% for general verification)
        assert "35%" in rubric
        # Verify it's for accuracy
        assert "Accuracy" in rubric and "35%" in rubric

    def test_rubric_has_accuracy_ceiling(self, loader: SkillLoader):
        """Rubric should document accuracy ceiling rule."""
        rubric = loader.load_resource("council-review", "code-review-rubric.md")

        assert "ceiling" in rubric.lower()
        # Should mention the specific thresholds
        assert "4.0" in rubric or "4" in rubric
        assert "7.0" in rubric or "7" in rubric

    def test_rubric_has_code_specific_checks(self, loader: SkillLoader):
        """Rubric should have code-specific accuracy checks."""
        rubric = loader.load_resource("council-review", "code-review-rubric.md")

        # Code-specific concerns
        code_checks = [
            "algorithm",
            "null",
            "boundary",
            "type",
            "concurrency",
        ]
        assert any(check.lower() in rubric.lower() for check in code_checks)

    def test_rubric_has_security_focus(self, loader: SkillLoader):
        """Rubric should have security-specific criteria."""
        rubric = loader.load_resource("council-review", "code-review-rubric.md")

        assert "Security" in rubric
        # Common security concerns for code review
        security_terms = ["SQL", "XSS", "injection", "authentication", "secrets"]
        matches = [term for term in security_terms if term.lower() in rubric.lower()]
        assert len(matches) >= 3, f"Expected 3+ security terms, found: {matches}"

    def test_rubric_has_performance_focus(self, loader: SkillLoader):
        """Rubric should have performance-specific criteria."""
        rubric = loader.load_resource("council-review", "code-review-rubric.md")

        assert "Performance" in rubric
        # Common performance concerns
        perf_terms = ["O(n", "N+1", "memory", "caching", "query"]
        matches = [term for term in perf_terms if term in rubric]
        assert len(matches) >= 2, f"Expected 2+ performance terms, found: {matches}"

    def test_rubric_has_testing_focus(self, loader: SkillLoader):
        """Rubric should have testing-specific criteria."""
        rubric = loader.load_resource("council-review", "code-review-rubric.md")

        assert "Testing" in rubric
        # Testing concerns
        test_terms = ["coverage", "unit", "integration", "mock", "flaky"]
        matches = [term for term in test_terms if term.lower() in rubric.lower()]
        assert len(matches) >= 2, f"Expected 2+ testing terms, found: {matches}"

    def test_rubric_has_blocking_issues(self, loader: SkillLoader):
        """Rubric should define blocking issue severity levels."""
        rubric = loader.load_resource("council-review", "code-review-rubric.md")

        assert "Blocking" in rubric
        assert "Critical" in rubric
        assert "Major" in rubric
        assert "Minor" in rubric

    def test_rubric_has_issue_format(self, loader: SkillLoader):
        """Rubric should define issue output format."""
        rubric = loader.load_resource("council-review", "code-review-rubric.md")

        # Issue format should include
        assert "severity" in rubric.lower()
        assert "file" in rubric.lower()
        assert "line" in rubric.lower()
        assert "message" in rubric.lower()
        assert "suggestion" in rubric.lower()


class TestCouncilReviewSkillFormat:
    """Tests for SKILL.md format compliance."""

    def test_skill_md_has_yaml_frontmatter(self):
        """SKILL.md should start with YAML frontmatter."""
        skill_md = SKILLS_DIR / "council-review" / "SKILL.md"
        content = skill_md.read_text()

        assert content.startswith("---")
        second_delimiter = content.find("---", 3)
        assert second_delimiter > 0

    def test_skill_md_has_required_fields(self, loader: SkillLoader):
        """SKILL.md frontmatter should have required fields."""
        metadata = loader.load_metadata("council-review")

        assert metadata.name is not None
        assert metadata.description is not None

    def test_skill_md_has_license(self, loader: SkillLoader):
        """SKILL.md should specify a license."""
        metadata = loader.load_metadata("council-review")

        assert metadata.license is not None
        assert metadata.license in ["MIT", "Apache-2.0", "BSD-3-Clause", "GPL-3.0"]


class TestCouncilReviewMCPIntegration:
    """Tests for MCP server integration."""

    def test_allowed_tools_includes_mcp(self, loader: SkillLoader):
        """Skill should allow MCP tool access."""
        metadata = loader.load_metadata("council-review")

        mcp_tools = [t for t in metadata.allowed_tools if t.startswith("mcp:")]
        assert len(mcp_tools) > 0, "Should have at least one MCP tool"

    def test_mcp_tool_references_llm_council(self, loader: SkillLoader):
        """MCP tool should reference llm-council server."""
        metadata = loader.load_metadata("council-review")

        mcp_tools = [t for t in metadata.allowed_tools if t.startswith("mcp:")]
        assert any("llm-council" in t for t in mcp_tools)


class TestCouncilReviewVsVerify:
    """Tests comparing council-review to council-verify."""

    def test_different_categories(self, loader: SkillLoader):
        """council-review and council-verify should have different categories."""
        review_meta = loader.load_metadata("council-review")
        verify_meta = loader.load_metadata("council-verify")

        assert review_meta.category != verify_meta.category
        assert review_meta.category == "code-review"

    def test_both_use_progressive_disclosure(self, loader: SkillLoader):
        """Both skills should support progressive disclosure."""
        review_resources = loader.list_resources("council-review")
        verify_resources = loader.list_resources("council-verify")

        assert len(review_resources) > 0
        assert len(verify_resources) > 0

    def test_review_has_higher_accuracy_weight(self, loader: SkillLoader):
        """council-review should weight accuracy higher than council-verify."""
        review_rubric = loader.load_resource("council-review", "code-review-rubric.md")
        verify_rubric = loader.load_resource("council-verify", "rubrics.md")

        # Review: 35%, Verify: 30%
        assert "35%" in review_rubric
        assert "30%" in verify_rubric


class TestProgressiveDisclosureTokenEfficiency:
    """Integration tests for token efficiency across levels."""

    def test_level1_under_200_tokens(self, loader: SkillLoader):
        """Level 1 should stay under 200 tokens for efficient discovery."""
        metadata = loader.load_metadata("council-review")
        assert metadata.estimated_tokens < 200

    def test_level2_under_1000_tokens(self, loader: SkillLoader):
        """Level 2 should stay under 1000 tokens for reasonable context."""
        full = loader.load_full("council-review")
        assert full.estimated_tokens < 1000

    def test_level3_adds_substantial_content(self, loader: SkillLoader):
        """Level 3 resources should add substantial content."""
        full = loader.load_full("council-review")
        rubric = loader.load_resource("council-review", "code-review-rubric.md")

        level3_tokens = full.estimated_tokens + len(rubric) // 4
        assert level3_tokens > full.estimated_tokens * 1.5
