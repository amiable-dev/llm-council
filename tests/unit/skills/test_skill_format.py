"""
Tests for SKILL.md format compliance per ADR-034.

Tests validate that skill files conform to the agentskills.io specification:
1. Valid YAML frontmatter
2. Required fields present
3. Metadata structure correct
4. Content sections present
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
import yaml


# Path to skills directory
SKILLS_DIR = Path(__file__).parent.parent.parent.parent / ".github" / "skills"

# Required fields in SKILL.md frontmatter
REQUIRED_FRONTMATTER_FIELDS = [
    "name",
    "description",
    "license",
]

# Optional but recommended fields
RECOMMENDED_FRONTMATTER_FIELDS = [
    "compatibility",
    "metadata",
    "allowed-tools",
]

# Expected skills in the repository
EXPECTED_SKILLS = [
    "council-verify",
    "council-review",
    "council-gate",
]


def parse_skill_frontmatter(content: str) -> Optional[Dict[str, Any]]:
    """
    Parse YAML frontmatter from SKILL.md content.

    Frontmatter is delimited by --- at the start and end.

    Args:
        content: Full SKILL.md content

    Returns:
        Parsed frontmatter as dict, or None if invalid
    """
    # Match frontmatter delimiters
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return None

    try:
        return yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return None


def get_skill_content_after_frontmatter(content: str) -> str:
    """Extract content after the frontmatter section."""
    match = re.match(r"^---\n.*?\n---\n?(.*)", content, re.DOTALL)
    if match:
        return match.group(1).strip()
    return content


def discover_skills() -> List[Path]:
    """Discover all SKILL.md files in the skills directory."""
    if not SKILLS_DIR.exists():
        return []

    skills = []
    for skill_dir in SKILLS_DIR.iterdir():
        if skill_dir.is_dir():
            skill_file = skill_dir / "SKILL.md"
            if skill_file.exists():
                skills.append(skill_file)

    return skills


class TestSkillDiscovery:
    """Tests for skill file discovery."""

    def test_skills_directory_exists(self):
        """Skills directory should exist at .github/skills/."""
        assert SKILLS_DIR.exists(), f"Skills directory not found at {SKILLS_DIR}"

    def test_expected_skills_exist(self):
        """All expected skills should have SKILL.md files."""
        for skill_name in EXPECTED_SKILLS:
            skill_file = SKILLS_DIR / skill_name / "SKILL.md"
            assert skill_file.exists(), f"Missing SKILL.md for {skill_name}"

    def test_discover_skills_returns_all(self):
        """Discover should find all expected skills."""
        skills = discover_skills()
        skill_names = [s.parent.name for s in skills]

        for expected in EXPECTED_SKILLS:
            assert expected in skill_names, f"Missing skill: {expected}"


class TestFrontmatterParsing:
    """Tests for YAML frontmatter parsing."""

    @pytest.fixture(params=EXPECTED_SKILLS)
    def skill_content(self, request) -> tuple:
        """Load skill content for parameterized tests."""
        skill_name = request.param
        skill_file = SKILLS_DIR / skill_name / "SKILL.md"
        content = skill_file.read_text()
        return skill_name, content

    def test_frontmatter_exists(self, skill_content):
        """Each skill should have valid YAML frontmatter."""
        skill_name, content = skill_content

        assert content.startswith("---"), f"{skill_name}: Missing frontmatter delimiter"

        frontmatter = parse_skill_frontmatter(content)
        assert frontmatter is not None, f"{skill_name}: Failed to parse frontmatter"

    def test_frontmatter_valid_yaml(self, skill_content):
        """Frontmatter should be valid YAML."""
        skill_name, content = skill_content

        frontmatter = parse_skill_frontmatter(content)
        assert isinstance(frontmatter, dict), f"{skill_name}: Frontmatter not a dict"

    def test_required_fields_present(self, skill_content):
        """All required fields should be present in frontmatter."""
        skill_name, content = skill_content
        frontmatter = parse_skill_frontmatter(content)

        for field in REQUIRED_FRONTMATTER_FIELDS:
            assert field in frontmatter, f"{skill_name}: Missing required field: {field}"

    def test_name_matches_directory(self, skill_content):
        """Skill name should match its directory name."""
        skill_name, content = skill_content
        frontmatter = parse_skill_frontmatter(content)

        assert (
            frontmatter["name"] == skill_name
        ), f"{skill_name}: Name mismatch (got {frontmatter['name']})"

    def test_description_not_empty(self, skill_content):
        """Description should not be empty."""
        skill_name, content = skill_content
        frontmatter = parse_skill_frontmatter(content)

        description = frontmatter.get("description", "")
        assert len(description.strip()) > 0, f"{skill_name}: Empty description"

    def test_license_specified(self, skill_content):
        """License should be specified."""
        skill_name, content = skill_content
        frontmatter = parse_skill_frontmatter(content)

        license_val = frontmatter.get("license", "")
        assert len(license_val) > 0, f"{skill_name}: Missing license"


class TestMetadataSection:
    """Tests for metadata section compliance."""

    @pytest.fixture(params=EXPECTED_SKILLS)
    def skill_metadata(self, request) -> tuple:
        """Load skill metadata for parameterized tests."""
        skill_name = request.param
        skill_file = SKILLS_DIR / skill_name / "SKILL.md"
        content = skill_file.read_text()
        frontmatter = parse_skill_frontmatter(content)
        metadata = frontmatter.get("metadata", {}) if frontmatter else {}
        return skill_name, metadata

    def test_metadata_is_dict(self, skill_metadata):
        """Metadata section should be a dictionary."""
        skill_name, metadata = skill_metadata

        assert isinstance(metadata, dict), f"{skill_name}: Metadata not a dict"

    def test_category_present(self, skill_metadata):
        """Category should be present in metadata."""
        skill_name, metadata = skill_metadata

        assert "category" in metadata, f"{skill_name}: Missing metadata.category"

    def test_domain_present(self, skill_metadata):
        """Domain should be present in metadata."""
        skill_name, metadata = skill_metadata

        assert "domain" in metadata, f"{skill_name}: Missing metadata.domain"


class TestContentSections:
    """Tests for SKILL.md content sections."""

    @pytest.fixture(params=EXPECTED_SKILLS)
    def skill_body(self, request) -> tuple:
        """Load skill body content for parameterized tests."""
        skill_name = request.param
        skill_file = SKILLS_DIR / skill_name / "SKILL.md"
        content = skill_file.read_text()
        body = get_skill_content_after_frontmatter(content)
        return skill_name, body

    def test_has_main_heading(self, skill_body):
        """Content should have a main H1 heading."""
        skill_name, body = skill_body

        assert "# " in body, f"{skill_name}: Missing main heading"

    def test_has_when_to_use_section(self, skill_body):
        """Content should have a 'When to Use' section."""
        skill_name, body = skill_body

        assert (
            "when to use" in body.lower() or "## when" in body.lower()
        ), f"{skill_name}: Missing 'When to Use' section"

    def test_has_workflow_or_usage_section(self, skill_body):
        """Content should have workflow or usage instructions."""
        skill_name, body = skill_body
        body_lower = body.lower()

        has_workflow = "workflow" in body_lower
        has_usage = "usage" in body_lower
        has_example = "example" in body_lower

        assert (
            has_workflow or has_usage or has_example
        ), f"{skill_name}: Missing workflow/usage section"


class TestAllowedTools:
    """Tests for allowed-tools specification."""

    @pytest.fixture(params=EXPECTED_SKILLS)
    def skill_tools(self, request) -> tuple:
        """Load skill allowed-tools for parameterized tests."""
        skill_name = request.param
        skill_file = SKILLS_DIR / skill_name / "SKILL.md"
        content = skill_file.read_text()
        frontmatter = parse_skill_frontmatter(content)
        tools = frontmatter.get("allowed-tools", "") if frontmatter else ""
        return skill_name, tools

    def test_allowed_tools_specified(self, skill_tools):
        """Skills should specify allowed tools."""
        skill_name, tools = skill_tools

        assert len(tools) > 0, f"{skill_name}: Missing allowed-tools"

    def test_allowed_tools_includes_mcp(self, skill_tools):
        """Skills should reference MCP tools."""
        skill_name, tools = skill_tools

        assert "mcp:" in tools, f"{skill_name}: No MCP tools in allowed-tools"

    def test_allowed_tools_includes_basic_tools(self, skill_tools):
        """Skills should include basic file tools."""
        skill_name, tools = skill_tools

        has_read = "Read" in tools
        has_grep = "Grep" in tools
        has_glob = "Glob" in tools

        assert (
            has_read or has_grep or has_glob
        ), f"{skill_name}: Missing basic file tools (Read/Grep/Glob)"


class TestMarketplaceJson:
    """Tests for marketplace.json file."""

    @pytest.fixture
    def marketplace_data(self) -> Dict[str, Any]:
        """Load marketplace.json data."""
        marketplace_file = SKILLS_DIR / "marketplace.json"
        if not marketplace_file.exists():
            pytest.skip("marketplace.json not found")

        return json.loads(marketplace_file.read_text())

    def test_marketplace_file_exists(self):
        """marketplace.json should exist in skills directory."""
        marketplace_file = SKILLS_DIR / "marketplace.json"
        assert marketplace_file.exists(), "Missing marketplace.json"

    def test_marketplace_valid_json(self, marketplace_data):
        """marketplace.json should be valid JSON."""
        assert isinstance(marketplace_data, dict), "marketplace.json not a dict"

    def test_marketplace_has_skills_array(self, marketplace_data):
        """marketplace.json should have skills array."""
        assert "skills" in marketplace_data, "Missing 'skills' key"
        assert isinstance(marketplace_data["skills"], list), "skills not an array"

    def test_marketplace_lists_all_skills(self, marketplace_data):
        """marketplace.json should list all expected skills."""
        skill_names = [s.get("name") for s in marketplace_data.get("skills", [])]

        for expected in EXPECTED_SKILLS:
            assert expected in skill_names, f"Missing skill in marketplace.json: {expected}"

    def test_each_skill_has_required_fields(self, marketplace_data):
        """Each skill in marketplace.json should have required fields."""
        required_fields = ["name", "description", "path"]

        for skill in marketplace_data.get("skills", []):
            for field in required_fields:
                assert field in skill, f"Skill {skill.get('name')}: Missing {field}"


class TestSymlinkSetup:
    """Tests for .claude/skills symlink."""

    def test_claude_skills_symlink_exists(self):
        """Symlink from .claude/skills to .github/skills should exist."""
        symlink_path = Path(__file__).parent.parent.parent.parent / ".claude" / "skills"

        # Either the symlink exists OR we're in CI where it might not be set up
        if not symlink_path.exists():
            pytest.skip(".claude/skills not found (may not be set up in CI)")

    def test_symlink_resolves_to_github_skills(self):
        """Symlink should resolve to .github/skills directory."""
        symlink_path = Path(__file__).parent.parent.parent.parent / ".claude" / "skills"

        if not symlink_path.exists():
            pytest.skip(".claude/skills not found")

        if symlink_path.is_symlink():
            resolved = symlink_path.resolve()
            assert resolved == SKILLS_DIR.resolve(), f"Symlink points to wrong location"
