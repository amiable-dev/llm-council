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
import hashlib
import logging
import time
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, HTTPException

from llm_council.tier_contract import create_tier_contract, get_tier_timeout
from llm_council.verification.context import (
    InvalidSnapshotError,
    VerificationContextManager,
    validate_snapshot_id,
)
from llm_council.verification.transcript import (
    TranscriptStore,
    create_transcript_store,
)
from llm_council.cache_context import (
    CacheContext,
    clear_cache_context,
    prompt_cache_ttl,
    set_cache_context,
)
from llm_council.verification.screening import (
    evaluate_screen,
    log_decision,
    screening_mode,
)
from llm_council.verification.verdict_extractor import (
    extract_rubric_scores_from_rankings,
    calculate_confidence_from_agreement,
)
from llm_council.performance.integration import persist_session_performance_data

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
    STAGE3_MAX_RESERVE_FRACTION,
    STAGE3_MIN_BUDGET_SECONDS,
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
    _neutralize_evidence_items,
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


# #720: split below the review cap. Re-exported for callers that import
# these from verification.api; patch them where they are CONSUMED.
from .prompt import _build_preflight_info, _build_verification_prompt  # noqa: F401,E402
from .escalation import retry_hint  # noqa: E402
from llm_council.chairman import reset_current_tier, set_current_tier  # noqa: E402
from .pipeline import (  # noqa: F401,E402
    ProgressCallback,
    _emit_posthog_generations,
    _run_verification_pipeline,
    _stage3_reserve,
    _stage_budget,
)




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
    # #549: validate the snapshot at THIS boundary. Defense in depth, NOT a live
    # hole: production callers build a VerifyRequest (Pydantic rejects a malformed
    # SHA), and the VerificationContextManager below re-validates before any git
    # argv call. This makes the guarantee explicit and independent of the context
    # manager keeping its position, and fails fast (before transcript setup) for a
    # caller that bypassed construction (VerifyRequest.model_construct, a future
    # caller). Shell injection is already precluded (argv arrays, no shell=True);
    # the residual class is ARGUMENT injection, which matters once P3.1 adds
    # pathspec-style `git ... -- <paths>` calls.
    validate_snapshot_id(request.snapshot_id)

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

        # #704: nothing to review is an error, not a verdict. When the caller
        # named no paths and discovery resolved none, the prompt's subject is
        # empty, and a council asked to judge nothing produces an arbitrary
        # verdict: the required CI gate passed three PRs and failed a fourth
        # over the same empty subject. Stop before any model is called. An
        # explicit `target_paths=[]` is the caller asking for zero files
        # (#584, evidence-only review), so it is not this case.
        #
        # Keyed on the receipt SAYING zero files, not on its absence: the real
        # fetch path always writes one, and "no receipt" is a different failure
        # (the #555 conservation marker's job), not evidence of an empty subject.
        _receipt = (evidence_render_info.get("expansion") or {}).get("coverage")
        if request.target_paths is None and _receipt is not None and not _receipt.get("reviewed"):
            omitted = _receipt.get("omitted") or []
            omitted_text = (
                ", ".join(f"{o['path']} ({o['reason']})" for o in omitted[:20])
                if omitted
                else "no changed files were found"
            )
            empty_result: Dict[str, Any] = {
                "verification_id": verification_id,
                "verdict": "unclear",
                "confidence": 0.0,
                "exit_code": 2,
                "error": "no_reviewable_content",
                "rubric_scores": {},
                "blocking_issues": [],
                "rationale": (
                    f"No reviewable content resolved from snapshot "
                    f"{request.snapshot_id}. The council did not run. "
                    f"Omitted: {omitted_text}. Pass target_paths, or check that "
                    f"the snapshot is a commit whose changes include text files."
                ),
                "transcript_location": str(transcript_dir),
                "partial": True,
                "timeout_fired": False,
                "completed_stages": [],
                "coverage": _receipt,
                "expansion_warnings": list(
                    (evidence_render_info.get("expansion") or {}).get("expansion_warnings") or []
                ),
            }
            _persist_result_safe(store, verification_id, empty_result)
            return empty_result

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

        # ADR-049 D2 (#460): publish the D1 segment map + session affinity key
        # to the request-scoped cache context. The session key is the STABLE
        # sequence id (hash of the target paths) — never the per-round SHA,
        # which would defeat the affinity it exists to provide. Cleared in
        # the finally below; consumers no-op when the context is absent.
        subject_key = hashlib.sha256(
            "\n".join(sorted(request.target_paths or ["<repo>"])).encode()
        ).hexdigest()[:12]
        set_cache_context(
            CacheContext(
                segments=evidence_render_info.get("segments") or [],
                session_id=f"verify:{subject_key}",
                ttl=prompt_cache_ttl("1h"),
                prompt_head=verification_query[:64],
            )
        )

        # #724/#725 review: the context is set above but the try/finally that
        # clears it starts below, so everything in between is guarded: an
        # exception here must not leak it into the next verify (ADR-049 D2).
        try:
            # ADR-047 P3 (#415): opt-in lightweight screening pre-gate.
            # off (default) = no screen call, byte-identical. shadow = screen +
            # log only. active = short-circuit on a unanimous screen pass.
            # Blocking-capable requests are NEVER screened (invariant in
            # screen_eligibility). Soft-fail: any screen error => full council.
            screening_info: Optional[Dict[str, Any]] = None
            mode = screening_mode()
            if mode != "off":
                decision = await evaluate_screen(
                    verification_id=verification_id,
                    verification_query=verification_query,
                    mode=mode,
                    content_chars=len(verification_query),
                    target_paths=request.target_paths,
                    rubric_focus=request.rubric_focus,
                    evidence=request.evidence,
                )
                if mode == "active" and decision.screen_pass and decision.scores:
                    decision.acted = True
                    log_decision(decision)
                    screen_confidence = round(min(decision.scores.values()) / 10.0, 2)
                    screen_result = {
                        "verification_id": verification_id,
                        "verdict": "pass",
                        "confidence": screen_confidence,
                        "exit_code": 0,
                        "rubric_scores": decision.scores,
                        "blocking_issues": [],
                        "rationale": (
                            "PASS via screening judge (ADR-047 P3): a single "
                            "quick-tier model scored every rubric dimension at or "
                            "above the screen minimum, the input was small, and "
                            "the request was not blocking-capable. AUDIT NOTE: the "
                            "full council did not deliberate; decision logged to "
                            ".council/screening/decisions.jsonl."
                        ),
                        "transcript_location": str(transcript_dir),
                        "partial": False,
                        "timeout_fired": False,
                        "completed_stages": [],
                        "screening": {
                            "mode": mode,
                            "eligible": True,
                            "scores": decision.scores,
                            "acted": True,
                        },
                    }
                    _persist_result_safe(store, verification_id, screen_result)
                    clear_cache_context()
                    return screen_result
                log_decision(decision)
                screening_info = {
                    "mode": mode,
                    "eligible": decision.eligible,
                    "reasons": decision.reasons,
                    "scores": decision.scores,
                    "screen_pass": decision.screen_pass,
                    "acted": False,
                }

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
        except BaseException:
            clear_cache_context()
            raise

        # #725: the tier picks the chairman. wait_for runs the pipeline as a
        # task, which copies this context; reset in the finally below.
        tier_token = set_current_tier(tier_contract)
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
                # ADR-056 / #695: the verify half of the external contract.
                # Inside the same soft-fail block as the local persist — the
                # two report the same run and neither may fail it.
                from llm_council.observability.external_spend import (
                    emit_external_spend,
                )

                emit_external_spend(
                    operation="verify",
                    usage_summary=partial_state.get("usage"),
                    model=None,
                )
            except Exception:
                logger.debug("ADR-041: Performance telemetry persistence failed", exc_info=True)

            # ADR-047 P3: shadow/ineligible screening audit rides on the result.
            if screening_info is not None:
                result["screening"] = screening_info

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

            hint = retry_hint(
                request.tier, unclear_reason="timeout", completed_stages=completed
            )
            timeout_result = {
                "verification_id": verification_id,
                "verdict": "unclear",
                "confidence": salvaged_confidence,
                "exit_code": 2,
                "unclear_reason": "timeout",  # ADR-047 P1 (#413)
                # #597: retry UP a tier; a lower one has less time, not more.
                "retry_hint": hint,
                "rubric_scores": salvaged_rubric,
                "blocking_issues": [],
                "rationale": (
                    f"Verification timed out after {global_deadline:.0f}s "
                    f"(tier={request.tier}, deadline={tier_contract.deadline_ms}ms "
                    f"x {VERIFICATION_TIMEOUT_MULTIPLIER} multiplier). "
                    f"Completed stages: {completed}.{advisory_note} "
                    f"{hint['message'] if hint else ''}"
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
                # #555: coverage receipt survives the timeout path too.
                "coverage": (
                    (partial_state.get("evidence_render_info") or {})
                    .get("expansion", {})
                    .get("coverage")
                ),
            }
            # #356: persist the partial/timeout result so timeouts (the dominant
            # real-world failure mode) are not lost from the transcript logs.
            _persist_result_safe(store, verification_id, timeout_result)
            return timeout_result
        finally:
            # ADR-049 D2: request-scoped cache context must not leak into a
            # subsequent verification handled by the same task.
            reset_current_tier(tier_token)  # first: cannot raise, so it always runs
            clear_cache_context()


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
                # #581: which repository the daemon actually searched.
                "repo_root": e.repo_root,
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
