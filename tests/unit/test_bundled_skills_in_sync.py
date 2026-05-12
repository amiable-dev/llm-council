"""Regression guard: src/llm_council/skills/bundled/ must match .github/skills/.

The wheel ships bundled/ via pyproject.toml's hatch `artifacts` config. The
.github/skills/ tree is the editable dev copy used by tests and by the
`llm-council install-skills` command's dev mode (when run from a checkout).

If the two drift, `pip install llm-council-core` users get stale skills even
after a release. v0.24.37 shipped with this bug — ADR-042 SKILL.md updates
landed in .github/skills/ but never made it into bundled/. This test exists
so the next person who edits a skill is forced to update both copies.
"""

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).parent.parent.parent
DEV_SKILLS = REPO_ROOT / ".github" / "skills"
BUNDLED_SKILLS = REPO_ROOT / "src" / "llm_council" / "skills" / "bundled"

# Skills the wheel ships (matches pyproject.toml's artifact glob).
BUNDLED_SKILL_NAMES = ["council-verify", "council-review", "council-gate"]


def _collect_files(root: Path) -> dict[str, str]:
    """Return {relative_path: content_sha256} for all files under root."""
    import hashlib

    result: dict[str, str] = {}
    if not root.exists():
        return result
    for path in sorted(root.rglob("*")):
        if path.is_file():
            # Skip pyc/cache files.
            if "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            rel = path.relative_to(root).as_posix()
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            result[rel] = digest
    return result


@pytest.mark.parametrize("skill_name", BUNDLED_SKILL_NAMES)
def test_bundled_skill_matches_dev_copy(skill_name: str) -> None:
    """The bundled skill (shipped in the wheel) must match the dev copy.

    If this fails, you edited one but not the other. Sync both before
    landing the change — the wheel users depend on bundled/.
    """
    dev_files = _collect_files(DEV_SKILLS / skill_name)
    bundled_files = _collect_files(BUNDLED_SKILLS / skill_name)

    assert dev_files, f"dev copy at {DEV_SKILLS / skill_name} is empty/missing"
    assert bundled_files, f"bundled copy at {BUNDLED_SKILLS / skill_name} is empty/missing"

    extra_in_dev = set(dev_files) - set(bundled_files)
    extra_in_bundled = set(bundled_files) - set(dev_files)
    mismatched = {
        path
        for path in dev_files.keys() & bundled_files.keys()
        if dev_files[path] != bundled_files[path]
    }

    assert not extra_in_dev, (
        f"{skill_name}: files in .github/skills/ but not in bundled/: "
        f"{sorted(extra_in_dev)}. Sync them with:\n"
        f"  cp .github/skills/{skill_name}/<file> "
        f"src/llm_council/skills/bundled/{skill_name}/<file>"
    )
    assert not extra_in_bundled, (
        f"{skill_name}: files in bundled/ but not in .github/skills/: "
        f"{sorted(extra_in_bundled)}. Remove from bundled or add to dev copy."
    )
    assert not mismatched, (
        f"{skill_name}: file contents differ between dev and bundled: "
        f"{sorted(mismatched)}. Sync both copies."
    )
