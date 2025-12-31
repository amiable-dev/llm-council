"""
Progressive disclosure skill loader for ADR-034.

Provides three levels of skill loading to minimize token usage:
- Level 1: Metadata only (~100-200 tokens) - YAML frontmatter
- Level 2: Full SKILL.md content (~500-1000 tokens)
- Level 3: Resources on demand - files from references/ directory
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml


class SkillError(Exception):
    """Base exception for skill loading errors."""

    pass


class SkillNotFoundError(SkillError):
    """Raised when a skill or resource is not found."""

    pass


class SkillParseError(SkillError):
    """Raised when skill content cannot be parsed."""

    pass


@dataclass
class SkillMetadata:
    """Level 1: Skill metadata from YAML frontmatter.

    Contains only essential information for skill discovery and selection.
    Target: ~100-200 tokens.
    """

    name: str
    description: str
    license: Optional[str] = None
    compatibility: Optional[str] = None
    allowed_tools: List[str] = field(default_factory=list)
    category: Optional[str] = None
    domain: Optional[str] = None
    author: Optional[str] = None
    repository: Optional[str] = None

    @property
    def estimated_tokens(self) -> int:
        """Estimate token count for this metadata.

        Uses rough approximation of ~4 characters per token.
        """
        text = f"{self.name} {self.description}"
        if self.license:
            text += f" {self.license}"
        if self.compatibility:
            text += f" {self.compatibility}"
        if self.allowed_tools:
            text += f" {' '.join(self.allowed_tools)}"
        if self.category:
            text += f" {self.category}"
        if self.domain:
            text += f" {self.domain}"

        return len(text) // 4


@dataclass
class SkillFull:
    """Level 2: Full skill content including body.

    Contains metadata plus the complete SKILL.md body.
    Target: ~500-1000 tokens.
    """

    metadata: SkillMetadata
    body: str

    @property
    def estimated_tokens(self) -> int:
        """Estimate token count for full content."""
        return self.metadata.estimated_tokens + len(self.body) // 4


# Regex to match YAML frontmatter
FRONTMATTER_PATTERN = re.compile(
    r"^---\s*\n(.*?)\n---\s*\n",
    re.DOTALL,
)


def _parse_frontmatter(content: str) -> tuple[Dict, str]:
    """Parse YAML frontmatter from skill content.

    Args:
        content: Full SKILL.md content

    Returns:
        Tuple of (frontmatter dict, body string)

    Raises:
        SkillParseError: If frontmatter is missing or invalid
    """
    match = FRONTMATTER_PATTERN.match(content)
    if not match:
        raise SkillParseError("SKILL.md must start with YAML frontmatter (--- delimiters)")

    try:
        frontmatter = yaml.safe_load(match.group(1))
        if not isinstance(frontmatter, dict):
            raise SkillParseError("YAML frontmatter must be a mapping")
    except yaml.YAMLError as e:
        raise SkillParseError(f"Invalid YAML in frontmatter: {e}")

    body = content[match.end() :].strip()
    return frontmatter, body


def _parse_allowed_tools(value: Optional[str]) -> List[str]:
    """Parse allowed-tools string into list.

    Args:
        value: Space-separated tool names or None

    Returns:
        List of tool names
    """
    if not value:
        return []
    return value.split()


def load_skill_metadata(content: str) -> SkillMetadata:
    """Load Level 1 metadata from skill content.

    Parses only the YAML frontmatter to extract essential metadata.
    This is the most token-efficient way to discover skill capabilities.

    Args:
        content: Full SKILL.md content string

    Returns:
        SkillMetadata with essential fields

    Raises:
        SkillParseError: If content is invalid
    """
    frontmatter, _ = _parse_frontmatter(content)

    # Required fields
    if "name" not in frontmatter:
        raise SkillParseError("SKILL.md frontmatter must include 'name' field")

    if "description" not in frontmatter:
        raise SkillParseError("SKILL.md frontmatter must include 'description' field")

    # Extract nested metadata
    nested_meta = frontmatter.get("metadata", {})

    return SkillMetadata(
        name=frontmatter["name"],
        description=frontmatter["description"],
        license=frontmatter.get("license"),
        compatibility=frontmatter.get("compatibility"),
        allowed_tools=_parse_allowed_tools(frontmatter.get("allowed-tools")),
        category=nested_meta.get("category"),
        domain=nested_meta.get("domain"),
        author=nested_meta.get("author"),
        repository=nested_meta.get("repository"),
    )


def load_skill_full(content: str) -> SkillFull:
    """Load Level 2 full skill content.

    Parses both frontmatter metadata and the complete body.
    Use when skill has been selected and full instructions are needed.

    Args:
        content: Full SKILL.md content string

    Returns:
        SkillFull with metadata and body

    Raises:
        SkillParseError: If content is invalid
    """
    frontmatter, body = _parse_frontmatter(content)
    metadata = load_skill_metadata(content)

    return SkillFull(
        metadata=metadata,
        body=body,
    )


def load_skill_resource(path: Path) -> str:
    """Load Level 3 resource file content.

    Loads additional reference files on demand.
    Use only when specific resource content is needed.

    Args:
        path: Path to resource file

    Returns:
        Resource file content

    Raises:
        SkillNotFoundError: If resource doesn't exist
    """
    if not path.exists():
        raise SkillNotFoundError(f"Resource not found: {path}")

    return path.read_text()


class SkillLoader:
    """Progressive disclosure skill loader.

    Discovers and loads skills from a directory structure:
    ```
    skills_dir/
    ├── skill-name/
    │   ├── SKILL.md
    │   └── references/
    │       ├── rubrics.md
    │       └── examples.md
    ```

    Supports three loading levels:
    - Level 1: load_metadata() - Just YAML frontmatter
    - Level 2: load_full() - Complete SKILL.md
    - Level 3: load_resource() - Reference files
    """

    def __init__(self, skills_dir: Path):
        """Initialize loader with skills directory.

        Args:
            skills_dir: Path to directory containing skill subdirectories
        """
        self.skills_dir = skills_dir
        self._metadata_cache: Dict[str, SkillMetadata] = {}

    def list_skills(self) -> List[str]:
        """List all available skill names.

        Returns:
            List of skill directory names that contain SKILL.md
        """
        if not self.skills_dir.exists():
            return []

        skills = []
        for item in self.skills_dir.iterdir():
            if item.is_dir() and (item / "SKILL.md").exists():
                skills.append(item.name)

        return sorted(skills)

    def _get_skill_path(self, skill_name: str) -> Path:
        """Get path to skill directory.

        Args:
            skill_name: Name of skill

        Returns:
            Path to skill directory

        Raises:
            SkillNotFoundError: If skill doesn't exist
        """
        skill_path = self.skills_dir / skill_name
        skill_md = skill_path / "SKILL.md"

        if not skill_md.exists():
            raise SkillNotFoundError(f"Skill not found: {skill_name}")

        return skill_path

    def load_metadata(self, skill_name: str) -> SkillMetadata:
        """Load Level 1 metadata for a skill.

        Caches results for performance.

        Args:
            skill_name: Name of skill to load

        Returns:
            SkillMetadata with essential fields

        Raises:
            SkillNotFoundError: If skill doesn't exist
            SkillParseError: If SKILL.md is invalid
        """
        if skill_name in self._metadata_cache:
            return self._metadata_cache[skill_name]

        skill_path = self._get_skill_path(skill_name)
        content = (skill_path / "SKILL.md").read_text()
        metadata = load_skill_metadata(content)

        self._metadata_cache[skill_name] = metadata
        return metadata

    def load_full(self, skill_name: str) -> SkillFull:
        """Load Level 2 full content for a skill.

        Args:
            skill_name: Name of skill to load

        Returns:
            SkillFull with metadata and body

        Raises:
            SkillNotFoundError: If skill doesn't exist
            SkillParseError: If SKILL.md is invalid
        """
        skill_path = self._get_skill_path(skill_name)
        content = (skill_path / "SKILL.md").read_text()
        return load_skill_full(content)

    def list_resources(self, skill_name: str) -> List[str]:
        """List available Level 3 resources for a skill.

        Args:
            skill_name: Name of skill

        Returns:
            List of resource filenames in references/ directory
        """
        skill_path = self._get_skill_path(skill_name)
        refs_dir = skill_path / "references"

        if not refs_dir.exists():
            return []

        return sorted([f.name for f in refs_dir.iterdir() if f.is_file()])

    def load_resource(self, skill_name: str, resource_name: str) -> str:
        """Load Level 3 resource content.

        Args:
            skill_name: Name of skill
            resource_name: Filename in references/ directory

        Returns:
            Resource file content

        Raises:
            SkillNotFoundError: If skill or resource doesn't exist
        """
        skill_path = self._get_skill_path(skill_name)
        resource_path = skill_path / "references" / resource_name

        return load_skill_resource(resource_path)
