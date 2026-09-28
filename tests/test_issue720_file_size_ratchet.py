"""#720: every source file stays small enough for the council to review.

Verify caps its input at ``TIER_MAX_CHARS`` (50K for high/reasoning). A file
over that cannot be reviewed: the gate truncates or refuses it, and a diff
passed as evidence is not accepted as review (#719 FAILED on exactly that).
ADR-046 P0 split ``council.py`` below the cap once and it grew straight back,
because nothing enforced the limit. This test is the enforcement.

``LIMIT`` leaves headroom under 50K for a test file and evidence in the same
review. ``CEILINGS`` grandfathers the files that were already over it at their
size when this test landed: a ceiling may only be LOWERED (split the file, then
lower or delete its entry). Never raise one, and never add a new file to it.
"""

from pathlib import Path

from llm_council.verification.constants import TIER_MAX_CHARS

SRC = Path(__file__).resolve().parent.parent / "src" / "llm_council"

LIMIT = 40_000

#: Oversized when #720 landed. Each entry is a debt to split, not a licence.
CEILINGS = {
    "unified_config.py": 68_689,
    "verification/file_ops.py": 55_710,
    "council.py": 54_738,
    "council_stages.py": 51_417,
    "mcp_server.py": 46_083,
}


def _sizes():
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC).as_posix()
        if rel == "_version.py":  # generated at build time
            continue
        yield rel, len(path.read_text(encoding="utf-8"))


def test_the_limit_leaves_room_under_the_review_cap():
    assert LIMIT < max(TIER_MAX_CHARS.values())


def test_no_source_file_outgrows_what_the_council_can_review():
    over = []
    for rel, size in _sizes():
        allowed = CEILINGS.get(rel, LIMIT)
        if size > allowed:
            over.append(f"{rel}: {size:,} chars > {allowed:,}")
    assert not over, (
        "Split these below the review cap (#720) — do not raise a ceiling:\n  "
        + "\n  ".join(over)
    )


def test_ceilings_only_name_files_that_still_need_them():
    """A split file must leave the list, so its ceiling cannot quietly let it
    grow back to the old size."""
    sizes = dict(_sizes())
    stale = [rel for rel in CEILINGS if rel not in sizes or sizes[rel] <= LIMIT]
    assert not stale, f"remove from CEILINGS (now within LIMIT or gone): {stale}"
