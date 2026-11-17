"""Fit the files under review into the prompt's character budget (#747).

Split out of ``file_ops.py``. Three defects lived in the loop this replaces:

- **The budget ignored the prompt around it.** Files could fill the whole tier
  cap; the instructions, evidence and review-target tail were added afterwards
  and the total was checked against the same cap. A change whose files came to
  about the cap was refused as ``input_too_large`` before any model was
  called. The caller now passes the room that is actually left, and everything
  rendered here (headings, fences, separators, markers) counts against it.
- **Path order decided what was reviewed.** ``CHANGELOG.md``, ``CLAUDE.md``
  and ``README.md`` sort ahead of ``src/`` and ``tests/``, and any one of them
  fills the budget alone. Files are now taken in review-value order.
- **The first file that did not fit ended the review.** Everything after it
  was dropped, even files that would have fitted. A file that does not fit is
  now skipped and the smaller ones behind it are still considered.

Files that did not fit are named in ``expansion_warnings`` and recorded in the
coverage receipt as omitted, not as reviewed.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import PurePosixPath
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from .constants import TIER_MAX_CHARS

#: Concurrent ``git show`` calls per batch (a large commit must not fork-bomb).
BATCH_SIZE = 5

#: Below this much room, no further file is fetched.
MIN_USEFUL_CHARS = 200

_SEPARATOR = "\n\n"

_DOC_SUFFIXES = frozenset({".md", ".mdx", ".rst", ".txt", ".adoc"})
_DOC_DIRS = frozenset({"docs", "doc"})
_DOC_STEMS = ("changelog", "readme", "license", "notice", "authors", "contributing")
_TEST_DIRS = frozenset({"tests", "test", "__tests__", "testing", "spec"})
_CONFIG_SUFFIXES = frozenset(
    {".toml", ".yaml", ".yml", ".json", ".ini", ".cfg", ".lock", ".env", ".properties"}
)

Fetch = Callable[..., Awaitable[Tuple[str, bool]]]

logger = logging.getLogger(__name__)

_CUT_MARKER = "\n\n... [truncated to fit the input budget]"


def review_priority(path: str) -> int:
    """Rank a path by how much a review of it is worth: lower is sooner.

    0 source, 1 tests, 2 configuration and data, 3 documentation.
    """
    pure = PurePosixPath(path.replace("\\", "/"))
    parts = [p.lower() for p in pure.parts]
    name = parts[-1] if parts else ""
    suffix = pure.suffix.lower()
    dirs = set(parts[:-1])

    if suffix in _DOC_SUFFIXES or dirs & _DOC_DIRS or name.startswith(_DOC_STEMS):
        return 3
    stem = name[: -len(suffix)] if suffix else name
    if (
        dirs & _TEST_DIRS
        or name.startswith("test_")
        or stem.endswith(("_test", ".test", ".spec"))
        or name == "conftest.py"
    ):
        return 1
    if suffix in _CONFIG_SUFFIXES or (parts and parts[0].startswith(".")):
        return 2
    return 0


def order_for_review(paths: List[str]) -> List[str]:
    """Source, then tests, then configuration, then docs. Stable within a rank."""
    return sorted(paths, key=review_priority)


def _section(path: str, content: str) -> str:
    return f"### {path}\n```\n{content}\n```"


def _not_fitted_marker(count: int, budget: int) -> str:
    return f"\n... [{count} file(s) omitted, {budget} char limit reached]"


async def assemble_subject(
    snapshot_id: str,
    files: List[str],
    tier: str,
    fetch: Fetch,
    max_chars: Optional[int] = None,
) -> Tuple[str, List[str], List[str]]:
    """Render ``files`` into the prompt's code section within ``max_chars``.

    Args:
        snapshot_id: commit the files are read at.
        files: paths to review, already selected (see ``select_blobs``).
        tier: tier name, for messages and the default budget.
        fetch: ``_fetch_file_at_commit_async`` (passed in so this module does
            not import ``file_ops``, and so patches on it keep working).
        max_chars: room for the returned text. ``None`` means the tier cap.

    Returns:
        ``(text, warnings, not_fitted)``. ``len(text) <= max_chars``, except
        that the first file is always included, cut to fit if need be, so a
        single large file is reviewed in part rather than not at all.
    """
    cap = TIER_MAX_CHARS.get(tier, 50000)
    budget = cap if max_chars is None else max(0, min(max_chars, cap))
    ordered = order_for_review(files)
    # Hold back room for the marker that says how many files were left out.
    reserve = len(_SEPARATOR + _not_fitted_marker(len(ordered), budget)) if len(ordered) > 1 else 0

    sections: List[str] = []
    warnings: List[str] = []
    not_fitted: List[str] = []
    used = 0

    def room() -> int:
        return budget - reserve - used - (len(_SEPARATOR) if sections else 0)

    for start in range(0, len(ordered), BATCH_SIZE):
        if sections and room() < MIN_USEFUL_CHARS:
            not_fitted.extend(ordered[start:])
            break
        batch = ordered[start : start + BATCH_SIZE]
        results = await asyncio.gather(
            *[fetch(snapshot_id, path, max_file_chars=budget) for path in batch]
        )
        for path, (content, truncated) in zip(batch, results):
            section = _section(path, content)
            kept = budget
            if len(section) > room():
                if sections:
                    not_fitted.append(path)
                    continue
                # Nothing included yet: cut this file to fit rather than
                # review nothing.
                kept = max(room() - len(_section(path, _CUT_MARKER)), 0)
                section = _section(path, content[:kept] + _CUT_MARKER)
                truncated = True
            used += len(section) + (len(_SEPARATOR) if sections else 0)
            sections.append(section)
            if truncated:
                warnings.append(
                    f"file '{path}' truncated at {kept} chars ({tier} tier per-file budget)"
                )

    if not_fitted:
        sections.append(_not_fitted_marker(len(not_fitted), budget))
        shown = ", ".join(not_fitted[:20])
        more = f", … and {len(not_fitted) - 20} more" if len(not_fitted) > 20 else ""
        warnings.append(
            f"{len(not_fitted)} file(s) did not fit the {tier} tier input budget "
            f"and were NOT reviewed: {shown}{more}"
        )
    return _SEPARATOR.join(sections), warnings, not_fitted


def subject_room(tier: str, *surrounding: str) -> int:
    """Characters left for file content once the rest of the prompt is counted."""
    return max(TIER_MAX_CHARS.get(tier, 50000) - sum(len(s) for s in surrounding), 0)


def coverage_receipt(
    target_paths: Optional[List[str]],
    files: List[str],
    omissions: List[Dict[str, str]],
    paths_truncated: bool,
    not_fitted: List[str],
) -> Dict[str, Any]:
    """#555 coverage receipt: typed omissions + conservation invariant.

    ``reviewed`` is what the council was actually shown. A file that passed
    selection but did not fit the budget is an omission (``too_large``), not a
    reviewed file: before #747 the receipt listed every selected file as
    reviewed, including ones the prompt never contained. A path the caller
    named keeps its ``explicit`` origin, so it clamps a pass like any other
    explicit omission.

    ``reviewed`` and ``omitted`` are disjoint by construction; the invariant is
    a defensive marker (ADR-051 C4), never a crash.
    """
    dropped = set(not_fitted)
    named = set(target_paths or [])
    reviewed = [p for p in dict.fromkeys(files) if p not in dropped]
    omitted = list(omissions) + [
        {
            "path": p,
            "reason": "too_large",
            "origin": "explicit" if p in named else "discovered",
        }
        for p in dict.fromkeys(not_fitted)
    ]
    conservation_ok = set(reviewed).isdisjoint(o["path"] for o in omitted)
    if not conservation_ok:
        logger.error("coverage conservation violated: a path is both reviewed and omitted")
    return {
        "requested": list(target_paths) if target_paths else None,
        "reviewed": reviewed,
        "omitted": omitted,
        "explicit_omitted": any(o["origin"] == "explicit" for o in omitted),
        "truncated": bool(paths_truncated),
        "conservation_ok": conservation_ok,
    }
