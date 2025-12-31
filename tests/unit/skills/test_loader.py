"""
Tests for progressive disclosure skill loader per ADR-034.

TDD Red Phase: These tests should fail until loader.py is implemented.

Progressive disclosure levels:
1. Metadata only (~100-200 tokens) - YAML frontmatter
2. Full SKILL.md content (~500-1000 tokens)
3. Resources on demand - files from references/ directory
"""

import tempfile
from pathlib import Path
from typing import Optional

import pytest

from llm_council.skills.loader import (
    SkillLoader,
    SkillMetadata,
    SkillNotFoundError,
    SkillParseError,
    load_skill_metadata,
    load_skill_full,
    load_skill_resource,
)


# Test fixtures
SAMPLE_SKILL_MD = """---
name: test-skill
description: |
  A test skill for unit testing.
  Keywords: test, example, demo

license: MIT
compatibility: "llm-council >= 2.0"
metadata:
  category: testing
  domain: development
  author: test-author

allowed-tools: "Read Grep Glob mcp:llm-council/test"
---

# Test Skill

This is the full content of the test skill.

## Usage

Use this skill for testing purposes.

## Example

```bash
test-skill --verbose
```
"""

SAMPLE_SKILL_MINIMAL = """---
name: minimal-skill
description: Minimal skill with required fields only.
---

# Minimal Skill

Basic content.
"""


class TestSkillMetadata:
    """Tests for SkillMetadata dataclass."""

    def test_metadata_has_required_fields(self):
        """SkillMetadata should have name and description."""
        metadata = SkillMetadata(
            name="test",
            description="Test description",
        )
        assert metadata.name == "test"
        assert metadata.description == "Test description"

    def test_metadata_has_optional_fields(self):
        """SkillMetadata should support optional fields."""
        metadata = SkillMetadata(
            name="test",
            description="Test description",
            license="MIT",
            compatibility="llm-council >= 2.0",
            allowed_tools=["Read", "Grep"],
            category="testing",
            domain="development",
            author="test-author",
        )
        assert metadata.license == "MIT"
        assert metadata.compatibility == "llm-council >= 2.0"
        assert metadata.allowed_tools == ["Read", "Grep"]
        assert metadata.category == "testing"

    def test_metadata_token_estimate(self):
        """Metadata should provide token estimate."""
        metadata = SkillMetadata(
            name="test-skill",
            description="A test skill for unit testing.\nKeywords: test, example",
        )
        # Rough estimate: ~4 chars per token
        # Minimal metadata should be small
        assert 10 <= metadata.estimated_tokens <= 50


class TestLoadSkillMetadata:
    """Tests for Level 1: Metadata extraction."""

    def test_load_metadata_from_string(self):
        """Should parse YAML frontmatter from skill content."""
        metadata = load_skill_metadata(SAMPLE_SKILL_MD)

        assert metadata.name == "test-skill"
        assert "test skill" in metadata.description.lower()
        assert metadata.license == "MIT"

    def test_load_metadata_extracts_allowed_tools(self):
        """Should parse allowed-tools into list."""
        metadata = load_skill_metadata(SAMPLE_SKILL_MD)

        assert "Read" in metadata.allowed_tools
        assert "Grep" in metadata.allowed_tools
        assert "mcp:llm-council/test" in metadata.allowed_tools

    def test_load_metadata_extracts_nested_metadata(self):
        """Should extract nested metadata fields."""
        metadata = load_skill_metadata(SAMPLE_SKILL_MD)

        assert metadata.category == "testing"
        assert metadata.domain == "development"
        assert metadata.author == "test-author"

    def test_load_metadata_handles_minimal_skill(self):
        """Should handle skill with only required fields."""
        metadata = load_skill_metadata(SAMPLE_SKILL_MINIMAL)

        assert metadata.name == "minimal-skill"
        assert "Minimal skill" in metadata.description
        assert metadata.license is None
        assert metadata.allowed_tools == []

    def test_load_metadata_raises_on_missing_frontmatter(self):
        """Should raise error if no YAML frontmatter."""
        with pytest.raises(SkillParseError) as exc_info:
            load_skill_metadata("# No frontmatter\n\nJust content.")
        assert "frontmatter" in str(exc_info.value).lower()

    def test_load_metadata_raises_on_missing_name(self):
        """Should raise error if name is missing."""
        invalid_skill = """---
description: Missing name field.
---
# Content
"""
        with pytest.raises(SkillParseError) as exc_info:
            load_skill_metadata(invalid_skill)
        assert "name" in str(exc_info.value).lower()


class TestLoadSkillFull:
    """Tests for Level 2: Full SKILL.md loading."""

    def test_load_full_returns_complete_content(self):
        """Should return full skill content including body."""
        result = load_skill_full(SAMPLE_SKILL_MD)

        assert result.metadata.name == "test-skill"
        assert "# Test Skill" in result.body
        assert "## Usage" in result.body
        assert "## Example" in result.body

    def test_load_full_separates_metadata_and_body(self):
        """Body should not include YAML frontmatter."""
        result = load_skill_full(SAMPLE_SKILL_MD)

        assert "---" not in result.body.strip()[:10]  # No frontmatter delimiter at start
        assert "name:" not in result.body

    def test_load_full_preserves_code_blocks(self):
        """Should preserve code blocks in body."""
        result = load_skill_full(SAMPLE_SKILL_MD)

        assert "```bash" in result.body
        assert "test-skill --verbose" in result.body

    def test_load_full_estimates_body_tokens(self):
        """Should estimate tokens for full content."""
        result = load_skill_full(SAMPLE_SKILL_MD)

        # Full content should be more than metadata
        assert result.estimated_tokens > result.metadata.estimated_tokens
        assert result.estimated_tokens < 2000  # Reasonable upper bound


class TestSkillLoader:
    """Tests for SkillLoader class."""

    @pytest.fixture
    def skill_dir(self) -> Path:
        """Create temporary skills directory with test skills."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_path = Path(tmpdir) / ".github" / "skills"

            # Create test-skill
            test_skill_dir = skills_path / "test-skill"
            test_skill_dir.mkdir(parents=True)
            (test_skill_dir / "SKILL.md").write_text(SAMPLE_SKILL_MD)

            # Create references
            refs_dir = test_skill_dir / "references"
            refs_dir.mkdir()
            (refs_dir / "rubrics.md").write_text("# Rubrics\n\nTest rubric content.")
            (refs_dir / "examples.md").write_text("# Examples\n\nTest examples.")

            # Create minimal-skill
            minimal_dir = skills_path / "minimal-skill"
            minimal_dir.mkdir(parents=True)
            (minimal_dir / "SKILL.md").write_text(SAMPLE_SKILL_MINIMAL)

            yield skills_path

    def test_loader_discovers_skills(self, skill_dir: Path):
        """Loader should discover all skills in directory."""
        loader = SkillLoader(skill_dir)
        skills = loader.list_skills()

        assert "test-skill" in skills
        assert "minimal-skill" in skills

    def test_loader_loads_metadata_level1(self, skill_dir: Path):
        """Loader should load Level 1 metadata."""
        loader = SkillLoader(skill_dir)
        metadata = loader.load_metadata("test-skill")

        assert metadata.name == "test-skill"
        assert metadata.category == "testing"

    def test_loader_loads_full_level2(self, skill_dir: Path):
        """Loader should load Level 2 full content."""
        loader = SkillLoader(skill_dir)
        full = loader.load_full("test-skill")

        assert full.metadata.name == "test-skill"
        assert "# Test Skill" in full.body

    def test_loader_loads_resource_level3(self, skill_dir: Path):
        """Loader should load Level 3 resources."""
        loader = SkillLoader(skill_dir)
        rubrics = loader.load_resource("test-skill", "rubrics.md")

        assert "# Rubrics" in rubrics
        assert "Test rubric content" in rubrics

    def test_loader_lists_resources(self, skill_dir: Path):
        """Loader should list available resources."""
        loader = SkillLoader(skill_dir)
        resources = loader.list_resources("test-skill")

        assert "rubrics.md" in resources
        assert "examples.md" in resources

    def test_loader_raises_skill_not_found(self, skill_dir: Path):
        """Loader should raise error for unknown skill."""
        loader = SkillLoader(skill_dir)

        with pytest.raises(SkillNotFoundError):
            loader.load_metadata("nonexistent-skill")

    def test_loader_raises_resource_not_found(self, skill_dir: Path):
        """Loader should raise error for unknown resource."""
        loader = SkillLoader(skill_dir)

        with pytest.raises(SkillNotFoundError):
            loader.load_resource("test-skill", "nonexistent.md")

    def test_loader_handles_skill_without_resources(self, skill_dir: Path):
        """Loader should handle skills with no references directory."""
        loader = SkillLoader(skill_dir)
        resources = loader.list_resources("minimal-skill")

        assert resources == []

    def test_loader_caches_metadata(self, skill_dir: Path):
        """Loader should cache metadata for performance."""
        loader = SkillLoader(skill_dir)

        # Load twice
        meta1 = loader.load_metadata("test-skill")
        meta2 = loader.load_metadata("test-skill")

        # Should be same object (cached)
        assert meta1 is meta2


class TestLoadSkillResource:
    """Tests for Level 3: Resource loading."""

    def test_load_resource_from_path(self):
        """Should load resource file content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            resource_path = Path(tmpdir) / "test.md"
            resource_path.write_text("# Test Resource\n\nContent here.")

            content = load_skill_resource(resource_path)

            assert "# Test Resource" in content
            assert "Content here" in content

    def test_load_resource_raises_on_missing(self):
        """Should raise error for missing resource."""
        with pytest.raises(SkillNotFoundError):
            load_skill_resource(Path("/nonexistent/path.md"))


class TestProgressiveDisclosureIntegration:
    """Integration tests for progressive disclosure workflow."""

    @pytest.fixture
    def skill_dir(self) -> Path:
        """Create temporary skills directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_path = Path(tmpdir) / ".github" / "skills"
            test_skill_dir = skills_path / "test-skill"
            test_skill_dir.mkdir(parents=True)
            (test_skill_dir / "SKILL.md").write_text(SAMPLE_SKILL_MD)

            refs_dir = test_skill_dir / "references"
            refs_dir.mkdir()
            (refs_dir / "detailed.md").write_text("# Detailed\n\n" + "x" * 1000)

            yield skills_path

    def test_progressive_loading_token_efficiency(self, skill_dir: Path):
        """Progressive loading should be token-efficient."""
        loader = SkillLoader(skill_dir)

        # Level 1: Just metadata
        meta = loader.load_metadata("test-skill")
        level1_tokens = meta.estimated_tokens

        # Level 2: Full content
        full = loader.load_full("test-skill")
        level2_tokens = full.estimated_tokens

        # Level 3: With resources
        resource = loader.load_resource("test-skill", "detailed.md")
        level3_tokens = level2_tokens + len(resource) // 4  # Rough estimate

        # Each level should add more tokens
        assert level1_tokens < level2_tokens
        assert level2_tokens < level3_tokens

        # Level 1 should be minimal
        assert level1_tokens < 300  # ~100-200 tokens target

    def test_load_all_levels_successively(self, skill_dir: Path):
        """Should be able to load all levels in sequence."""
        loader = SkillLoader(skill_dir)

        # Start with metadata discovery
        skills = loader.list_skills()
        assert len(skills) > 0

        # Load metadata for first skill
        skill_name = skills[0]
        meta = loader.load_metadata(skill_name)
        assert meta.name == skill_name

        # Decide to load full content
        full = loader.load_full(skill_name)
        assert full.body is not None

        # Check for resources
        resources = loader.list_resources(skill_name)
        if resources:
            content = loader.load_resource(skill_name, resources[0])
            assert len(content) > 0
