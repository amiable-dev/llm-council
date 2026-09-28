"""Verification stage orchestration (split from api.py, #720).

Stages 1-3 with the ADR-040 waterfall budget. ``run_verification`` in api.py
wraps this in the global deadline. Patches on names consumed HERE (the stage
functions, aggregation, ``build_verification_result``) must target
``llm_council.verification.pipeline``: api.py no longer imports them, so a
stale patch on api fails loudly instead of silently calling a real model.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


from llm_council.council import (
    calculate_aggregate_rankings,
    stage1_collect_responses_with_status,
    stage2_collect_rankings,
    stage3_synthesize_final,
)
from llm_council.verdict import VerdictType as CouncilVerdictType
from llm_council.verification.transcript import (
    TranscriptStore,
)
from llm_council.cache_context import (
    get_cache_context,
)
from llm_council.verification.calibration import load_mapping
from llm_council.verification.verdict_extractor import (
    build_verification_result,
    derive_unclear_reason,
)
from llm_council.verdict import parse_evidence_dispositions

# Router for verification endpoints



# (#380: GIT_SHA_PATTERN / SOURCE_PATTERN / EVIDENCE_ID_PATTERN moved to
# .schemas alongside the validators that use them; re-exported below.)



# ============================================================================
# #380: split into submodules (schemas / constants / evidence_render /
# file_ops). Re-exported here verbatim for backward compatibility — many
# callers and tests import these names from verification.api.
# ============================================================================
from .constants import (
    MAX_EVIDENCE_CHARS_RATIO,
    TIER_MAX_CHARS,
    STAGE3_MAX_RESERVE_FRACTION,
    STAGE3_MIN_BUDGET_SECONDS,
    VERIFICATION_TIMEOUT_MULTIPLIER,
)
from .schemas import (
    EvidenceDisposition,
    SnapshotResolutionError,
    VerifyRequest,
    _verdict_to_exit_code,
)
from .evidence_render import (
    _build_dispositions_instruction,
    _evidence_input_metrics,
    _usage_input_metrics,
)
from .file_ops import (
    _get_git_root_async,
)


ProgressCallback = Callable[[int, int, str], Awaitable[None]]


def _emit_posthog_generations(
    usage: Optional[Dict[str, Any]],
    *,
    verification_id: str,
    tier: str,
    subject_sha: Optional[str] = None,
) -> None:
    """ADR-050 D2: opt-in PostHog ``$ai_generation`` emission (soft-fail).

    Gated on ``posthog_emission_enabled`` BEFORE importing the mapper, so a
    verify with no ``POSTHOG_API_KEY`` pays only one env check and is
    byte-identical. Telemetry never breaks a verify.
    """
    try:
        from llm_council.observability.posthog_emitter import posthog_emission_enabled

        if not posthog_emission_enabled():
            return
        from llm_council.observability.ai_generation import emit_generation_events

        emit_generation_events(
            usage,
            verification_id=verification_id,
            tier=tier,
            subject_sha=subject_sha,
        )
    except Exception:  # telemetry must never break a verify
        logger.debug("posthog $ai_generation emission failed (ignored)", exc_info=True)


# Maximum characters per file to include in prompt.


def _stage3_reserve(remaining: float) -> float:
    """Seconds held back for stage 3 (#545). Proportional, so `quick` isn't starved."""
    return min(STAGE3_MIN_BUDGET_SECONDS, max(remaining, 0.0) * STAGE3_MAX_RESERVE_FRACTION)


def _stage_budget(remaining: float, fraction: float) -> float:
    """Waterfall slice for a stage, reserving the stage-3 floor (#545, ADR-040).

    ``remaining`` is wall-clock seconds left before the global deadline. Stages 1
    and 2 divide up ``remaining - _stage3_reserve(remaining)`` so the chairman is
    never handed a budget it cannot use but is still billed for. Clamped positive:
    once the deadline is already blown, the pipeline's own ``asyncio.wait_for``
    is what stops the run.
    """
    usable = remaining - _stage3_reserve(remaining)
    if usable <= 0:
        return max(remaining, 1.0)
    return max(usable * fraction, 1.0)


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
    # Issue #545: the slice is taken from (remaining - stage-3 floor).
    remaining = max(deadline_at - time.monotonic(), 1.0)
    stage1_budget = _stage_budget(remaining, 0.50)
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
    # Issue #545: the slice is taken from (remaining - stage-3 floor).
    remaining = max(deadline_at - time.monotonic(), 1.0)
    stage2_budget = _stage_budget(remaining, 0.70)
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
        # ADR-054 D3a (#563): calibration never gates a verdict — the
        # calibrated value is REPORTED (filled below from the persisted
        # mapping) but no threshold consumes it.
        calibrate=None,
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
    unclear_reason = derive_unclear_reason(
        verdict, stage3_result, diagnostics=verification_output.get("diagnostics")
    )

    # #556 (ADR-053): coverage clamp. A `pass` may not stand over a changed-or-
    # explicit file the council did not review, unless acknowledged. Runs on the
    # #555 receipt; `pass` → `unclear(incomplete_coverage)` under the default
    # `clamp` policy, a hard raise under `fail`, no-op under `warn`. The default
    # ack reason-set (binary/generated/vendored/too_large/ignored/noise) means
    # only surprising omissions (non-text = #542, not_found, truncated,
    # denied_secret) clamp; explicit-origin omissions clamp regardless.
    from llm_council.verification.coverage import (
        coverage_ack_reasons,
        coverage_clamp_decision,
        coverage_policy,
    )

    _coverage = (evidence_render_info.get("expansion") or {}).get("coverage")
    _policy = coverage_policy()
    if _coverage is not None:
        _coverage["policy"] = _policy
    _clampers = coverage_clamp_decision(verdict, _coverage, _policy, coverage_ack_reasons())
    if _clampers:
        if _policy == "fail":
            raise SnapshotResolutionError(
                snapshot_id=request.snapshot_id,
                repo_root=await _get_git_root_async(),
                unresolved_paths=[c["path"] for c in _clampers],
                expansion_warnings=[
                    f"coverage: {c['path']} ({c['reason']}) not reviewed "
                    f"[LLM_COUNCIL_COVERAGE_POLICY=fail]"
                    for c in _clampers
                ],
            )
        verdict = "unclear"
        unclear_reason = "incomplete_coverage"
        exit_code = _verdict_to_exit_code(verdict)
        if _coverage is not None:
            _coverage["clamped"] = _clampers

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
        # ADR-049 D4: session affinity key for log-only hit-rate grouping —
        # stable across rounds on the same subject (published at pipeline
        # entry, still in scope here; None when caching is disabled).
        "cache_session_id": getattr(get_cache_context(), "session_id", None),
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
        # ADR-051 (#486): structured findings + telemetry diagnostics (empty
        # defaults when the flag is off ⇒ additive, non-breaking).
        "findings": verification_output.get("findings", []),
        "diagnostics": verification_output.get("diagnostics", {}),
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
        # #555: structural coverage receipt (additive; no verdict effect).
        "coverage": expansion.get("coverage"),
    }

    # Persist result
    store.write_stage(verification_id, "result", result)

    # ADR-050 D2 (#474): opt-in PostHog $ai_generation emission — one event per
    # council-member model, keyed to this verification_id. No-op + soft-fail
    # when POSTHOG_API_KEY is unset (byte-identical); never delays a verify.
    _emit_posthog_generations(
        partial_state.get("usage"),
        verification_id=verification_id,
        tier=request.tier,
        subject_sha=request.snapshot_id,
    )

    return result
