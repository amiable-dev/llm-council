"""3-stage LLM Council orchestration."""

import asyncio
import html
import random
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Dict, Any, Tuple, Optional, Callable, Awaitable

# Core imports that don't cause circular dependencies
from llm_council.gateway_adapter import (
    query_models_parallel,
    query_model,
    query_model_with_status,
    query_models_with_progress,
    STATUS_OK,
    STATUS_TIMEOUT,
    STATUS_RATE_LIMITED,
    STATUS_AUTH_ERROR,
    STATUS_ERROR,
)
from llm_council.unified_config import get_config

# Type-only imports for type hints (no circular import issues)
if TYPE_CHECKING:
    from llm_council.tier_contract import TierContract
    from llm_council.webhooks import WebhookConfig


# =============================================================================
# ADR-032: Lazy-loaded config helpers
# =============================================================================
# IMPORTANT: Always use these helper functions instead of caching config values.
# Calling get_config() at each use ensures config changes are picked up without
# requiring a restart in long-running applications.
#
# These helpers also check for patched module attributes to support test mocking.
# Tests can patch e.g. "llm_council.council.COUNCIL_MODELS" and the helper will
# use the patched value.

import sys as _sys


def _get_council_config():
    """Get council config section."""
    return get_config().council


def _check_patched_attr(attr_name: str):
    """Check if a module attribute was patched (for test support).

    When tests use `patch("llm_council.council.COUNCIL_MODELS", [...])`,
    the patch creates a real attribute on the module. We check for this
    to support test mocking while still using lazy loading in production.
    """
    module = _sys.modules.get(__name__)
    if module is not None:
        # Check if attribute exists directly on module (was patched)
        # but NOT in _DEPRECATED_CONFIG_ATTRS (which means it was set by test)
        if attr_name in module.__dict__:
            return module.__dict__[attr_name]
    return None


def _get_council_models() -> list:
    """Get council models from unified config."""
    patched = _check_patched_attr("COUNCIL_MODELS")
    if patched is not None:
        return patched
    return _get_council_config().models


def _get_chairman_model() -> str:
    patched = _check_patched_attr("CHAIRMAN_MODEL")
    if patched is not None:
        return patched
    return _get_council_config().chairman


def _get_synthesis_mode() -> str:
    patched = _check_patched_attr("SYNTHESIS_MODE")
    if patched is not None:
        return patched
    return _get_council_config().synthesis_mode


def _get_exclude_self_votes() -> bool:
    patched = _check_patched_attr("EXCLUDE_SELF_VOTES")
    if patched is not None:
        return patched
    return _get_council_config().exclude_self_votes


def _get_style_normalization():
    patched = _check_patched_attr("STYLE_NORMALIZATION")
    if patched is not None:
        return patched
    return _get_council_config().style_normalization


def _get_normalizer_model() -> str:
    patched = _check_patched_attr("NORMALIZER_MODEL")
    if patched is not None:
        return patched
    return _get_council_config().normalizer_model


def _get_max_reviewers():
    patched = _check_patched_attr("MAX_REVIEWERS")
    if patched is not None:
        return patched
    return _get_council_config().max_reviewers


def _get_cache_enabled() -> bool:
    patched = _check_patched_attr("CACHE_ENABLED")
    if patched is not None:
        return patched
    return get_config().cache.enabled


# =============================================================================
# Deferred imports to avoid circular dependencies
# =============================================================================
# These modules import from layer_contracts, which imports from triage,
# which may import back to council. Placing them here ensures all config
# helpers are defined first.

from llm_council.bias_audit import (
    run_bias_audit,
    extract_scores_from_stage2,
    derive_position_mapping,
    BiasAuditResult,
)
from llm_council.bias_persistence import persist_session_bias_data
import logging

from llm_council.early_consensus import (
    borda_update,
    early_consensus_enabled,
    estimate_reviewers_cost,
    unassailable_leader,
)
from llm_council.observability.usage_metrics import emit_usage_metrics

logger = logging.getLogger(__name__)
from llm_council.cache import get_cache_key, get_cached_response, save_to_cache
from llm_council.dissent import extract_dissent_from_stage2
from llm_council.layer_contracts import (
    LayerEvent,
    LayerEventType,
    emit_layer_event,
    cross_l1_to_l2,
    cross_l2_to_l3,
)
from llm_council.quality import (
    calculate_quality_metrics,
    should_include_quality_metrics,
)
from llm_council.rubric import (
    parse_rubric_evaluation,
    calculate_weighted_score,
    calculate_weighted_score_with_accuracy_ceiling,
)
from llm_council.safety_gate import (
    check_response_safety,
    apply_safety_gate_to_score,
    SafetyCheckResult,
)
from llm_council.telemetry import get_telemetry
from llm_council.tier_contract import TierContract
from llm_council.triage import run_triage
from llm_council.verdict import (
    VerdictType,
    VerdictResult,
    get_chairman_prompt,
    parse_binary_verdict,
    parse_tie_breaker_verdict,
    detect_deadlock,
    calculate_borda_spread,
)
from llm_council.voting import VotingAuthority, get_vote_weight
from llm_council.webhooks import (
    WebhookConfig,
    EventBridge,
    DispatchMode,
)


# =============================================================================
# Backwards compatibility: Dynamic attribute access for deprecated constants
# =============================================================================
# These were previously frozen at import time. Now they are looked up dynamically
# via __getattr__ to ensure fresh config values in long-running applications.
# Tests can still patch these by patching the helper functions.

_DEPRECATED_CONFIG_ATTRS = {
    "COUNCIL_MODELS": _get_council_models,
    "CHAIRMAN_MODEL": _get_chairman_model,
    "SYNTHESIS_MODE": _get_synthesis_mode,
    "EXCLUDE_SELF_VOTES": _get_exclude_self_votes,
    "STYLE_NORMALIZATION": _get_style_normalization,
    "NORMALIZER_MODEL": _get_normalizer_model,
    "MAX_REVIEWERS": _get_max_reviewers,
    "CACHE_ENABLED": _get_cache_enabled,
}


def __getattr__(name: str):
    """Provide lazy access to deprecated config constants.

    This allows:
    - from llm_council.council import COUNCIL_MODELS (for backwards compatibility)
    - Fresh config values on each access (not frozen at import time)
    - Tests to still mock llm_council.council.COUNCIL_MODELS
    """
    if name in _DEPRECATED_CONFIG_ATTRS:
        return _DEPRECATED_CONFIG_ATTRS[name]()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")



# =============================================================================
# ADR-046 P0 (#408): council.py split — re-exports for back-compat
# =============================================================================
# Stage functions, ranking/aggregation, and shared constants moved to
# council_stages / council_rankings / council_usage. Names are re-imported
# here so `from llm_council.council import X` and test patches on
# `llm_council.council.X` keep working; the orchestrators below look these up
# as module globals, so patching them here still intercepts the calls.

from llm_council.council_usage import (  # noqa: E402
    MODEL_STATUS_AUTH_ERROR,
    MODEL_STATUS_ERROR,
    MODEL_STATUS_OK,
    MODEL_STATUS_RATE_LIMITED,
    MODEL_STATUS_TIMEOUT,
    TIMEOUT_PER_MODEL_HARD,
    TIMEOUT_PER_MODEL_SOFT,
    TIMEOUT_RESPONSE_DEADLINE,
    TIMEOUT_SYNTHESIS_TRIGGER,
    ProgressCallback,
    _add_cost_to_usage,
    _build_usage_summary,
)
from llm_council.council_rankings import (  # noqa: E402
    _coerce_score,
    _get_model_from_label_value,
    calculate_aggregate_rankings,
    detect_score_rank_mismatch,
    emit_shadow_vote_events,
    parse_ranking_from_text,
    should_track_shadow_votes,
)
from llm_council.council_stages import (  # noqa: E402
    generate_conversation_title,
    generate_partial_warning,
    quick_synthesis,
    should_normalize_styles,
    stage1_5_normalize_styles,
    stage1_collect_responses,
    stage1_collect_responses_with_status,
    stage2_collect_rankings,
    stage3_synthesize_final,
)

async def run_council_with_fallback(
    user_query: str,
    bypass_cache: bool = False,
    on_progress: Optional[ProgressCallback] = None,
    synthesis_deadline: float = TIMEOUT_SYNTHESIS_TRIGGER,
    per_model_timeout: float = TIMEOUT_PER_MODEL_HARD,
    models: Optional[List[str]] = None,
    tier_contract: Optional[TierContract] = None,
    use_wildcard: bool = False,
    optimize_prompts: bool = False,
    *,
    webhook_config: Optional[WebhookConfig] = None,
    on_event: Optional[Callable] = None,
    request_id: Optional[str] = None,
    verdict_type: VerdictType = VerdictType.SYNTHESIS,
    include_dissent: bool = False,
    stream_synthesis: bool = False,
) -> Dict[str, Any]:
    """
    Run the council with timeout handling and fallback synthesis (ADR-012).

    This is the reliability-enhanced version of run_full_council that:
    - Returns structured results per ADR-012 schema
    - Handles timeouts gracefully with partial results
    - Provides fallback synthesis when full pipeline can't complete
    - Tracks per-model status throughout
    - Supports tier-sovereign timeouts (ADR-012 Section 5)
    - Supports tier-appropriate model selection (ADR-022)
    - Supports triage layer with wildcard and optimization (ADR-020)
    - Supports webhook notifications via EventBridge (ADR-025a)
    - Supports Jury Mode verdict types (ADR-025b)

    Args:
        user_query: The user's question
        bypass_cache: If True, skip cache lookup
        on_progress: Optional async callback for progress updates
        synthesis_deadline: Time limit before triggering fallback synthesis
        per_model_timeout: Time limit per individual model query (default: 25s, reasoning: 150s)
        models: Optional list of model identifiers to use (overrides tier_contract and _get_council_models())
        tier_contract: Optional TierContract for tier-appropriate execution (ADR-022)
        use_wildcard: If True, add domain specialist via triage (ADR-020)
        optimize_prompts: If True, apply per-model prompt optimization (ADR-020)
        webhook_config: Optional WebhookConfig for real-time event notifications (ADR-025a)
        on_event: Optional callback for local event capture (e.g., SSE streaming).
                  Called for each event as it happens, enabling real-time streaming.
        request_id: Optional request ID for trace continuity. If not provided,
                    EventBridge generates one. Pass this for SSE streaming to
                    correlate events with the original request.
        verdict_type: Type of verdict to render (ADR-025b Jury Mode):
            - SYNTHESIS: Default behavior, unstructured natural language synthesis
            - BINARY: Go/no-go decision (approved/rejected)
            - TIE_BREAKER: Chairman resolves deadlocked decisions
        include_dissent: If True, extract minority opinions from Stage 2 (ADR-025b)

    Returns:
        Dict with ADR-012 structured schema:
        {
            "synthesis": str,
            "model_responses": {model: {status, latency_ms, response?, error?}},
            "metadata": {
                "status": "complete" | "partial" | "failed",
                "completed_models": int,
                "requested_models": int,
                "synthesis_type": "full" | "partial" | "stage1_only",
                "warning": str | None,
                "tier": str | None (when tier_contract provided),
                "triage": dict | None (when triage used),
                "webhooks_enabled": bool (when webhook_config provided),
                "verdict": dict | None (when verdict_type is BINARY/TIE_BREAKER),
                ...
            }
        }
    """
    triage_metadata = None

    # ADR-025a: Initialize EventBridge for webhook notifications
    event_bridge = EventBridge(
        webhook_config=webhook_config,
        mode=DispatchMode.SYNC,  # Use sync mode for deterministic event ordering
        on_event=on_event,
        request_id=request_id,  # Pass caller's request_id for trace continuity
    )

    # ADR-024 (Observability): Record L1 -> L2 boundary
    if tier_contract:
        cross_l1_to_l2(tier_contract, user_query)

    # ADR-020: Apply triage if wildcard or optimization enabled
    if use_wildcard or optimize_prompts:
        triage_result = run_triage(
            user_query,
            tier_contract=tier_contract,
            include_wildcard=use_wildcard,
            optimize_prompts=optimize_prompts,
        )

        # ADR-024 (Observability): Record L2 -> L3 boundary
        cross_l2_to_l3(triage_result, tier_contract)

        council_models = triage_result.resolved_models
        triage_metadata = triage_result.metadata
    # Determine models to use: explicit > tier_contract > default
    elif models is not None:
        council_models = models
    elif tier_contract is not None:
        council_models = tier_contract.allowed_models
    else:
        council_models = _get_council_models()

    requested_models = len(council_models)

    # Initialize result structure per ADR-012 schema
    result: Dict[str, Any] = {
        "synthesis": "",
        "model_responses": {},
        "metadata": {
            "status": "complete",
            "completed_models": 0,
            "requested_models": requested_models,
            "synthesis_type": "full",
            "warning": None,
            "tier": tier_contract.tier if tier_contract else None,
            "triage": triage_metadata,
            "webhooks_enabled": webhook_config is not None,
            "include_dissent": include_dissent,  # ADR-025b: Dissent extraction enabled
        },
    }

    # ADR-025a: Start EventBridge for webhook notifications
    try:
        await event_bridge.start()

        # ADR-024: Emit L3 Start Event
        start_event = LayerEvent(
            event_type=LayerEventType.L3_COUNCIL_START,
            data={
                "model_count": requested_models,
                "models": council_models,
                "tier": tier_contract.tier if tier_contract else None,
                "triage_metadata": triage_metadata,
            },
        )
        emit_layer_event(
            LayerEventType.L3_COUNCIL_START,
            start_event.data,
            layer_from="L2",
            layer_to="L3",
        )
        # ADR-025a: Also emit to webhook bridge
        await event_bridge.emit(start_event)
    except Exception:
        pass  # Bridge start/emit failure shouldn't block council execution

    # Shared dict for incremental model responses - survives timeout cancellation
    # This fixes ADR-012 diagnostic loss: even if the pipeline is cancelled by
    # asyncio.wait_for timeout, we'll have per-model status from completed queries
    shared_raw_responses: Dict[str, Dict[str, Any]] = {}

    # Helper for progress reporting
    async def report_progress(step: int, total: int, message: str):
        if on_progress:
            try:
                await on_progress(step, total, message)
            except Exception:
                pass  # Progress reporting is best-effort

    total_steps = requested_models * 2 + 3  # stage1 + stage2 + synthesis + finalize
    await report_progress(0, total_steps, "Starting council...")

    # ADR-046 P1: rich per-model stream events. Wired ONLY when a stream
    # consumer exists (SSE on_event or webhooks) — otherwise the callbacks
    # stay None and every stage takes its exact pre-P1 code path.
    on_model_complete = None
    on_review_event = None
    on_synthesis_delta = None
    if on_event is not None or webhook_config is not None:

        if stream_synthesis:

            async def on_synthesis_delta(text: str) -> None:
                try:
                    await event_bridge.emit(
                        LayerEvent(
                            event_type=LayerEventType.L3_SYNTHESIS_DELTA,
                            data={"text": text},
                        )
                    )
                except Exception:
                    pass

        async def on_model_complete(model: str, model_result: Dict[str, Any]) -> None:
            try:
                await event_bridge.emit(
                    LayerEvent(
                        event_type=LayerEventType.L3_STAGE1_RESPONSE,
                        data={
                            "model": model,
                            "response": model_result.get("content"),
                            "status": model_result.get("status"),
                            "latency_ms": model_result.get("latency_ms"),
                            "usage": model_result.get("usage"),
                        },
                    )
                )
            except Exception:
                pass  # streaming is best-effort, never blocks deliberation

        async def on_review_event(kind: str, data: Dict[str, Any]) -> None:
            try:
                event_type = (
                    LayerEventType.L3_EARLY_CONSENSUS_TERMINATION
                    if kind == "early_termination"
                    else LayerEventType.L3_STAGE2_REVIEW
                )
                await event_bridge.emit(LayerEvent(event_type=event_type, data=data))
            except Exception:
                pass

    # Generate session_id early to share between bias persistence and telemetry
    session_id = str(uuid.uuid4())

    # Inner coroutine for the main council work (allows timeout wrapping)
    async def run_council_pipeline() -> Dict[str, Any]:
        nonlocal result

        # Stage 1 with status tracking
        async def stage1_progress(completed, total, msg):
            await report_progress(completed, total_steps, f"Stage 1: {msg}")

        stage1_results, stage1_usage, model_statuses = await stage1_collect_responses_with_status(
            user_query,
            timeout=per_model_timeout,  # ADR-012 Section 5: Tier-sovereign timeout
            on_progress=stage1_progress,
            on_model_complete=on_model_complete,  # ADR-046 P1
            shared_raw_responses=shared_raw_responses,  # Preserve state on timeout
            models=council_models,  # ADR-022: Use tier-appropriate models
        )

        result["model_responses"] = model_statuses
        result["metadata"]["completed_models"] = len(stage1_results)

        # Check if we have any responses
        if not stage1_results:
            result["metadata"]["status"] = "failed"
            result["metadata"]["synthesis_type"] = "none"
            result["synthesis"] = "Error: All models failed to respond. Please try again."
            result["metadata"]["warning"] = generate_partial_warning(
                model_statuses, requested_models
            )
            await report_progress(total_steps, total_steps, "Failed - no responses")
            return result

        await report_progress(
            requested_models, total_steps, "Stage 1 complete, starting peer review..."
        )

        # ADR-025a: Emit Stage 1 complete webhook event
        try:
            stage1_event = LayerEvent(
                event_type=LayerEventType.L3_STAGE_COMPLETE,
                data={"stage": 1, "responses": len(stage1_results)},
            )
            await event_bridge.emit(stage1_event)
        except Exception:
            pass  # Webhook failure shouldn't block council execution

        # Stage 1.5: Style normalization (if enabled)
        responses_for_review, stage1_5_usage = await stage1_5_normalize_styles(stage1_results)

        # Stage 2: Peer review
        await report_progress(requested_models + 1, total_steps, "Stage 2: Peer review...")
        stage2_results, label_to_model, stage2_usage = await stage2_collect_rankings(
            user_query, responses_for_review, on_review_event=on_review_event
        )

        # ADR-027: Track shadow votes for frontier tier
        track_shadows = should_track_shadow_votes(tier_contract)
        aggregate_rankings = calculate_aggregate_rankings(
            stage2_results, label_to_model, return_shadow_votes=track_shadows
        )

        # ADR-027: Emit shadow vote events for observability
        if track_shadows and aggregate_rankings:
            shadow_votes = aggregate_rankings[0].get("shadow_votes", [])
            consensus_winner = aggregate_rankings[0].get("model") if aggregate_rankings else None
            emit_shadow_vote_events(shadow_votes, consensus_winner)

        # ADR-018: Persist bias data for cross-session analysis
        # Only if enabled in config (checked inside function)
        # Use the session_id generated at start of outer scope (now nonlocal)
        # Run in thread to avoid blocking the event loop with file I/O
        await asyncio.to_thread(
            persist_session_bias_data,
            session_id=session_id,
            stage1_results=stage1_results,
            stage2_results=stage2_results,
            label_to_model=label_to_model,
            query=user_query,
        )

        await report_progress(
            requested_models * 2, total_steps, "Stage 2 complete, synthesizing..."
        )

        # ADR-025a: Emit Stage 2 complete webhook event
        try:
            stage2_event = LayerEvent(
                event_type=LayerEventType.L3_STAGE_COMPLETE,
                data={"stage": 2, "rankings": len(stage2_results)},
            )
            await event_bridge.emit(stage2_event)
        except Exception:
            pass  # Webhook failure shouldn't block council execution

        # ADR-025b: Detect deadlock and escalate to TIE_BREAKER if needed
        effective_verdict_type = verdict_type
        deadlock_detected = False
        if verdict_type == VerdictType.BINARY and aggregate_rankings:
            borda_scores = [
                r.get("borda_score", 0.0) for r in aggregate_rankings if "borda_score" in r
            ]
            if detect_deadlock(borda_scores, threshold=0.1):
                deadlock_detected = True
                effective_verdict_type = VerdictType.TIE_BREAKER
                import logging

                logging.getLogger(__name__).info(
                    "Deadlock detected. Escalating from BINARY to TIE_BREAKER."
                )

        # ADR-046 P1: announce synthesis start to stream consumers
        if on_event is not None or webhook_config is not None:
            try:
                await event_bridge.emit(
                    LayerEvent(
                        event_type=LayerEventType.L3_STAGE3_START,
                        data={"chairman": _get_chairman_model()},
                    )
                )
            except Exception:
                pass

        # Stage 3: Full synthesis (with verdict type support)
        stage3_result, stage3_usage, verdict_result = await stage3_synthesize_final(
            user_query,
            stage1_results,
            stage2_results,
            aggregate_rankings,
            verdict_type=effective_verdict_type,
            on_synthesis_delta=on_synthesis_delta,  # ADR-046 P2 (None unless opted in)
        )

        # If we escalated due to deadlock, update the verdict result
        if deadlock_detected and verdict_result is not None:
            verdict_result.deadlocked = True

        result["synthesis"] = stage3_result.get("response", "")
        result["metadata"]["status"] = "complete"
        result["metadata"]["synthesis_type"] = "full"
        result["metadata"]["aggregate_rankings"] = aggregate_rankings
        result["metadata"]["label_to_model"] = label_to_model
        result["metadata"]["verdict_type"] = verdict_type.value
        result["metadata"]["effective_verdict_type"] = effective_verdict_type.value
        result["metadata"]["deadlock_detected"] = deadlock_detected

        # ADR-011: aggregate usage into metadata so the MCP path reports cost +
        # tokens (previously absent on this fallback path — parity with
        # run_full_council).
        result["metadata"]["usage"] = _build_usage_summary(
            {
                "stage1": stage1_usage,
                "stage1_5": stage1_5_usage,
                "stage2": stage2_usage,
                "stage3": stage3_usage,
            }
        )
        # ADR-011 Phase 2: emit OTel GenAI token/cost metrics (soft-fail).
        emit_usage_metrics(result["metadata"]["usage"])

        # ADR-025b: Add verdict result for BINARY/TIE_BREAKER modes
        if verdict_result is not None:
            result["metadata"]["verdict"] = verdict_result.to_dict()

        # ADR-025b: Extract constructive dissent from Stage 2 if requested
        if include_dissent and stage2_results:
            dissent_text = extract_dissent_from_stage2(stage2_results)
            if dissent_text:
                if verdict_result is not None:
                    verdict_result.dissent = dissent_text
                    # Update the verdict dict with dissent
                    result["metadata"]["verdict"] = verdict_result.to_dict()
                else:
                    # Add dissent to metadata directly for SYNTHESIS mode
                    result["metadata"]["dissent"] = dissent_text

        # Add warning if some models failed
        warning = generate_partial_warning(model_statuses, requested_models)
        if warning:
            result["metadata"]["warning"] = warning
            result["metadata"]["status"] = "partial"

        # Emit telemetry event (fire-and-forget)
        telemetry = get_telemetry()
        if telemetry.is_enabled():
            telemetry_event = {
                "type": "council_completed",
                "session_id": session_id,  # Shared with bias persistence
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "council_size": len(council_models),
                "responses_received": len(stage1_results),
                "synthesis_mode": _get_synthesis_mode(),
                "rankings": [
                    {
                        "model": r["model"],
                        "borda_score": r.get("borda_score"),
                        "vote_count": r.get("vote_count", 0),
                    }
                    for r in aggregate_rankings
                ],
                "config": {
                    "exclude_self_votes": _get_exclude_self_votes(),
                    "style_normalization": _get_style_normalization(),
                    "max_reviewers": _get_max_reviewers(),
                },
            }
            # Fire-and-forget
            asyncio.create_task(telemetry.send_event(telemetry_event))

        # ADR-024: Emit L3 Complete Event
        complete_event_data = {
            "status": result["metadata"].get("status", "ok"),
            "synthesis_type": result["metadata"].get("synthesis_type"),
            "model_count": len(result.get("model_responses", {})),
            "tier": tier_contract.tier if tier_contract else None,
        }
        emit_layer_event(
            LayerEventType.L3_COUNCIL_COMPLETE,
            complete_event_data,
            layer_from="L3",
            layer_to="L2",
        )

        # ADR-025a: Emit council complete webhook event
        try:
            complete_event = LayerEvent(
                event_type=LayerEventType.L3_COUNCIL_COMPLETE,
                data=complete_event_data,
            )
            await event_bridge.emit(complete_event)
        except Exception:
            pass  # Webhook failure shouldn't block council completion

        await report_progress(total_steps, total_steps, "Complete")
        return result

    try:
        # Run with timeout (Python 3.10 compatible)
        return await asyncio.wait_for(run_council_pipeline(), timeout=synthesis_deadline)

    except asyncio.TimeoutError:
        # Global timeout - synthesize from what we have
        # IMPORTANT: Use shared_raw_responses which was populated incrementally
        # even as the pipeline was cancelled. This preserves diagnostic info.
        result["metadata"]["status"] = "partial"

        # Build model_responses from shared dict (preserved across cancellation)
        model_statuses: Dict[str, Dict[str, Any]] = {}
        successful_responses: Dict[str, str] = {}

        for model, response in shared_raw_responses.items():
            model_statuses[model] = {
                "status": response.get("status", MODEL_STATUS_ERROR),
                "latency_ms": response.get("latency_ms", 0),
            }
            if response.get("error"):
                model_statuses[model]["error"] = response["error"]
            if response.get("status") == STATUS_OK and response.get("content"):
                model_statuses[model]["response"] = response.get("content", "")
                successful_responses[model] = response.get("content", "")

        # Mark models that didn't respond as timeout
        for model in council_models:
            if model not in model_statuses:
                model_statuses[model] = {
                    "status": MODEL_STATUS_TIMEOUT,
                    "latency_ms": int(synthesis_deadline * 1000),
                    "error": f"Global timeout after {synthesis_deadline}s",
                }

        result["model_responses"] = model_statuses
        result["metadata"]["completed_models"] = len(successful_responses)

        if successful_responses:
            # We have some responses - do quick synthesis
            await report_progress(total_steps - 1, total_steps, "Timeout - quick synthesis...")

            synthesis, usage = await quick_synthesis(user_query, result["model_responses"])
            result["synthesis"] = synthesis
            result["metadata"]["synthesis_type"] = (
                "partial" if len(successful_responses) > 1 else "stage1_only"
            )
            result["metadata"]["warning"] = generate_partial_warning(
                result["model_responses"], requested_models
            )
        else:
            # No responses at all - but now we have diagnostic info!
            result["metadata"]["status"] = "failed"
            result["metadata"]["synthesis_type"] = "none"
            result["synthesis"] = "Error: Council timed out before any models responded."
            result["metadata"]["warning"] = generate_partial_warning(
                result["model_responses"], requested_models
            )

        # ADR-024: Emit L3 Complete Event (timeout/partial)
        emit_layer_event(
            LayerEventType.L3_COUNCIL_COMPLETE,
            {
                "status": result["metadata"].get("status", "partial"),
                "synthesis_type": result["metadata"].get("synthesis_type"),
                "model_count": len(result.get("model_responses", {})),
                "tier": tier_contract.tier if tier_contract else None,
                "timeout": True,
            },
            layer_from="L3",
            layer_to="L2",
        )

        await report_progress(total_steps, total_steps, "Complete (partial)")
        return result

    except Exception as e:
        # Unexpected error
        result["metadata"]["status"] = "failed"
        result["metadata"]["synthesis_type"] = "none"
        result["synthesis"] = f"Error: Unexpected failure - {str(e)}"

        # ADR-024: Emit L3 Complete Event (error)
        emit_layer_event(
            LayerEventType.L3_COUNCIL_COMPLETE,
            {
                "status": "failed",
                "synthesis_type": "none",
                "model_count": len(result.get("model_responses", {})),
                "tier": tier_contract.tier if tier_contract else None,
                "error": str(e),
            },
            layer_from="L3",
            layer_to="L2",
        )

        await report_progress(total_steps, total_steps, f"Failed: {e}")
        return result

    finally:
        # ADR-025a: Always shutdown EventBridge to ensure cleanup
        try:
            await event_bridge.shutdown()
        except Exception:
            pass  # Shutdown failure shouldn't raise


async def run_full_council(
    user_query: str,
    bypass_cache: bool = False,
    models: Optional[List[str]] = None,
    *,
    webhook_config: Optional[WebhookConfig] = None,
    verdict_type: VerdictType = VerdictType.SYNTHESIS,
    include_dissent: bool = False,
) -> Tuple[List, List, Dict, Dict]:
    """
    Run the complete 3-stage council process.

    Pipeline:
    1. Stage 1: Collect individual responses from all council models
    2. Stage 1.5 (optional): Normalize response styles if _get_style_normalization() is enabled
    3. Stage 2: Anonymous peer review with JSON-based rankings
    4. Stage 3: Chairman synthesis (consensus, debate, or verdict mode)

    Args:
        user_query: The user's question
        bypass_cache: If True, skip cache lookup and force fresh query
        models: Optional list of model identifiers to use (overrides _get_council_models())
        webhook_config: Optional WebhookConfig for real-time event notifications (ADR-025a)
        verdict_type: Type of verdict to render (ADR-025b Jury Mode):
            - SYNTHESIS: Default behavior, unstructured natural language synthesis
            - BINARY: Go/no-go decision (approved/rejected)
            - TIE_BREAKER: Chairman resolves deadlocked decisions
        include_dissent: If True, extract minority opinions from Stage 2 (ADR-025b)

    Returns:
        Tuple of (stage1_results, stage2_results, stage3_result, metadata)
        For BINARY/TIE_BREAKER modes, metadata includes 'verdict' with VerdictResult
    """
    # ADR-025a: Initialize EventBridge for webhook notifications
    event_bridge: Optional[EventBridge] = None
    if webhook_config:
        event_bridge = EventBridge(
            webhook_config=webhook_config,
            mode=DispatchMode.SYNC,
        )
        await event_bridge.start()

        # Emit council start event
        from llm_council.layer_contracts import LayerEventType, LayerEvent

        await event_bridge.emit(
            LayerEvent(
                event_type=LayerEventType.L3_COUNCIL_START,
                data={"query": user_query[:100], "models": models or _get_council_models()},
            )
        )

    # Check cache first (unless bypassed)
    cache_key = get_cache_key(user_query)
    if _get_cache_enabled() and not bypass_cache:
        cached = get_cached_response(cache_key)
        if cached:
            # Add cache hit indicator to metadata
            metadata = cached.get("metadata", {})
            metadata["cache_hit"] = True
            metadata["cache_key"] = cache_key
            return (
                cached.get("stage1_results", []),
                cached.get("stage2_results", []),
                cached.get("stage3_result", {}),
                metadata,
            )

    # Initialize usage tracking
    total_usage = {
        "stage1": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "stage1_5": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "stage2": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "stage3": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }

    # Stage 1: Collect individual responses
    stage1_results, stage1_usage = await stage1_collect_responses(user_query)
    total_usage["stage1"] = stage1_usage
    num_responses = len(stage1_results)

    # ADR-016: Safety Gate - check responses for harmful content
    # ADR-031: Get evaluation config from unified_config
    eval_config = get_config().evaluation
    safety_results = {}
    if eval_config.safety.enabled:
        for result in stage1_results:
            model = result.get("model", "unknown")
            response = result.get("response", "")
            safety_check = check_response_safety(response)
            safety_results[model] = {
                "passed": safety_check.passed,
                "reason": safety_check.reason,
                "flagged_patterns": safety_check.flagged_patterns,
            }
            # Add safety result to the stage1 result
            result["safety_check"] = safety_results[model]

    # If no models responded successfully, return error
    if num_responses == 0:
        return (
            [],
            [],
            {"model": "error", "response": "All models failed to respond. Please try again."},
            {"usage": total_usage},
        )

    # Handle small councils (N ≤ 2) - peer review is unstable or meaningless
    degraded_mode = None
    stage2_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    stage1_5_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    if num_responses == 1:
        # Single model: skip peer review entirely
        degraded_mode = "single_model"
        stage2_results = []
        # Enhanced format (v0.3.0+) with explicit display_index
        label_to_model = {"Response A": {"model": stage1_results[0]["model"], "display_index": 0}}
        aggregate_rankings = [
            {
                "model": stage1_results[0]["model"],
                "rank": 1,
                "average_score": None,
                "average_position": None,
                "vote_count": 0,
                "note": "Single model - no peer review",
            }
        ]
    elif num_responses == 2:
        # Two models: peer review gives only 1 vote each (unstable)
        # Proceed but mark as degraded
        degraded_mode = "two_models"
        responses_for_review, stage1_5_usage = await stage1_5_normalize_styles(stage1_results)
        stage2_results, label_to_model, stage2_usage = await stage2_collect_rankings(
            user_query, responses_for_review
        )
        aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)
        # Add warning to each ranking
        for r in aggregate_rankings:
            r["note"] = "Two-model council - rankings based on single vote"
    else:
        # Normal flow (N ≥ 3)
        responses_for_review, stage1_5_usage = await stage1_5_normalize_styles(stage1_results)
        stage2_results, label_to_model, stage2_usage = await stage2_collect_rankings(
            user_query, responses_for_review
        )
        aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)

    total_usage["stage1_5"] = stage1_5_usage
    total_usage["stage2"] = stage2_usage

    # ADR-025b: Detect deadlock and escalate to TIE_BREAKER if needed
    effective_verdict_type = verdict_type
    deadlock_detected = False
    if verdict_type == VerdictType.BINARY and aggregate_rankings:
        # Extract Borda scores for deadlock detection
        borda_scores = [r.get("borda_score", 0.0) for r in aggregate_rankings if "borda_score" in r]
        if detect_deadlock(borda_scores, threshold=0.1):
            deadlock_detected = True
            effective_verdict_type = VerdictType.TIE_BREAKER
            import logging

            logging.getLogger(__name__).info(
                f"Deadlock detected (top 2 within threshold). "
                f"Escalating from BINARY to TIE_BREAKER mode."
            )

    # ADR-015: Run bias audit if enabled
    bias_audit_result = None
    if eval_config.bias.audit_enabled and len(stage2_results) > 0:
        # Extract scores from Stage 2 results
        stage2_scores = extract_scores_from_stage2(stage2_results, label_to_model)
        # Derive position mapping from label_to_model (Response A → 0, Response B → 1, etc.)
        position_mapping = derive_position_mapping(label_to_model)
        # Run bias audit with position data for position bias detection
        bias_audit_result = run_bias_audit(
            stage1_results, stage2_scores, position_mapping=position_mapping
        )

    # Stage 3: Synthesize final answer (with mode and verdict type support)
    stage3_result, stage3_usage, verdict_result = await stage3_synthesize_final(
        user_query,
        stage1_results,  # Use original responses for synthesis context
        stage2_results,
        aggregate_rankings,
        verdict_type=effective_verdict_type,  # May be escalated to TIE_BREAKER
    )
    total_usage["stage3"] = stage3_usage

    # If we escalated due to deadlock, update the verdict result
    if deadlock_detected and verdict_result is not None:
        verdict_result.deadlocked = True

    # ADR-025b: Extract constructive dissent from Stage 2 if requested
    dissent_text = None
    if include_dissent and stage2_results:
        dissent_text = extract_dissent_from_stage2(stage2_results)
        if dissent_text and verdict_result is not None:
            verdict_result.dissent = dissent_text

    # ADR-011: assemble the usage summary (tokens + cost + per-model).
    usage_summary = _build_usage_summary(total_usage)
    # ADR-011 Phase 2: emit OTel GenAI token/cost metrics (soft-fail).
    emit_usage_metrics(usage_summary)

    # Collect abstention info and score/rank mismatches from Stage 2
    abstentions = []
    score_rank_mismatches = []
    for r in stage2_results:
        parsed = r.get("parsed_ranking", {})
        if parsed.get("abstained"):
            abstentions.append(
                {"model": r["model"], "reason": parsed.get("abstention_reason", "Unknown")}
            )
        if parsed.get("score_rank_mismatch"):
            score_rank_mismatches.append(
                {
                    "model": r["model"],
                    "note": "Ranking order used (scores ignored per council recommendation)",
                }
            )

    # Prepare metadata with configuration info
    metadata = {
        "label_to_model": label_to_model,
        "aggregate_rankings": aggregate_rankings,
        "config": {
            "synthesis_mode": _get_synthesis_mode(),
            "exclude_self_votes": _get_exclude_self_votes(),
            "style_normalization": _get_style_normalization(),
            "max_reviewers": _get_max_reviewers(),
            "council_size": len(_get_council_models()),
            "responses_received": num_responses,
            "chairman": _get_chairman_model(),
            "verdict_type": verdict_type.value,  # ADR-025b: Requested verdict type
            "effective_verdict_type": effective_verdict_type.value,  # ADR-025b: Actual type used
            "deadlock_detected": deadlock_detected,  # ADR-025b: True if escalated to TIE_BREAKER
            "include_dissent": include_dissent,  # ADR-025b: Dissent extraction enabled
        },
        "usage": usage_summary,
    }

    # ADR-025b: Add verdict result for BINARY/TIE_BREAKER modes
    if verdict_result is not None:
        metadata["verdict"] = verdict_result.to_dict()

    # ADR-025b: Add dissent to metadata if extracted (even without verdict)
    if dissent_text and verdict_result is None:
        metadata["dissent"] = dissent_text

    # Add abstention info if any reviewers abstained
    if abstentions:
        metadata["abstentions"] = abstentions

    # Add score/rank mismatch warnings if any detected
    if score_rank_mismatches:
        metadata["score_rank_mismatches"] = score_rank_mismatches

    # Add degraded mode info if applicable
    if degraded_mode:
        metadata["degraded_mode"] = degraded_mode

    # ADR-015: Add bias audit results if enabled and computed
    if bias_audit_result is not None:
        from dataclasses import asdict

        metadata["bias_audit"] = asdict(bias_audit_result)

    # ADR-016: Add safety gate results if enabled
    if eval_config.safety.enabled and safety_results:
        metadata["safety_gate"] = {
            "enabled": True,
            "results": safety_results,
            "failed_models": [
                model for model, result in safety_results.items() if not result["passed"]
            ],
            "score_cap": eval_config.safety.score_cap,
        }

    # ADR-036: Add quality metrics if enabled
    if should_include_quality_metrics() and len(stage1_results) > 0:
        # Convert stage1_results list to dict format expected by quality metrics
        stage1_dict = {r["model"]: {"content": r.get("response", "")} for r in stage1_results}

        # Convert aggregate_rankings to tuple format (model_id, avg_position)
        rankings_tuples = [
            (r["model"], r.get("average_position", r.get("borda_score", 0.0)))
            for r in aggregate_rankings
        ]

        quality_metrics = calculate_quality_metrics(
            stage1_responses=stage1_dict,
            stage2_rankings=stage2_results,
            stage3_synthesis=stage3_result,
            aggregate_rankings=rankings_tuples,
            label_to_model=label_to_model,
        )
        metadata["quality_metrics"] = quality_metrics.to_dict()

    # Emit telemetry event (non-blocking, fire-and-forget)
    telemetry = get_telemetry()
    if telemetry.is_enabled():
        telemetry_event = {
            "type": "council_completed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "council_size": len(_get_council_models()),
            "responses_received": num_responses,
            "synthesis_mode": _get_synthesis_mode(),
            "rankings": [
                {
                    "model": r["model"],
                    "borda_score": r.get("borda_score"),
                    "vote_count": r.get("vote_count", 0),
                }
                for r in aggregate_rankings
            ],
            "config": {
                "exclude_self_votes": _get_exclude_self_votes(),
                "style_normalization": _get_style_normalization(),
                "max_reviewers": _get_max_reviewers(),
            },
        }
        # Fire-and-forget - don't await to avoid blocking response
        import asyncio

        asyncio.create_task(telemetry.send_event(telemetry_event))

    # Save to cache if caching is enabled
    if _get_cache_enabled():
        metadata["cache_hit"] = False
        metadata["cache_key"] = cache_key
        save_to_cache(cache_key, stage1_results, stage2_results, stage3_result, metadata)

    return stage1_results, stage2_results, stage3_result, metadata
