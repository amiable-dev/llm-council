"""
Skills module for ADR-034 Agent Skills Integration.

Provides progressive disclosure loading for agent skills:
- Level 1: Metadata only (~100-200 tokens)
- Level 2: Full SKILL.md content
- Level 3: Resources on demand
"""

from llm_council.skills.loader import (
    SkillError,
    SkillFull,
    SkillLoader,
    SkillMetadata,
    SkillNotFoundError,
    SkillParseError,
    load_skill_full,
    load_skill_metadata,
    load_skill_resource,
)

__all__ = [
    # Exceptions
    "SkillError",
    "SkillNotFoundError",
    "SkillParseError",
    # Data classes
    "SkillMetadata",
    "SkillFull",
    # Functions
    "load_skill_metadata",
    "load_skill_full",
    "load_skill_resource",
    # Loader class
    "SkillLoader",
]
