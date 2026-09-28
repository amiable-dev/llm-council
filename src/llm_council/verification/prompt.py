"""Verification prompt assembly (split from api.py, #720).

Stability-ordered segments for prompt caching (ADR-049 D1) and the
preflight size line. ``run_verification`` in api.py is the caller, so tests
keep patching ``llm_council.verification.api._build_verification_prompt``;
patches on names consumed HERE (e.g. the file fetch) target this module.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)



# Router for verification endpoints



# (#380: GIT_SHA_PATTERN / SOURCE_PATTERN / EVIDENCE_ID_PATTERN moved to
# .schemas alongside the validators that use them; re-exported below.)



# ============================================================================
# #380: split into submodules (schemas / constants / evidence_render /
# file_ops). Re-exported here verbatim for backward compatibility — many
# callers and tests import these names from verification.api.
# ============================================================================
from .constants import (
    TIER_MAX_CHARS,
)
from .schemas import (
    EvidenceItem,
    SnapshotResolutionError,
)
from .evidence_render import (
    _budget_evidence,
    _build_evidence_instructions,
    _build_evidence_section,
    _neutralize_evidence_items,
)
from .file_ops import (
    _fetch_files_for_verification_async_with_metadata,
    _get_git_root_async,
)


async def _build_verification_prompt(
    snapshot_id: str,
    target_paths: Optional[List[str]] = None,
    rubric_focus: Optional[str] = None,
    evidence: Optional[List[EvidenceItem]] = None,
    tier: str = "balanced",
) -> Tuple[str, Dict[str, Any]]:
    """Build verification prompt for council deliberation.

    Creates a structured prompt that asks the council to review
    code/documentation at the given snapshot, including actual file contents.

    ADR-042: When `evidence` is provided, renders a Pre-computed Evidence
    section between focus_section and the code block. Carves the evidence
    budget out of TIER_MAX_CHARS BEFORE file content is sized.

    Args:
        snapshot_id: Git commit SHA for the code version
        target_paths: Optional list of paths to focus on
        rubric_focus: Optional focus area (Security, Performance, etc.)
        evidence: ADR-042 optional pre-computed analysis items
        tier: Tier name (used to pick MAX_EVIDENCE_CHARS_RATIO)

    Returns:
        (prompt, evidence_render_info) where evidence_render_info is a dict:
          - kept: List[Tuple[int, EvidenceItem]]  — items that were rendered
          - warnings: List[EvidenceWarning]       — items that were dropped
          - chars_rendered: int                   — rendered section length
          - chars_submitted: int                  — sum of submitted content
    """
    # ADR-042: budget + render evidence first; carve from TIER_MAX_CHARS.
    # #625: neutralize <evidence_item> tag sequences inside bodies BEFORE
    # budgeting, so byte-math (incl. the fail-closed oversized-blocking
    # check) sees final bytes. Clean bodies pass through byte-identical.
    evidence, neutralize_warnings = _neutralize_evidence_items(evidence)
    kept_evidence, evidence_warnings = _budget_evidence(evidence, tier)
    evidence_warnings = neutralize_warnings + evidence_warnings
    evidence_section = _build_evidence_section(kept_evidence)
    chars_rendered = len(evidence_section)
    chars_submitted = sum(len(item.content) for item in (evidence or []))

    focus_section = ""
    if rubric_focus:
        focus_section = f"\n\n**Focus Area**: {rubric_focus}\nPay particular attention to {rubric_focus.lower()}-related concerns."

    # Fetch actual file contents (async to avoid blocking event loop).
    # Issue #340: use the metadata-aware variant so we can surface
    # expansion warnings on the response — and hard-fail when caller-
    # supplied target_paths resolved to zero files (otherwise the council
    # silently reviews a boilerplate-only prompt).
    file_contents, expansion_metadata = await _fetch_files_for_verification_async_with_metadata(
        snapshot_id, target_paths, tier=tier
    )

    if target_paths and not expansion_metadata.get("expanded_paths"):
        # #581: name the repository that was searched. The daemon resolves one
        # root process-wide from its spawn cwd, so "not found" is frequently
        # "found nothing HERE" — which the operator cannot tell without this.
        raise SnapshotResolutionError(
            snapshot_id=snapshot_id,
            unresolved_paths=list(target_paths),
            expansion_warnings=list(expansion_metadata.get("expansion_warnings", [])),
            repo_root=await _get_git_root_async(),
        )

    evidence_instructions = _build_evidence_instructions(bool(kept_evidence))

    # ADR-049 D1: stable-prefix-first assembly. Segments render in stability
    # order — static head (round- AND subject-invariant), evidence, subject,
    # volatile tail — so provider prompt caches can reuse the unchanged
    # prefix across verification rounds. The snapshot SHA is the canonical
    # cache-buster and lives ONLY in the tail; nothing above the tail may
    # contain timestamps, UUIDs, or per-round values.
    static_head = f"""You are reviewing code for quality verification.{focus_section}

## Instructions

Please provide a thorough review with the following structure:

1. **Summary**: Brief overview of what the code does
2. **Quality Assessment**: Evaluate code quality, readability, and maintainability
3. **Potential Issues**: Identify any bugs, security vulnerabilities, or performance concerns
4. **Recommendations**: Suggest improvements if any
{evidence_instructions}
At the end of your review, provide a clear verdict:
- **APPROVED** if the code is ready for production
- **REJECTED** if there are critical issues that must be fixed
- **NEEDS REVIEW** if you're uncertain and recommend human review

Be specific and cite file paths and line numbers when identifying issues.
"""
    subject = f"""
## Code to Review

{file_contents}
"""
    volatile_tail = f"""
## Review Target

Commit under review: `{snapshot_id}`"""

    prompt = static_head + evidence_section + subject + volatile_tail

    # Contiguous char-offset segment map (est_tokens = chars // 4), exposed
    # for ADR-049 D2 breakpoint placement and the byte-stability tests.
    segments = []
    cursor = 0
    for name, text in (
        ("static_head", static_head),
        ("evidence", evidence_section),
        ("subject", subject),
        ("volatile_tail", volatile_tail),
    ):
        end = cursor + len(text)
        segments.append(
            {"name": name, "start": cursor, "end": end,
             "est_tokens": (end - cursor) // 4}
        )
        cursor = end

    render_info = {
        "segments": segments,
        "kept": kept_evidence,
        "warnings": evidence_warnings,
        "chars_rendered": chars_rendered,
        "chars_submitted": chars_submitted,
        # Issue #340: surface expansion metadata so the pipeline can copy
        # expanded_paths / paths_truncated / expansion_warnings onto the
        # response. Was being silently discarded before.
        "expansion": expansion_metadata,
    }
    return prompt, render_info




def _build_preflight_info(content_chars: int, tier_contract: Any, tier: str) -> str:
    """Build pre-flight info message with complexity estimation.

    Args:
        content_chars: Number of characters in verification prompt
        tier_contract: TierContract for this verification
        tier: Tier name string

    Returns:
        Preflight info message string
    """
    max_chars = TIER_MAX_CHARS.get(tier, 50000)
    num_models = len(tier_contract.allowed_models)
    deadline_s = tier_contract.deadline_ms / 1000
    pct_used = (content_chars / max_chars) * 100 if max_chars > 0 else 0

    msg = (
        f"Preflight: tier={tier}, {content_chars} chars "
        f"({pct_used:.0f}% of {max_chars} limit), "
        f"{num_models} models, deadline={deadline_s:.0f}s"
    )

    if pct_used > 80:
        msg += " | WARNING: near tier input size limit, consider reducing scope"

    return msg
