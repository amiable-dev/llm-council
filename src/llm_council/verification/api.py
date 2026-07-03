"""
Verification API endpoint per ADR-034.

Provides POST /v1/council/verify for structured work verification
using LLM Council multi-model deliberation.

Exit codes:
- 0: PASS - Approved with confidence >= threshold
- 1: FAIL - Rejected
- 2: UNCLEAR - Confidence below threshold, requires human review
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Literal, Optional, Set, Tuple

logger = logging.getLogger(__name__)

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from llm_council.council import (
    calculate_aggregate_rankings,
    stage1_collect_responses,
    stage1_collect_responses_with_status,
    stage2_collect_rankings,
    stage3_synthesize_final,
)
from llm_council.tier_contract import create_tier_contract, get_tier_timeout
from llm_council.verdict import VerdictType as CouncilVerdictType
from llm_council.verification.context import (
    InvalidSnapshotError,
    VerificationContextManager,
    validate_snapshot_id,
)
from llm_council.verification.transcript import (
    TranscriptStore,
    create_transcript_store,
)
from llm_council.verification.calibration import (
    calibrated_confidence_enabled,
    load_mapping,
)
from llm_council.verification.verdict_extractor import (
    build_verification_result,
    extract_rubric_scores_from_rankings,
    derive_unclear_reason,
    extract_verdict_from_synthesis,
    calculate_confidence_from_agreement,
)
from llm_council.performance.integration import persist_session_performance_data
from llm_council.verdict import parse_evidence_dispositions

# Router for verification endpoints
router = APIRouter(tags=["verification"])


# (#380: GIT_SHA_PATTERN / SOURCE_PATTERN / EVIDENCE_ID_PATTERN moved to
# .schemas alongside the validators that use them; re-exported below.)



# ============================================================================
# #380: split into submodules (schemas / constants / evidence_render /
# file_ops). Re-exported here verbatim for backward compatibility — many
# callers and tests import these names from verification.api.
# ============================================================================
from .constants import (  # noqa: F401
    ASYNC_SUBPROCESS_TIMEOUT,
    GARBAGE_FILENAMES,
    MAX_EVIDENCE_CHARS_RATIO,
    MAX_FILE_CHARS,
    MAX_FILES_EXPANSION,
    MAX_TOTAL_CHARS,
    TEXT_EXTENSIONS,
    TIER_MAX_CHARS,
    VERIFICATION_TIMEOUT_MULTIPLIER,
)
from .schemas import (  # noqa: F401
    EVIDENCE_ID_PATTERN,
    GIT_SHA_PATTERN,
    SOURCE_PATTERN,
    BlockingEvidenceTooLarge,
    BlockingIssueResponse,
    EvidenceDisposition,
    EvidenceItem,
    EvidenceWarning,
    RubricScoresResponse,
    SnapshotResolutionError,
    VerifyRequest,
    VerifyResponse,
    _verdict_to_exit_code,
)
from .evidence_render import (  # noqa: F401
    _budget_evidence,
    _build_dispositions_instruction,
    _build_evidence_instructions,
    _build_evidence_section,
    _evidence_input_metrics,
    _render_evidence_item,
    _usage_input_metrics,
)
from .file_ops import (  # noqa: F401
    MAX_CONCURRENT_GIT_OPS,
    _expand_target_paths,
    _fetch_file_at_commit_async,
    _fetch_files_for_verification_async,
    _fetch_files_for_verification_async_with_metadata,
    _get_git_object_type,
    _get_git_root_async,
    _get_git_semaphore,
    _git_ls_tree_z_name_only,
    _is_garbage_file,
    _is_text_file,
    _validate_file_path,
)

def _persist_result_safe(store: Any, verification_id: str, result: Dict[str, Any]) -> None:
    """Best-effort persist of a final ``result.json`` for early-return paths.

    The happy path writes the result via ``store.write_stage(..., "result", ...)``;
    the input-cap and timeout early returns previously skipped it, so those
    outcomes vanished from ``.council/logs`` and could not be audited (#356).
    Persistence must never turn a degraded result into a hard failure, so any
    store error is swallowed.
    """
    try:
        store.write_stage(verification_id, "result", result)
    except Exception:
        logger.debug("Failed to persist partial/timeout result.json", exc_info=True)


# Maximum characters per file to include in prompt.

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
    kept_evidence, evidence_warnings = _budget_evidence(evidence, tier)
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
        raise SnapshotResolutionError(
            snapshot_id=snapshot_id,
            unresolved_paths=list(target_paths),
            expansion_warnings=list(expansion_metadata.get("expansion_warnings", [])),
        )

    evidence_instructions = _build_evidence_instructions(bool(kept_evidence))

    prompt = f"""You are reviewing code at commit `{snapshot_id}`.{focus_section}{evidence_section}

## Code to Review

{file_contents}

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

Be specific and cite file paths and line numbers when identifying issues."""

    render_info = {
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


ProgressCallback = Callable[[int, int, str], Awaitable[None]]


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


async def _run_verification_pipeline(
    request: VerifyRequest,
    store: TranscriptStore,
    on_progress: Optional[ProgressCallback],
    verification_id: str,
    transcript_dir: str,
    verification_query: str,
    tier_contract: Any,
    tier_timeout: Dict[str, int],
    ctx: Any,
    partial_state: Dict[str, Any],
    deadline_at: float,
) -> Dict[str, Any]:
    """Inner pipeline that runs the 3-stage council deliberation.

    Extracted from run_verification to allow wrapping with asyncio.wait_for()
    for global timeout enforcement (ADR-040).

    Uses waterfall time budgeting: each stage receives a proportional share of
    the remaining time budget rather than a static per-model timeout.

    Args:
        request: Verification request
        store: Transcript store
        on_progress: Progress callback
        verification_id: Unique verification ID
        transcript_dir: Path to transcript directory
        verification_query: Built verification prompt
        tier_contract: TierContract for this tier
        tier_timeout: Timeout config dict
        ctx: Verification context
        partial_state: Shared mutable dict for partial results (survives cancellation)
        deadline_at: Monotonic clock deadline for waterfall budgeting

    Returns:
        Verification result dictionary
    """
    num_models = len(tier_contract.allowed_models)

    # ADR-041: Initialize timing capture
    pipeline_start = time.monotonic()
    partial_state["stage_timings"] = {}

    # Progress: num_models (stage1) + num_models (stage2) + 2 (stage3 + finalize)
    total_steps = num_models + num_models + 2
    current_step = 0

    async def report_progress(message: str):
        nonlocal current_step
        current_step += 1
        if on_progress:
            try:
                await on_progress(current_step, total_steps, message)
            except Exception:
                pass  # Progress reporting is best-effort

    # Bridge stage1 per-model progress to our callback
    async def stage1_progress(completed: int, total: int, message: str):
        nonlocal current_step
        current_step = max(current_step, completed)  # Monotonic (models finish out-of-order)
        if on_progress:
            try:
                await on_progress(completed, total_steps, f"Stage 1: {message}")
            except Exception:
                pass

    # ADR-040: Waterfall time budgeting - Stage 1 gets 50% of remaining time
    remaining = max(deadline_at - time.monotonic(), 1.0)
    stage1_budget = remaining * 0.50
    stage1_per_model = min(stage1_budget, tier_timeout["per_model"])

    # Stage 1: Collect individual model responses with tier-appropriate models
    stage1_start = time.monotonic()
    try:
        stage1_results, stage1_usage, model_statuses = await stage1_collect_responses_with_status(
            verification_query,
            timeout=stage1_per_model,
            models=tier_contract.allowed_models,
            on_progress=stage1_progress,
        )
    finally:
        partial_state["stage_timings"]["stage1_elapsed_ms"] = int(
            (time.monotonic() - stage1_start) * 1000
        )
    current_step = num_models

    # ADR-040: Persist stage1 results to partial_state (survives cancellation)
    partial_state["completed_stages"].append("stage1")
    partial_state["stage1_results"] = stage1_results
    # ADR-041: Preserve model_statuses for performance tracker
    partial_state["model_statuses"] = model_statuses

    # Persist Stage 1
    store.write_stage(
        verification_id,
        "stage1",
        {
            "responses": stage1_results,
            "usage": stage1_usage,
            "timestamp": datetime.utcnow().isoformat(),
        },
    )

    # Stage 2: Peer ranking with rubric evaluation
    # ADR-040: Pass tier timeout and models to stage2
    if on_progress:
        try:
            await on_progress(num_models, total_steps, "Stage 2: Peer review starting...")
        except Exception:
            pass

    # Bridge stage2 per-model progress
    async def stage2_progress(completed: int, total: int, message: str):
        nonlocal current_step
        step = num_models + completed  # Offset by stage1 steps
        current_step = max(current_step, step)
        if on_progress:
            try:
                await on_progress(step, total_steps, f"Stage 2: {message}")
            except Exception:
                pass

    # ADR-040: Waterfall - Stage 2 gets 70% of remaining time after Stage 1
    remaining = max(deadline_at - time.monotonic(), 1.0)
    stage2_budget = remaining * 0.70
    stage2_per_model = min(stage2_budget, tier_timeout["per_model"])

    stage2_start = time.monotonic()
    try:
        stage2_results, label_to_model, stage2_usage = await stage2_collect_rankings(
            verification_query,
            stage1_results,
            timeout=stage2_per_model,
            models=tier_contract.allowed_models,
            on_progress=stage2_progress,
        )
    finally:
        partial_state["stage_timings"]["stage2_elapsed_ms"] = int(
            (time.monotonic() - stage2_start) * 1000
        )
    current_step = num_models + num_models

    # ADR-040: Persist stage2 results to partial_state
    partial_state["completed_stages"].append("stage2")
    partial_state["stage2_results"] = stage2_results
    partial_state["label_to_model"] = label_to_model

    # Persist Stage 2
    store.write_stage(
        verification_id,
        "stage2",
        {
            "rankings": stage2_results,
            "label_to_model": label_to_model,
            "usage": stage2_usage,
            "timestamp": datetime.utcnow().isoformat(),
        },
    )

    # Calculate aggregate rankings
    aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)
    # ADR-041: Preserve aggregate_rankings for performance tracker
    partial_state["aggregate_rankings"] = aggregate_rankings

    # Stage 3: Chairman synthesis with verdict
    # ADR-040: Waterfall - Stage 3 gets all remaining time
    remaining = max(deadline_at - time.monotonic(), 1.0)
    stage3_budget = min(remaining, tier_timeout["per_model"])

    # ADR-042: build dispositions instruction from kept evidence (None if no evidence).
    evidence_render_info = partial_state.get("evidence_render_info") or {}
    kept_evidence = evidence_render_info.get("kept", [])
    dispositions_instruction = _build_dispositions_instruction(kept_evidence)

    await report_progress("Stage 3: Synthesizing verdict...")
    stage3_start = time.monotonic()
    try:
        stage3_result, stage3_usage, verdict_result = await stage3_synthesize_final(
            verification_query,
            stage1_results,
            stage2_results,
            aggregate_rankings=aggregate_rankings,
            verdict_type=CouncilVerdictType.BINARY,
            timeout=stage3_budget,
            dispositions_instruction=dispositions_instruction,
        )
    finally:
        partial_state["stage_timings"]["stage3_elapsed_ms"] = int(
            (time.monotonic() - stage3_start) * 1000
        )

    # ADR-040: Persist stage3 results to partial_state
    partial_state["completed_stages"].append("stage3")

    # Persist Stage 3
    store.write_stage(
        verification_id,
        "stage3",
        {
            "synthesis": stage3_result,
            "aggregate_rankings": aggregate_rankings,
            "usage": stage3_usage,
            "timestamp": datetime.utcnow().isoformat(),
        },
    )

    # ADR-011 Phase 3: expose a per-model usage/cost summary so the performance
    # tracker can record cost-per-quality (soft — never break verification).
    try:
        from llm_council.council import _build_usage_summary

        partial_state["usage"] = _build_usage_summary(
            {"stage1": stage1_usage, "stage2": stage2_usage, "stage3": stage3_usage}
        )
    except Exception:  # pragma: no cover - telemetry best effort
        pass

    # ADR-042: parse evidence_dispositions + emit evidence.json artefact.
    evidence_summary_payload: Optional[List[Dict[str, Any]]] = None
    evidence_warnings_payload: List[Dict[str, Any]] = []
    if evidence_render_info:
        for w in evidence_render_info.get("warnings", []):
            evidence_warnings_payload.append(w.model_dump())

    if kept_evidence:
        chairman_text = ""
        if isinstance(stage3_result, dict):
            chairman_text = stage3_result.get("synthesis") or stage3_result.get("response") or ""
        dispositions, parser_warnings = parse_evidence_dispositions(
            chairman_response=chairman_text,
            submitted_items=kept_evidence,
        )

        # Append dropped (budget) items as not_reviewed_due_to_budget dispositions.
        kept_ids = {d.evidence_id for d in dispositions}
        for w in evidence_render_info.get("warnings", []):
            if w.reason != "budget_overflow_dropped":
                continue
            request_evidence = request.evidence or []
            if 0 <= w.request_index < len(request_evidence):
                src_item = request_evidence[w.request_index]
                ev_id = src_item.evidence_id or f"auto-{w.request_index}"
                if ev_id not in kept_ids:
                    dispositions.append(
                        EvidenceDisposition(
                            evidence_id=ev_id,
                            request_index=w.request_index,
                            source=src_item.source,
                            strength=src_item.strength,
                            status="not_reviewed_due_to_budget",
                            council_confirmed=None,
                            council_rationale=None,
                        )
                    )

        # Caller-stable order: sort by request_index.
        dispositions.sort(key=lambda d: d.request_index)
        evidence_summary_payload = [d.model_dump() for d in dispositions]
        for w in parser_warnings:
            evidence_warnings_payload.append(w.model_dump())

    partial_state["evidence_summary"] = evidence_summary_payload
    partial_state["evidence_warnings"] = evidence_warnings_payload or None

    # ADR-042: Persist evidence.json when evidence was submitted (kept OR dropped).
    if evidence_render_info and (
        evidence_render_info.get("kept") or evidence_render_info.get("warnings")
    ):
        request_evidence = request.evidence or []
        items_payload: List[Dict[str, Any]] = []
        kept_indices = {req_idx for req_idx, _ in evidence_render_info["kept"]}
        rendered_positions = {
            req_idx: i + 1 for i, (req_idx, _) in enumerate(evidence_render_info["kept"])
        }
        for idx, item in enumerate(request_evidence):
            items_payload.append(
                {
                    "request_index": idx,
                    "evidence_id": item.evidence_id or f"auto-{idx}",
                    "source": item.source,
                    "strength": item.strength,
                    "format": item.format,
                    "content_chars_submitted": len(item.content),
                    "content_chars_rendered": (len(item.content) if idx in kept_indices else 0),
                    "kept": idx in kept_indices,
                    "rendered_position": rendered_positions.get(idx),
                    "drop_reason": (None if idx in kept_indices else "budget_overflow_dropped"),
                    "content": item.content,
                }
            )

        store.write_stage(
            verification_id,
            "evidence",
            {
                "evidence_present": True,
                "tier_max_chars": TIER_MAX_CHARS.get(request.tier, 50000),
                "max_evidence_chars": int(
                    TIER_MAX_CHARS.get(request.tier, 50000)
                    * MAX_EVIDENCE_CHARS_RATIO.get(request.tier, 0.20)
                ),
                "items": items_payload,
                "warnings": evidence_warnings_payload,
                "ordering_rule": "strength_then_source_then_id",
            },
        )

    await report_progress("Finalizing verification result...")

    # Extract verdict and scores from council output.
    # ADR-047 P2 (#414): load the persisted calibration mapping (identity when
    # none fitted). The threshold consumes it only behind the flag; the
    # calibrated value is REPORTED either way.
    calibration_mapping = load_mapping()
    verification_output = build_verification_result(
        stage1_results,
        stage2_results,
        stage3_result,
        confidence_threshold=request.confidence_threshold,
        # #355: prefer the chairman's structured BINARY verdict over a regex
        # over the synthesis prose. ``verdict_result`` is parsed in Stage 3.
        verdict_result=verdict_result,
        calibrate=(
            calibration_mapping.calibrate if calibrated_confidence_enabled() else None
        ),
    )

    verdict = verification_output["verdict"]
    confidence = verification_output["confidence"]
    confidence_calibrated = verification_output.get("confidence_calibrated")
    if confidence_calibrated is None:
        try:
            confidence_calibrated = calibration_mapping.calibrate(confidence)
        except Exception:
            confidence_calibrated = None  # calibration never fails a run
    exit_code = _verdict_to_exit_code(verdict)
    # ADR-047 P1 (#413): disambiguate UNCLEAR for automation.
    unclear_reason = derive_unclear_reason(verdict, stage3_result)

    # ADR-041: Build timing summary
    total_elapsed_ms = int((time.monotonic() - pipeline_start) * 1000)
    global_deadline_ms = int(
        (tier_contract.deadline_ms / 1000) * VERIFICATION_TIMEOUT_MULTIPLIER * 1000
    )
    timing = {
        **partial_state.get("stage_timings", {}),
        "total_elapsed_ms": total_elapsed_ms,
        "global_deadline_ms": global_deadline_ms,
        "budget_utilization": round(total_elapsed_ms / max(global_deadline_ms, 1), 3),
    }
    input_metrics = {
        "content_chars": len(verification_query),
        "tier_max_chars": TIER_MAX_CHARS.get(request.tier, 50000),
        "num_models": num_models,
        "num_reviewers": num_models,
        "tier": request.tier,
        # ADR-011 (#366): per-run token/cost totals (absent if usage unavailable).
        **_usage_input_metrics(partial_state.get("usage")),
        # ADR-042: evidence-specific input metrics.
        **_evidence_input_metrics(
            request.evidence,
            evidence_render_info,
            request.tier,
        ),
    }

    # Issue #340: surface expansion metadata so operators can see when
    # some paths failed to resolve even if the verdict still came back OK.
    expansion = evidence_render_info.get("expansion") or {}

    result = {
        "verification_id": verification_id,
        "verdict": verdict,
        "confidence": confidence,
        "confidence_calibrated": confidence_calibrated,
        "exit_code": exit_code,
        "unclear_reason": unclear_reason,
        "rubric_scores": verification_output["rubric_scores"],
        "blocking_issues": verification_output["blocking_issues"],
        "rationale": verification_output["rationale"],
        "transcript_location": str(transcript_dir),
        "partial": False,
        "timeout_fired": False,
        "completed_stages": ["stage1", "stage2", "stage3"],
        "timing": timing,
        "input_metrics": input_metrics,
        # ADR-042: per-source dispositions + structured warnings.
        "evidence_summary": partial_state.get("evidence_summary"),
        "evidence_warnings": partial_state.get("evidence_warnings"),
        # Issue #340: expansion metadata (was orphaned in the response schema).
        "expanded_paths": expansion.get("expanded_paths") or None,
        "paths_truncated": expansion.get("paths_truncated"),
        "expansion_warnings": expansion.get("expansion_warnings") or None,
    }

    # Persist result
    store.write_stage(verification_id, "result", result)

    return result


async def run_verification(
    request: VerifyRequest,
    store: TranscriptStore,
    on_progress: Optional[ProgressCallback] = None,
) -> Dict[str, Any]:
    """
    Run verification using LLM Council.

    This is the core verification logic that:
    1. Creates isolated context
    2. Runs council deliberation (with global timeout guardrail)
    3. Persists transcript
    4. Returns structured result (partial if timeout fires)

    ADR-040: Wraps pipeline in asyncio.wait_for() with global deadline
    derived from tier_contract.deadline_ms * VERIFICATION_TIMEOUT_MULTIPLIER.

    Args:
        request: Verification request
        store: Transcript store for persistence
        on_progress: Optional async callback(step, total, message) for progress

    Returns:
        Verification result dictionary
    """
    verification_id = str(uuid.uuid4())[:8]

    # Create isolated context for this verification
    with VerificationContextManager(
        snapshot_id=request.snapshot_id,
        rubric_focus=request.rubric_focus,
    ) as ctx:
        # Create transcript directory
        transcript_dir = store.create_verification_directory(verification_id)

        # Persist request
        store.write_stage(
            verification_id,
            "request",
            {
                "snapshot_id": request.snapshot_id,
                "target_paths": request.target_paths,
                "rubric_focus": request.rubric_focus,
                "confidence_threshold": request.confidence_threshold,
                "context_id": ctx.context_id,
                "timestamp": datetime.utcnow().isoformat(),
                # ADR-042: surface evidence presence for fast transcript scanning.
                "evidence_present": bool(request.evidence),
            },
        )

        # Build verification prompt for council (async to avoid blocking).
        # ADR-042: builder now returns (prompt, evidence_render_info).
        verification_query, evidence_render_info = await _build_verification_prompt(
            snapshot_id=request.snapshot_id,
            target_paths=request.target_paths,
            rubric_focus=request.rubric_focus,
            evidence=request.evidence,
            tier=request.tier,
        )

        # Get tier-appropriate models and timeouts (Issue #325)
        tier_contract = create_tier_contract(request.tier)
        tier_timeout = get_tier_timeout(request.tier)

        # ADR-040 Step 5: Tiered input size limit check
        max_chars = TIER_MAX_CHARS.get(request.tier, 50000)
        if len(verification_query) > max_chars:
            # #357: this is NOT a deliberated verdict — the council never ran.
            # Carry a distinct `error` marker so automation cannot mistake an
            # unreviewed oversized input for a passed/accepted gate.
            cap_result = {
                "verification_id": verification_id,
                "verdict": "unclear",
                "confidence": 0.0,
                "exit_code": 2,
                "error": "input_too_large",
                "rubric_scores": {},
                "blocking_issues": [],
                "rationale": (
                    f"Input size ({len(verification_query)} chars) exceeds "
                    f"{request.tier} tier limit ({max_chars} chars). "
                    f"The council did not run. Reduce scope, split the input, "
                    f"or use a higher tier."
                ),
                "transcript_location": str(transcript_dir),
                "partial": True,
                "timeout_fired": False,
                "completed_stages": [],
            }
            # #356: persist so input-cap rejections are auditable in the logs.
            _persist_result_safe(store, verification_id, cap_result)
            return cap_result

        # ADR-040 Step 6: Pre-flight info as first progress callback
        if on_progress:
            preflight_msg = _build_preflight_info(
                len(verification_query), tier_contract, request.tier
            )
            try:
                await on_progress(0, len(tier_contract.allowed_models) * 2 + 2, preflight_msg)
            except Exception:
                pass

        # ADR-040 Step 4: Global timeout wrapper with waterfall budgeting
        global_deadline = (tier_contract.deadline_ms / 1000) * VERIFICATION_TIMEOUT_MULTIPLIER
        deadline_at = time.monotonic() + global_deadline

        # Shared mutable state that survives asyncio.CancelledError on timeout
        partial_state: Dict[str, Any] = {
            "completed_stages": [],
            "stage1_results": None,
            "stage2_results": None,
            "label_to_model": None,
            # ADR-042: carried through pipeline for transcript + dispositions.
            "evidence_render_info": evidence_render_info,
            "evidence_summary": None,
            "evidence_warnings": None,
        }

        try:
            result = await asyncio.wait_for(
                _run_verification_pipeline(
                    request=request,
                    store=store,
                    on_progress=on_progress,
                    verification_id=verification_id,
                    transcript_dir=str(transcript_dir),
                    verification_query=verification_query,
                    tier_contract=tier_contract,
                    tier_timeout=tier_timeout,
                    ctx=ctx,
                    partial_state=partial_state,
                    deadline_at=deadline_at,
                ),
                timeout=global_deadline,
            )

            # ADR-041: Wire performance tracker (telemetry must never fail verification)
            try:
                model_statuses = partial_state.get("model_statuses", {})
                agg_list = partial_state.get("aggregate_rankings", [])
                agg_dict = {r["model"]: r for r in agg_list} if agg_list else {}
                if model_statuses and agg_dict:
                    persist_session_performance_data(
                        session_id=verification_id,
                        model_statuses=model_statuses,
                        aggregate_rankings=agg_dict,
                        stage2_results=partial_state.get("stage2_results"),
                        # ADR-011 Phase 3: per-model cost for cost-per-quality
                        # (None until present; fully populated with #366).
                        usage_by_model=(partial_state.get("usage") or {}).get("by_model"),
                    )
            except Exception:
                logger.debug("ADR-041: Performance telemetry persistence failed", exc_info=True)

            return result

        except asyncio.TimeoutError:
            # Global deadline exceeded - return partial result with completed stages
            completed = partial_state["completed_stages"]
            stage_timings = partial_state.get("stage_timings", {})
            global_deadline_ms = int(global_deadline * 1000)

            # #356 graceful degradation: if stage 2 (peer review) finished before
            # the chairman was starved, salvage an *advisory* signal — the rubric
            # scores and reviewer-agreement confidence — instead of a bare
            # unclear/0.0. The verdict stays "unclear" (no chairman go/no-go was
            # reached), but the caller gets something actionable rather than a
            # blank gate. Best-effort: any failure falls back to the empty result.
            salvaged_rubric: Dict[str, Any] = {}
            salvaged_confidence = 0.0
            advisory_note = ""
            try:
                stage2_results = partial_state.get("stage2_results")
                if stage2_results:
                    salvaged_rubric = extract_rubric_scores_from_rankings(stage2_results)
                    salvaged_confidence = calculate_confidence_from_agreement(
                        stage2_results, "unclear"
                    )
                    advisory_note = (
                        " Advisory only: rubric scores and confidence were recovered "
                        "from completed peer review (stage 2); the chairman synthesis "
                        "(stage 3) did not finish, so no pass/fail verdict was rendered."
                    )
            except Exception:
                logger.debug("Failed to salvage advisory signal on timeout", exc_info=True)

            timeout_result = {
                "verification_id": verification_id,
                "verdict": "unclear",
                "confidence": salvaged_confidence,
                "exit_code": 2,
                "unclear_reason": "timeout",  # ADR-047 P1 (#413)
                "rubric_scores": salvaged_rubric,
                "blocking_issues": [],
                "rationale": (
                    f"Verification timed out after {global_deadline:.0f}s "
                    f"(tier={request.tier}, deadline={tier_contract.deadline_ms}ms "
                    f"x {VERIFICATION_TIMEOUT_MULTIPLIER} multiplier). "
                    f"Completed stages: {completed}.{advisory_note} "
                    f"Consider using a faster tier or reducing input scope."
                ),
                "transcript_location": str(transcript_dir),
                "partial": True,
                "timeout_fired": True,
                "completed_stages": completed,
                "timing": {
                    **stage_timings,
                    "total_elapsed_ms": global_deadline_ms,
                    "global_deadline_ms": global_deadline_ms,
                    "budget_utilization": 1.0,
                },
                "input_metrics": {
                    "content_chars": len(verification_query),
                    "tier_max_chars": TIER_MAX_CHARS.get(request.tier, 50000),
                    "num_models": len(tier_contract.allowed_models),
                    "num_reviewers": len(tier_contract.allowed_models),
                    "tier": request.tier,
                    # ADR-042: evidence-specific input metrics on timeout path too.
                    **_evidence_input_metrics(
                        request.evidence,
                        partial_state.get("evidence_render_info"),
                        request.tier,
                    ),
                },
                # ADR-042: evidence_summary is None on timeout (we never
                # parsed dispositions); evidence_warnings may be populated
                # if the budgeter ran before timing out.
                "evidence_summary": None,
                "evidence_warnings": partial_state.get("evidence_warnings"),
                # Issue #340: expansion metadata is computed in the prompt
                # builder before the wait_for wrapper, so it's available
                # even on timeout.
                "expanded_paths": (
                    (partial_state.get("evidence_render_info") or {})
                    .get("expansion", {})
                    .get("expanded_paths")
                    or None
                ),
                "paths_truncated": (
                    (partial_state.get("evidence_render_info") or {})
                    .get("expansion", {})
                    .get("paths_truncated")
                ),
                "expansion_warnings": (
                    (partial_state.get("evidence_render_info") or {})
                    .get("expansion", {})
                    .get("expansion_warnings")
                    or None
                ),
            }
            # #356: persist the partial/timeout result so timeouts (the dominant
            # real-world failure mode) are not lost from the transcript logs.
            _persist_result_safe(store, verification_id, timeout_result)
            return timeout_result


@router.post("/verify", response_model=VerifyResponse)
async def verify_endpoint(request: VerifyRequest) -> VerifyResponse:
    """
    Verify code, documents, or implementation using LLM Council.

    This endpoint provides structured work verification with:
    - Multi-model consensus via LLM Council deliberation
    - Context isolation per verification (no session bleed)
    - Transcript persistence for audit trail
    - Exit codes for CI/CD integration

    Exit Codes:
    - 0: PASS - Approved with confidence >= threshold
    - 1: FAIL - Rejected with blocking issues
    - 2: UNCLEAR - Confidence below threshold, requires human review

    Args:
        request: VerificationRequest with snapshot_id and optional parameters

    Returns:
        VerificationResult with verdict, confidence, and transcript location
    """
    try:
        # Validate snapshot ID
        validate_snapshot_id(request.snapshot_id)
    except InvalidSnapshotError as e:
        raise HTTPException(status_code=422, detail=str(e))

    try:
        # Create transcript store
        store = create_transcript_store()

        # Run verification
        result = await run_verification(request, store)

        return VerifyResponse(**result)

    except BlockingEvidenceTooLarge as e:
        # ADR-042: oversized blocking evidence is the exact failure mode
        # this design prevents. Fail closed with a structured 422 body.
        raise HTTPException(
            status_code=422,
            detail={
                "error": "blocking_evidence_too_large",
                "message": str(e),
                "evidence_index": e.index,
                "source": e.source,
                "chars": e.chars,
                "budget": e.budget,
                "tier": request.tier,
            },
        )

    except SnapshotResolutionError as e:
        # Issue #340: target_paths could not be resolved at snapshot_id —
        # do not silently fall back to a boilerplate-only review. Caller
        # needs to know the council never saw their code.
        raise HTTPException(
            status_code=422,
            detail={
                "error": "snapshot_resolution_failed",
                "message": str(e),
                "snapshot_id": e.snapshot_id,
                "unresolved_paths": e.unresolved_paths,
                "expansion_warnings": e.expansion_warnings,
            },
        )

    except Exception as e:
        # Handle errors gracefully
        raise HTTPException(
            status_code=500,
            detail={"error": str(e), "type": type(e).__name__},
        )
